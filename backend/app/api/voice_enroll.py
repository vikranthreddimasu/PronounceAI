"""
Voice enrollment endpoints — multi-take store + synthesis.

POST /api/voice/enroll
  multipart: audio (Blob), ref_text (str), user_id (str)
  -> { take, takes, duration_s, bundle_duration_s }
  Appends a new take to the user. Bundle is rebuilt lazily on next read.

GET  /api/voice/{user_id}
  -> { user_id, takes: [...], duration_s, bundle_duration_s,
       created_at, updated_at, revision }
  or 404.

DELETE /api/voice/{user_id}
  -> { deleted: bool }

DELETE /api/voice/{user_id}/takes/{take_id}
  -> { deleted: bool, remaining: int }

POST /api/voice/speak
  multipart: user_id (str), text (str), accent (str), strategy (str?)
  -> audio/wav  — `text` synthesised in the enrolled voice + target accent.
                  Response header `X-Word-Timings` carries a base64-encoded
                  JSON array of `{word, start_ms, end_ms}` for live highlight.
"""
import base64
import json
import logging
import time

from fastapi import APIRouter, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from app.utils.audio import AudioError, preprocess
from app.utils.voice_store import (
    VoiceStoreError,
    add_take,
    delete_enrollment,
    delete_take,
    get_enrollment,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _enrollment_summary(user_id: str) -> dict | None:
    info = get_enrollment(user_id)
    if info is None:
        return None
    # Strip the local filesystem path before returning to the client.
    return {k: v for k, v in info.items() if k != "ref_path"}


@router.post("/voice/enroll")
async def enroll(
    audio: UploadFile,
    ref_text: str = Form(...),
    user_id: str = Form(...),
):
    try:
        raw = await audio.read()
        wav, _ = preprocess(raw)
    except AudioError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Enrollment audio decode failed: {e}")
        raise HTTPException(status_code=400, detail="Could not read audio file.")

    wav_np = wav.squeeze(0).numpy()
    try:
        take = add_take(user_id=user_id, wav_16k_mono=wav_np, ref_text=ref_text)
    except VoiceStoreError as e:
        raise HTTPException(status_code=422, detail=str(e))

    summary = _enrollment_summary(user_id) or {}
    return {"take": take, **summary}


@router.get("/voice/{user_id}")
async def get_voice(user_id: str):
    try:
        summary = _enrollment_summary(user_id)
    except VoiceStoreError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if summary is None:
        raise HTTPException(status_code=404, detail="No enrollment found.")
    return summary


@router.delete("/voice/{user_id}")
async def delete_voice(user_id: str):
    try:
        deleted = delete_enrollment(user_id)
    except VoiceStoreError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"deleted": deleted}


@router.delete("/voice/{user_id}/takes/{take_id}")
async def delete_voice_take(user_id: str, take_id: str):
    try:
        deleted = delete_take(user_id, take_id)
    except VoiceStoreError as e:
        raise HTTPException(status_code=400, detail=str(e))
    summary = _enrollment_summary(user_id) or {}
    remaining = len(summary.get("takes", []))
    if remaining == 0:
        # Last take gone — remove the user dir entirely so /voice/<id> 404s cleanly.
        try:
            delete_enrollment(user_id)
        except Exception:
            pass
    return {"deleted": deleted, "remaining": remaining}


_MAX_TEXT_CHARS = 400


def _ascii_safe_header(value: str, limit: int = 200) -> str:
    """HTTP headers must be Latin-1. Strip non-ASCII so smart quotes, em-dashes,
    emoji, and accented chars don't crash uvicorn when echoed back to the client.
    """
    snippet = value[:limit]
    return snippet.encode("ascii", "ignore").decode("ascii")


@router.post("/voice/speak")
async def speak(
    request: Request,
    user_id: str = Form(...),
    text: str = Form(...),
    accent: str = Form("GA"),
    strategy: str = Form("target_accent"),
    emotion: str = Form("neutral"),
):
    accent = accent.upper()
    text = (text or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="Text is required.")
    if len(text) > _MAX_TEXT_CHARS:
        raise HTTPException(
            status_code=422,
            detail=f"Text too long (max {_MAX_TEXT_CHARS} chars).",
        )

    voice_clone = getattr(request.app.state, "voice_clone", None)
    if voice_clone is None:
        raise HTTPException(status_code=503, detail="Voice cloning engine not loaded.")
    if accent not in voice_clone.supported_accents():
        raise HTTPException(
            status_code=400,
            detail=f"Accent '{accent}' not supported. Choose: {voice_clone.supported_accents()}",
        )
    emotion_input = (emotion or "neutral").lower()
    detected_label = ""
    detected_score = 0.0
    if emotion_input == "auto":
        detector = getattr(request.app.state, "emotion_detector", None)
        if detector is None:
            emotion = "neutral"
        else:
            emotion, detected_score, detected_label = detector.detect(text)
            logger.info(
                f"voice/speak auto-emotion: raw={detected_label} "
                f"score={detected_score:.2f} → {emotion}"
            )
    elif emotion_input not in voice_clone.supported_emotions():
        raise HTTPException(
            status_code=400,
            detail=f"Emotion '{emotion}' not supported. Choose: {voice_clone.supported_emotions()} or 'auto'",
        )
    else:
        emotion = emotion_input

    try:
        info = get_enrollment(user_id)
    except VoiceStoreError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if info is None:
        raise HTTPException(
            status_code=404,
            detail="No voice enrollment found for this user. Record an enrollment first.",
        )

    t0 = time.perf_counter()
    try:
        result = voice_clone.speak(
            text=text,
            ref_audio_path=info["ref_path"],
            accent=accent,
            ref_text=info.get("ref_text", ""),
            strategy=strategy,
            emotion=emotion,
        )
    except Exception as e:
        logger.exception(f"Speak synthesis failed: {e}")
        raise HTTPException(status_code=500, detail="Voice synthesis failed.")
    elapsed = round((time.perf_counter() - t0) * 1000)
    logger.info(
        f"voice/speak {user_id[:6]}… → {accent} ({result.strategy}/{result.mode}) "
        f"| '{text[:40]}…' | {elapsed}ms "
        f"(ref bundle {info.get('bundle_duration_s', 0):.1f}s, "
        f"{len(info.get('takes', []))} takes, {len(result.words)} words)"
    )

    # Pack word timings into a single header. Base64 keeps the value
    # header-safe and compact for the typical 50–80 word outputs.
    words_b64 = base64.b64encode(
        json.dumps(result.words, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")

    headers = {
        "X-Target-Text": _ascii_safe_header(text),
        "X-Accent": accent,
        "X-Voice-Strategy": result.strategy,
        "X-Voice-Mode": result.mode,
        "X-Voice-Emotion": emotion,
        "X-Word-Timings": words_b64,
        "Access-Control-Expose-Headers": (
            "X-Target-Text, X-Accent, X-Voice-Strategy, X-Voice-Mode, "
            "X-Voice-Emotion, X-Voice-Emotion-Source, "
            "X-Voice-Emotion-Raw, X-Voice-Emotion-Score, X-Word-Timings"
        ),
    }
    if emotion_input == "auto":
        headers["X-Voice-Emotion-Source"] = "auto"
        headers["X-Voice-Emotion-Raw"] = detected_label or "neutral"
        headers["X-Voice-Emotion-Score"] = f"{detected_score:.3f}"
    else:
        headers["X-Voice-Emotion-Source"] = "manual"
    return FileResponse(
        path=str(result.path),
        media_type="audio/wav",
        headers=headers,
    )
