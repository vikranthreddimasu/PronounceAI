"""
Single Kokoro TTS pipeline shared by every code path that needs native-accent
synthesis: /api/tts, native pitch reference extraction, and CosyVoice VC
source rendering. Centralising the pipeline removes the four-way duplication
that previously had each consumer load its own KPipeline + KModel.

Pipelines are cached per lang_code ("a" American / "b" British) under a single
lock so concurrent first-callers don't double-load the model.
"""
from __future__ import annotations

import io
import logging
import os
import threading
from functools import lru_cache

import numpy as np
import resampy
import soundfile as sf

logger = logging.getLogger(__name__)

KOKORO_SR = 24_000
KOKORO_REPO_ID = os.getenv("KOKORO_REPO_ID", "hexgrad/Kokoro-82M")
KOKORO_DEVICE = os.getenv("KOKORO_DEVICE", "cpu")
KOKORO_CONFIG = os.getenv("KOKORO_CONFIG", "").strip()
KOKORO_MODEL_FILE = os.getenv("KOKORO_MODEL", "").strip()

VOICE_MAP: dict[str, tuple[str, str]] = {
    "GA":       ("a", "af_heart"),
    "RP":       ("b", "bf_emma"),
    "AUE":      ("a", "af_bella"),
    "IRISH":    ("b", "bm_george"),
    "SCOTTISH": ("b", "bm_lewis"),
    "INDIANE":  ("a", "am_michael"),
}

_PIPELINE_LOCK = threading.RLock()


@lru_cache(maxsize=1)
def _get_model():
    if not (KOKORO_CONFIG and KOKORO_MODEL_FILE):
        return True
    from kokoro.model import KModel
    logger.info(
        f"kokoro_speaker: loading model config={KOKORO_CONFIG} model={KOKORO_MODEL_FILE}"
    )
    return (
        KModel(
            repo_id=KOKORO_REPO_ID,
            config=KOKORO_CONFIG,
            model=KOKORO_MODEL_FILE,
        )
        .to(KOKORO_DEVICE)
        .eval()
    )


@lru_cache(maxsize=2)
def _get_pipeline_cached(lang_code: str):
    from kokoro import KPipeline
    logger.info(
        f"kokoro_speaker: loading lang_code={lang_code} repo_id={KOKORO_REPO_ID}"
    )
    return KPipeline(
        lang_code=lang_code,
        repo_id=KOKORO_REPO_ID,
        model=_get_model(),
        device=KOKORO_DEVICE,
    )


def _accent_voice(accent: str) -> tuple[str, str]:
    return VOICE_MAP.get(accent.upper(), VOICE_MAP["GA"])


def _pipeline(lang_code: str):
    with _PIPELINE_LOCK:
        return _get_pipeline_cached(lang_code)


def synth_array(text: str, accent: str, speed: float = 0.9) -> np.ndarray:
    """Synthesise → float32 mono numpy at KOKORO_SR."""
    lang_code, voice = _accent_voice(accent)
    pipe = _pipeline(lang_code)
    chunks: list[np.ndarray] = []
    for _, _, audio in pipe(text, voice=voice, speed=speed):
        if hasattr(audio, "detach"):
            audio = audio.detach().cpu().numpy()
        chunks.append(np.asarray(audio, dtype=np.float32))
    if not chunks:
        raise RuntimeError(f"kokoro_speaker: no audio produced for accent={accent}")
    return np.concatenate(chunks).astype(np.float32)


def synth_array_at(text: str, accent: str, target_sr: int, speed: float = 0.9) -> np.ndarray:
    """Synthesise and resample to ``target_sr`` (skips resample when equal)."""
    wav = synth_array(text, accent, speed)
    if target_sr == KOKORO_SR:
        return wav
    return resampy.resample(wav, KOKORO_SR, target_sr).astype(np.float32)


def synth_wav_bytes(text: str, accent: str, speed: float = 0.9) -> bytes:
    """Synthesise → 16-bit PCM WAV bytes at KOKORO_SR (for HTTP responses)."""
    wav = synth_array(text, accent, speed)
    buf = io.BytesIO()
    sf.write(buf, wav, KOKORO_SR, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def supported_accents() -> list[str]:
    return list(VOICE_MAP.keys())
