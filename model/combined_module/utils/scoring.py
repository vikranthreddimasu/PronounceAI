"""
Combined scoring utilities.

Provides:
  - compute_final_score  : weighted combination of module scores
  - generate_feedback    : rule-based human-readable feedback
  - CombinedScorer       : loads trained combined RF model for meta-prediction
  - predict_final_score  : convenience end-to-end function
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from .load_module1 import Module1Scorer
    from .load_module2 import Module2Scorer

_COMBINED_MODELS = Path(__file__).resolve().parent.parent / "models"


def compute_final_score(
    module1_score: float,
    module2_score: float,
    w1: float = 0.5,
    w2: float = 0.5,
) -> float:
    """
    Weighted combination: final = w1 * module1 + w2 * module2.
    w1 + w2 should sum to 1.0 but is not enforced.
    Returns float in [0, 100].
    """
    return float(w1 * module1_score + w2 * module2_score)


def generate_feedback(
    module1_score: float,
    module2_score: float,
    final_score: float,
) -> str:
    """
    Rule-based feedback string. Checks correctness (module1) first,
    then acoustic quality (module2), then overall score.
    """
    if module1_score < 50:
        return "Words do not match the expected sentence."
    if module2_score < 50:
        return "Pronunciation/acoustic quality needs improvement."
    if final_score >= 80:
        return "Good pronunciation."
    if final_score >= 60:
        return "Pronunciation is mostly correct with minor issues."
    return "Pronunciation needs improvement in both accuracy and quality."


class CombinedScorer:
    """
    Loads the combined Random Forest trained in notebook2 and predicts
    a pronunciation quality score from [module1_score, module2_score].
    Gracefully handles missing model files — check is_available before use.
    """

    def __init__(self, models_dir: Optional[str | Path] = None) -> None:
        self.models_dir = Path(models_dir) if models_dir else _COMBINED_MODELS
        self._rf      = None
        self._scaler  = None
        self._loaded  = False
        self._try_load()

    def _try_load(self) -> None:
        rf_path     = self.models_dir / "combined_rf.joblib"
        scaler_path = self.models_dir / "combined_scaler.joblib"
        if not (rf_path.exists() and scaler_path.exists()):
            return
        import joblib
        self._rf     = joblib.load(rf_path)
        self._scaler = joblib.load(scaler_path)
        self._loaded = True

    @property
    def is_available(self) -> bool:
        return self._loaded

    def predict(self, module1_score: float, module2_score: float) -> float:
        """
        Predict pronunciation quality using the trained combined model.
        Returns P(good) * 100 in [0, 100].
        Raises RuntimeError if model files are not found.
        """
        if not self._loaded:
            raise RuntimeError(
                f"Combined model not found in {self.models_dir}.\n"
                "Run notebook2_combined_model_training.ipynb first."
            )
        feat   = np.array([[module1_score, module2_score]], dtype=np.float32)
        scaled = self._scaler.transform(feat)
        prob   = float(self._rf.predict_proba(scaled)[0, 1])
        return prob * 100.0


def predict_final_score(
    audio_path: str,
    reference_text: str,
    w1: float = 0.5,
    w2: float = 0.5,
    m1_scorer: Optional[Module1Scorer] = None,
    m2_scorer: Optional[Module2Scorer] = None,
    combined_scorer: Optional[CombinedScorer] = None,
) -> dict:
    """
    Full end-to-end pipeline: transcribe → acoustic score → combine → feedback.

    Returns dict with keys:
      module1_score, module2_score, weighted_final_score,
      combined_model_score, feedback, transcript
    """
    from .load_module1 import Module1Scorer
    from .load_module2 import Module2Scorer

    if m1_scorer is None:
        m1_scorer = Module1Scorer()
    if m2_scorer is None:
        m2_scorer = Module2Scorer()
    if combined_scorer is None:
        combined_scorer = CombinedScorer()

    transcript    = m1_scorer.transcribe(audio_path)
    module1_score = 0.0
    from .load_module1 import _word_f1
    module1_score = _word_f1(transcript, reference_text.strip()) * 100.0

    module2_score  = m2_scorer.score(audio_path)
    final_score    = compute_final_score(module1_score, module2_score, w1, w2)
    feedback       = generate_feedback(module1_score, module2_score, final_score)

    combined_model_score: Optional[float] = None
    if combined_scorer.is_available:
        try:
            combined_model_score = round(combined_scorer.predict(module1_score, module2_score), 2)
        except Exception:
            combined_model_score = None

    return {
        "module1_score":         round(module1_score, 2),
        "module2_score":         round(module2_score, 2),
        "weighted_final_score":  round(final_score, 2),
        "combined_model_score":  combined_model_score,
        "feedback":              feedback,
        "transcript":            transcript,
    }
