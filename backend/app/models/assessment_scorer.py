"""
Optional learned multi-aspect pronunciation scorer.

The default acoustic pipeline remains deterministic and explainable. When a
checkpoint trained by `training.train_multitask_assessment` is present, this
module adds a modern speech-foundation-model assessment head on top of WavLM
utterance embeddings plus compact acoustic features.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

logger = logging.getLogger(__name__)

DEFAULT_OUTPUTS = ("accuracy", "fluency", "prosody", "completeness", "overall")


class MultiAspectHead(nn.Module):
    def __init__(self, input_dim: int, output_dim: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.LayerNorm(input_dim),
            nn.Linear(input_dim, 512),
            nn.GELU(),
            nn.Dropout(0.15),
            nn.Linear(512, 256),
            nn.GELU(),
            nn.Dropout(0.10),
            nn.Linear(256, 128),
            nn.GELU(),
            nn.Linear(128, output_dim),
            nn.Sigmoid(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x) * 100.0


def extract_audio_features(wav_np: np.ndarray, sr: int = 16_000) -> np.ndarray:
    """Small, stable acoustic feature vector used by training and inference."""
    wav = np.asarray(wav_np, dtype=np.float32)
    if wav.ndim > 1:
        wav = wav.mean(axis=0)
    if len(wav) == 0:
        return np.zeros(12, dtype=np.float32)

    duration = len(wav) / sr
    peak = float(np.max(np.abs(wav)))
    rms = float(np.sqrt(np.mean(np.square(wav)) + 1e-12))
    zcr = float(np.mean(np.abs(np.diff(np.signbit(wav)))))
    silence_ratio = float(np.mean(np.abs(wav) < 0.015))

    frame = max(1, int(0.025 * sr))
    hop = max(1, int(0.010 * sr))
    if len(wav) < frame:
        frames = wav.reshape(1, -1)
    else:
        starts = range(0, len(wav) - frame + 1, hop)
        frames = np.stack([wav[s:s + frame] for s in starts])
    energy = np.sqrt(np.mean(np.square(frames), axis=1) + 1e-12)
    voiced = energy > max(0.01, np.percentile(energy, 35))

    spectrum = np.abs(np.fft.rfft(wav[: min(len(wav), sr * 8)]))
    freqs = np.fft.rfftfreq(len(wav[: min(len(wav), sr * 8)]), d=1 / sr)
    spec_sum = float(spectrum.sum() + 1e-9)
    centroid = float((freqs * spectrum).sum() / spec_sum)
    bandwidth = float(np.sqrt((((freqs - centroid) ** 2) * spectrum).sum() / spec_sum))

    features = np.array(
        [
            min(duration / 30.0, 1.0),
            min(rms / 0.2, 1.0),
            min(peak, 1.0),
            min(zcr / 0.25, 1.0),
            silence_ratio,
            float(np.mean(voiced)),
            min(float(np.std(energy)) / 0.1, 1.0),
            min(float(np.max(energy)) / 0.5, 1.0),
            min(centroid / 6000.0, 1.0),
            min(bandwidth / 6000.0, 1.0),
            min(float(np.percentile(energy, 90)) / 0.3, 1.0),
            min(float(np.percentile(energy, 10)) / 0.1, 1.0),
        ],
        dtype=np.float32,
    )
    return np.nan_to_num(features, nan=0.0, posinf=1.0, neginf=0.0)


class AssessmentScorer:
    def __init__(self, checkpoint_path: str | Path, device: str = "cpu"):
        self.device = torch.device(device)
        data = torch.load(checkpoint_path, map_location=self.device, weights_only=False)
        self.output_names = tuple(data.get("output_names", DEFAULT_OUTPUTS))
        self.embedding_dim = int(data.get("embedding_dim", 1024))
        self.audio_feature_dim = int(data.get("audio_feature_dim", 12))
        input_dim = int(data.get("input_dim", self.embedding_dim + self.audio_feature_dim))

        self.model = MultiAspectHead(input_dim=input_dim, output_dim=len(self.output_names)).to(self.device)
        self.model.load_state_dict(data["model_state_dict"])
        self.model.eval()
        logger.info(
            "Assessment scorer loaded from %s (outputs=%s, val_loss=%s)",
            checkpoint_path,
            list(self.output_names),
            data.get("val_loss", "?"),
        )

    @torch.inference_mode()
    def predict(self, embedding: torch.Tensor, wav_np: np.ndarray) -> dict[str, float]:
        if embedding.dim() > 1:
            embedding = embedding.squeeze(0)
        emb = embedding.detach().to(self.device).float()
        audio_features = torch.from_numpy(extract_audio_features(wav_np)).to(self.device)
        x = torch.cat([emb, audio_features], dim=0).unsqueeze(0)
        pred = self.model(x).squeeze(0).detach().cpu().numpy()
        return {name: round(float(value), 1) for name, value in zip(self.output_names, pred)}
