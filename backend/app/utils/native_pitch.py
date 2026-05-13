"""
Native pitch (F0) reference for a (text, accent) pair.

Pipeline:
  1. Synthesise the phrase with Kokoro using the same voice as /api/tts.
  2. Extract the F0 contour via the ProsodyEngine (Parselmouth, with pYIN fallback).
  3. Cache the array so repeated playback of the same phrase pays the synthesis
     cost exactly once.

Returned as a numpy float32 array with 0.0 for unvoiced frames, plus the
synthesised duration in milliseconds. Sample rate is matched to the prosody
engine (16 kHz) by resampling the Kokoro output, which lets the same engine
consume both user and native audio without an sr parameter on every call.
"""
from __future__ import annotations

import logging
import hashlib
import os
import threading
from functools import lru_cache
from pathlib import Path

import numpy as np
import resampy

from app.models.prosody_engine import ProsodyEngine

logger = logging.getLogger(__name__)

KOKORO_SR = 24_000
TARGET_SR = 16_000
DISK_CACHE_ENABLED = os.getenv("NATIVE_F0_DISK_CACHE", "1") == "1"
DISK_CACHE_DIR = Path(os.getenv("NATIVE_F0_CACHE_DIR", "cache/native_f0"))
KOKORO_REPO_ID = os.getenv("KOKORO_REPO_ID", "hexgrad/Kokoro-82M")
KOKORO_DEVICE = os.getenv("KOKORO_DEVICE", "cpu")
KOKORO_CONFIG = os.getenv("KOKORO_CONFIG", "").strip()
KOKORO_MODEL = os.getenv("KOKORO_MODEL", "").strip()


# Voice map mirrors app/api/tts.py — kept inline so this module has zero coupling
# to the HTTP layer.
_VOICE_MAP = {
    "GA":       ("a", "af_heart"),
    "RP":       ("b", "bf_emma"),
    "AUE":      ("a", "af_bella"),
    "IRISH":    ("b", "bm_george"),
    "SCOTTISH": ("b", "bm_lewis"),
    "INDIANE":  ("a", "am_michael"),
}

_PIPELINE_LOCK = threading.RLock()


@lru_cache(maxsize=1)
def _get_model_cached():
    if not (KOKORO_CONFIG and KOKORO_MODEL):
        return True
    from kokoro.model import KModel
    logger.info(f"native_pitch: loading Kokoro model files config={KOKORO_CONFIG} model={KOKORO_MODEL}")
    return KModel(
        repo_id=KOKORO_REPO_ID,
        config=KOKORO_CONFIG,
        model=KOKORO_MODEL,
    ).to(KOKORO_DEVICE).eval()


@lru_cache(maxsize=2)
def _get_pipeline_cached(lang_code: str):
    """Cached Kokoro pipeline — one per language code."""
    from kokoro import KPipeline
    logger.info(f"native_pitch: loading Kokoro lang_code={lang_code} repo_id={KOKORO_REPO_ID}")
    return KPipeline(
        lang_code=lang_code,
        repo_id=KOKORO_REPO_ID,
        model=_get_model_cached(),
        device=KOKORO_DEVICE,
    )


def _get_pipeline(lang_code: str):
    with _PIPELINE_LOCK:
        return _get_pipeline_cached(lang_code)


def _synth_to_16k(text: str, accent: str, speed: float) -> np.ndarray:
    lang_code, voice = _VOICE_MAP.get(accent, _VOICE_MAP["GA"])
    pipe = _get_pipeline(lang_code)
    chunks: list[np.ndarray] = []
    for _, _, audio in pipe(text, voice=voice, speed=speed):
        if hasattr(audio, "detach"):
            audio = audio.detach().cpu().numpy()
        chunks.append(np.asarray(audio, dtype=np.float32))
    if not chunks:
        raise RuntimeError("Kokoro returned no audio")
    wav24 = np.concatenate(chunks).astype(np.float32)
    wav16 = resampy.resample(wav24, KOKORO_SR, TARGET_SR).astype(np.float32)
    return wav16


# Cache stores (f0_array, duration_ms). Keyed by (text[:200], accent, speed).
_F0_CACHE: dict[tuple, tuple[np.ndarray, int]] = {}
_MAX_CACHE = 512
_CACHE_LOCK = threading.RLock()


def _cache_key(text: str, accent: str, speed: float) -> tuple[str, str, float]:
    return (" ".join(text.split())[:200], accent.upper(), round(speed, 2))


def _cache_path(key: tuple[str, str, float]) -> Path:
    raw = "\n".join(map(str, key)).encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()[:24]
    return DISK_CACHE_DIR / f"{digest}.npz"


def _load_disk_cache(key: tuple[str, str, float]) -> tuple[np.ndarray, int] | None:
    if not DISK_CACHE_ENABLED:
        return None
    path = _cache_path(key)
    if not path.exists():
        return None
    try:
        data = np.load(path)
        return data["f0"].astype(np.float32), int(data["duration_ms"])
    except Exception as e:
        logger.warning(f"native_pitch: could not read disk cache {path}: {e}")
        return None


def _save_disk_cache(key: tuple[str, str, float], f0: np.ndarray, duration_ms: int) -> None:
    if not DISK_CACHE_ENABLED:
        return
    try:
        DISK_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(_cache_path(key), f0=f0.astype(np.float32), duration_ms=duration_ms)
    except Exception as e:
        logger.warning(f"native_pitch: could not write disk cache: {e}")


def get_native_f0(
    text: str,
    accent: str,
    prosody_engine: ProsodyEngine,
    speed: float = 0.9,
) -> tuple[np.ndarray, int]:
    """
    Returns (f0_array, duration_ms) for the native rendition.
    f0_array is float32, length matches the engine's Parselmouth output;
    0.0 entries are unvoiced frames.
    """
    key = _cache_key(text, accent, speed)
    with _CACHE_LOCK:
        cached = _F0_CACHE.get(key)
        if cached is not None:
            return cached

    disk_cached = _load_disk_cache(key)
    if disk_cached is not None:
        with _CACHE_LOCK:
            _F0_CACHE[key] = disk_cached
        return disk_cached

    try:
        wav16 = _synth_to_16k(text, key[1], speed)
    except Exception as e:
        logger.warning(f"native_pitch: synth failed for accent={accent}: {e}")
        return np.zeros(0, dtype=np.float32), 0

    f0, _voiced = prosody_engine._extract_f0(wav16)
    f0 = f0.astype(np.float32)
    duration_ms = int(round(len(wav16) / TARGET_SR * 1000))

    _save_disk_cache(key, f0, duration_ms)
    with _CACHE_LOCK:
        if len(_F0_CACHE) >= _MAX_CACHE:
            _F0_CACHE.pop(next(iter(_F0_CACHE)))
        _F0_CACHE[key] = (f0, duration_ms)
    return f0, duration_ms
