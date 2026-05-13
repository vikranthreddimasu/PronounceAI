"""Async orchestrator for /api/score.

Coordinates four engines (phoneme + prosody + whisper + wavlm-embed) over
the audio buffer, blends their outputs via ``fusion``, builds the response
payload, and manages the three score-path caches (result / transcript /
embedding) plus the prewarm bookkeeping.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import logging
import os
import threading
import time
from pathlib import Path

import numpy as np
from fastapi import HTTPException
from pydantic import BaseModel

from app.cache import LRUCache
from app.scoring.feedback import build_feedback, phonological_diagnostics
from app.scoring.fusion import (
    blend_learned_scores,
    classify_phrase_match,
    ground_overall_score,
)
from app.scoring.pitch_contour import build_pitch_contour
from app.scoring.vowel_quality import vowel_quality_score
from app.utils.audio import AudioError, preprocess
from app.utils.native_pitch import get_native_f0
from app.utils.text_metrics import phrase_match_metrics

logger = logging.getLogger(__name__)

SCORE_WORD_TIMESTAMPS = os.getenv("SCORE_WORD_TIMESTAMPS", "0") == "1"
SCORE_ASR_MODE = os.getenv("SCORE_ASR_MODE", "fast").lower()
SCORE_INCLUDE_FORMANTS = os.getenv("SCORE_INCLUDE_FORMANTS", "0") == "1"
SCORE_WAVLM_MODE = os.getenv("SCORE_WAVLM_MODE", "auto").lower()
SCORE_RESPONSE_CACHE = os.getenv("SCORE_RESPONSE_CACHE", "1") == "1"
SCORE_RESPONSE_CACHE_SIZE = int(os.getenv("SCORE_RESPONSE_CACHE_SIZE", "256"))
SCORE_TRANSCRIPT_CACHE_SIZE = int(os.getenv("SCORE_TRANSCRIPT_CACHE_SIZE", "256"))
SCORE_EMBEDDING_CACHE_SIZE = int(os.getenv("SCORE_EMBEDDING_CACHE_SIZE", "256"))


_RESULT_CACHE: LRUCache[str, dict] = LRUCache(SCORE_RESPONSE_CACHE_SIZE)
_TRANSCRIPT_CACHE: LRUCache[str, dict] = LRUCache(SCORE_TRANSCRIPT_CACHE_SIZE)
_EMBEDDING_CACHE: LRUCache[str, object] = LRUCache(SCORE_EMBEDDING_CACHE_SIZE)
_PREWARM_LOCK = threading.RLock()
_PREWARM_IN_FLIGHT: set[tuple[str, str]] = set()


# Scoring dimension weights for the deterministic overall score.
# Phonemes (GOP) drive the majority signal — the WavLM assessment head adds
# a second utterance-level opinion on top when its checkpoint is loaded.
# Vowel quality is intentionally low-weighted: formant extraction is noisy on
# short clips and the value is more useful as a visual diagnostic than as a
# heavy scoring input.
WEIGHT_PHONEME = 0.55
WEIGHT_INTONATION = 0.20
WEIGHT_STRESS_RHYTHM = 0.15
WEIGHT_VOWEL_QUALITY = 0.10


class PrewarmPayload(BaseModel):
    phrase: str
    accent: str = "GA"


_ACCEPTED_ACCENTS = ("GA", "RP", "AUE", "IRISH", "SCOTTISH", "INDIANE")


def _timed_call(fn, *args, **kwargs):
    start = time.perf_counter()
    result = fn(*args, **kwargs)
    return result, round((time.perf_counter() - start) * 1000)


def _normalise_accent(accent: str) -> str:
    accent = (accent or "GA").upper()
    return accent if accent in _ACCEPTED_ACCENTS else "GA"


def _audio_digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _checkpoint_signature(path_str: str) -> str:
    """Stat-based fingerprint of a checkpoint file. Empty when missing."""
    if not path_str:
        return ""
    p = Path(path_str)
    if not p.exists():
        return ""
    try:
        st = p.stat()
        return f"{p.name}:{st.st_size}:{int(st.st_mtime)}"
    except OSError:
        return ""


# Resolved at module import; if the operator swaps checkpoints, restart the
# process to pick up the new fingerprint.
_ASSESSMENT_CKPT_SIG = _checkpoint_signature(os.getenv("ASSESSMENT_SCORER_CHECKPOINT", ""))
_ACCENT_CENTROIDS_SIG = _checkpoint_signature(os.getenv("ACCENT_CENTROIDS_PATH", ""))


def _result_cache_key(audio_key: str, phrase: str, accent: str, l1: str) -> str:
    parts = [
        audio_key,
        " ".join(phrase.split()).lower(),
        accent,
        (l1 or "unknown").lower(),
        f"asr={SCORE_ASR_MODE}",
        f"words={int(SCORE_WORD_TIMESTAMPS)}",
        f"formants={int(SCORE_INCLUDE_FORMANTS)}",
        f"wavlm={SCORE_WAVLM_MODE}",
        f"ckpt={_ASSESSMENT_CKPT_SIG}",
        f"centroids={_ACCENT_CENTROIDS_SIG}",
    ]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def _transcribe_for_score(whisper, wav_np: np.ndarray) -> dict:
    if SCORE_ASR_MODE == "words" or SCORE_WORD_TIMESTAMPS:
        return whisper.transcribe(wav_np)
    return {
        "text": whisper.transcribe_fast(wav_np),
        "words": [],
        "language_probability": None,
    }


def _transcribe_cached(whisper, wav_np: np.ndarray, audio_key: str) -> dict:
    cache_key = f"{audio_key}:{SCORE_ASR_MODE}:{int(SCORE_WORD_TIMESTAMPS)}"
    cached = _TRANSCRIPT_CACHE.get(cache_key)
    if cached is not None:
        return copy.deepcopy(cached)
    transcript = _transcribe_for_score(whisper, wav_np)
    _TRANSCRIPT_CACHE.set(cache_key, copy.deepcopy(transcript))
    return transcript


def _embed_cached(accent_engine, wav_np: np.ndarray, audio_key: str):
    cached = _EMBEDDING_CACHE.get(audio_key)
    if cached is not None:
        return cached
    embedding = accent_engine.embed(wav_np)
    _EMBEDDING_CACHE.set(audio_key, embedding.detach())
    return embedding


async def prewarm_context(app, phrase: str, accent: str) -> None:
    phrase = " ".join((phrase or "").split())
    if not phrase:
        return
    accent = _normalise_accent(accent)
    key = (phrase[:200].lower(), accent)
    with _PREWARM_LOCK:
        if key in _PREWARM_IN_FLIGHT:
            return
        _PREWARM_IN_FLIGHT.add(key)
    try:
        phoneme_engine = getattr(app.state, "phoneme_engine", None)
        prosody_engine = getattr(app.state, "prosody_engine", None)
        tasks = []
        if phoneme_engine is not None and hasattr(phoneme_engine, "prepare_phrase"):
            tasks.append(asyncio.to_thread(phoneme_engine.prepare_phrase, phrase))
        if prosody_engine is not None:
            tasks.append(asyncio.to_thread(get_native_f0, phrase, accent, prosody_engine))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            logger.info("Prewarmed score context phrase=%r accent=%s", phrase, accent)
    finally:
        with _PREWARM_LOCK:
            _PREWARM_IN_FLIGHT.discard(key)


async def warmup_score_stack(app, phrases: list[str], accents: list[str]) -> None:
    """Aggressively warm demo-critical models/caches without external APIs."""
    phrase = phrases[0] if phrases else "Ship or sheep?"
    jobs = []
    phoneme_engine = getattr(app.state, "phoneme_engine", None)
    whisper = getattr(app.state, "whisper", None)
    accent_engine = getattr(app.state, "accent_engine", None)
    if phoneme_engine is not None and hasattr(phoneme_engine, "warmup"):
        jobs.append(asyncio.to_thread(phoneme_engine.warmup, phrase))
    if whisper is not None and hasattr(whisper, "warmup") and SCORE_ASR_MODE != "off":
        jobs.append(asyncio.to_thread(whisper.warmup))
    if accent_engine is not None and hasattr(accent_engine, "warmup") and SCORE_WAVLM_MODE != "off":
        jobs.append(asyncio.to_thread(accent_engine.warmup))
    for p in phrases:
        for a in accents:
            jobs.append(prewarm_context(app, p, a))
    if jobs:
        await asyncio.gather(*jobs, return_exceptions=True)
    logger.info("Score stack warmup completed (%d phrases, accents=%s)", len(phrases), accents)


async def run_score(
    app,
    *,
    raw: bytes,
    phrase: str,
    accent: str,
    l1: str,
) -> dict:
    t0 = time.perf_counter()
    accent = _normalise_accent(accent)

    try:
        audio_key = _audio_digest(raw)
        cache_key = _result_cache_key(audio_key, phrase, accent, l1)
        if SCORE_RESPONSE_CACHE:
            cached = _RESULT_CACHE.get(cache_key)
            if cached is not None:
                response = copy.deepcopy(cached)
                response.setdefault("debug", {})
                response["debug"]["cache_hit"] = True
                response["debug"]["cached_from_elapsed_ms"] = response["debug"].get("elapsed_ms")
                response["debug"]["elapsed_ms"] = round((time.perf_counter() - t0) * 1000)
                response["debug"]["stage_ms"] = {"score_cache": response["debug"]["elapsed_ms"]}
                return response
        wav, _sr = preprocess(raw)
    except AudioError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Audio load failed: {e}")
        raise HTTPException(status_code=400, detail="Could not read audio file.")

    wav_np = wav.squeeze(0).numpy()

    phoneme_engine = app.state.phoneme_engine
    prosody_engine = app.state.prosody_engine
    accent_engine = getattr(app.state, "accent_engine", None)
    whisper = app.state.whisper
    assessment_scorer = getattr(app.state, "assessment_scorer", None)
    stage_ms: dict[str, int] = {}

    has_target_centroid = (
        accent_engine is not None
        and hasattr(accent_engine, "has_centroid")
        and accent_engine.has_centroid(accent)
    )
    needs_wavlm = (
        SCORE_WAVLM_MODE != "off"
        and accent_engine is not None
        and (assessment_scorer is not None or has_target_centroid)
    )

    phoneme_task = asyncio.create_task(
        asyncio.to_thread(_timed_call, phoneme_engine.score, wav, phrase, True)
    )
    native_task = asyncio.create_task(
        asyncio.to_thread(_timed_call, get_native_f0, phrase, accent, prosody_engine)
    )
    whisper_task = (
        asyncio.create_task(asyncio.to_thread(_timed_call, _transcribe_cached, whisper, wav_np, audio_key))
        if SCORE_ASR_MODE != "off"
        else None
    )
    wavlm_task = (
        asyncio.create_task(asyncio.to_thread(_timed_call, _embed_cached, accent_engine, wav_np, audio_key))
        if needs_wavlm
        else None
    )

    try:
        phoneme_payload, stage_ms["phoneme"] = await phoneme_task
        phoneme_results, phoneme_diagnostics = phoneme_payload
    except Exception as e:
        logger.error(f"Phoneme engine failed: {e}")
        phoneme_results = []
        phoneme_diagnostics = {
            "expected_phone_count": 0,
            "predicted_phone_count": 0,
            "phone_error_rate": None,
            "ctc_sequence_score": None,
            "predicted_phones": [],
        }

    phoneme_accuracy_raw = phoneme_engine.accuracy_score(phoneme_results)
    phoneme_accuracy = phoneme_accuracy_raw

    try:
        (native_f0, native_dur_ms), stage_ms["native_f0"] = await native_task
    except Exception as e:
        logger.warning(f"Native F0 unavailable: {e}")
        native_f0 = np.zeros(0, dtype=np.float32)
        native_dur_ms = 0

    native_voiced = native_f0[native_f0 > 0] if len(native_f0) else None

    phoneme_dicts = [
        {
            "phoneme": r.phoneme,
            "expected": r.expected,
            "start_ms": r.start_ms,
            "end_ms": r.end_ms,
        }
        for r in phoneme_results
    ]
    prosody_task = asyncio.create_task(
        asyncio.to_thread(
            _timed_call,
            prosody_engine.analyze,
            wav_np,
            phoneme_dicts,
            reference_f0=native_voiced,
            include_formants=SCORE_INCLUDE_FORMANTS,
        )
    )
    try:
        prosody, stage_ms["prosody"] = await prosody_task
    except Exception as e:
        logger.error(f"Prosody engine failed: {e}")
        prosody = {
            "intonation": 70.0,
            "stress_rhythm": 70.0,
            "rate_score": 80.0,
            "npvi": 50.0,
            "f0_contour": [],
            "formants": {},
            "speech_rate_sps": 4.0,
        }

    user_f0_full = np.asarray(prosody.get("f0_contour", []), dtype=np.float32)
    user_duration_ms = int(round(len(wav_np) / 16000 * 1000))
    pitch_contour = build_pitch_contour(
        user_f0_full,
        native_f0,
        user_duration_ms=user_duration_ms,
        native_duration_ms=max(int(native_dur_ms), 1),
    )

    learned_scores = None
    accent_score = None
    try:
        embedding = None
        if wavlm_task is not None:
            embedding, stage_ms["wavlm_embedding"] = await wavlm_task
            accent_score = accent_engine.distance_score_from_embedding(embedding, accent)
        if assessment_scorer is not None and embedding is not None:
            learned_scores, stage_ms["learned_assessment"] = _timed_call(
                assessment_scorer.predict,
                embedding,
                wav_np,
            )
    except Exception as e:
        logger.warning(f"WavLM assessment/accent distance failed: {e}")
        accent_score = None

    if whisper_task is None:
        transcript = {"text": "", "words": [], "language_probability": 0.0}
        phrase_metrics = None
        wer = None
    else:
        try:
            transcript, stage_ms["whisper"] = await whisper_task
            phrase_metrics = phrase_match_metrics(transcript["text"], phrase)
            wer = phrase_metrics["wer"]
        except Exception as e:
            logger.warning(f"Whisper transcription failed: {e}")
            transcript = {"text": "", "words": [], "language_probability": 0.0}
            phrase_metrics = None
            wer = None

    scores = {
        "phoneme_accuracy": round(phoneme_accuracy, 1),
        "intonation": round(prosody.get("intonation", 70.0), 1),
        "stress_rhythm": round(prosody.get("stress_rhythm", 70.0), 1),
        "vowel_quality": vowel_quality_score(prosody.get("formants", {}), accent),
    }
    scores, learned_overall = blend_learned_scores(scores, learned_scores)
    deterministic_overall = round(
        scores["phoneme_accuracy"] * WEIGHT_PHONEME +
        scores["intonation"] * WEIGHT_INTONATION +
        scores["stress_rhythm"] * WEIGHT_STRESS_RHYTHM +
        scores["vowel_quality"] * WEIGHT_VOWEL_QUALITY,
        1,
    )
    if learned_overall is None:
        overall_raw = deterministic_overall
    else:
        overall_raw = round(deterministic_overall * 0.65 + learned_overall * 0.35, 1)

    overall, overall_gate = ground_overall_score(overall_raw, phrase_metrics)
    phrase_match_status = classify_phrase_match(phrase_metrics)
    gates = [overall_gate] if overall_gate is not None else []
    phonological_diag = phonological_diagnostics(phoneme_results)
    tips = build_feedback(phoneme_results, scores, phrase_metrics, gates)

    elapsed_ms = round((time.perf_counter() - t0) * 1000)
    logger.info(
        f"Score request completed in {elapsed_ms}ms — overall {overall} "
        f"(raw {overall_raw}) | whisper: '{transcript['text']}' | WER: {wer} | "
        f"stages={stage_ms}"
    )

    response = {
        "phonemes": [
            {
                "phoneme": r.phoneme,
                "expected": r.expected,
                "gop": r.gop,
                "correct": r.correct,
                "substitution": r.substitution,
                "start_ms": r.start_ms,
                "end_ms": r.end_ms,
            }
            for r in phoneme_results
        ],
        "scores": scores,
        "feedback": tips,
        "overall": overall,
        "pitch_contour": pitch_contour,
        "transcript": transcript,
        "wer": wer,
        "phrase_match_status": phrase_match_status,
        "debug": {
            "elapsed_ms": elapsed_ms,
            "stage_ms": stage_ms,
            "cache_hit": False,
            "latency_mode": {
                "asr": SCORE_ASR_MODE,
                "formants": SCORE_INCLUDE_FORMANTS,
                "wavlm": SCORE_WAVLM_MODE,
                "response_cache": SCORE_RESPONSE_CACHE,
            },
            "accent_score": accent_score,
            "phrase_match": phrase_metrics,
            "phoneme_alignment": phoneme_diagnostics,
            "learned_assessment": learned_scores,
            "score_gates": gates,
            "phonological_diagnostics": phonological_diag,
            "raw_overall": overall_raw,
            "raw_phoneme_accuracy": phoneme_accuracy_raw,
            "weights": {
                "phoneme_accuracy": WEIGHT_PHONEME,
                "intonation": WEIGHT_INTONATION,
                "stress_rhythm": WEIGHT_STRESS_RHYTHM,
                "vowel_quality": WEIGHT_VOWEL_QUALITY,
                "learned_overall_blend": 0.35,
            },
            "npvi": prosody.get("npvi"),
            "speech_rate_sps": prosody.get("speech_rate_sps"),
            "formants": prosody.get("formants"),
        },
    }
    if SCORE_RESPONSE_CACHE:
        _RESULT_CACHE.set(cache_key, copy.deepcopy(response))
    return response
