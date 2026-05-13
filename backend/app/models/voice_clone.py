"""
Voice cloning + accent transfer via CosyVoice 3 (mlx-audio-plus).

The app has two different user goals:

  1. TARGET ACCENT — speak arbitrary text with the user's timbre but with
     a requested English accent. This must prioritize accent consistency.
     We synthesize a target-accent source with Kokoro, then use CosyVoice
     voice conversion to transfer it to the enrolled speaker.

  2. NATURAL CLONE — speak arbitrary text as close to the enrolled voice
     as possible. This uses CosyVoice zero-shot (`ref_audio + ref_text`).
     It intentionally preserves the reference accent, so it is not the
     default for an accent-coaching product.

Fallback modes:

  - INSTRUCT — CosyVoice 3 LLM end-to-end with a TINY accent style tag
     ("American accent." / "British accent.") and the user's enrollment as
    speaker prompt. Good style control, but still stochastic.

  - VC is deterministic about accent because the source audio already has
    the target accent.
"""
from __future__ import annotations

from dataclasses import dataclass
import logging
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Optional

import numpy as np
import resampy
import soundfile as sf

from app.utils.kokoro_speaker import synth_array_at
from app.utils.text_metrics import phrase_match_metrics, word_tokens

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

# Single-word style noun appended to the accent clause. CV3 recites long
# imperative prompts ("Speak happily in American accent.") aloud, so we keep
# the emotion to a terse trailing tag instead.
EMOTION_TAGS: dict[str, str] = {
    "neutral": "",
    "happy": "Happy.",
    "sad": "Sad.",
    "angry": "Angry.",
    "excited": "Excited.",
    "calm": "Calm.",
    "whisper": "Whisper.",
}

DEFAULT_EMOTION = "neutral"

# CosyVoice 3 inline prosody markers (<laughter>, [breath], etc). Pass
# through to synth; strip from text used for whisper validation so they
# don't tank coverage. CV2-style [happy]/[surprised] tokens are NOT used
# anymore — CV3 speaks them as literal text ("S. Orbis", "Ope-Tay-Tess").
INLINE_MARKER_RE = re.compile(r"<[^>]+>|\[[^\]]+\]")

# Words that, if present in the synth transcript but not the input text,
# strongly suggest the LLM recited the instruct prompt aloud.
_INSTRUCT_LEAK_TERMS = (
    "american accent",
    "british accent",
    "speak happily",
    "speak sadly",
    "speak angrily",
    "speak excitedly",
    "speak calmly",
    "in a whisper",
    # terse emotion tags can also be spoken literally by the model
    "happy",
    "sad",
    "angry",
    "excited",
    "calm",
    "whisper",
)

# Verbose forms kept ONLY for the legacy clone() shim; not used by speak().
ACCENT_INSTRUCTIONS: dict[str, str] = {
    "GA": "American English, neutral US Midwestern news anchor accent.",
    "RP": "British Received Pronunciation, BBC newsreader accent.",
}

COSYVOICE_SR = 24_000
COSYVOICE3_ZERO_SHOT_PREFIX = "You are a helpful assistant.<|endofprompt|>"

# Validation thresholds for direct CosyVoice generations.
MIN_WORD_COVERAGE = 0.80   # tolerate proper-name ASR variants
MAX_LENGTH_RATIO = 1.45    # transcript >1.45x longer than input = hallucination
MIN_SEQUENCE_SIM = 0.62    # character similarity over normalized text


@dataclass(frozen=True)
class VoiceSynthesisResult:
    path: Path
    words: list[dict]
    mode: str
    strategy: str
    metrics: dict | None = None


class VoiceClone:
    def __init__(
        self,
        model_id: str = DEFAULT_MODEL,
        whisper_engine: Optional[object] = None,
    ):
        self.model_id = model_id
        self._whisper = whisper_engine
        self._warmed = False

    def supported_accents(self) -> list[str]:
        return list(KOKORO_VOICE_MAP.keys())

    def supported_emotions(self) -> list[str]:
        return list(EMOTION_TAGS.keys())

    @staticmethod
    def _normalize_emotion(emotion: str | None) -> str:
        if not emotion:
            return DEFAULT_EMOTION
        key = emotion.strip().lower()
        return key if key in EMOTION_TAGS else DEFAULT_EMOTION

    @staticmethod
    def _compose_instruct_tag(accent: str, emotion: str) -> str:
        accent_phrase = SHORT_ACCENT_TAG[accent]
        emotion_phrase = EMOTION_TAGS.get(emotion, "")
        if emotion_phrase:
            return f"{accent_phrase} {emotion_phrase}"
        return accent_phrase

    @staticmethod
    def _strip_inline_markers(text: str) -> str:
        return INLINE_MARKER_RE.sub(" ", text)

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

    def _render_accent_audio(self, text: str, accent: str) -> Path:
        accent = accent.upper()
        if accent not in KOKORO_VOICE_MAP:
            raise ValueError(f"Unsupported accent: {accent}")
        wav = synth_array_at(text, accent, COSYVOICE_SR, speed=1.0)
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

    # ─── Path 1: zero-shot mode (best naturalness) ─────────────────────

    def _zero_shot_ref_text(self, ref_text: str) -> str:
        text = (ref_text or "").strip()
        if not text:
            return text
        model = self.model_id.lower()
        if "cosyvoice3" in model and "<|endofprompt|>" not in text:
            return COSYVOICE3_ZERO_SHOT_PREFIX + text
        return text

    def _speak_zero_shot(self, text: str, ref_audio_path: Path, ref_text: str) -> Path:
        from mlx_audio.tts.generate import generate_audio
        _, file_prefix = self._new_tempfile()
        generate_audio(
            text=text,
            model=self.model_id,
            ref_audio=str(ref_audio_path),
            ref_text=self._zero_shot_ref_text(ref_text),
            instruct_text=None,
            file_prefix=file_prefix,
        )
        return self._resolve_output(file_prefix)

    # ─── Path 2: instruct mode (best accent control) ───────────────────

    def _speak_instruct(
        self,
        text: str,
        ref_audio_path: Path,
        accent: str,
        emotion: str = DEFAULT_EMOTION,
    ) -> Path:
        from mlx_audio.tts.generate import generate_audio
        tag = self._compose_instruct_tag(accent, emotion)
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

    # ─── Path 3: VC fallback (correct words guaranteed) ────────────────

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
        return " ".join(word_tokens(s))

    @staticmethod
    def _strip_instruct_tag_from_transcript(tag: str, transcript: str) -> str:
        """Remove leaked instruct words (accent + emotion) from the transcript
to avoid validation penalising harmless style-tag recitation.
        """
        if not tag or not transcript:
            return transcript
        # Split tag into individual words; strip punctuation before comparing
        tag_words = {
            re.sub(r"[^a-zA-Z]", "", w).lower()
            for w in tag.split()
            if len(re.sub(r"[^a-zA-Z]", "", w)) >= 2
        }
        words = transcript.split()
        filtered: list[str] = []
        for w in words:
            core = re.sub(r"[^a-zA-Z]", "", w).lower()
            if core and core in tag_words and len(core) >= 3:
                continue
            filtered.append(w)
        return " ".join(filtered)

    @staticmethod
    def _trim_silence(
        wav: np.ndarray,
        sr: int = COSYVOICE_SR,
        threshold: float = 0.015,
        frame_ms: int = 20,
        pre_roll_ms: int = 60,
        post_roll_ms: int = 60,
    ) -> np.ndarray:
        """Trim leading / trailing digital silence so the audio starts at speech
        onset and ends on the last voiced frame."""
        if wav.size < sr // 10:
            return wav
        frame = max(1, int(sr * frame_ms / 1000))
        usable = len(wav) - (len(wav) % frame)
        if usable <= frame:
            return wav
        frames = wav[:usable].reshape(-1, frame)
        rms = np.sqrt(np.mean(frames ** 2, axis=1))
        if rms.size == 0:
            return wav
        peak = float(rms.max())
        thresh = max(threshold, peak * 0.12)
        voiced = np.flatnonzero(rms >= thresh)
        if voiced.size == 0:
            return wav
        pre_frames = max(1, int(pre_roll_ms / frame_ms))
        post_frames = max(1, int(post_roll_ms / frame_ms))
        start_frame = max(0, int(voiced[0]) - pre_frames)
        end_frame = min(len(rms), int(voiced[-1]) + 1 + post_frames)
        start_sample = start_frame * frame
        end_sample = min(end_frame * frame, len(wav))
        return wav[start_sample:end_sample]

    @staticmethod
    def _word_metrics(expected: str, actual: str) -> tuple[float, float, float]:
        e_words = word_tokens(expected)
        a_words = word_tokens(actual)
        if not e_words:
            return 1.0, 1.0, 1.0
        metrics = phrase_match_metrics(actual, expected)
        coverage = metrics["word_coverage"]
        length_ratio = len(a_words) / len(e_words) if e_words else 1.0
        seq_sim = metrics["char_similarity"]
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

    @staticmethod
    def _instruct_leaked(expected_text: str, transcript: str) -> bool:
        """Detect when CV3 recited the instruct prompt aloud.

        We compare against the *expected* text — leak terms are flagged only
        when they appear in the transcript but not in the user's input.
        """
        t = (transcript or "").lower()
        e = (expected_text or "").lower()
        for term in _INSTRUCT_LEAK_TERMS:
            if term in t and term not in e:
                return True
        return False

    def _validate(self, expected_text: str, transcript: str) -> tuple[bool, dict]:
        """Pure metric check — caller supplies the transcript."""
        coverage, length_ratio, seq_sim = self._word_metrics(expected_text, transcript)
        leaked = self._instruct_leaked(expected_text, transcript)
        passes = (
            coverage >= MIN_WORD_COVERAGE
            and length_ratio <= MAX_LENGTH_RATIO
            and seq_sim >= MIN_SEQUENCE_SIM
            and not leaked
        )
        return passes, {
            "coverage": round(coverage, 3),
            "length_ratio": round(length_ratio, 3),
            "seq_sim": round(seq_sim, 3),
            "leaked": leaked,
            "transcript_preview": transcript[:80],
        }

    @staticmethod
    def _trim_and_rewrite(audio_path: Path) -> Path:
        """Trim leading / trailing silence from a WAV and overwrite in place."""
        try:
            wav, sr = sf.read(str(audio_path), dtype="float32")
            if wav.ndim > 1:
                wav = wav.mean(axis=1)
            trimmed = VoiceClone._trim_silence(wav, sr=sr)
            sf.write(str(audio_path), trimmed, sr, format="WAV", subtype="PCM_16")
        except Exception as e:
            logger.warning(f"voice_clone: silence trim failed — {e}")
        return audio_path

    @staticmethod
    def _estimate_word_timings(text: str, audio_path: Path) -> list[dict]:
        tokens = word_tokens(text)
        if not tokens:
            return []
        try:
            info = sf.info(str(audio_path))
            duration_ms = max(300, int(info.frames / max(info.samplerate, 1) * 1000))
        except Exception:
            duration_ms = max(300, len(tokens) * 280)
        step = duration_ms / len(tokens)
        return [
            {
                "word": word,
                "start_ms": int(i * step),
                "end_ms": int((i + 1) * step),
            }
            for i, word in enumerate(tokens)
        ]

    @staticmethod
    def _strategy_name(strategy: str) -> str:
        normalized = (strategy or "target_accent").strip().lower().replace("-", "_")
        if normalized in {"natural", "natural_clone", "zero_shot"}:
            return "natural"
        return "target_accent"

    @classmethod
    def _select_mode(
        cls,
        strategy_name: str,
        emotion: str,
        ref_text: str,
    ) -> str:
        """Pick exactly one synthesis mode based on the user-facing knobs.

        Mode selection rules — there is no fallback chain; we run the chosen
        mode once and return the audio + metrics so the caller can decide
        whether to surface a warning.

          * non-neutral emotion → ``instruct`` (only mode that carries emotion)
          * ``strategy=natural`` with a real ref_text → ``zero_shot``
          * everything else → ``vc`` (deterministic accent transfer)
        """
        if emotion != DEFAULT_EMOTION:
            return "instruct"
        if strategy_name == "natural" and ref_text.strip():
            return "zero_shot"
        return "vc"

    # ─── Public entry point ────────────────────────────────────────────

    def speak(
        self,
        text: str,
        ref_audio_path: str | Path,
        accent: str,
        ref_text: str = "",
        strategy: str = "target_accent",
        emotion: str = DEFAULT_EMOTION,
        out_path: str | Path | None = None,
    ) -> VoiceSynthesisResult:
        """Synthesize ``text`` in the user's voice + target accent.

        One mode runs per call (no retry chain). Selection rules live in
        ``_select_mode``. The synthesised audio is post-processed (silence
        trim) and passed through a single Whisper STT call that produces
        both the validation transcript and the per-word timings.
        """
        accent = accent.upper()
        if accent not in KOKORO_VOICE_MAP:
            raise ValueError(f"Unsupported accent: {accent}")
        emotion = self._normalize_emotion(emotion)
        ref_path = Path(ref_audio_path)
        if not ref_path.exists():
            raise FileNotFoundError(f"Reference audio not found: {ref_path}")

        t_total = time.perf_counter()
        strategy_name = self._strategy_name(strategy)
        mode = self._select_mode(strategy_name, emotion, ref_text)

        # Inline prosody markers (<laughter>, [breath]) pass through to the
        # synth but must be stripped from validation text since the Whisper
        # transcript won't contain them.
        validation_text = self._strip_inline_markers(text)

        t0 = time.perf_counter()
        if mode == "vc":
            path = self._speak_vc(text, ref_path, accent)
        elif mode == "zero_shot":
            path = self._speak_zero_shot(text, ref_path, ref_text)
        else:  # instruct
            path = self._speak_instruct(text, ref_path, accent, emotion)
        t_synth = time.perf_counter() - t0

        # Single STT pass — provides both the validation transcript and the
        # per-word timings the frontend overlays.
        t1 = time.perf_counter()
        stt = self._transcribe_with_words(path)
        t_stt = time.perf_counter() - t1

        raw_transcript = stt.get("text", "")
        if mode == "instruct":
            tag_words = self._compose_instruct_tag(accent, emotion)
            clean_transcript = self._strip_instruct_tag_from_transcript(tag_words, raw_transcript)
        else:
            clean_transcript = raw_transcript
        _passes, metrics = self._validate(validation_text, clean_transcript)

        trimmed_path = self._trim_and_rewrite(path)
        words = stt.get("words", []) or self._estimate_word_timings(validation_text, trimmed_path)

        logger.info(
            f"voice_clone.speak: text={len(text)}c accent={accent} emotion={emotion} "
            f"strategy={strategy_name} mode={mode} "
            f"({t_synth:.1f}s synth + {t_stt:.1f}s stt, total {time.perf_counter()-t_total:.1f}s) "
            f"metrics={metrics}"
        )
        return VoiceSynthesisResult(
            path=trimmed_path,
            words=words,
            mode=mode,
            strategy=strategy_name,
            metrics=metrics,
        )

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
        result = self.speak(
            text=text,
            ref_audio_path=ref_audio_path,
            accent=accent,
            ref_text=ref_text,
            strategy="target_accent",
            out_path=out_path,
        )
        return result.path
