"""
POST /api/score

Accepts: multipart form with audio (Blob), phrase (str), accent (str), l1 (str?)
Returns: AssessmentResult JSON matching the frontend's types.ts schema
"""
import logging
import time

import numpy as np
from fastapi import APIRouter, Form, HTTPException, Request, UploadFile

from app.utils.audio import AudioError, preprocess

logger = logging.getLogger(__name__)
router = APIRouter()


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
    accent = accent.upper()
    if accent not in ("GA", "RP", "AUE", "IRISH", "SCOTTISH", "INDIANE"):
        accent = "GA"

    # Load + preprocess audio
    try:
        raw = await audio.read()
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
    accent_engine = request.app.state.accent_engine
    feedback_gen = request.app.state.feedback_gen
    whisper = request.app.state.whisper

    # Layer 2 — Phoneme scoring
    try:
        phoneme_results = phoneme_engine.score(wav, phrase)
    except Exception as e:
        logger.error(f"Phoneme engine failed: {e}")
        phoneme_results = []

    phoneme_accuracy = phoneme_engine.accuracy_score(phoneme_results)

    # Layer 3 — Prosody
    phoneme_dicts = [
        {
            "phoneme": r.phoneme,
            "expected": r.expected,
            "start_ms": r.start_ms,
            "end_ms": r.end_ms,
        }
        for r in phoneme_results
    ]
    try:
        prosody = prosody_engine.analyze(wav_np, phoneme_dicts)
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

    # Layer 4 — Accent distance
    try:
        accent_score = accent_engine.distance_score(wav_np, accent)
    except Exception as e:
        logger.warning(f"Accent distance failed: {e}")
        accent_score = None

    # Compute overall weighted score
    scores = {
        "phoneme_accuracy": round(phoneme_accuracy, 1),
        "intonation": round(prosody.get("intonation", 70.0), 1),
        "stress_rhythm": round(prosody.get("stress_rhythm", 70.0), 1),
        "vowel_quality": _vowel_quality_score(prosody.get("formants", {}), accent),
    }
    overall = round(
        scores["phoneme_accuracy"] * 0.35 +
        scores["intonation"] * 0.20 +
        scores["stress_rhythm"] * 0.15 +
        scores["vowel_quality"] * 0.30,
        1,
    )

    # Layer 5 — Feedback
    errors = [r for r in phoneme_results if not r.correct]
    errors_sorted = sorted(errors, key=lambda r: r.gop)[:6]
    error_dicts = [
        {
            "phoneme": r.phoneme,
            "expected": r.expected,
            "gop": r.gop,
            "substitution": r.substitution,
            "start_ms": r.start_ms,
        }
        for r in errors_sorted
    ]
    prosody_issues = {
        "intonation": scores["intonation"],
        "stress_rhythm": scores["stress_rhythm"],
        "vowel_quality": scores["vowel_quality"],
    }
    try:
        tips = await feedback_gen.generate(error_dicts, prosody_issues, accent, l1)
    except Exception as e:
        logger.error(f"Feedback generation failed: {e}")
        tips = []

    # Whisper transcription cross-check (non-blocking — runs after scoring)
    try:
        transcript = whisper.transcribe(wav_np)
        wer = whisper.word_error_rate(transcript["text"], phrase)
    except Exception as e:
        logger.warning(f"Whisper transcription failed: {e}")
        transcript = {"text": "", "words": [], "language_probability": 0.0}
        wer = None

    elapsed_ms = round((time.perf_counter() - t0) * 1000)
    logger.info(f"Score request completed in {elapsed_ms}ms — overall {overall} | whisper: '{transcript['text']}' | WER: {wer}")

    return {
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
        "transcript": transcript,
        "wer": wer,
        "debug": {
            "elapsed_ms": elapsed_ms,
            "accent_score": accent_score,
            "npvi": prosody.get("npvi"),
            "speech_rate_sps": prosody.get("speech_rate_sps"),
            "formants": prosody.get("formants"),
            "f0_contour": prosody.get("f0_contour", [])[:100],
        },
    }


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
