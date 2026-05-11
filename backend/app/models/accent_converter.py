"""
Accent conversion via kNN-VC (bshall/knn-vc).

Given a user recording, returns a 16 kHz wav of the same words spoken in the
target accent. Pipeline:

  1. Extract WavLM-Large layer-6 features from the user audio.
  2. Replace each frame with the average of its top-k nearest neighbours in
     a pre-built reference pool of target-accent speech features.
  3. Decode the replaced feature sequence with a HiFi-GAN vocoder trained on
     WavLM features (the "prematched" variant).

The reference pool per accent is synthesised once via Kokoro from a fixed
phrase list, encoded to WavLM features, and cached under
`checkpoints/accent_refs_{accent}.pt`. Pool quality is the main quality
ceiling for v0 — swap to real human corpora (VCTK, CommonVoice) later.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import numpy as np
import resampy
import torch

KNN_TOPK = int(os.getenv("KNN_TOPK", "4"))
KNN_PREMATCHED = os.getenv("KNN_PREMATCHED", "1") != "0"

logger = logging.getLogger(__name__)

REFERENCE_PHRASES = [
    "The quick brown fox jumps over the lazy dog.",
    "She sells seashells by the seashore on Sunday morning.",
    "Could you please pass the salt and pepper to the table?",
    "Yesterday I walked to the park and watched the children play.",
    "Tomorrow we will travel to the mountains for a weekend hike.",
    "How much wood would a woodchuck chuck if it could chuck wood?",
    "The early bird catches the worm but the second mouse gets the cheese.",
    "Please remember to lock the door before you leave the house.",
    "Three thirsty turtles thoroughly thanked the thoughtful thunderstorm.",
    "Around the rugged rock the ragged rascal ran with reckless abandon.",
    "Peter Piper picked a peck of pickled peppers in the garden.",
    "I scream you scream we all scream for ice cream on hot summer days.",
    "The rain in Spain stays mainly in the plain throughout the year.",
    "Better late than never but better never late they always say.",
    "All that glitters is not gold and all who wander are not lost.",
    "A penny saved is a penny earned according to my grandmother.",
    "Where there is a will there is a way and where there is smoke there is fire.",
    "Practice makes perfect but nobody is perfect so why practice?",
    "Birds of a feather flock together when the weather turns cold.",
    "The pen is mightier than the sword but the keyboard is mightier still.",
    "Time flies like an arrow but fruit flies like a banana.",
    "Don't count your chickens before they hatch or your money before you earn it.",
    "Every cloud has a silver lining even on the darkest stormy days.",
    "Actions speak louder than words but pictures speak loudest of all.",
    "When in Rome do as the Romans do and eat plenty of pasta.",
    "Curiosity killed the cat but satisfaction brought it back home.",
    "The proof of the pudding is in the eating not in the recipe.",
    "Two heads are better than one when solving difficult problems together.",
    "Beauty is in the eye of the beholder and so is everything else.",
    "A journey of a thousand miles begins with a single step forward.",
]

# Kokoro voice per accent — mirrors /api/tts and utils/native_pitch.
_VOICE_MAP = {
    "GA": ("a", "af_heart"),
    "RP": ("b", "bf_emma"),
}

KOKORO_SR = 24_000
KNNVC_SR = 16_000


class AccentConverter:
    """Wraps the bshall/knn-vc model + per-accent reference pools."""

    def __init__(self, device: str = "cpu", refs_dir: str | Path = "checkpoints"):
        # knn-vc's bundled WavLM forces CPU when torch.cuda is unavailable and then
        # crashes on the half-MPS / half-CPU mix (float64 unsupported on MPS).
        # Pinning to CPU avoids the mixed-device crash; throughput on M-series CPU
        # is fast enough for single-utterance conversion.
        self.device = device
        self.refs_dir = Path(refs_dir)
        self.refs_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"Loading knn-vc via torch.hub (device={device}, "
            f"prematched={KNN_PREMATCHED}, topk={KNN_TOPK})"
        )
        self.model = torch.hub.load(
            "bshall/knn-vc",
            "knn_vc",
            prematched=KNN_PREMATCHED,
            trust_repo=True,
            pretrained=True,
            device=device,
        )
        self.topk = KNN_TOPK
        logger.info("knn-vc loaded")

        # In-memory pool cache: accent → (matching_set, file_mtime).
        # Auto-reloads when the on-disk file changes (e.g. swapped from
        # Kokoro pool → VCTK pool without backend restart).
        self._pools: dict[str, tuple[torch.Tensor, float]] = {}

    # ---- public API ----------------------------------------------------

    def supported_accents(self) -> list[str]:
        return list(_VOICE_MAP.keys())

    @torch.inference_mode()
    def convert(
        self,
        wav16k: np.ndarray | torch.Tensor,
        target_accent: str,
        topk: int = 4,
    ) -> np.ndarray:
        """
        Convert a 16 kHz mono float32 waveform to the target accent.
        Returns float32 numpy at 16 kHz.
        """
        accent = target_accent.upper()
        if accent not in _VOICE_MAP:
            raise ValueError(f"Unsupported accent for conversion: {target_accent}")

        if isinstance(wav16k, np.ndarray):
            wav_t = torch.from_numpy(np.ascontiguousarray(wav16k, dtype=np.float32))
        else:
            wav_t = wav16k.float()
        if wav_t.dim() == 1:
            wav_t = wav_t.unsqueeze(0)  # (1, T)
        wav_t = wav_t.to(self.device)

        # User features
        query = self.model.get_features(wav_t)

        # Target pool
        matching_set = self._get_pool(accent)

        # kNN match → wav (use env-configured topk if caller didn't override)
        effective_topk = topk if topk != 4 else self.topk
        out = self.model.match(query, matching_set, topk=effective_topk)
        if out.dim() > 1:
            out = out.squeeze(0)
        return out.detach().cpu().numpy().astype(np.float32)

    # ---- reference pool ------------------------------------------------

    def _pool_path(self, accent: str) -> Path:
        return self.refs_dir / f"accent_refs_{accent}.pt"

    def _get_pool(self, accent: str) -> torch.Tensor:
        path = self._pool_path(accent)
        current_mtime = path.stat().st_mtime if path.exists() else 0.0

        cached = self._pools.get(accent)
        if cached is not None and cached[1] == current_mtime and current_mtime > 0:
            return cached[0]

        if path.exists():
            logger.info(f"Loading accent reference pool from {path}")
            pool = torch.load(path, map_location=self.device)
        else:
            logger.info(f"Building accent reference pool for {accent} — this is a one-time cost")
            pool = self._build_pool(accent)
            torch.save(pool.cpu(), path)
            current_mtime = path.stat().st_mtime
            logger.info(f"Saved pool to {path} (shape={tuple(pool.shape)})")

        pool = pool.to(self.device)
        self._pools[accent] = (pool, current_mtime)
        return pool

    @torch.inference_mode()
    def _build_pool(self, accent: str) -> torch.Tensor:
        """Synth phrases with Kokoro, extract WavLM-L6 features, concat."""
        from kokoro import KPipeline

        lang_code, voice = _VOICE_MAP[accent]
        pipe = KPipeline(lang_code=lang_code)

        feat_chunks: list[torch.Tensor] = []
        for i, phrase in enumerate(REFERENCE_PHRASES):
            audio_parts: list[np.ndarray] = []
            for _, _, audio in pipe(phrase, voice=voice, speed=1.0):
                if hasattr(audio, "detach"):
                    audio = audio.detach().cpu().numpy()
                audio_parts.append(np.asarray(audio, dtype=np.float32))
            if not audio_parts:
                continue
            wav24 = np.concatenate(audio_parts).astype(np.float32)
            wav16 = resampy.resample(wav24, KOKORO_SR, KNNVC_SR).astype(np.float32)
            wav_t = torch.from_numpy(wav16).unsqueeze(0).to(self.device)
            feats = self.model.get_features(wav_t)
            feat_chunks.append(feats.detach().cpu())
            if (i + 1) % 5 == 0:
                logger.info(f"  pool[{accent}] {i+1}/{len(REFERENCE_PHRASES)} phrases")

        if not feat_chunks:
            raise RuntimeError(f"Failed to build reference pool for {accent}")
        return torch.cat(feat_chunks, dim=0)
