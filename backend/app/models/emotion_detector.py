"""
Text-based emotion detection for auto-emotion voice synthesis.

Uses j-hartmann/emotion-english-distilroberta-base (~330MB), which outputs
7 emotion classes. We map them onto the 6 emotions exposed in EMOTION_TAGS:

    anger    → angry
    disgust  → angry
    fear     → whisper   (whisper conveys quiet/nervous register)
    joy      → happy
    neutral  → neutral
    sadness  → sad
    surprise → excited

The model is loaded lazily on first detect() call so server startup stays
fast when auto-emotion is never requested.
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.getenv(
    "EMOTION_MODEL",
    "j-hartmann/emotion-english-distilroberta-base",
)

# Model label → our EMOTION_TAGS key
LABEL_TO_EMOTION: dict[str, str] = {
    "anger": "angry",
    "disgust": "angry",
    "fear": "whisper",
    "joy": "happy",
    "neutral": "neutral",
    "sadness": "sad",
    "surprise": "excited",
}

# Below this top-class confidence we fall back to neutral. The model is
# usually very confident (>0.9) on clear emotion; values near 0.5 mean it
# can't pick — neutral is safer than guessing.
MIN_CONFIDENCE = float(os.getenv("EMOTION_MIN_CONFIDENCE", "0.55"))


class EmotionDetector:
    def __init__(self, model_id: str = DEFAULT_MODEL, device: Optional[str] = None):
        self.model_id = model_id
        # transformers' text-classification pipeline accepts -1=CPU, 0=cuda:0,
        # "mps" via torch.device. Force CPU — model is tiny, MPS gives no win
        # and breaks on some macOS torch builds.
        self.device = device or "cpu"
        self._pipe = None
        self._load_lock = threading.Lock()

    def _ensure_loaded(self) -> None:
        if self._pipe is not None:
            return
        with self._load_lock:
            if self._pipe is not None:
                return
            from transformers import pipeline
            logger.info(f"emotion_detector: loading {self.model_id}")
            self._pipe = pipeline(
                "text-classification",
                model=self.model_id,
                top_k=1,
                device=-1 if self.device == "cpu" else 0,
            )
            logger.info("emotion_detector: ready")

    def detect(self, text: str) -> tuple[str, float, str]:
        """Return (emotion_key, score, raw_label).

        emotion_key is always a valid EMOTION_TAGS key. On model failure or
        low confidence we return ("neutral", score, raw_label).
        """
        text = (text or "").strip()
        if not text:
            return "neutral", 0.0, "neutral"
        try:
            self._ensure_loaded()
            assert self._pipe is not None
            # pipeline with top_k=1 returns list[list[{"label","score"}]]
            out = self._pipe(text[:512])
            if isinstance(out, list) and out and isinstance(out[0], list):
                out = out[0]
            if not out:
                return "neutral", 0.0, "neutral"
            top = out[0]
            label = str(top.get("label", "")).lower()
            score = float(top.get("score", 0.0))
            mapped = LABEL_TO_EMOTION.get(label, "neutral")
            if score < MIN_CONFIDENCE:
                return "neutral", score, label
            return mapped, score, label
        except Exception as e:
            logger.warning(f"emotion_detector: detect failed — {e}")
            return "neutral", 0.0, "error"
