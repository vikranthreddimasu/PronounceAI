"""
POST /api/score      — pronunciation assessment
POST /api/prewarm    — best-effort warmup of a (phrase, accent) pair

Both endpoints are thin wrappers around ``app.scoring.pipeline``. All scoring
logic, blending, gates, caches, contour math, and feedback construction live
inside that package.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Form, HTTPException, Request, UploadFile

from app.scoring import (
    PrewarmPayload,
    prewarm_context,
    run_score,
    warmup_score_stack,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/prewarm")
async def prewarm_score_context(request: Request, payload: PrewarmPayload):
    phrase = " ".join(payload.phrase.split())
    if not phrase:
        return {"status": "ignored"}
    asyncio.create_task(prewarm_context(request.app, phrase, payload.accent))
    return {"status": "scheduled", "phrase": phrase[:200], "accent": payload.accent.upper()}


@router.post("/score")
async def score_recording(
    request: Request,
    audio: UploadFile,
    phrase: str = Form(...),
    accent: str = Form("GA"),
    l1: str = Form("unknown"),
):
    try:
        raw = await audio.read()
    except Exception as e:
        logger.error(f"Audio read failed: {e}")
        raise HTTPException(status_code=400, detail="Could not read audio file.")
    return await run_score(
        request.app,
        raw=raw,
        phrase=phrase,
        accent=accent,
        l1=l1,
    )


# Backwards-compat re-exports so callers that imported helpers from this
# module continue to work after the scoring/ package split.
from app.scoring.fusion import (
    ground_overall_score as _ground_overall_score,
    blend_learned_scores as _blend_learned_scores,
    classify_phrase_match as _classify_phrase_match,
)
from app.scoring.pitch_contour import build_pitch_contour as _build_pitch_contour
from app.scoring.vowel_quality import vowel_quality_score as _vowel_quality_score
from app.scoring.feedback import (
    build_feedback as _build_feedback,
    phonological_diagnostics as _phonological_diagnostics,
)
from app.scoring.pipeline import (
    _normalise_accent,
    _audio_digest,
    _result_cache_key,
    _transcribe_for_score,
    _transcribe_cached,
    _embed_cached,
    _timed_call,
    _RESULT_CACHE,
    _TRANSCRIPT_CACHE,
    _EMBEDDING_CACHE,
    _PREWARM_LOCK,
    _PREWARM_IN_FLIGHT,
    prewarm_context as _prewarm_context,
    PrewarmPayload,
)

__all__ = ["router", "warmup_score_stack"]
