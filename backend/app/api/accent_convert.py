"""
POST /api/accent-convert

Accepts: multipart form with audio (Blob), accent (str, target accent)
Returns: audio/wav — the same words spoken in the target accent (kNN-VC).
"""
import io
import logging

import numpy as np
import soundfile as sf
from fastapi import APIRouter, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response

from app.utils.audio import AudioError, preprocess

logger = logging.getLogger(__name__)
router = APIRouter()

OUTPUT_SR = 16_000


@router.post("/accent-convert")
async def accent_convert(
    request: Request,
    audio: UploadFile,
    accent: str = Form("GA"),
):
    accent = accent.upper()
    converter = getattr(request.app.state, "accent_converter", None)
    if converter is None:
        raise HTTPException(status_code=503, detail="Accent converter not loaded")
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
