"""
GET /api/tts?text=...&accent=GA&speed=0.9

Returns audio/wav of the phrase spoken in the target accent using Kokoro TTS.
Kokoro voices used:
  GA  → af_heart   (American female, most natural-sounding)
  RP  → bf_emma    (British RP female)

Audio is cached in-memory (LRU 512) so repeated playback of the same phrase
hits zero latency after the first synthesis.
"""
import io
import logging
import threading
from functools import lru_cache

import numpy as np
import soundfile as sf
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

logger = logging.getLogger(__name__)
router = APIRouter()

VOICE_MAP = {
    "GA":       ("a", "af_heart"),   # lang_code, voice
    "RP":       ("b", "bf_emma"),
    "AuE":      ("a", "af_bella"),   # closest available
    "Irish":    ("b", "bm_george"),
    "Scottish": ("b", "bm_lewis"),
    "IndianE":  ("a", "am_michael"),
}

SAMPLE_RATE = 24000   # Kokoro native output rate
_PIPELINE_LOCK = threading.RLock()
_AUDIO_CACHE_LOCK = threading.RLock()


def _synthesize(text: str, lang_code: str, voice: str, speed: float) -> bytes:
    """Synthesize text → WAV bytes at 24 kHz mono."""
    from kokoro import KPipeline
    pipe = _get_pipeline(lang_code)
    chunks = []
    for _, _, audio in pipe(text, voice=voice, speed=speed):
        chunks.append(audio)
    if not chunks:
        raise RuntimeError("Kokoro returned no audio chunks")
    audio = np.concatenate(chunks).astype(np.float32)
    buf = io.BytesIO()
    sf.write(buf, audio, SAMPLE_RATE, format="WAV", subtype="PCM_16")
    return buf.getvalue()


@lru_cache(maxsize=2)
def _get_pipeline_cached(lang_code: str):
    """Cached pipeline — one per language code (a=American, b=British)."""
    from kokoro import KPipeline
    logger.info(f"Loading Kokoro pipeline lang_code={lang_code}")
    return KPipeline(lang_code=lang_code)


def _get_pipeline(lang_code: str):
    with _PIPELINE_LOCK:
        return _get_pipeline_cached(lang_code)


# In-memory audio cache: (text, accent, speed) → wav bytes
_audio_cache: dict[tuple, bytes] = {}
_MAX_CACHE = 512


@router.get("/tts")
async def tts(
    request: Request,
    text: str,
    accent: str = "GA",
    speed: float = 0.9,
):
    accent = accent.upper()
    if accent not in VOICE_MAP:
        accent = "GA"
    if not 0.5 <= speed <= 1.5:
        speed = 0.9

    cache_key = (text[:200], accent, round(speed, 2))
    with _AUDIO_CACHE_LOCK:
        cached = _audio_cache.get(cache_key)
    if cached is not None:
        return Response(content=cached, media_type="audio/wav")

    lang_code, voice = VOICE_MAP[accent]
    try:
        wav_bytes = _synthesize(text, lang_code, voice, speed)
    except Exception as e:
        logger.error(f"TTS synthesis failed: {e}")
        raise HTTPException(status_code=500, detail="TTS synthesis failed")

    with _AUDIO_CACHE_LOCK:
        if len(_audio_cache) >= _MAX_CACHE:
            _audio_cache.pop(next(iter(_audio_cache)))
        _audio_cache[cache_key] = wav_bytes

    return Response(
        content=wav_bytes,
        media_type="audio/wav",
        headers={"Cache-Control": "public, max-age=86400"},
    )
