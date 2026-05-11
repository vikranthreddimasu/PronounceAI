"""
Layer 4 — Accent Distance.

WavLM-Large utterance embedding → cosine distance to target accent centroid.
Centroids are pre-computed from VCTK native speakers and stored on disk.
Falls back to a neutral zero-distance score if centroids aren't built yet.
"""
import logging
from pathlib import Path

import numpy as np
import torch
from transformers import AutoFeatureExtractor, AutoModel

logger = logging.getLogger(__name__)

SUPPORTED_ACCENTS = ["GA", "RP", "AuE", "Irish", "Scottish", "IndianE"]


class AccentDistanceEngine:
    def __init__(self, model_id: str, device: str, centroids_path: str | None = None):
        self.device = torch.device(device)
        logger.info(f"Loading WavLM from {model_id}")
        self.extractor = AutoFeatureExtractor.from_pretrained(model_id)
        self.model = AutoModel.from_pretrained(model_id).to(self.device)
        self.model.eval()

        self.centroids: dict[str, torch.Tensor] = {}
        if centroids_path and Path(centroids_path).exists():
            data = torch.load(centroids_path, map_location=self.device)
            self.centroids = data
            logger.info(f"Loaded accent centroids for: {list(data.keys())}")
        else:
            logger.info("No accent centroids found — accent distance will return None until centroids are built")

    @torch.no_grad()
    def embed(self, wav_np: np.ndarray, sr: int = 16000) -> torch.Tensor:
        """Mean-pool WavLM hidden states → 1024-dim utterance embedding."""
        inputs = self.extractor(
            wav_np, sampling_rate=sr, return_tensors="pt", padding=True
        )
        input_values = inputs.input_values.to(self.device)
        outputs = self.model(input_values, output_hidden_states=False)
        # Mean-pool over time
        embedding = outputs.last_hidden_state.mean(dim=1)  # [1, 1024]
        return embedding.squeeze(0)

    def distance_score(self, wav_np: np.ndarray, target_accent: str) -> float | None:
        """
        Returns 0-100 accent similarity to target (100 = indistinguishable from native).
        Returns None if centroids not yet built.
        """
        centroid = self.centroids.get(target_accent)
        if centroid is None:
            return None

        emb = self.embed(wav_np)
        cos_sim = torch.nn.functional.cosine_similarity(
            emb.unsqueeze(0), centroid.unsqueeze(0)
        ).item()
        # cos_sim ∈ [-1, 1]; convert to 0-100
        score = (cos_sim + 1) / 2 * 100
        return round(score, 1)

    def add_centroid(self, accent: str, embeddings: list[torch.Tensor]) -> None:
        """Average a list of embeddings into a centroid and save."""
        stacked = torch.stack(embeddings)
        centroid = torch.nn.functional.normalize(stacked.mean(dim=0), dim=0)
        self.centroids[accent] = centroid

    def save_centroids(self, path: str) -> None:
        torch.save(self.centroids, path)
        logger.info(f"Saved centroids to {path}: {list(self.centroids.keys())}")
