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
import threading

import numpy as np

from app.utils.text_metrics import word_error_rate

logger = logging.getLogger(__name__)

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "large-v3-turbo")
WHISPER_FALLBACK_MODEL = os.getenv("WHISPER_FALLBACK_MODEL", "large-v3")
WHISPER_DEVICE = "cpu"   # faster-whisper uses CTranslate2; MPS not yet supported
WHISPER_COMPUTE = "int8" # int8 quantisation — fast on M5 Pro CPU, ~1GB RAM
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

    def transcribe(self, wav_np: np.ndarray, sr: int = 16000) -> dict:
        """
        Transcribe audio → {text, words, wer_vs_expected (None until phrase given)}.
        wav_np: float32 array at 16 kHz.
        """
        with self._lock:
            segments, info = self.model.transcribe(
                wav_np,
                language="en",
                task="transcribe",
                word_timestamps=True,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 300},
            )
            return self._collect(segments, info, with_words=True)

    def transcribe_fast(self, wav_np: np.ndarray) -> str:
        """Lightweight transcription used for output validation.

        Skips word timestamps + VAD, uses greedy decoding. ~2-3x faster than
        the full `transcribe()` because we don't need word-level alignment —
        we only need a text string to compare against an expected reference.
        """
        with self._lock:
            segments, _ = self.model.transcribe(
                wav_np,
                language="en",
                task="transcribe",
                word_timestamps=False,
                vad_filter=False,
                beam_size=1,
                best_of=1,
                temperature=0.0,
                condition_on_previous_text=False,
            )
            return "".join(seg.text for seg in segments).strip()

    def transcribe_with_words(self, wav_np: np.ndarray) -> dict:
        """Greedy decode WITH word timestamps. Used by /api/voice/speak so the
        client can highlight the active word during playback.

        Faster than the full `transcribe()` (no beam search, no VAD) but still
        emits per-word start/end times. Same single STT pass also serves as
        the instruct-mode validation transcript.
        """
        with self._lock:
            segments, _ = self.model.transcribe(
                wav_np,
                language="en",
                task="transcribe",
                word_timestamps=True,
                vad_filter=False,
                beam_size=1,
                best_of=1,
                temperature=0.0,
                condition_on_previous_text=False,
            )
            words = []
            text = ""
            for seg in segments:
                text += seg.text
                if seg.words:
                    for w in seg.words:
                        words.append({
                            "word": w.word,
                            "start_ms": round(w.start * 1000),
                            "end_ms": round(w.end * 1000),
                        })
            return {"text": text.strip(), "words": words}

    def warmup(self) -> None:
        """Run a tiny greedy decode so CTranslate2 has initialized workers."""
        self.transcribe_fast(np.zeros(16_000, dtype=np.float32))

    def _collect(self, segments, info, *, with_words: bool) -> dict:
        words = []
        full_text = ""
        for seg in segments:
            full_text += seg.text
            if with_words and seg.words:
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

    @staticmethod
    def word_error_rate(hypothesis: str, reference: str) -> float:
        """Normalized WER with punctuation/case stripped."""
        return word_error_rate(hypothesis, reference)
