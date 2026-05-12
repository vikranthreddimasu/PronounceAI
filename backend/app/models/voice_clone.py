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
)

# Verbose forms kept ONLY for the legacy clone() shim; not used by speak().
ACCENT_INSTRUCTIONS: dict[str, str] = {
    "GA": "American English, neutral US Midwestern news anchor accent.",
    "RP": "British Received Pronunciation, BBC newsreader accent.",
}

KOKORO_SR = 24_000
COSYVOICE_SR = 24_000
COSYVOICE3_ZERO_SHOT_PREFIX = "You are a helpful assistant.<|endofprompt|>"

# Validation thresholds for direct CosyVoice generations.
MIN_WORD_COVERAGE = 0.80   # tolerate proper-name ASR variants
MAX_LENGTH_RATIO = 1.45    # transcript >1.45x longer than input = hallucination
MIN_SEQUENCE_SIM = 0.62    # character similarity over normalized text


def _mode_order(env_name: str, default: str) -> tuple[str, ...]:
    valid = {"vc", "instruct", "zero_shot"}
    raw = os.getenv(env_name, default)
    order = tuple(mode.strip().lower() for mode in raw.split(",") if mode.strip())
    return tuple(mode for mode in order if mode in valid) or tuple(default.split(","))


TARGET_ACCENT_ORDER = _mode_order("VOICE_TARGET_ACCENT_ORDER", "vc,instruct")
NATURAL_ORDER = _mode_order("VOICE_NATURAL_ORDER", "zero_shot,instruct,vc")


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
        self._kokoro_pipes: dict[str, "object"] = {}

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

    def _timings_for_output(
        self,
        expected_text: str,
        audio_path: Path,
        min_coverage: float = 0.55,
    ) -> tuple[list[dict], dict]:
        stt = self._transcribe_with_words(audio_path)
        _, metrics = self._validate(expected_text, stt.get("text", ""))
        words = stt.get("words", []) or []
        if words and metrics["coverage"] >= min_coverage:
            return words, metrics
        return self._estimate_word_timings(expected_text, audio_path), metrics

    @staticmethod
    def _strategy_order(strategy: str) -> tuple[str, tuple[str, ...]]:
        normalized = (strategy or "target_accent").strip().lower().replace("-", "_")
        if normalized in {"natural", "natural_clone", "zero_shot"}:
            return "natural", NATURAL_ORDER
        return "target_accent", TARGET_ACCENT_ORDER

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
        """Synthesize `text` in the user's voice.

        `strategy="target_accent"` uses VC-first for accent consistency.
        `strategy="natural"` uses zero-shot first and preserves the enrolled
        accent more strongly. `emotion` is a key from EMOTION_TAGS — anything
        other than "neutral" forces instruct-first because VC source audio
        (Kokoro) is prosodically flat.
        """
        accent = accent.upper()
        if accent not in KOKORO_VOICE_MAP:
            raise ValueError(f"Unsupported accent: {accent}")
        emotion = self._normalize_emotion(emotion)
        ref_path = Path(ref_audio_path)
        if not ref_path.exists():
            raise FileNotFoundError(f"Reference audio not found: {ref_path}")

        t_total = time.perf_counter()
        strategy_name, order = self._strategy_order(strategy)
        if emotion != DEFAULT_EMOTION:
            # VC erases emotion (flat Kokoro source). Zero-shot ignores
            # instruct_text. Only instruct mode carries the emotion clause.
            order = ("instruct",) + tuple(m for m in order if m != "instruct")

        # Inline prosody markers (<laughter>, [breath]) pass through to the
        # synth but must be stripped from the text used for validation —
        # whisper transcripts won't contain them.
        validation_text = self._strip_inline_markers(text)

        for mode in order:
            if mode == "zero_shot" and not ref_text.strip():
                continue
            if mode == "vc":
                t0 = time.perf_counter()
                try:
                    out = self._speak_vc(text, ref_path, accent)
                    t_vc = time.perf_counter() - t0
                    t1 = time.perf_counter()
                    words, metrics = self._timings_for_output(validation_text, out)
                    t_stt = time.perf_counter() - t1
                    logger.info(
                        f"voice_clone.speak: text={len(text)}c accent={accent} "
                        f"emotion={emotion} strategy={strategy_name} mode=vc "
                        f"({t_vc:.1f}s synth + {t_stt:.1f}s stt, "
                        f"total {time.perf_counter()-t_total:.1f}s) metrics={metrics}"
                    )
                    return VoiceSynthesisResult(
                        path=out,
                        words=words,
                        mode="vc",
                        strategy=strategy_name,
                        metrics=metrics,
                    )
                except Exception as e:
                    logger.warning(f"voice_clone.speak: vc failed — {e}")
                    continue

            path: Optional[Path] = None
            t0 = time.perf_counter()
            try:
                if mode == "zero_shot":
                    path = self._speak_zero_shot(text, ref_path, ref_text)
                else:
                    path = self._speak_instruct(text, ref_path, accent, emotion)
                t_synth = time.perf_counter() - t0
            except Exception as e:
                t_synth = time.perf_counter() - t0
                logger.warning(f"voice_clone.speak: {mode} failed in {t_synth:.1f}s — {e}")
                continue

            t1 = time.perf_counter()
            stt = self._transcribe_with_words(path)
            t_val = time.perf_counter() - t1
            passes, metrics = self._validate(validation_text, stt.get("text", ""))
            if passes:
                logger.info(
                    f"voice_clone.speak: text={len(text)}c accent={accent} "
                    f"emotion={emotion} strategy={strategy_name} mode={mode} "
                    f"({t_synth:.1f}s synth + {t_val:.1f}s stt) "
                    f"metrics={metrics}"
                )
                words = stt.get("words", []) or self._estimate_word_timings(validation_text, path)
                return VoiceSynthesisResult(
                    path=path,
                    words=words,
                    mode=mode,
                    strategy=strategy_name,
                    metrics=metrics,
                )
            logger.info(
                f"voice_clone.speak: {mode} failed validation in {t_val:.1f}s — {metrics}"
            )
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass

        raise RuntimeError(f"No voice synthesis mode succeeded (strategy={strategy_name}, order={order})")

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
