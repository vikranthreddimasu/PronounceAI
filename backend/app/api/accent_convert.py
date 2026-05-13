"""
POST /api/accent-convert

Accepts: multipart form with audio (Blob), accent (str, target accent)
Returns: audio/wav — the same words spoken in the target accent (kNN-VC).
"""
import io
import logging
import asyncio

import numpy as np
import soundfile as sf
from fastapi import APIRouter, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response

from app.utils.audio import AudioError, preprocess

logger = logging.getLogger(__name__)
router = APIRouter()

OUTPUT_SR = 16_000


async def _get_converter(request: Request):
    converter = getattr(request.app.state, "accent_converter", None)
    if converter is not None:
        return converter

    lock = getattr(request.app.state, "accent_converter_lock", None)
    if lock is None:
        request.app.state.accent_converter_lock = asyncio.Lock()
        lock = request.app.state.accent_converter_lock

    async with lock:
        converter = getattr(request.app.state, "accent_converter", None)
        if converter is not None:
            return converter
        try:
            from app.models.accent_converter import AccentConverter
            converter = await asyncio.to_thread(AccentConverter, device="cpu")
            request.app.state.accent_converter = converter
            logger.info("Accent converter lazy-loaded")
            return converter
        except Exception as e:
            logger.exception("Accent converter lazy-load failed: %s", e)
            raise HTTPException(status_code=503, detail="Accent converter unavailable")


@router.post("/accent-convert")
async def accent_convert(
    request: Request,
    audio: UploadFile,
    accent: str = Form("GA"),
):
    accent = accent.upper()
    converter = await _get_converter(request)
    if accent not in converter.supported_accents():
        raise HTTPException(
            status_code=400,
            detail=f"Accent '{accent}' not supported. Choose: {converter.supported_accents()}",
        )

    try:
        raw = await audio.read()
        wav, sr = preprocess(raw)
    except AudioError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Audio load failed: {e}")
        raise HTTPException(status_code=400, detail="Could not read audio file.")

    wav_np = wav.squeeze(0).numpy().astype(np.float32)

    try:
        out_wav = converter.convert(wav_np, accent)
    except Exception as e:
        logger.exception(f"Accent conversion failed: {e}")
        raise HTTPException(status_code=500, detail="Accent conversion failed")

    buf = io.BytesIO()
    sf.write(buf, out_wav, OUTPUT_SR, format="WAV", subtype="PCM_16")
    return Response(content=buf.getvalue(), media_type="audio/wav")
