"""Shared voice-synthesis service.

Both ``/api/voice/speak`` and ``/api/accent-clone`` render text in the user's
enrolled voice + target accent. The previous implementation had two routers
each importing private cache helpers from the other; this module owns that
logic once.

Flow:

  1. Look up enrollment bundle (24 kHz prompt audio + ref_text).
  2. Compose cache key (user_id, text, accent, strategy, emotion, revision).
  3. On hit: return cached WAV + word timings.
  4. On miss: run VoiceClone (CosyVoice 3) or Kokoro fallback, persist to cache.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf

from app.cache import DiskCache
from app.utils.voice_store import VoiceStoreError, get_enrollment

logger = logging.getLogger(__name__)

_VOICE_SYNTH_CACHE_ENABLED = os.getenv("VOICE_SYNTH_CACHE", "1") == "1"
_VOICE_SYNTH_CACHE_DIR = Path(os.getenv("VOICE_SYNTH_CACHE_DIR", "cache/voice_synth"))
_VOICE_SYNTH_CACHE_MAX_AGE_HOURS = int(os.getenv("VOICE_SYNTH_CACHE_MAX_AGE_HOURS", "24"))

_disk_cache = DiskCache(_VOICE_SYNTH_CACHE_DIR, ttl_hours=_VOICE_SYNTH_CACHE_MAX_AGE_HOURS)

MAX_TEXT_CHARS = 400


class VoiceSynthError(Exception):
    """Raised for invalid request inputs (text too long, unknown accent, etc.)."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class SynthResult:
    wav_bytes: bytes
    words: list[dict]
    mode: str
    strategy: str
    accent: str
    emotion: str
    text: str
    enrollment: dict
    elapsed_ms: int
    from_cache: bool
    emotion_source: str
    detected_label: str
    detected_score: float


def cache_dir() -> Path:
    return _disk_cache._ensure().resolve()


def cache_paths(key: str) -> tuple[Path, Path]:
    return _disk_cache.path(key, ".wav"), _disk_cache.path(key, ".json")


def cache_key(
    user_id: str,
    text: str,
    accent: str,
    strategy: str,
    emotion: str,
    revision: str = "",
) -> str:
    payload = f"{user_id}:{accent}:{strategy}:{emotion}:{revision}:{text}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def cache_read(key: str) -> Optional[tuple[bytes, list[dict]]]:
    if not _VOICE_SYNTH_CACHE_ENABLED:
        return None
    pair = _disk_cache.read_pair(key, ".wav", ".json")
    if pair is None:
        return None
    wav_bytes, meta_text = pair
    try:
        meta = json.loads(meta_text)
    except Exception:
        return None
    return wav_bytes, meta.get("words", [])


def cache_write(key: str, wav_bytes: bytes, words: list[dict]) -> None:
    if not _VOICE_SYNTH_CACHE_ENABLED:
        return
    try:
        meta_text = json.dumps({"words": words, "cached_at": time.time()}, indent=2)
        _disk_cache.write_pair(key, ".wav", wav_bytes, ".json", meta_text)
    except Exception as e:
        logger.warning(f"voice_synth.cache_write failed: {e}")


# ── Audio post-processing ─────────────────────────────────────────────


def trim_wav_bytes(data: bytes) -> bytes:
    """Strip leading/trailing silence from raw WAV bytes (returns input on error)."""
    try:
        wav, sr = sf.read(io.BytesIO(data), dtype="float32")
        if wav.ndim > 1:
            wav = wav.mean(axis=1)
        frame = max(1, int(sr * 0.02))
        usable = len(wav) - (len(wav) % frame)
        if usable > frame:
            frames = wav[:usable].reshape(-1, frame)
            rms = np.sqrt(np.mean(frames ** 2, axis=1))
            peak = float(rms.max())
            thresh = max(0.015, peak * 0.12)
            voiced = np.flatnonzero(rms >= thresh)
            if voiced.size:
                pre = max(1, int(0.06 / 0.02))
                post = max(1, int(0.06 / 0.02))
                start = max(0, int(voiced[0]) - pre) * frame
                end = min(len(wav), (int(voiced[-1]) + 1 + post) * frame)
                wav = wav[start:end]
        buf = io.BytesIO()
        sf.write(buf, wav, sr, format="WAV", subtype="PCM_16")
        return buf.getvalue()
    except Exception:
        return data


def estimate_word_timings(text: str, duration_ms: int) -> list[dict]:
    words = text.split()
    if not words:
        return []
    weights = [max(1, len("".join(ch for ch in word if ch.isalpha()))) for word in words]
    total = sum(weights) or len(words)
    cursor = 0.0
    timings = []
    for word, weight in zip(words, weights):
        span = duration_ms * (weight / total)
        start = cursor
        cursor += span
        timings.append({"word": word, "start_ms": round(start), "end_ms": round(cursor)})
    return timings


def encode_word_timings(words: list[dict]) -> str:
    return base64.b64encode(
        json.dumps(words, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")


def _ascii_safe_header(value: str, limit: int = 200) -> str:
    """HTTP headers are latin-1; strip non-ASCII so smart-quotes don't crash uvicorn."""
    snippet = value[:limit]
    return snippet.encode("ascii", "ignore").decode("ascii")


def response_headers(result: SynthResult) -> dict[str, str]:
    headers = {
        "X-Target-Text": _ascii_safe_header(result.text),
        "X-Accent": result.accent,
        "X-Voice-Strategy": result.strategy,
        "X-Voice-Mode": result.mode,
        "X-Voice-Emotion": result.emotion,
        "X-Word-Timings": encode_word_timings(result.words),
        "Access-Control-Expose-Headers": (
            "X-Target-Text, X-Accent, X-Voice-Strategy, X-Voice-Mode, "
            "X-Voice-Emotion, X-Voice-Emotion-Source, "
            "X-Voice-Emotion-Raw, X-Voice-Emotion-Score, X-Word-Timings"
        ),
        "X-Voice-Emotion-Source": result.emotion_source,
    }
    if result.emotion_source == "auto":
        headers["X-Voice-Emotion-Raw"] = result.detected_label or "neutral"
        headers["X-Voice-Emotion-Score"] = f"{result.detected_score:.3f}"
    return headers


# ── Core synthesis entry point ────────────────────────────────────────


def _validate_text(text: str) -> str:
    text = (text or "").strip()
    if not text:
        raise VoiceSynthError(422, "Text is required.")
    if len(text) > MAX_TEXT_CHARS:
        raise VoiceSynthError(422, f"Text too long (max {MAX_TEXT_CHARS} chars).")
    return text


def _resolve_emotion(app, emotion: str, text: str) -> tuple[str, str, str, float]:
    """Return (resolved_emotion, source, detected_label, detected_score)."""
    voice_clone = getattr(app.state, "voice_clone", None)
    emotion_input = (emotion or "neutral").lower()
    if emotion_input == "auto":
        detector = getattr(app.state, "emotion_detector", None)
        if detector is None:
            return "neutral", "auto", "", 0.0
        resolved, score, label = detector.detect(text)
        logger.info(
            f"voice_synth: auto-emotion raw={label} score={score:.2f} → {resolved}"
        )
        return resolved, "auto", label, score
    if voice_clone is not None and emotion_input not in voice_clone.supported_emotions():
        raise VoiceSynthError(
            400,
            f"Emotion '{emotion}' not supported. "
            f"Choose: {voice_clone.supported_emotions()} or 'auto'",
        )
    return emotion_input, "manual", "", 0.0


def _kokoro_fallback(text: str, accent: str) -> tuple[bytes, list[dict]]:
    """When the voice clone engine isn't available, render via Kokoro TTS."""
    from app.utils.kokoro_speaker import VOICE_MAP, synth_wav_bytes

    accent_norm = accent if accent in VOICE_MAP else "GA"
    wav_bytes = synth_wav_bytes(text, accent_norm, 0.9)
    wav_bytes = trim_wav_bytes(wav_bytes)
    try:
        duration_ms = int(round(sf.info(io.BytesIO(wav_bytes)).duration * 1000))
    except Exception:
        duration_ms = max(500, len(text.split()) * 380)
    words = estimate_word_timings(text, duration_ms)
    return wav_bytes, words


async def synthesize_user_voice(
    app,
    *,
    user_id: str,
    text: str,
    accent: str,
    strategy: str = "target_accent",
    emotion: str = "neutral",
) -> SynthResult:
    """Render ``text`` in the user's enrolled voice + target accent.

    Concurrency: VoiceClone.speak is synchronous + lock-bound, so this is
    wrapped in ``asyncio.to_thread`` to keep the FastAPI event loop free.
    """
    accent = accent.upper()
    text = _validate_text(text)

    voice_clone = getattr(app.state, "voice_clone", None)
    if voice_clone is not None and accent not in voice_clone.supported_accents():
        raise VoiceSynthError(
            400,
            f"Accent '{accent}' not supported. Choose: {voice_clone.supported_accents()}",
        )

    resolved_emotion, emotion_source, detected_label, detected_score = _resolve_emotion(
        app, emotion, text
    )

    try:
        info = get_enrollment(user_id)
    except VoiceStoreError as e:
        raise VoiceSynthError(400, str(e))
    if info is None:
        raise VoiceSynthError(
            404,
            "No voice enrollment found for this user. Record an enrollment first.",
        )

    revision = info.get("revision", "")
    key = cache_key(user_id, text, accent, strategy, resolved_emotion, revision)

    t0 = time.perf_counter()
    cached = cache_read(key)
    if cached is not None:
        wav_bytes, words = cached
        elapsed_ms = round((time.perf_counter() - t0) * 1000)
        return SynthResult(
            wav_bytes=wav_bytes,
            words=words,
            mode="cache_hit",
            strategy=strategy,
            accent=accent,
            emotion=resolved_emotion,
            text=text,
            enrollment=info,
            elapsed_ms=elapsed_ms,
            from_cache=True,
            emotion_source=emotion_source,
            detected_label=detected_label,
            detected_score=detected_score,
        )

    if voice_clone is None:
        try:
            wav_bytes, words = _kokoro_fallback(text, accent)
        except Exception as e:
            logger.exception(f"voice_synth: kokoro fallback failed: {e}")
            raise VoiceSynthError(500, "Voice synthesis failed.")
        elapsed_ms = round((time.perf_counter() - t0) * 1000)
        cache_write(key, wav_bytes, words)
        return SynthResult(
            wav_bytes=wav_bytes,
            words=words,
            mode="kokoro_fallback",
            strategy=strategy,
            accent=accent,
            emotion=resolved_emotion,
            text=text,
            enrollment=info,
            elapsed_ms=elapsed_ms,
            from_cache=False,
            emotion_source=emotion_source,
            detected_label=detected_label,
            detected_score=detected_score,
        )

    try:
        result = await asyncio.to_thread(
            voice_clone.speak,
            text=text,
            ref_audio_path=info["ref_path"],
            accent=accent,
            ref_text=info.get("ref_text", ""),
            strategy=strategy,
            emotion=resolved_emotion,
        )
    except Exception as e:
        logger.exception(f"voice_synth: voice_clone.speak failed: {e}")
        raise VoiceSynthError(500, "Voice synthesis failed.")

    try:
        wav_bytes = result.path.read_bytes()
        wav_bytes = trim_wav_bytes(wav_bytes)
        cache_write(key, wav_bytes, result.words)
        try:
            result.path.unlink(missing_ok=True)
        except Exception:
            pass
    except Exception as e:
        logger.warning(f"voice_synth: cache write failed: {e}")
        wav_bytes = result.path.read_bytes()

    elapsed_ms = round((time.perf_counter() - t0) * 1000)
    return SynthResult(
        wav_bytes=wav_bytes,
        words=result.words,
        mode=result.mode,
        strategy=result.strategy,
        accent=accent,
        emotion=resolved_emotion,
        text=text,
        enrollment=info,
        elapsed_ms=elapsed_ms,
        from_cache=False,
        emotion_source=emotion_source,
        detected_label=detected_label,
        detected_score=detected_score,
    )
