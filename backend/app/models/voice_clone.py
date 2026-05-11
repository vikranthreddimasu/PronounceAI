"""
Voice cloning + accent transfer via CosyVoice 3 (mlx-audio-plus).

Two synthesis paths, raced from best-quality to most-reliable:

  1. INSTRUCT — CosyVoice 3 LLM end-to-end with a TINY accent style tag
     ("American accent." / "British accent.") and the user's enrollment as
     the speaker prompt. Best accent quality (CosyVoice's full acoustic
     prior). Risk: LLM occasionally speaks the prompt itself or appends a
     hallucination tail on longer inputs.

  2. VC FALLBACK — Kokoro TTS renders the target text in the target accent;
     CosyVoice 3 voice-conversion mode swaps the timbre to the user's
     voice. Words and accent guaranteed correct; accent slightly softer
     than instruct because VC re-rendering smooths some accent cues.

`speak()` runs path 1, then validates the output by Whisper-transcribing
it and comparing back to the input. If the transcription matches (good
coverage, no hallucination tail), ship the instruct output. Otherwise,
fall through to path 2.

End user gets instruct-quality accent on the happy path, VC reliability
on the edge cases — without ever hearing wrong words.
"""
from __future__ import annotations

import logging
import os
import re
import tempfile
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

import numpy as np
import resampy
import soundfile as sf

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.getenv(
    "COSYVOICE_MODEL",
    "mlx-community/Fun-CosyVoice3-0.5B-2512-fp16",
)

KOKORO_VOICE_MAP: dict[str, tuple[str, str]] = {
    "GA": ("a", "af_heart"),
    "RP": ("b", "bf_emma"),
}

# Keep tags short — long imperative prompts make the LLM speak them aloud.
SHORT_ACCENT_TAG: dict[str, str] = {
    "GA": "American accent.",
    "RP": "British accent.",
}

# Verbose forms kept ONLY for the legacy clone() shim; not used by speak().
ACCENT_INSTRUCTIONS: dict[str, str] = {
    "GA": "American English, neutral US Midwestern news anchor accent.",
    "RP": "British Received Pronunciation, BBC newsreader accent.",
}

KOKORO_SR = 24_000
COSYVOICE_SR = 24_000

# Validation thresholds for the instruct-mode race.
MIN_WORD_COVERAGE = 0.85   # >=85% of expected unique words must appear
MAX_LENGTH_RATIO = 1.45    # transcript >1.45x longer than input = hallucination
MIN_SEQUENCE_SIM = 0.62    # SequenceMatcher ratio over normalized text


class VoiceClone:
    def __init__(
        self,
        model_id: str = DEFAULT_MODEL,
        whisper_engine: Optional[object] = None,
    ):
        self.model_id = model_id
        self._whisper = whisper_engine
        self._warmed = False
        self._kokoro_pipes: dict[str, "object"] = {}

    def supported_accents(self) -> list[str]:
        return list(KOKORO_VOICE_MAP.keys())

    def instruction_for(self, accent: str) -> str:
        return ACCENT_INSTRUCTIONS.get(accent.upper(), ACCENT_INSTRUCTIONS["GA"])

    def set_whisper(self, engine: object) -> None:
        """Inject the whisper engine after VoiceClone has been constructed."""
        self._whisper = engine

    def warmup(self) -> None:
        if self._warmed:
            return
        try:
            from mlx_audio.tts.generate import generate_audio  # noqa: F401
            self._warmed = True
            logger.info(f"voice_clone: mlx_audio import OK (model={self.model_id})")
        except Exception as e:
            logger.warning(f"voice_clone: warmup failed: {e}")

    # ─── Kokoro accent rendering (used by the VC fallback) ─────────────

    def _kokoro_pipeline(self, lang_code: str):
        pipe = self._kokoro_pipes.get(lang_code)
        if pipe is None:
            from kokoro import KPipeline
            pipe = KPipeline(lang_code=lang_code)
            self._kokoro_pipes[lang_code] = pipe
        return pipe

    def _render_accent_audio(self, text: str, accent: str) -> Path:
        accent = accent.upper()
        if accent not in KOKORO_VOICE_MAP:
            raise ValueError(f"Unsupported accent: {accent}")
        lang_code, voice = KOKORO_VOICE_MAP[accent]
        pipe = self._kokoro_pipeline(lang_code)

        chunks: list[np.ndarray] = []
        for _, _, audio in pipe(text, voice=voice, speed=1.0):
            if hasattr(audio, "detach"):
                audio = audio.detach().cpu().numpy()
            chunks.append(np.asarray(audio, dtype=np.float32))
        if not chunks:
            raise RuntimeError(f"Kokoro produced no audio for accent={accent}")
        wav = np.concatenate(chunks).astype(np.float32)
        if KOKORO_SR != COSYVOICE_SR:
            wav = resampy.resample(wav, KOKORO_SR, COSYVOICE_SR).astype(np.float32)
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        sf.write(tmp.name, wav, COSYVOICE_SR, format="WAV", subtype="PCM_16")
        tmp.close()
        return Path(tmp.name)

    # ─── Output-path scaffolding ───────────────────────────────────────

    @staticmethod
    def _new_tempfile() -> tuple[Path, str]:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        out_path = Path(tmp.name)
        tmp.close()
        return out_path, str(out_path.with_suffix(""))

    @staticmethod
    def _resolve_output(file_prefix: str) -> Path:
        stem = Path(file_prefix)
        candidates = sorted(
            c for c in stem.parent.glob(stem.name + "*")
            if c.suffix.lower() in {".wav", ".mp3", ".flac"}
        )
        if not candidates:
            raise RuntimeError(f"voice_clone: no output for prefix {file_prefix}")
        return candidates[-1]

    # ─── Path 1: instruct mode (best accent) ───────────────────────────

    def _speak_instruct(self, text: str, ref_audio_path: Path, accent: str) -> Path:
        from mlx_audio.tts.generate import generate_audio
        tag = SHORT_ACCENT_TAG[accent]
        _, file_prefix = self._new_tempfile()
        # Force instruct dispatch in CosyVoice 3: ref_text=None means the
        # `ref_text` branch is skipped, so `instruct_text` wins.
        generate_audio(
            text=text,
            model=self.model_id,
            ref_audio=str(ref_audio_path),
            ref_text=None,
            instruct_text=tag,
            file_prefix=file_prefix,
        )
        return self._resolve_output(file_prefix)

    # ─── Path 2: VC fallback (correct words guaranteed) ────────────────

    def _speak_vc(self, text: str, ref_audio_path: Path, accent: str) -> Path:
        from mlx_audio.tts.generate import generate_audio
        source = self._render_accent_audio(text, accent)
        _, file_prefix = self._new_tempfile()
        try:
            generate_audio(
                text=text,
                model=self.model_id,
                ref_audio=str(ref_audio_path),
                source_audio=str(source),
                file_prefix=file_prefix,
            )
        finally:
            try:
                source.unlink(missing_ok=True)
            except Exception:
                pass
        return self._resolve_output(file_prefix)

    # ─── Validation: whisper-transcribe + compare ──────────────────────

    @staticmethod
    def _normalise(s: str) -> str:
        return " ".join(re.findall(r"[a-z']+", s.lower()))

    @staticmethod
    def _word_metrics(expected: str, actual: str) -> tuple[float, float, float]:
        e_norm = VoiceClone._normalise(expected)
        a_norm = VoiceClone._normalise(actual)
        if not e_norm:
            return 1.0, 1.0, 1.0
        e_words = e_norm.split()
        a_words = a_norm.split()
        if not e_words:
            return 1.0, 1.0, 1.0
        e_set = set(e_words)
        a_set = set(a_words)
        coverage = len(e_set & a_set) / len(e_set)
        length_ratio = len(a_words) / len(e_words) if e_words else 1.0
        seq_sim = SequenceMatcher(None, e_norm, a_norm).ratio()
        return coverage, length_ratio, seq_sim

    def _transcribe_with_words(self, audio_path: Path) -> dict:
        """Run STT on the synthesised audio, returning {text, words}."""
        if self._whisper is None:
            return {"text": "", "words": []}
        try:
            wav, sr = sf.read(str(audio_path))
        except Exception as e:
            logger.warning(f"voice_clone: stt read failed: {e}")
            return {"text": "", "words": []}
        wav = np.asarray(wav, dtype=np.float32)
        if wav.ndim > 1:
            wav = wav.mean(axis=1)
        if sr != 16_000:
            wav = resampy.resample(wav, sr, 16_000).astype(np.float32)
        try:
            if hasattr(self._whisper, "transcribe_with_words"):
                return self._whisper.transcribe_with_words(wav.astype(np.float32))
            # Fallback to full transcribe
            tx = self._whisper.transcribe(wav.astype(np.float32))
            return {"text": tx.get("text", ""), "words": tx.get("words", [])}
        except Exception as e:
            logger.warning(f"voice_clone: stt failed: {e}")
            return {"text": "", "words": []}

    def _validate(self, expected_text: str, transcript: str) -> tuple[bool, dict]:
        """Pure metric check — caller supplies the transcript."""
        coverage, length_ratio, seq_sim = self._word_metrics(expected_text, transcript)
        passes = (
            coverage >= MIN_WORD_COVERAGE
            and length_ratio <= MAX_LENGTH_RATIO
            and seq_sim >= MIN_SEQUENCE_SIM
        )
        return passes, {
            "coverage": round(coverage, 3),
            "length_ratio": round(length_ratio, 3),
            "seq_sim": round(seq_sim, 3),
            "transcript_preview": transcript[:80],
        }

    # ─── Public entry point ────────────────────────────────────────────

    def speak(
        self,
        text: str,
        ref_audio_path: str | Path,
        accent: str,
        out_path: str | Path | None = None,
    ) -> tuple[Path, list[dict]]:
        """Synthesize `text` in user's voice + target accent.

        Returns (audio_path, word_timings) where word_timings is a list of
        `{word, start_ms, end_ms}` derived from Whisper. The same STT pass
        validates instruct-mode output against the input text.
        """
        accent = accent.upper()
        if accent not in KOKORO_VOICE_MAP:
            raise ValueError(f"Unsupported accent: {accent}")
        ref_path = Path(ref_audio_path)
        if not ref_path.exists():
            raise FileNotFoundError(f"Reference audio not found: {ref_path}")

        t_total = time.perf_counter()

        # Path 1: instruct (best accent)
        instruct_path: Optional[Path] = None
        t0 = time.perf_counter()
        try:
            instruct_path = self._speak_instruct(text, ref_path, accent)
            t_instruct = time.perf_counter() - t0
        except Exception as e:
            t_instruct = time.perf_counter() - t0
            logger.warning(f"voice_clone.speak: instruct failed in {t_instruct:.1f}s — {e}")

        if instruct_path is not None:
            t1 = time.perf_counter()
            stt = self._transcribe_with_words(instruct_path)
            t_val = time.perf_counter() - t1
            passes, metrics = self._validate(text, stt.get("text", ""))
            if passes:
                logger.info(
                    f"voice_clone.speak: text={len(text)}c accent={accent} "
                    f"mode=instruct ({t_instruct:.1f}s synth + {t_val:.1f}s stt) "
                    f"metrics={metrics}"
                )
                return instruct_path, stt.get("words", [])
            logger.info(
                f"voice_clone.speak: instruct failed validation in {t_val:.1f}s — {metrics}"
            )
            try:
                instruct_path.unlink(missing_ok=True)
            except Exception:
                pass

        # Path 2: VC fallback (guaranteed words)
        t2 = time.perf_counter()
        out = self._speak_vc(text, ref_path, accent)
        t_vc = time.perf_counter() - t2

        # Get word timings on the fallback output too — caller wants them.
        t3 = time.perf_counter()
        stt = self._transcribe_with_words(out)
        t_stt = time.perf_counter() - t3

        logger.info(
            f"voice_clone.speak: text={len(text)}c accent={accent} mode=vc "
            f"({t_vc:.1f}s synth + {t_stt:.1f}s stt, total {time.perf_counter()-t_total:.1f}s)"
        )
        return out, stt.get("words", [])

    # ─── Legacy compat ─────────────────────────────────────────────────

    def clone(
        self,
        text: str,
        ref_audio_path: str | Path,
        ref_text: str,
        instruct_text: str | None = None,
        out_path: str | Path | None = None,
    ) -> Path:
        """Forwarded to `speak()`. Recover accent from instruct prefix."""
        accent = "GA"
        if instruct_text:
            for acc, hint in ACCENT_INSTRUCTIONS.items():
                if hint == instruct_text:
                    accent = acc
                    break
            for acc, hint in SHORT_ACCENT_TAG.items():
                if hint == instruct_text:
                    accent = acc
                    break
        return self.speak(text=text, ref_audio_path=ref_audio_path, accent=accent, out_path=out_path)
