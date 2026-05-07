"""Pydantic request/response schemas for the PronounceAI API."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class PredictResponse(BaseModel):
    module1_score: float = Field(
        ..., ge=0, le=100,
        description="Transcription accuracy vs. reference text (0–100). "
                    "Word-level F1 between Whisper output and reference.",
    )
    module2_score: float = Field(
        ..., ge=0, le=100,
        description="Acoustic pronunciation quality from Module 2 models (0–100). "
                    "Average of RF and NN P(good) probabilities.",
    )
    final_combined_score: float = Field(
        ..., ge=0, le=100,
        description="Weighted combination: w1×module1 + w2×module2 (0–100).",
    )
    combined_model_score: Optional[float] = Field(
        None, ge=0, le=100,
        description="Score from the trained combined RF meta-model (null if not yet trained).",
    )
    feedback: str = Field(..., description="Human-readable pronunciation feedback.")
    transcript: Optional[str] = Field(
        None, description="Raw Whisper transcript of the uploaded audio."
    )


class HealthResponse(BaseModel):
    status: str
    module1_loaded: bool
    module2_loaded: bool
    combined_model_available: bool
