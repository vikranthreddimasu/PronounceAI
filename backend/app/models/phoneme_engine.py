"""
Layer 2 — Phoneme Engine.

Pipeline:
  1. wav2vec2-large-robust-L2 → per-frame CTC log-probs
  2. torchaudio.functional.forced_align (CPU) → frame-level phoneme token assignments
  3. Parse non-blank runs → start_ms / end_ms per phoneme
  4. GOP score = mean log P(expected_ph | frames in segment)
  5. Substitution detection = argmax over segment vs expected token

Note: forced_align is a CPU-only operation; log_probs are computed on MPS then
moved to CPU before alignment.

The legacy per-phone calibration head was removed: the underlying speechocean762
dataset on HF only exposes utterance-level scores, so the same calibrated value
was being attached to every phone in a clip, implying granularity that did not
exist. The WavLM multi-aspect AssessmentScorer covers utterance-level
calibration; raw GOP is the authentic per-phone signal.
"""
import logging
import os
import threading
from collections import OrderedDict
from dataclasses import dataclass

import numpy as np
import torch
import torchaudio
from transformers import AutoProcessor, AutoModelForCTC

from app.utils.text_metrics import edit_distance

logger = logging.getLogger(__name__)

# GOP thresholds (validated against speechocean762 human ratings)
GOP_GREEN  =  -1.0   # > -1.0  → correct (green)
GOP_YELLOW = -2.0    # -1.0 to -2.0 → marginal (yellow)
                     # < -2.0  → incorrect (red)

FRAME_DURATION_MS = 20   # wav2vec2 outputs ~50 frames/sec
PHRASE_CACHE_SIZE = int(os.getenv("PHONEME_PHRASE_CACHE_SIZE", "2048"))


@dataclass
class PhonemeResult:
    phoneme: str
    expected: str
    gop: float
    correct: bool
    substitution: str | None
    start_ms: int
    end_ms: int


class PhonemeEngine:
    def __init__(self, model_id: str, device: str, checkpoint_path: str | None = None):
        self.device = torch.device(device)
        logger.info(f"Loading phoneme model {model_id} on {device}")
        self.processor = AutoProcessor.from_pretrained(model_id)
        self.model = AutoModelForCTC.from_pretrained(model_id).to(self.device)
        self.model.eval()
        self._lock = threading.RLock()
        self._phrase_cache_lock = threading.RLock()
        self._phrase_token_cache: OrderedDict[str, tuple[int, ...]] = OrderedDict()

        vocab = self.processor.tokenizer.get_vocab()
        self.vocab = vocab
        self.id_to_token = {v: k for k, v in vocab.items()}
        self.blank_id = vocab.get("<pad>", 0)
        logger.info(f"Vocab size: {len(vocab)}, blank_id: {self.blank_id}")

        # The ``checkpoint_path`` argument is retained for backwards-compatible
        # signatures with app.main but is unused — see module docstring.
        if checkpoint_path:
            logger.info("Phoneme engine: legacy regression head ignored (using raw GOP).")

    @torch.inference_mode()
    def score(
        self,
        wav: torch.Tensor,
        phrase: str,
        include_diagnostics: bool = False,
    ) -> list[PhonemeResult] | tuple[list[PhonemeResult], dict]:
        """wav: [1, T] float32 at 16 kHz. Returns one result per expected phoneme."""
        with self._lock:
            wav = wav.to(self.device)
            inputs = self.processor(
                wav.squeeze(0).cpu().numpy(),
                sampling_rate=16000,
                return_tensors="pt",
                padding=True,
            )
            logits = self.model(inputs.input_values.to(self.device)).logits  # [1, T, vocab]
            log_probs_dev = torch.log_softmax(logits, dim=-1)                # [1, T, vocab]
            log_probs_cpu = log_probs_dev.cpu()                              # forced_align needs CPU

        expected_tokens = self.prepare_phrase(phrase)
        if not expected_tokens:
            logger.warning("Could not convert phrase to phoneme token IDs")
            empty_diag = {
                "expected_phone_count": 0,
                "predicted_phone_count": 0,
                "phone_error_rate": None,
                "ctc_sequence_score": None,
                "predicted_phones": [],
            }
            return ([], empty_diag) if include_diagnostics else []

        diagnostics = self._ctc_diagnostics(log_probs_cpu[0], expected_tokens)

        try:
            targets = torch.tensor([expected_tokens], dtype=torch.int32)
            alignments, _ = torchaudio.functional.forced_align(
                log_probs_cpu,
                targets,
                blank=self.blank_id,
            )
            # alignments: [1, T] — token ID per frame (blank or phoneme)
            segments = self._parse_segments(alignments[0], expected_tokens)
        except Exception as e:
            logger.warning(f"forced_align failed ({e}), using uniform split")
            n_frames = log_probs_cpu.shape[1]
            segments = self._uniform_segments(expected_tokens, n_frames)

        results = []
        expected_phonemes = self._token_ids_to_strings(expected_tokens)
        for seg_idx, (ph_str, start_f, end_f) in enumerate(zip(expected_phonemes, *zip(*segments))):
            results.append(self._make_result(
                ph_str, expected_tokens[seg_idx],
                log_probs_cpu[0], start_f, end_f,
            ))

        return (results, diagnostics) if include_diagnostics else results

    def _make_result(
        self,
        expected_str: str,
        expected_id: int,
        log_probs: torch.Tensor,   # [T, vocab] CPU
        start_f: int,
        end_f: int,
    ) -> PhonemeResult:
        seg = log_probs[start_f : end_f + 1]  # [frames, vocab]
        if len(seg) == 0:
            seg = log_probs[start_f : start_f + 1]

        # GOP = mean log P(expected_phoneme | frame) over segment
        gop = float(seg[:, expected_id].mean().item())

        # What did the model actually predict most in this segment?
        pred_id = int(seg.mean(dim=0).argmax().item())
        pred_str = self.id_to_token.get(pred_id, expected_str)
        # Ignore blanks and pipe tokens when reporting prediction
        if pred_str in ("<pad>", "|", "<unk>"):
            pred_str = expected_str

        correct = gop > GOP_GREEN
        substitution = None
        if pred_str != expected_str and not correct:
            substitution = f"{pred_str}→{expected_str}"

        return PhonemeResult(
            phoneme=pred_str if not correct else expected_str,
            expected=expected_str,
            gop=round(gop, 3),
            correct=correct,
            substitution=substitution,
            start_ms=start_f * FRAME_DURATION_MS,
            end_ms=end_f * FRAME_DURATION_MS,
        )

    def _parse_segments(
        self, alignments: torch.Tensor, expected_ids: list[int]
    ) -> list[tuple[int, int]]:
        """
        Parse forced_align output into (start_frame, end_frame) per target phoneme.
        alignments: [T] int tensor with token IDs (blank_id for blank frames).
        Returns list of (start_f, end_f) tuples, same length as expected_ids.
        """
        frames = alignments.tolist()
        segments: list[tuple[int, int]] = []
        ph_idx = 0
        seg_start = None

        for t, tok in enumerate(frames):
            if ph_idx >= len(expected_ids):
                break
            if tok == self.blank_id:
                # Blank frame: if we were in a segment, close it
                if seg_start is not None:
                    segments.append((seg_start, t - 1))
                    seg_start = None
                    ph_idx += 1
            else:
                # Non-blank: start or continue a segment
                if seg_start is None:
                    seg_start = t
                elif tok != expected_ids[ph_idx]:
                    # Token changed — close current segment, open next
                    segments.append((seg_start, t - 1))
                    seg_start = t
                    ph_idx += 1
                    if ph_idx >= len(expected_ids):
                        break

        # Close any open segment
        if seg_start is not None and ph_idx < len(expected_ids):
            segments.append((seg_start, len(frames) - 1))

        # Pad with single-frame segments if forced_align returned fewer than expected
        while len(segments) < len(expected_ids):
            last_end = segments[-1][1] if segments else 0
            segments.append((last_end, last_end))

        return segments[: len(expected_ids)]

    def _uniform_segments(self, expected_ids: list[int], n_frames: int) -> list[tuple[int, int]]:
        """Fallback: divide frames uniformly across phonemes."""
        n = len(expected_ids)
        fpb = max(1, n_frames // n)
        return [(i * fpb, min((i + 1) * fpb - 1, n_frames - 1)) for i in range(n)]

    def _is_phone_token(self, token_id: int) -> bool:
        token = self.id_to_token.get(token_id, "")
        return token not in ("<pad>", "|", "<unk>", "", "<s>", "</s>")

    def _collapse_ctc_ids(self, frame_ids: list[int]) -> list[int]:
        """Greedy CTC collapse: remove repeats and blanks/special tokens."""
        collapsed: list[int] = []
        prev: int | None = None
        for token_id in frame_ids:
            if token_id == prev:
                continue
            prev = token_id
            if self._is_phone_token(token_id):
                collapsed.append(token_id)
        return collapsed

    def _ctc_diagnostics(self, log_probs: torch.Tensor, expected_ids: list[int]) -> dict:
        """
        Alignment-independent CTC sanity check.

        Forced alignment is good for timestamps, but it can hide insertions or
        deletions because it must align the expected phone string. A greedy CTC
        transcript gives us a cheap second opinion without another model pass.
        """
        pred_ids = self._collapse_ctc_ids(log_probs.argmax(dim=-1).tolist())
        if not expected_ids:
            per = None
            seq_score = None
        else:
            distance = edit_distance(pred_ids, expected_ids)
            per = round(distance / len(expected_ids), 3)
            seq_score = round(max(0.0, 100.0 * (1.0 - min(1.0, per))), 1)
        return {
            "expected_phone_count": len(expected_ids),
            "predicted_phone_count": len(pred_ids),
            "phone_error_rate": per,
            "ctc_sequence_score": seq_score,
            "predicted_phones": self._token_ids_to_strings(pred_ids[:80]),
        }

    def prepare_phrase(self, text: str) -> list[int]:
        """Precompute/cache the target phone IDs for a phrase.

        G2P startup is surprisingly noticeable on first score. Keeping this
        tiny cache hot lets the UI prewarm a phrase as soon as the user selects
        it, before they press record.
        """
        key = " ".join(text.split())[:200].lower()
        with self._phrase_cache_lock:
            cached = self._phrase_token_cache.get(key)
            if cached is not None:
                self._phrase_token_cache.move_to_end(key)
                return list(cached)

        ids = self._text_to_token_ids_uncached(text)
        with self._phrase_cache_lock:
            self._phrase_token_cache[key] = tuple(ids)
            self._phrase_token_cache.move_to_end(key)
            while len(self._phrase_token_cache) > PHRASE_CACHE_SIZE:
                self._phrase_token_cache.popitem(last=False)
        return ids

    def warmup(self, phrase: str = "Ship or sheep?") -> None:
        """Run one cheap forward pass so MPS/transformer kernels are hot."""
        self.prepare_phrase(phrase)
        t = np.arange(16_000, dtype=np.float32) / 16_000
        wav = torch.from_numpy(0.02 * np.sin(2 * np.pi * 220 * t)).unsqueeze(0)
        self.score(wav, phrase, include_diagnostics=True)

    def _text_to_token_ids_uncached(self, text: str) -> list[int]:
        """
        Convert English text → ARPAbet phones → model vocab IDs.
        Uses g2p-en (CMU dict + neural fallback) which outputs ARPAbet directly,
        matching this model's vocabulary (aa, ae, ah, dh, ih, …).
        """
        try:
            from g2p_en import G2p
            if not hasattr(self, "_g2p"):
                self._g2p = G2p()
            raw = self._g2p(text)
            # Strip stress markers (IH1 → ih) and spaces
            phones = [
                tok.lower().rstrip("012")
                for tok in raw
                if tok.strip() and tok != " "
            ]
            ids = [self.vocab[ph] for ph in phones if ph in self.vocab]
            if ids:
                return ids
        except Exception as e:
            logger.warning(f"g2p_en failed: {e}")

        # Fallback: tokenize uppercase text through the model's own tokenizer
        try:
            enc = self.processor.tokenizer(text.upper(), return_tensors=None)
            ids = [
                i for i in enc["input_ids"]
                if self.id_to_token.get(i, "") not in ("<pad>", "|", "<unk>", "", "<s>", "</s>")
            ]
            if ids:
                return ids
        except Exception as e:
            logger.warning(f"Tokenizer fallback failed: {e}")

        return []

    def _token_ids_to_strings(self, ids: list[int]) -> list[str]:
        return [self.id_to_token.get(i, "?") for i in ids]

    def accuracy_score(self, results: list[PhonemeResult]) -> float:
        """0-100 phoneme accuracy from raw GOP.

        Monotone map: GOP=0 → 100, GOP=-3 → 0, with mild compression so the
        head-room around perfect phonation does not produce 100 for everyone.
        """
        if not results:
            return 0.0
        scores: list[float] = []
        for r in results:
            gop = float(r.gop)
            scores.append(max(0.0, min(100.0, (gop + 3.0) / 3.0 * 100.0)))
        return round(sum(scores) / len(scores), 1)
