"""
POST /api/score

Accepts: multipart form with audio (Blob), phrase (str), accent (str), l1 (str?)
Returns: AssessmentResult JSON matching the frontend's types.ts schema
"""
import logging
import asyncio
import copy
import hashlib
import os
import threading
import time
from collections import OrderedDict

import numpy as np
from fastapi import APIRouter, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from app.models.phonology import diagnose_substitution
from app.utils.audio import AudioError, preprocess
from app.utils.native_pitch import get_native_f0
from app.utils.text_metrics import phrase_match_metrics

logger = logging.getLogger(__name__)
router = APIRouter()

PITCH_CONTOUR_FRAMES = 80   # downsample target for the frontend overlay
SCORE_WORD_TIMESTAMPS = os.getenv("SCORE_WORD_TIMESTAMPS", "0") == "1"
SCORE_ASR_MODE = os.getenv("SCORE_ASR_MODE", "fast").lower()       # off | fast | words
SCORE_INCLUDE_FORMANTS = os.getenv("SCORE_INCLUDE_FORMANTS", "0") == "1"
SCORE_WAVLM_MODE = os.getenv("SCORE_WAVLM_MODE", "auto").lower()   # auto | off
SCORE_RESPONSE_CACHE = os.getenv("SCORE_RESPONSE_CACHE", "1") == "1"
SCORE_RESPONSE_CACHE_SIZE = int(os.getenv("SCORE_RESPONSE_CACHE_SIZE", "256"))
SCORE_TRANSCRIPT_CACHE_SIZE = int(os.getenv("SCORE_TRANSCRIPT_CACHE_SIZE", "256"))
SCORE_EMBEDDING_CACHE_SIZE = int(os.getenv("SCORE_EMBEDDING_CACHE_SIZE", "256"))


class _LRUCache:
    def __init__(self, max_size: int):
        self.max_size = max(0, max_size)
        self._items: OrderedDict[str, object] = OrderedDict()
        self._lock = threading.RLock()

    def get(self, key: str):
        if self.max_size <= 0:
            return None
        with self._lock:
            value = self._items.get(key)
            if value is None:
                return None
            self._items.move_to_end(key)
            return value

    def set(self, key: str, value) -> None:
        if self.max_size <= 0:
            return
        with self._lock:
            self._items[key] = value
            self._items.move_to_end(key)
            while len(self._items) > self.max_size:
                self._items.popitem(last=False)


_RESULT_CACHE = _LRUCache(SCORE_RESPONSE_CACHE_SIZE)
_TRANSCRIPT_CACHE = _LRUCache(SCORE_TRANSCRIPT_CACHE_SIZE)
_EMBEDDING_CACHE = _LRUCache(SCORE_EMBEDDING_CACHE_SIZE)
_PREWARM_LOCK = threading.RLock()
_PREWARM_IN_FLIGHT: set[tuple[str, str]] = set()


class PrewarmPayload(BaseModel):
    phrase: str
    accent: str = "GA"


def _resample_f0(f0: np.ndarray, n_out: int) -> np.ndarray:
    """Linear resample of an F0 contour to a fixed length. Unvoiced=0 preserved."""
    if len(f0) == 0:
        return np.zeros(n_out, dtype=np.float32)
    src_idx = np.linspace(0, len(f0) - 1, n_out)
    return np.interp(src_idx, np.arange(len(f0)), f0).astype(np.float32)


def _zscore_voiced(arr: np.ndarray) -> np.ndarray:
    """Z-score using only voiced (>0) frames; unvoiced kept as 0 sentinel."""
    voiced = arr[arr > 0]
    if len(voiced) < 2:
        return arr - arr.mean()
    mean = voiced.mean()
    std = voiced.std()
    if std <= 1e-6:
        return arr - mean
    out = (arr - mean) / std
    # Re-mark unvoiced as 0 sentinel (will become None in JSON)
    out[arr <= 0] = 0.0
    return out


def _contour_to_json(arr: np.ndarray) -> list[float | None]:
    """0.0 sentinel → None so the SVG path breaks on unvoiced frames."""
    return [None if v == 0.0 else round(float(v), 3) for v in arr]


def _build_pitch_contour(
    user_f0: np.ndarray, native_f0: np.ndarray, duration_ms: int
) -> dict:
    """Returns the frontend's PitchContour shape — z-scored, equal length, null-unvoiced."""
    user_r = _resample_f0(user_f0, PITCH_CONTOUR_FRAMES)
    native_r = _resample_f0(native_f0, PITCH_CONTOUR_FRAMES)
    return {
        "user": _contour_to_json(_zscore_voiced(user_r)),
        "native": _contour_to_json(_zscore_voiced(native_r)),
        "duration_ms": int(duration_ms),
    }


def _timed_call(fn, *args, **kwargs):
    start = time.perf_counter()
    result = fn(*args, **kwargs)
    return result, round((time.perf_counter() - start) * 1000)


def _normalise_accent(accent: str) -> str:
    accent = (accent or "GA").upper()
    return accent if accent in ("GA", "RP", "AUE", "IRISH", "SCOTTISH", "INDIANE") else "GA"


def _audio_digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


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


def _ctc_grounded_phoneme_score(score: float, diagnostics: dict) -> tuple[float, dict | None]:
    seq_score = diagnostics.get("ctc_sequence_score")
    per = diagnostics.get("phone_error_rate")
    if seq_score is None or per is None:
        return score, None

    adjusted = score
    reason = None
    if per >= 0.65:
        adjusted = min(adjusted, 60.0)
        reason = "ctc_phone_sequence_mismatch"
    elif per >= 0.45:
        adjusted = min(adjusted, 75.0)
        reason = "ctc_phone_sequence_weak"

    gate = None
    if adjusted != score:
        gate = {
            "type": reason,
            "raw": round(score, 1),
            "adjusted": round(adjusted, 1),
            "phone_error_rate": per,
            "ctc_sequence_score": seq_score,
        }
    return round(adjusted, 1), gate


def _ground_overall_score(overall: float, phrase_metrics: dict | None) -> tuple[float, dict | None]:
    if not phrase_metrics:
        return overall, None

    match = phrase_metrics["phrase_match"]
    adjusted = overall
    reason = None
    if match < 45:
        adjusted = min(adjusted, 55.0)
        reason = "phrase_mismatch"
    elif match < 65:
        adjusted = min(adjusted, 70.0)
        reason = "phrase_match_weak"
    elif match < 78:
        adjusted = min(adjusted, 85.0)
        reason = "phrase_match_partial"

    gate = None
    if adjusted != overall:
        gate = {
            "type": reason,
            "raw": round(overall, 1),
            "adjusted": round(adjusted, 1),
            **phrase_metrics,
        }
    return round(adjusted, 1), gate


def _blend_learned_scores(scores: dict, learned: dict | None) -> tuple[dict, float | None]:
    """
    Blend optional learned APA predictions with deterministic acoustic scores.

    The learned head captures global speech quality cues from WavLM embeddings;
    the deterministic scorer keeps local interpretability. A conservative blend
    improves model quality when a validated checkpoint is installed without
    making the product opaque.
    """
    if not learned:
        return scores, None

    blended = dict(scores)
    mapping = {
        "accuracy": "phoneme_accuracy",
        "prosody": "intonation",
        "fluency": "stress_rhythm",
    }
    for learned_key, score_key in mapping.items():
        if learned_key in learned and score_key in blended:
            blended[score_key] = round(blended[score_key] * 0.60 + learned[learned_key] * 0.40, 1)

    learned_overall = learned.get("overall")
    return blended, learned_overall


def _build_feedback(
    phoneme_results: list,
    scores: dict,
    phrase_metrics: dict | None,
    gates: list[dict],
) -> list[dict]:
    tips: list[dict] = []
    if phrase_metrics and phrase_metrics["phrase_match"] < 65:
        tips.append({
            "text": "Repeat the assigned words first; the scorer detected a phrase mismatch.",
        })

    weak = sorted(
        [r for r in phoneme_results if not r.correct],
        key=lambda r: r.gop,
    )
    if weak:
        worst = weak[0]
        diagnosis = diagnose_substitution(worst.phoneme, worst.expected)
        if diagnosis is not None:
            tips.append({
                "text": (
                    f"Your /{worst.expected}/ is drifting toward /{worst.phoneme}/; "
                    f"{diagnosis['hint']}."
                ),
                "timestamp_ms": worst.start_ms,
            })
        else:
            tips.append({
                "text": f"Focus on /{worst.expected}/; your closest detected sound was /{worst.phoneme}/.",
                "timestamp_ms": worst.start_ms,
            })

    lowest_dim = min(scores.items(), key=lambda kv: kv[1])
    if lowest_dim[1] < 70:
        labels = {
            "phoneme_accuracy": "sound accuracy",
            "intonation": "pitch movement",
            "stress_rhythm": "stress and rhythm",
            "vowel_quality": "vowel placement",
        }
        tips.append({"text": f"Next pass: prioritize {labels.get(lowest_dim[0], lowest_dim[0])}."})

    if not tips and gates:
        tips.append({"text": "The main score was adjusted because transcript evidence was uncertain."})

    return tips[:3]


def _phonological_diagnostics(phoneme_results: list) -> list[dict]:
    diagnostics = []
    for r in phoneme_results:
        diagnosis = diagnose_substitution(r.phoneme, r.expected)
        if diagnosis is None:
            continue
        diagnostics.append({
            **diagnosis,
            "start_ms": r.start_ms,
            "end_ms": r.end_ms,
            "gop": r.gop,
        })
    diagnostics.sort(key=lambda d: d["gop"])
    return diagnostics[:8]


async def _prewarm_context(app, phrase: str, accent: str) -> None:
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
    """Aggressively warms demo-critical models/caches without external APIs."""
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
            jobs.append(_prewarm_context(app, p, a))
    if jobs:
        await asyncio.gather(*jobs, return_exceptions=True)
    logger.info("Score stack warmup completed (%d phrases, accents=%s)", len(phrases), accents)


@router.post("/prewarm")
async def prewarm_score_context(request: Request, payload: PrewarmPayload):
    phrase = " ".join(payload.phrase.split())
    if not phrase:
        return {"status": "ignored"}
    accent = _normalise_accent(payload.accent)
    asyncio.create_task(_prewarm_context(request.app, phrase, accent))
    return {"status": "scheduled", "phrase": phrase[:200], "accent": accent}


@router.post("/score")
async def score_recording(
    request: Request,
    audio: UploadFile,
    phrase: str = Form(...),
    accent: str = Form("GA"),
    l1: str = Form("unknown"),
):
    t0 = time.perf_counter()

    # Validate accent
    accent = _normalise_accent(accent)

    # Load + preprocess audio
    try:
        raw = await audio.read()
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
        wav, sr = preprocess(raw)
    except AudioError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Audio load failed: {e}")
        raise HTTPException(status_code=400, detail="Could not read audio file.")

    wav_np = wav.squeeze(0).numpy()  # [T] float32

    # Pull engines from app state (loaded at startup)
    phoneme_engine = request.app.state.phoneme_engine
    prosody_engine = request.app.state.prosody_engine
    accent_engine = getattr(request.app.state, "accent_engine", None)
    whisper = request.app.state.whisper
    assessment_scorer = getattr(request.app.state, "assessment_scorer", None)
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

    # Start independent work together: MPS phoneme scoring, CPU ASR, native
    # reference retrieval, and optional WavLM embedding. For demo latency, ASR
    # can be removed from the critical path via SCORE_ASR_MODE=off while CTC
    # phoneme diagnostics still guard against obvious phrase drift.
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

    # Layer 2 — Phoneme scoring + alignment-independent CTC cross-check
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
    phoneme_accuracy, phoneme_gate = _ctc_grounded_phoneme_score(
        phoneme_accuracy_raw,
        phoneme_diagnostics,
    )

    # Native F0 reference (cached) — drives DTW intonation + frontend contour overlay
    try:
        (native_f0, native_dur_ms), stage_ms["native_f0"] = await native_task
    except Exception as e:
        logger.warning(f"Native F0 unavailable: {e}")
        native_f0 = np.zeros(0, dtype=np.float32)
        native_dur_ms = 0

    native_voiced = native_f0[native_f0 > 0] if len(native_f0) else None

    # Layer 3 — Prosody (with native reference for DTW intonation)
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

    # Build the pitch_contour field the frontend expects — z-scored, fixed length.
    user_f0_full = np.asarray(prosody.get("f0_contour", []), dtype=np.float32)
    user_duration_ms = int(round(len(wav_np) / 16000 * 1000))
    pitch_contour = _build_pitch_contour(
        user_f0_full,
        native_f0,
        duration_ms=max(user_duration_ms, native_dur_ms),
    )

    # Layer 4 — Accent distance
    learned_scores = None
    try:
        accent_score = None
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

    # Whisper transcript cross-check. This is used as a grounding gate, not as
    # generated feedback, so text-only greedy decoding is the default fast path.
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

    # Compute overall weighted score
    scores = {
        "phoneme_accuracy": round(phoneme_accuracy, 1),
        "intonation": round(prosody.get("intonation", 70.0), 1),
        "stress_rhythm": round(prosody.get("stress_rhythm", 70.0), 1),
        "vowel_quality": _vowel_quality_score(prosody.get("formants", {}), accent),
    }
    scores, learned_overall = _blend_learned_scores(scores, learned_scores)
    deterministic_overall = round(
        scores["phoneme_accuracy"] * 0.35 +
        scores["intonation"] * 0.20 +
        scores["stress_rhythm"] * 0.15 +
        scores["vowel_quality"] * 0.30,
        1,
    )
    if learned_overall is None:
        overall_raw = deterministic_overall
    else:
        overall_raw = round(deterministic_overall * 0.65 + learned_overall * 0.35, 1)

    overall, overall_gate = _ground_overall_score(overall_raw, phrase_metrics)
    gates = [g for g in (phoneme_gate, overall_gate) if g is not None]
    phonological_diagnostics = _phonological_diagnostics(phoneme_results)
    tips = _build_feedback(phoneme_results, scores, phrase_metrics, gates)

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
            "phonological_diagnostics": phonological_diagnostics,
            "raw_overall": overall_raw,
            "raw_phoneme_accuracy": phoneme_accuracy_raw,
            "npvi": prosody.get("npvi"),
            "speech_rate_sps": prosody.get("speech_rate_sps"),
            "formants": prosody.get("formants"),
        },
    }
    if SCORE_RESPONSE_CACHE:
        _RESULT_CACHE.set(cache_key, copy.deepcopy(response))
    return response


def _vowel_quality_score(formants: dict, accent: str) -> float:
    """
    Compare learner's vowel F1/F2 positions to target accent norms.
    Returns 0-100. Falls back to 70 if no formant data.
    """
    # GA vowel space norms (Peterson & Barney 1952 / Hillenbrand 1995, male avg)
    GA_NORMS = {
        "IY": (437, 2761), "IH": (483, 2365), "EY": (536, 2530),
        "EH": (611, 1952), "AE": (669, 1843), "AH": (753, 1426),
        "AA": (936, 1551), "AO": (781, 1136), "OW": (555, 1035),
        "UH": (469, 1122), "UW": (459, 1105), "ER": (474, 1379),
    }
    RP_NORMS = {
        "IY": (280, 2620), "IH": (390, 2090), "EY": (450, 2360),
        "EH": (580, 1950), "AE": (720, 1730), "AH": (710, 1220),
        "AA": (700, 1220), "AO": (600, 920),  "OW": (450, 900),
        "UH": (430, 1020), "UW": (310, 940),  "ER": (490, 1350),
    }
    norms = RP_NORMS if accent == "RP" else GA_NORMS

    if not formants:
        return 70.0

    distances = []
    for vowel, fvals in formants.items():
        if vowel in norms:
            target_f1, target_f2 = norms[vowel]
            dist = np.sqrt((fvals["f1"] - target_f1) ** 2 + (fvals["f2"] - target_f2) ** 2)
            # Max expected deviation ~500 Hz — scale to 0-100
            score = max(0.0, 100 - dist / 5)
            distances.append(score)

    if not distances:
        return 70.0
    return round(np.mean(distances), 1)
