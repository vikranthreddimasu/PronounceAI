"""
Whisper transcription layer — cross-checks what the user actually said
against the expected phrase. Runs faster-whisper (CTranslate2 backend)
with the large-v3 model on MPS/CPU.

Used in the scoring pipeline to:
  1. Detect if the user said the wrong words entirely
  2. Provide word-level timestamps for display
  3. Feed word error rate as a signal into the overall score
"""
import logging
import os

import numpy as np

logger = logging.getLogger(__name__)

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "large-v3")
WHISPER_DEVICE = "cpu"   # faster-whisper uses CTranslate2; MPS not yet supported
WHISPER_COMPUTE = "int8" # int8 quantisation — fast on M5 Pro CPU, ~1GB RAM


class WhisperEngine:
    def __init__(self, model_size: str = WHISPER_MODEL):
        logger.info(f"Loading Whisper {model_size} (CTranslate2 int8, CPU)")
        from faster_whisper import WhisperModel
        self.model = WhisperModel(
            model_size,
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE,
        )
        logger.info("Whisper ready")

    def transcribe(self, wav_np: np.ndarray, sr: int = 16000) -> dict:
        """
        Transcribe audio → {text, words, wer_vs_expected (None until phrase given)}.
        wav_np: float32 array at 16 kHz.
        """
        segments, info = self.model.transcribe(
            wav_np,
            language="en",
            word_timestamps=True,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 300},
        )
        words = []
        full_text = ""
        for seg in segments:
            full_text += seg.text
            if seg.words:
                for w in seg.words:
                    words.append({
                        "word": w.word.strip(),
                        "start_ms": round(w.start * 1000),
                        "end_ms": round(w.end * 1000),
                        "probability": round(w.probability, 3),
                    })

        return {
            "text": full_text.strip(),
            "words": words,
            "language_probability": round(info.language_probability, 3),
        }

    def word_error_rate(self, hypothesis: str, reference: str) -> float:
        """Simple WER: edit distance on word tokens."""
        hyp = hypothesis.lower().split()
        ref = reference.lower().split()
        if not ref:
            return 0.0
        # Dynamic programming edit distance
        d = list(range(len(hyp) + 1))
        for r_word in ref:
            prev = d[0]
            d[0] += 1
            for i, h_word in enumerate(hyp):
                cur = d[i + 1]
                d[i + 1] = min(
                    d[i] + 1,        # insertion
                    cur + 1,         # deletion
                    prev + (0 if h_word == r_word else 1),  # substitution
                )
                prev = cur
        return round(d[len(hyp)] / len(ref), 3)
