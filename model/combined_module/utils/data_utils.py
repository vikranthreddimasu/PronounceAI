"""
Data utilities for combined module training.

Provides helpers to:
  - locate LibriSpeech audio + transcript pairs
  - load and augment audio
  - build the combined feature dataset
"""
from __future__ import annotations

import warnings
from pathlib import Path
from typing import List, Optional, Tuple

import librosa
import numpy as np

warnings.filterwarnings("ignore")

# Path: utils/ -> combined_module/ -> model/ -> PronounceAI/
_LIBRI_ROOT = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "librispeech" / "LibriSpeech"
)


def get_librispeech_root(override: Optional[str | Path] = None) -> Path:
    root = Path(override) if override else _LIBRI_ROOT
    if not root.exists():
        raise FileNotFoundError(
            f"LibriSpeech dataset not found at:\n  {root}\n"
            "Extract the dataset archives first."
        )
    return root


def find_audio_files(
    split: str = "train-clean-100",
    max_files: int = 50,
    libri_root: Optional[Path] = None,
) -> List[Path]:
    """Return up to max_files .flac paths from the given LibriSpeech split."""
    root = get_librispeech_root(libri_root)
    return sorted((root / split).rglob("*.flac"))[:max_files]


def find_transcript(audio_path: Path) -> str:
    """
    Look up the ground-truth transcript for a LibriSpeech .flac file.
    Transcripts live in the same folder in a .trans.txt file.
    Returns empty string if not found.
    """
    stem = audio_path.stem                               # e.g. 1089-134686-0000
    parts = stem.split("-")
    trans_file = audio_path.parent / f"{parts[0]}-{parts[1]}.trans.txt"
    if not trans_file.exists():
        return ""
    with open(trans_file) as fh:
        for line in fh:
            line = line.strip()
            if line.startswith(stem):
                return line[len(stem):].strip().lower()
    return ""


def load_audio(path: str | Path, sr: int = 16_000) -> np.ndarray:
    """Load any audio file and resample to target sample rate."""
    y, _ = librosa.load(str(path), sr=sr, mono=True)
    return y


def augment_audio(y: np.ndarray, sr: int = 16_000) -> np.ndarray:
    """
    Create a degraded version of the audio for label generation.
    Mirrors the augmentation used in module_2 training.
    """
    mode = np.random.choice(["pitch", "noise", "stretch", "compound"])
    if mode == "pitch":
        return librosa.effects.pitch_shift(y, sr=sr, n_steps=np.random.choice([-6, -5, 5, 6]))
    if mode == "noise":
        return np.clip(y + np.random.normal(0, 0.05, len(y)), -1, 1)
    if mode == "compound":
        shifted = librosa.effects.pitch_shift(
            y, sr=sr, n_steps=np.random.choice([-4, -3, 3, 4])
        )
        return np.clip(shifted + np.random.normal(0, 0.025, len(shifted)), -1, 1)
    # stretch
    return librosa.effects.time_stretch(y, rate=np.random.choice([0.6, 0.7, 1.5, 1.6]))


def build_sample_list(
    split: str = "train-clean-100",
    max_files: int = 50,
    libri_root: Optional[Path] = None,
) -> List[Tuple[Path, str]]:
    """
    Return a list of (audio_path, reference_text) tuples for clean samples.
    Skips files whose transcript cannot be found.
    """
    audio_files = find_audio_files(split, max_files, libri_root)
    samples: List[Tuple[Path, str]] = []
    for path in audio_files:
        transcript = find_transcript(path)
        if transcript:
            samples.append((path, transcript))
    return samples
