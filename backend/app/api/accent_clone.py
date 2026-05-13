"""
POST /api/accent-clone

Personal accent conversion that preserves the user's voice timbre.

Two input modes:
  * Caller provides ``override_text`` — render that text in the user's voice.
  * Caller uploads ``audio`` — Whisper ASR derives the text, then we synth.

Both modes converge on ``services.voice_synth.synthesize_user_voice`` so the
caching / fallback / emotion-routing logic is shared with ``/api/voice/speak``.
"""
from __future__ import annotations

import logging

import numpy as np
from fastapi import APIRouter, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response

from app.services import voice_synth
from app.services.voice_synth import (
    VoiceSynthError,
    MAX_TEXT_CHARS,
    response_headers as _voice_headers,
)
from app.utils.audio import AudioError, preprocess

logger = logging.getLogger(__name__)
router = APIRouter()


def _transcribe_audio(request: Request, audio_bytes: bytes) -> str:
    whisper = getattr(request.app.state, "whisper", None)
    if whisper is None:
        raise HTTPException(status_code=503, detail="Transcription engine not loaded.")
    try:
        wav, _ = preprocess(audio_bytes)
    except AudioError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Audio decode failed: {e}")
        raise HTTPException(status_code=400, detail="Could not read audio file.")
    wav_np = wav.squeeze(0).numpy().astype(np.float32)
    try:
        asr = whisper.transcribe(wav_np)
        return asr["text"].strip()
    except Exception as e:
        logger.warning(f"Whisper failed during accent-clone: {e}")
        raise HTTPException(status_code=500, detail="Could not transcribe your recording.")


@router.post("/accent-clone")
async def accent_clone(
    request: Request,
    audio: UploadFile,
    accent: str = Form("GA"),
    user_id: str = Form(...),
    override_text: str = Form(""),
    emotion: str = Form("neutral"),
):
    target_text = override_text.strip()
    if not target_text:
        audio_bytes = await audio.read()
        target_text = _transcribe_audio(request, audio_bytes)
    if not target_text:
        raise HTTPException(
            status_code=422,
            detail="Could not detect any words in the recording.",
        )
    if len(target_text) > MAX_TEXT_CHARS:
        target_text = target_text[:MAX_TEXT_CHARS]

    try:
        result = await voice_synth.synthesize_user_voice(
            request.app,
            user_id=user_id,
            text=target_text,
            accent=accent,
            strategy="target_accent",
            emotion=emotion,
        )
    except VoiceSynthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)

    logger.info(
        f"accent-clone {user_id[:6]}… → {result.accent} "
        f"({result.strategy}/{result.mode}) | '{result.text[:40]}…' "
        f"| {result.elapsed_ms}ms | {len(result.words)} words"
    )
    return Response(
        content=result.wav_bytes,
        media_type="audio/wav",
        headers=_voice_headers(result),
    )
