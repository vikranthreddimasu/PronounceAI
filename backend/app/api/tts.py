"""
GET /api/tts?text=...&accent=GA&speed=0.9

Returns audio/wav of the phrase spoken in the target accent using Kokoro TTS
(shared singleton in ``app.utils.kokoro_speaker``). Audio is cached in-memory
so repeated playback of the same phrase hits zero latency after the first call.
"""
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.cache import LRUCache
from app.utils.kokoro_speaker import (
    KOKORO_SR,
    VOICE_MAP,
    supported_accents,
    synth_wav_bytes,
)

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_TTS_TEXT_CHARS = 400
SAMPLE_RATE = KOKORO_SR

# In-memory audio cache: (text, accent, speed) → wav bytes
_AUDIO_CACHE: LRUCache[tuple, bytes] = LRUCache(512)


@router.get("/tts")
async def tts(
    text: str,
    accent: str = "GA",
    speed: float = 0.9,
):
    accent = accent.upper()
    if accent not in VOICE_MAP:
        accent = "GA"
    if not 0.5 <= speed <= 1.5:
        speed = 0.9
    text = (text or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="Text is required.")
    if len(text) > MAX_TTS_TEXT_CHARS:
        raise HTTPException(
            status_code=422,
            detail=f"Text too long (max {MAX_TTS_TEXT_CHARS} chars).",
        )

    cache_key = (text, accent, round(speed, 2))
    cached = _AUDIO_CACHE.get(cache_key)
    if cached is not None:
        return Response(content=cached, media_type="audio/wav")

    try:
        wav_bytes = synth_wav_bytes(text, accent, speed)
    except Exception as e:
        logger.error(f"TTS synthesis failed: {e}")
        raise HTTPException(status_code=500, detail="TTS synthesis failed")

    _AUDIO_CACHE.set(cache_key, wav_bytes)

    return Response(
        content=wav_bytes,
        media_type="audio/wav",
        headers={"Cache-Control": "public, max-age=86400"},
    )


# Backwards-compat re-exports for callers that still reach into this module.
def _synthesize(text: str, lang_code: str, voice: str, speed: float) -> bytes:
    """Shim preserved for any caller importing ``app.api.tts._synthesize``.

    The lang_code/voice arguments are derived from ``accent`` in the singleton,
    so we ignore them here and recompute via VOICE_MAP for symmetry.
    """
    accent = next(
        (a for a, (lc, v) in VOICE_MAP.items() if lc == lang_code and v == voice),
        "GA",
    )
    return synth_wav_bytes(text, accent, speed)


__all__ = ["router", "VOICE_MAP", "MAX_TTS_TEXT_CHARS", "SAMPLE_RATE", "_synthesize", "supported_accents"]
