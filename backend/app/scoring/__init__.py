"""Scoring pipeline package.

Splits the monolithic /api/score implementation into focused modules:

  * pitch_contour — F0 z-scoring + onset alignment for the frontend overlay
  * fusion        — score blending and gates
  * feedback      — phonology hint generation + lowest-dimension tips
  * vowel_quality — formant-based vowel-space comparison
  * pipeline      — async orchestrator that runs phoneme/prosody/whisper/wavlm

The HTTP router (``app.api.score``) is a thin wrapper around ``pipeline.run``.
"""

from app.scoring.pipeline import (
    PrewarmPayload,
    prewarm_context,
    run_score,
    warmup_score_stack,
)

__all__ = [
    "PrewarmPayload",
    "prewarm_context",
    "run_score",
    "warmup_score_stack",
]
