"""
Build accent reference pools for kNN-VC from the VCTK corpus.

Reads audio directly from the VCTK zip without fully extracting it.
For each target speaker we encode the silence-trimmed mic1 flac files
into WavLM-Large layer-6 features and save the concatenated tensor as
`backend/checkpoints/accent_refs_{accent}.pt`.

Run from the backend dir:
    python -m scripts.build_vctk_pool \
        --zip data/vctk/VCTK-Corpus-0.92.zip \
        --max-utts-per-speaker 80

The default speaker sets below produce ~5 min of speech per accent.
"""
from __future__ import annotations

import argparse
import io
import logging
import sys
import time
import zipfile
from pathlib import Path

import numpy as np
import resampy
import soundfile as sf
import torch

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# Hand-curated speakers by accent.
# RP — Southern England female + male voices (closest mass-media "RP-ish")
SPEAKERS = {
    "RP": ["p225", "p228", "p229", "p231", "p232", "p240", "p254", "p258", "p268"],
    "GA": ["p294", "p299", "p300", "p305", "p306", "p311", "p339", "p345", "p360", "p362"],
}

TARGET_SR = 16_000


def load_knn_vc(device: str = "cpu"):
    logger.info(f"Loading knn-vc model (device={device}) …")
    model = torch.hub.load(
        "bshall/knn-vc",
        "knn_vc",
        prematched=True,
        trust_repo=True,
        pretrained=True,
        device=device,
    )
    return model


def list_speaker_files(zf: zipfile.ZipFile, speaker: str) -> list[str]:
    """Return flac paths inside the zip for a given speaker (mic1 only)."""
    prefix = f"wav48_silence_trimmed/{speaker}/"
    files = [
        n for n in zf.namelist()
        if n.startswith(prefix) and n.endswith("_mic1.flac")
    ]
    return sorted(files)


def load_audio_from_zip(zf: zipfile.ZipFile, member: str) -> np.ndarray | None:
    """Returns 16 kHz mono float32 or None on failure."""
    try:
        data = zf.read(member)
    except Exception as e:
        logger.warning(f"  read fail {member}: {e}")
        return None
    try:
        wav, sr = sf.read(io.BytesIO(data), always_2d=False)
    except Exception as e:
        logger.warning(f"  decode fail {member}: {e}")
        return None
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    wav = wav.astype(np.float32)
    if sr != TARGET_SR:
        wav = resampy.resample(wav, sr, TARGET_SR).astype(np.float32)
    # Skip very short clips (<0.6 s)
    if len(wav) < int(0.6 * TARGET_SR):
        return None
    # Peak-normalise
    peak = float(np.max(np.abs(wav)))
    if peak > 0:
        wav = wav / peak * 0.95
    return wav


@torch.inference_mode()
def build_pool(
    zip_path: Path,
    accent: str,
    model,
    max_utts_per_speaker: int,
    out_path: Path,
) -> None:
    speakers = SPEAKERS[accent]
    logger.info(f"Building {accent} pool from {len(speakers)} speakers …")
    feat_chunks: list[torch.Tensor] = []
    total_seconds = 0.0

    with zipfile.ZipFile(zip_path) as zf:
        for spk in speakers:
            members = list_speaker_files(zf, spk)[:max_utts_per_speaker]
            logger.info(f"  {spk}: {len(members)} utterances")
            spk_chunks: list[torch.Tensor] = []
            for member in members:
                wav = load_audio_from_zip(zf, member)
                if wav is None:
                    continue
                wav_t = torch.from_numpy(wav).unsqueeze(0)
                try:
                    feats = model.get_features(wav_t)
                except Exception as e:
                    logger.warning(f"  features fail {member}: {e}")
                    continue
                spk_chunks.append(feats.detach().cpu())
                total_seconds += len(wav) / TARGET_SR
            if spk_chunks:
                feat_chunks.append(torch.cat(spk_chunks, dim=0))
                logger.info(
                    f"  {spk} done — {sum(c.shape[0] for c in spk_chunks):,} frames "
                    f"(running total: {total_seconds:.1f}s)"
                )

    if not feat_chunks:
        raise RuntimeError(f"No features collected for accent={accent}")

    pool = torch.cat(feat_chunks, dim=0)
    logger.info(
        f"{accent} pool ready — shape={tuple(pool.shape)}, ~{total_seconds:.0f}s of speech"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(pool, out_path)
    logger.info(f"Saved → {out_path}  ({out_path.stat().st_size / 1e6:.1f} MB)")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--zip", default="data/vctk/VCTK-Corpus-0.92.zip")
    p.add_argument("--accents", nargs="+", default=["RP", "GA"])
    p.add_argument("--max-utts-per-speaker", type=int, default=80)
    p.add_argument("--out-dir", default="checkpoints")
    p.add_argument("--device", default="cpu")
    args = p.parse_args()

    zip_path = Path(args.zip).resolve()
    if not zip_path.exists():
        sys.exit(f"VCTK zip not found: {zip_path}")

    model = load_knn_vc(device=args.device)

    out_dir = Path(args.out_dir).resolve()
    for accent in args.accents:
        if accent not in SPEAKERS:
            logger.warning(f"Skipping unknown accent {accent}")
            continue
        out_path = out_dir / f"accent_refs_{accent}.pt"
        t0 = time.perf_counter()
        build_pool(
            zip_path=zip_path,
            accent=accent,
            model=model,
            max_utts_per_speaker=args.max_utts_per_speaker,
            out_path=out_path,
        )
        logger.info(f"{accent} build time: {time.perf_counter() - t0:.1f}s")


if __name__ == "__main__":
    main()
