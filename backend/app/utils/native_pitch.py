"""
Native pitch (F0) reference for a (text, accent) pair.

Pipeline:
  1. Synthesise the phrase via the shared Kokoro singleton (16 kHz mono).
  2. Extract the F0 contour through the ProsodyEngine (Parselmouth + pYIN fallback).
  3. Cache the result on disk + in-memory so repeat scoring of the same phrase
     pays the synthesis cost exactly once.

Returned as float32 numpy with 0.0 marking unvoiced frames, plus duration in ms.
"""
from __future__ import annotations

import hashlib
import io
import logging
import os
from pathlib import Path

import numpy as np

from app.cache import LRUCache, DiskCache
from app.models.prosody_engine import ProsodyEngine
from app.utils.kokoro_speaker import synth_array_at

logger = logging.getLogger(__name__)

TARGET_SR = 16_000
DISK_CACHE_ENABLED = os.getenv("NATIVE_F0_DISK_CACHE", "1") == "1"
DISK_CACHE_DIR = Path(os.getenv("NATIVE_F0_CACHE_DIR", "cache/native_f0"))

_MEM_CACHE: LRUCache[tuple, tuple[np.ndarray, int]] = LRUCache(512)
_DISK_CACHE = DiskCache(DISK_CACHE_DIR)


def _cache_key(text: str, accent: str, speed: float) -> tuple[str, str, float]:
    return (" ".join(text.split())[:200], accent.upper(), round(speed, 2))


def _digest(key: tuple[str, str, float]) -> str:
    raw = "\n".join(map(str, key)).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def _load_disk_cache(key: tuple[str, str, float]) -> tuple[np.ndarray, int] | None:
    if not DISK_CACHE_ENABLED:
        return None
    data_bytes = _DISK_CACHE.read_bytes(_digest(key), ".npz")
    if data_bytes is None:
        return None
    try:
        data = np.load(io.BytesIO(data_bytes))
        return data["f0"].astype(np.float32), int(data["duration_ms"])
    except Exception as e:
        logger.warning(f"native_pitch: could not decode disk cache for {key}: {e}")
        return None


def _save_disk_cache(key: tuple[str, str, float], f0: np.ndarray, duration_ms: int) -> None:
    if not DISK_CACHE_ENABLED:
        return
    try:
        buf = io.BytesIO()
        np.savez_compressed(buf, f0=f0.astype(np.float32), duration_ms=duration_ms)
        _DISK_CACHE.write_bytes(_digest(key), ".npz", buf.getvalue())
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
    cached = _MEM_CACHE.get(key)
    if cached is not None:
        return cached

    disk_cached = _load_disk_cache(key)
    if disk_cached is not None:
        _MEM_CACHE.set(key, disk_cached)
        return disk_cached

    try:
        wav16 = synth_array_at(text, key[1], TARGET_SR, speed)
    except Exception as e:
        logger.warning(f"native_pitch: synth failed for accent={accent}: {e}")
        return np.zeros(0, dtype=np.float32), 0

    f0, _voiced = prosody_engine._extract_f0(wav16)
    f0 = f0.astype(np.float32)
    duration_ms = int(round(len(wav16) / TARGET_SR * 1000))

    _save_disk_cache(key, f0, duration_ms)
    _MEM_CACHE.set(key, (f0, duration_ms))
    return f0, duration_ms
