"""
Module 2 Loader — Acoustic pronunciation quality scorer.

Loads Random Forest + PronunciationNet saved by module_2 and provides:
  - Module2Scorer.score(audio_path)        -> float [0, 100]
  - predict_module2_score(audio_path)      -> float [0, 100]

Score is the average of RF P(good) and NN P(good), each in [0,1], scaled to 100.
No reference audio is needed — this measures intrinsic acoustic quality.
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Optional

import librosa
import numpy as np
import torch
import torch.nn as nn

warnings.filterwarnings("ignore")

# Path: utils/ -> combined_module/ -> model/ -> module_2/
_MODULE2_MODELS = (
    Path(__file__).resolve().parent.parent.parent
    / "module_2" / "models"
)


class PronunciationNet(nn.Module):
    """Exact architecture from module_2 — must match saved weights."""

    def __init__(self, input_dim: int) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, 128), nn.ReLU(), nn.Dropout(0.3),
            nn.Linear(128, 64),        nn.ReLU(), nn.Dropout(0.3),
            nn.Linear(64, 2),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class Module2Scorer:
    """
    Wraps Module 2 models (RF + NN) for acoustic quality scoring.
    Models are loaded once at instantiation.
    """

    def __init__(self, models_dir: Optional[str | Path] = None) -> None:
        self.models_dir = Path(models_dir) if models_dir else _MODULE2_MODELS
        if not self.models_dir.exists():
            raise FileNotFoundError(
                f"Module 2 models not found at:\n  {self.models_dir}\n"
                "Run notebook1_feature_extraction_training.ipynb in module_2/ first."
            )
        self._load_config()
        self._load_models()

    def _load_config(self) -> None:
        with open(self.models_dir / "feature_config.json") as f:
            cfg = json.load(f)
        self.n_mfcc      = cfg["n_mfcc"]       # 40
        self.input_dim   = cfg["input_dim"]     # 86
        self.sample_rate = cfg["sample_rate"]   # 16000

    def _load_models(self) -> None:
        import joblib
        self.rf_model = joblib.load(self.models_dir / "random_forest.joblib")
        self.scaler   = joblib.load(self.models_dir / "scaler.joblib")

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.nn_model = PronunciationNet(self.input_dim).to(self.device)
        self.nn_model.load_state_dict(
            torch.load(
                self.models_dir / "pronunciation_net.pt",
                map_location=self.device,
            )
        )
        self.nn_model.eval()

    def extract_features(self, y: np.ndarray) -> np.ndarray:
        """
        Extract the same 86-dim feature vector used during module_2 training.
        Must NOT be changed without retraining module_2.
        """
        mfcc      = librosa.feature.mfcc(y=y, sr=self.sample_rate, n_mfcc=self.n_mfcc)
        mfcc_mean = np.mean(mfcc, axis=1)
        mfcc_std  = np.std(mfcc,  axis=1)

        f0, voiced_flag, _ = librosa.pyin(
            y,
            fmin=librosa.note_to_hz("C2"),
            fmax=librosa.note_to_hz("C7"),
        )
        f0_voiced  = f0[voiced_flag] if voiced_flag is not None else np.array([])
        pitch_mean = float(np.mean(f0_voiced)) if len(f0_voiced) > 0 else 0.0
        pitch_std  = float(np.std(f0_voiced))  if len(f0_voiced) > 0 else 0.0

        rms      = librosa.feature.rms(y=y)[0]
        centroid = librosa.feature.spectral_centroid(y=y, sr=self.sample_rate)[0]

        return np.concatenate([
            mfcc_mean, mfcc_std,
            [pitch_mean, pitch_std,
             np.mean(rms), np.std(rms),
             np.mean(centroid), np.std(centroid)],
        ])

    def score_array(self, y: np.ndarray) -> float:
        """Score a pre-loaded audio array. Returns float in [0, 100]."""
        feats  = self.extract_features(y)
        scaled = self.scaler.transform([feats])   # scaler must match training

        rf_prob = float(self.rf_model.predict_proba(scaled)[0, 1])

        t = torch.tensor(scaled[0], dtype=torch.float32).unsqueeze(0).to(self.device)
        with torch.no_grad():
            nn_prob = float(torch.softmax(self.nn_model(t), dim=1)[0, 1])

        return (0.5 * rf_prob + 0.5 * nn_prob) * 100.0

    def score(self, audio_path: str) -> float:
        """Load audio from path and return acoustic quality score [0, 100]."""
        y, _ = librosa.load(audio_path, sr=self.sample_rate, mono=True)
        return self.score_array(y)


def predict_module2_score(
    audio_path: str,
    scorer: Optional[Module2Scorer] = None,
) -> float:
    """
    Convenience wrapper. Creates Module2Scorer on first call if not provided.
    Returns float in [0, 100].
    """
    if scorer is None:
        scorer = Module2Scorer()
    return scorer.score(audio_path)
