"""
Layer 2 — Phoneme Engine.

Pipeline:
  1. wav2vec2-large-robust-L2 → per-frame CTC log-probs
  2. torchaudio.functional.forced_align (CPU) → frame-level phoneme token assignments
  3. Parse non-blank runs → start_ms / end_ms per phoneme
  4. GOP score = mean log P(expected_ph | frames in segment)
  5. Substitution detection = argmax over segment vs expected token
  6. MLP regression head (optional) → calibrated 0-100 score from raw GOP

Note: forced_align is a CPU-only operation; log_probs are computed on MPS then
moved to CPU before alignment.
"""
import logging
from dataclasses import dataclass
from pathlib import Path

import torch
import torch.nn as nn
import torchaudio
from transformers import AutoProcessor, AutoModelForCTC

logger = logging.getLogger(__name__)

# GOP thresholds (validated against speechocean762 human ratings)
GOP_GREEN  =  -1.0   # > -1.0  → correct (green)
GOP_YELLOW = -2.0    # -1.0 to -2.0 → marginal (yellow)
                     # < -2.0  → incorrect (red)

FRAME_DURATION_MS = 20   # wav2vec2 outputs ~50 frames/sec


@dataclass
class PhonemeResult:
    phoneme: str
    expected: str
    gop: float
    correct: bool
    substitution: str | None
    start_ms: int
    end_ms: int
    calibrated_score: float | None


class MLPHead(nn.Module):
    def __init__(self, input_dim: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.BatchNorm1d(input_dim),
            nn.Linear(input_dim, 256),
            nn.GELU(),
            nn.Dropout(0.2),
            nn.Linear(256, 128),
            nn.GELU(),
            nn.Dropout(0.15),
            nn.Linear(128, 64),
            nn.GELU(),
            nn.Linear(64, 1),
            nn.Sigmoid(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x).squeeze(-1) * 100  # → [B] in [0, 100]


class PhonemeEngine:
    def __init__(self, model_id: str, device: str, checkpoint_path: str | None = None):
        self.device = torch.device(device)
        logger.info(f"Loading phoneme model {model_id} on {device}")
        self.processor = AutoProcessor.from_pretrained(model_id)
        self.model = AutoModelForCTC.from_pretrained(model_id).to(self.device)
        self.model.eval()

        vocab = self.processor.tokenizer.get_vocab()
        self.vocab = vocab
        self.id_to_token = {v: k for k, v in vocab.items()}
        self.blank_id = vocab.get("<pad>", 0)
        logger.info(f"Vocab size: {len(vocab)}, blank_id: {self.blank_id}")

        # Optional regression head
        self.head: MLPHead | None = None
        self.head_input_dim: int | None = None
        if checkpoint_path and Path(checkpoint_path).exists():
            state = torch.load(checkpoint_path, map_location=self.device, weights_only=False)
            dim = state.get("input_dim", len(vocab))
            head = MLPHead(input_dim=dim)
            head.load_state_dict(state["model_state_dict"])
            head.to(self.device).eval()
            self.head = head
            self.head_input_dim = dim
            logger.info(f"Regression head loaded (dim={dim}, val_loss={state.get('val_loss', '?'):.4f})")
        else:
            logger.info("No regression head — raw GOP scores used")

    @torch.no_grad()
    def score(self, wav: torch.Tensor, phrase: str) -> list[PhonemeResult]:
        """wav: [1, T] float32 at 16 kHz. Returns one PhonemeResult per phoneme."""
        wav = wav.to(self.device)
        inputs = self.processor(
            wav.squeeze(0).cpu().numpy(),
            sampling_rate=16000,
            return_tensors="pt",
            padding=True,
        )
        logits = self.model(inputs.input_values.to(self.device)).logits  # [1, T, vocab]
        log_probs_dev = torch.log_softmax(logits, dim=-1)                # [1, T, vocab] on device
        log_probs_cpu = log_probs_dev.cpu()                              # forced_align needs CPU

        expected_tokens = self._text_to_token_ids(phrase)
        if not expected_tokens:
            logger.warning("Could not convert phrase to phoneme token IDs")
            return []

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

        return results

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

        # Calibrated score from regression head
        calibrated: float | None = None
        if self.head is not None and self.head_input_dim is not None:
            # Use mean log-prob vector (same feature as training)
            feat = log_probs.mean(dim=0).unsqueeze(0).to(self.device)  # [1, vocab]
            calibrated = float(self.head(feat).item())

        return PhonemeResult(
            phoneme=pred_str if not correct else expected_str,
            expected=expected_str,
            gop=round(gop, 3),
            correct=correct,
            substitution=substitution,
            start_ms=start_f * FRAME_DURATION_MS,
            end_ms=end_f * FRAME_DURATION_MS,
            calibrated_score=round(calibrated, 1) if calibrated is not None else None,
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

    def _text_to_token_ids(self, text: str) -> list[int]:
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
        """0-100 phoneme accuracy. Uses calibrated scores when available."""
        if not results:
            return 0.0
        scores = []
        for r in results:
            if r.calibrated_score is not None:
                scores.append(r.calibrated_score)
            else:
                # Map raw GOP to 0-100: GOP=0 → 100, GOP=-3 → 0
                scores.append(max(0.0, min(100.0, (r.gop + 3.0) / 3.0 * 100.0)))
        return round(sum(scores) / len(scores), 1)
