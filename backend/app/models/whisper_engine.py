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
        return self._collect(segments, info, with_words=True)

    def transcribe_fast(self, wav_np: np.ndarray) -> str:
        """Lightweight transcription used for output validation.

        Skips word timestamps + VAD, uses greedy decoding. ~2-3x faster than
        the full `transcribe()` because we don't need word-level alignment —
        we only need a text string to compare against an expected reference.
        """
        segments, _ = self.model.transcribe(
            wav_np,
            language="en",
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
        segments, _ = self.model.transcribe(
            wav_np,
            language="en",
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
