"""
Voice enrollment endpoints — multi-take store + synthesis.

POST /api/voice/enroll
  multipart: audio (Blob), ref_text (str), user_id (str)
  -> { take, takes, duration_s, bundle_duration_s }

GET  /api/voice/{user_id}                       -> enrollment summary or 404
DELETE /api/voice/{user_id}                     -> { deleted: bool }
DELETE /api/voice/{user_id}/takes/{take_id}     -> { deleted: bool, remaining: int }

POST /api/voice/speak
  multipart: user_id, text, accent, strategy?, emotion?
  -> audio/wav  — text synthesised in the enrolled voice + target accent.
                  Response header X-Word-Timings carries per-word timings.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Form, HTTPException, UploadFile, Request
from fastapi.responses import Response

from app.services import voice_synth
from app.services.voice_synth import (
    VoiceSynthError,
    cache_key as _voice_synth_cache_key,
    cache_dir as _voice_synth_cache_dir,
    cache_paths as _voice_synth_cache_paths,
    cache_read as _voice_synth_cache_read,
    cache_write as _voice_synth_cache_write,
    response_headers as _voice_headers,
    trim_wav_bytes as _trim_wav_bytes,
    estimate_word_timings as _estimate_word_timings,
)
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
        try:
            delete_enrollment(user_id)
        except Exception:
            pass
    return {"deleted": deleted, "remaining": remaining}


@router.post("/voice/speak")
async def speak(
    request: Request,
    user_id: str = Form(...),
    text: str = Form(...),
    accent: str = Form("GA"),
    strategy: str = Form("target_accent"),
    emotion: str = Form("neutral"),
):
    try:
        result = await voice_synth.synthesize_user_voice(
            request.app,
            user_id=user_id,
            text=text,
            accent=accent,
            strategy=strategy,
            emotion=emotion,
        )
    except VoiceSynthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)

    logger.info(
        f"voice/speak {user_id[:6]}… → {result.accent} ({result.strategy}/{result.mode}) "
        f"| '{result.text[:40]}…' | {result.elapsed_ms}ms "
        f"(ref bundle {result.enrollment.get('bundle_duration_s', 0):.1f}s, "
        f"{len(result.enrollment.get('takes', []))} takes, {len(result.words)} words)"
    )
    return Response(
        content=result.wav_bytes,
        media_type="audio/wav",
        headers=_voice_headers(result),
    )


__all__ = [
    "router",
    "_voice_synth_cache_key",
    "_voice_synth_cache_dir",
    "_voice_synth_cache_paths",
    "_voice_synth_cache_read",
    "_voice_synth_cache_write",
    "_voice_headers",
    "_trim_wav_bytes",
    "_estimate_word_timings",
]
