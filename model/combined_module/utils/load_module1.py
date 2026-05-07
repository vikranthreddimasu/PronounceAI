"""
Module 1 Loader — Whisper ASR scorer.

Loads the fine-tuned Whisper model saved by module_1 and provides:
  - Module1Scorer.transcribe(audio_path)        -> str
  - Module1Scorer.score(audio_path, ref_text)   -> float [0, 100]
  - predict_module1_score(audio_path, ref_text) -> float [0, 100]

Score is word-level F1 between the Whisper transcript and the reference text.
A score of 100 means every word in the reference was correctly spoken.
"""
from __future__ import annotations

import warnings
from pathlib import Path
from typing import Optional

import numpy as np
import torch

warnings.filterwarnings("ignore")

# Path: utils/ -> combined_module/ -> model/ -> module_1/
_MODULE1_WEIGHTS = (
    Path(__file__).resolve().parent.parent.parent
    / "module_1" / "weights" / "whisper-base-librispeech"
)


def _word_f1(pred: str, ref: str) -> float:
    """Word-level F1 similarity between two strings. Returns [0, 1]."""
    p_words = set(pred.lower().split())
    r_words = set(ref.lower().split())
    if not r_words:
        return 1.0
    overlap = len(p_words & r_words)
    prec = overlap / len(p_words) if p_words else 0.0
    rec  = overlap / len(r_words)
    if prec + rec == 0.0:
        return 0.0
    return 2.0 * prec * rec / (prec + rec)


class Module1Scorer:
    """
    Wraps the fine-tuned Whisper model for transcription and scoring.
    Models are loaded once at instantiation.
    """

    def __init__(self, weights_dir: Optional[str | Path] = None) -> None:
        self.weights_dir = Path(weights_dir) if weights_dir else _MODULE1_WEIGHTS
        if not self.weights_dir.exists():
            raise FileNotFoundError(
                f"Module 1 weights not found at:\n  {self.weights_dir}\n"
                "Run notebook1_train_test_save.ipynb in module_1/ first."
            )
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self._load()

    def _load(self) -> None:
        from transformers import WhisperProcessor, WhisperForConditionalGeneration
        self.processor = WhisperProcessor.from_pretrained(str(self.weights_dir))
        self.model = (
            WhisperForConditionalGeneration
            .from_pretrained(str(self.weights_dir))
            .to(self.device)
        )
        self.model.eval()

    def transcribe(self, audio_path: str, sr: int = 16_000) -> str:
        """Transcribe an audio file. Returns lowercase string."""
        import librosa
        y, _ = librosa.load(audio_path, sr=sr, mono=True)
        return self._transcribe_array(y, sr)

    def _transcribe_array(self, y: np.ndarray, sr: int = 16_000) -> str:
        """Transcribe a pre-loaded numpy audio array."""
        feats = (
            self.processor(y, sampling_rate=sr, return_tensors="pt")
            .input_features
            .to(self.device)
        )
        with torch.no_grad():
            ids = self.model.generate(feats, language="en")
        return self.processor.batch_decode(ids, skip_special_tokens=True)[0].strip().lower()

    def score(self, audio_path: str, reference_text: str) -> float:
        """
        Transcribe audio and compare to reference_text via word-level F1.
        Returns float in [0, 100].
        """
        transcript = self.transcribe(audio_path)
        return _word_f1(transcript, reference_text.strip()) * 100.0

    def score_array(
        self, y: np.ndarray, reference_text: str, sr: int = 16_000
    ) -> float:
        """Same as score() but from a pre-loaded numpy array."""
        transcript = self._transcribe_array(y, sr)
        return _word_f1(transcript, reference_text.strip()) * 100.0


def predict_module1_score(
    audio_path: str,
    reference_text: str,
    scorer: Optional[Module1Scorer] = None,
) -> float:
    """
    Convenience wrapper. Creates Module1Scorer on first call if not provided.
    Returns float in [0, 100].
    """
    if scorer is None:
        scorer = Module1Scorer()
    return scorer.score(audio_path, reference_text)
