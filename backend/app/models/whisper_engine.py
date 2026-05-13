"""
Whisper transcription layer — cross-checks what the user actually said.
Runs faster-whisper (CTranslate2) with int8 quantisation on CPU.

Single transcribe entry point with two orthogonal flags:

  * ``words``: include per-word timestamps (slightly slower)
  * ``fast``:  greedy decode + no VAD (faster, used when we only need text)

The full ``words=True, fast=False`` combination uses beam search + VAD, which
is the slowest but most reliable; it is the default for one-shot transcription
of recordings such as ``/api/accent-clone`` audio.
"""
import logging
import os
import threading

import numpy as np

from app.utils.text_metrics import word_error_rate

logger = logging.getLogger(__name__)

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "large-v3-turbo")
WHISPER_FALLBACK_MODEL = os.getenv("WHISPER_FALLBACK_MODEL", "large-v3")
WHISPER_DEVICE = "cpu"   # CTranslate2; MPS unsupported.
WHISPER_COMPUTE = "int8"
WHISPER_CPU_THREADS = int(os.getenv("WHISPER_CPU_THREADS", "0"))


class WhisperEngine:
    def __init__(self, model_size: str = WHISPER_MODEL):
        from faster_whisper import WhisperModel
        self._lock = threading.RLock()
        try:
            logger.info(f"Loading Whisper {model_size} (CTranslate2 int8, CPU)")
            self.model = WhisperModel(
                model_size,
                device=WHISPER_DEVICE,
                compute_type=WHISPER_COMPUTE,
                cpu_threads=WHISPER_CPU_THREADS,
            )
            self.model_size = model_size
        except Exception as e:
            if model_size == WHISPER_FALLBACK_MODEL:
                raise
            logger.warning(
                f"Whisper {model_size} unavailable ({e}); falling back to {WHISPER_FALLBACK_MODEL}"
            )
            self.model = WhisperModel(
                WHISPER_FALLBACK_MODEL,
                device=WHISPER_DEVICE,
                compute_type=WHISPER_COMPUTE,
                cpu_threads=WHISPER_CPU_THREADS,
            )
            self.model_size = WHISPER_FALLBACK_MODEL
        logger.info(f"Whisper ready ({self.model_size})")

    def transcribe(
        self,
        wav_np: np.ndarray,
        *,
        words: bool = False,
        fast: bool = True,
    ) -> dict:
        """Transcribe ``wav_np`` (float32, 16 kHz mono).

        ``fast=True`` (default) uses greedy decode + no VAD, which is the right
        choice for output validation and reference checks. ``fast=False`` adds
        beam search + VAD for higher-quality one-shot transcription.
        """
        if fast:
            decode_kwargs = {
                "beam_size": 1,
                "best_of": 1,
                "temperature": 0.0,
                "condition_on_previous_text": False,
            }
            vad_kwargs: dict = {"vad_filter": False}
        else:
            decode_kwargs = {}
            vad_kwargs = {
                "vad_filter": True,
                "vad_parameters": {"min_silence_duration_ms": 300},
            }

        with self._lock:
            segments, info = self.model.transcribe(
                wav_np,
                language="en",
                task="transcribe",
                word_timestamps=words,
                **vad_kwargs,
                **decode_kwargs,
            )
            return self._collect(segments, info, with_words=words)

    # ── Backwards-compat shims for older callers ──────────────────────

    def transcribe_fast(self, wav_np: np.ndarray) -> str:
        return self.transcribe(wav_np, words=False, fast=True)["text"]

    def transcribe_with_words(self, wav_np: np.ndarray) -> dict:
        return self.transcribe(wav_np, words=True, fast=True)

    def warmup(self) -> None:
        """Tiny greedy decode so CTranslate2 has warm workers."""
        self.transcribe(np.zeros(16_000, dtype=np.float32), words=False, fast=True)

    def _collect(self, segments, info, *, with_words: bool) -> dict:
        words: list[dict] = []
        full_text = ""
        for seg in segments:
            full_text += seg.text
            if with_words and seg.words:
                for w in seg.words:
                    words.append({
                        "word": w.word.strip() if not with_words else w.word,
                        "start_ms": round(w.start * 1000),
                        "end_ms": round(w.end * 1000),
                        **({"probability": round(w.probability, 3)} if hasattr(w, "probability") else {}),
                    })
        return {
            "text": full_text.strip(),
            "words": words,
            "language_probability": round(info.language_probability, 3)
            if info is not None and hasattr(info, "language_probability")
            else None,
        }

    @staticmethod
    def word_error_rate(hypothesis: str, reference: str) -> float:
        """Normalized WER with punctuation/case stripped."""
        return word_error_rate(hypothesis, reference)
