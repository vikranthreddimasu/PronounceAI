"""
PronounceAI — FastAPI Backend

Exposes a single POST /predict endpoint that accepts an audio file upload
and a reference text string, then returns scores from both modules plus
a weighted final score and human-readable feedback.

Start the server:
    # From PronounceAI/model/
    uvicorn combined_module.api.app:app --reload --port 8000

    # Or from this directory directly:
    uvicorn app:app --reload --port 8000
"""
from __future__ import annotations

import os
import sys
import tempfile
import traceback
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

# Ensure `combined_module` is importable regardless of working directory
_MODEL_DIR = Path(__file__).resolve().parent.parent.parent   # .../model/
if str(_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(_MODEL_DIR))

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from combined_module.utils.load_module1 import Module1Scorer
from combined_module.utils.load_module2 import Module2Scorer
from combined_module.utils.scoring import (
    CombinedScorer,
    compute_final_score,
    generate_feedback,
)
from combined_module.api.schemas import HealthResponse, PredictResponse

# ── Global model singletons ────────────────────────────────────────────────
_m1:       Optional[Module1Scorer]  = None
_m2:       Optional[Module2Scorer]  = None
_combined: Optional[CombinedScorer] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load all models at startup; release at shutdown."""
    global _m1, _m2, _combined

    print("⟳  Loading Module 1 (Whisper ASR) — this may take 20–30 s on CPU...")
    try:
        _m1 = Module1Scorer()
        print("✓  Module 1 loaded.")
    except FileNotFoundError as exc:
        print(f"⚠  Module 1 unavailable: {exc}")

    print("⟳  Loading Module 2 (Acoustic models)...")
    try:
        _m2 = Module2Scorer()
        print("✓  Module 2 loaded.")
    except FileNotFoundError as exc:
        print(f"⚠  Module 2 unavailable: {exc}")

    _combined = CombinedScorer()
    if _combined.is_available:
        print("✓  Combined meta-model loaded.")
    else:
        print("ℹ  Combined meta-model not found — run notebooks 1 & 2 to generate it.")

    yield   # server is running


# ── App ────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="PronounceAI API",
    description=(
        "Pronunciation assessment backend.\n\n"
        "Combines Whisper ASR (Module 1) and acoustic quality analysis "
        "(Module 2) into a single scored response."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # restrict to specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_ALLOWED_EXTENSIONS = {".wav", ".flac", ".mp3", ".ogg", ".m4a"}


# ── Endpoints ──────────────────────────────────────────────────────────────

@app.get("/", response_model=HealthResponse, tags=["Health"])
async def health_check() -> HealthResponse:
    """Returns the loaded state of all model components."""
    return HealthResponse(
        status="ok",
        module1_loaded=_m1 is not None,
        module2_loaded=_m2 is not None,
        combined_model_available=(_combined is not None and _combined.is_available),
    )


@app.post("/predict", response_model=PredictResponse, tags=["Scoring"])
async def predict(
    audio: UploadFile = File(..., description="Audio file (.wav, .flac, .mp3, .ogg, .m4a)"),
    reference_text: str = Form(..., description="The sentence the user was supposed to say"),
    w1: float = Form(0.5, description="Weight for Module 1 score (default 0.5)"),
    w2: float = Form(0.5, description="Weight for Module 2 score (default 0.5)"),
) -> PredictResponse:
    """
    Assess the pronunciation of an uploaded audio file against a reference sentence.

    - **module1_score** — word accuracy (Whisper transcript vs reference text)
    - **module2_score** — acoustic quality (RF + NN from Module 2)
    - **final_combined_score** — weighted average of the two scores
    - **combined_model_score** — trained meta-model prediction (null until trained)
    - **feedback** — one-line human-readable assessment
    - **transcript** — raw Whisper output
    """
    # Validate module availability
    if _m1 is None:
        raise HTTPException(503, detail="Module 1 (Whisper) not loaded. Check server logs.")
    if _m2 is None:
        raise HTTPException(503, detail="Module 2 (acoustic models) not loaded. Check server logs.")
    if not reference_text.strip():
        raise HTTPException(422, detail="reference_text must not be empty.")

    # Validate file extension
    suffix = Path(audio.filename or "audio.wav").suffix.lower()
    if suffix not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            415,
            detail=f"Unsupported audio format '{suffix}'. "
                   f"Allowed: {sorted(_ALLOWED_EXTENSIONS)}",
        )

    # Save upload to a temporary file, process, then clean up
    tmp_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(await audio.read())
            tmp_path = tmp.name

        transcript    = _m1.transcribe(tmp_path)
        from combined_module.utils.load_module1 import _word_f1
        module1_score = _word_f1(transcript, reference_text.strip()) * 100.0
        module2_score = _m2.score(tmp_path)
        final_score   = compute_final_score(module1_score, module2_score, w1, w2)
        feedback      = generate_feedback(module1_score, module2_score, final_score)

        combined_score: Optional[float] = None
        if _combined and _combined.is_available:
            try:
                combined_score = round(_combined.predict(module1_score, module2_score), 2)
            except Exception:
                pass

    except HTTPException:
        raise
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(500, detail=f"Scoring failed: {exc}") from exc
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

    return PredictResponse(
        module1_score        = round(module1_score, 2),
        module2_score        = round(module2_score, 2),
        final_combined_score = round(final_score, 2),
        combined_model_score = combined_score,
        feedback             = feedback,
        transcript           = transcript,
    )
