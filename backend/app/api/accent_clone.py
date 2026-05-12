"""
POST /api/accent-clone

Personal accent conversion that preserves the user's voice timbre.

Pipeline:
  1. The user's submitted recording is transcribed with Whisper to get the
     target text we should render.
  2. Their enrollment clip (recorded once via /api/voice/enroll) provides
     target speaker timbre.
  3. The requested accent is rendered first, then voice-converted into the
     enrolled speaker for more reliable accent consistency.

Returns: audio/wav at the CosyVoice native sample rate.
"""
import logging
import time

import numpy as np
from fastapi import APIRouter, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from app.utils.audio import AudioError, preprocess
from app.utils.voice_store import VoiceStoreError, get_enrollment

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/accent-clone")
async def accent_clone(
    request: Request,
    audio: UploadFile,
    accent: str = Form("GA"),
    user_id: str = Form(...),
    override_text: str = Form(""),
):
    accent = accent.upper()

    voice_clone = getattr(request.app.state, "voice_clone", None)
    whisper = getattr(request.app.state, "whisper", None)
    if voice_clone is None:
        raise HTTPException(status_code=503, detail="Voice cloning engine not loaded.")
    if whisper is None:
        raise HTTPException(status_code=503, detail="Transcription engine not loaded.")

    if accent not in voice_clone.supported_accents():
        raise HTTPException(
            status_code=400,
            detail=f"Accent '{accent}' not supported. Choose: {voice_clone.supported_accents()}",
        )

    try:
        info = get_enrollment(user_id)
    except VoiceStoreError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if info is None:
        raise HTTPException(
            status_code=404,
            detail="No voice enrollment found for this user. Record an enrollment first.",
        )

    # Decide target text. If the caller already knows the target text
    # (e.g. the phrase they were asked to read) we skip ASR — faster + no
    # risk of transcription errors. Otherwise Whisper handles it.
    target_text = override_text.strip()
    if not target_text:
        try:
            raw = await audio.read()
            wav, _ = preprocess(raw)
        except AudioError as e:
            raise HTTPException(status_code=422, detail=str(e))
        except Exception as e:
            logger.error(f"Audio decode failed: {e}")
            raise HTTPException(status_code=400, detail="Could not read audio file.")
        wav_np = wav.squeeze(0).numpy().astype(np.float32)
        try:
            asr = whisper.transcribe(wav_np)
            target_text = asr["text"].strip()
        except Exception as e:
            logger.warning(f"Whisper failed during accent-clone: {e}")
            raise HTTPException(status_code=500, detail="Could not transcribe your recording.")
    if not target_text:
        raise HTTPException(
            status_code=422,
            detail="Could not detect any words in the recording.",
        )

    t0 = time.perf_counter()
    try:
        result = voice_clone.speak(
            text=target_text,
            ref_audio_path=info["ref_path"],
            accent=accent,
            ref_text=info.get("ref_text", ""),
            strategy="target_accent",
        )
    except Exception as e:
        logger.exception(f"CosyVoice synthesis failed: {e}")
        raise HTTPException(status_code=500, detail="Accent clone failed.")
    elapsed = round((time.perf_counter() - t0) * 1000)
    logger.info(
        f"Accent clone {user_id[:6]}… → {accent} ({result.strategy}/{result.mode}) "
        f"| '{target_text[:40]}…' | {elapsed}ms | {len(result.words)} words"
    )

    import base64, json as _json
    words_b64 = base64.b64encode(
        _json.dumps(result.words, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")

    return FileResponse(
        path=str(result.path),
        media_type="audio/wav",
        headers={
            "X-Target-Text": target_text[:200],
            "X-Voice-Strategy": result.strategy,
            "X-Voice-Mode": result.mode,
            "X-Word-Timings": words_b64,
            "Access-Control-Expose-Headers": "X-Target-Text, X-Voice-Strategy, X-Voice-Mode, X-Word-Timings",
        },
    )
