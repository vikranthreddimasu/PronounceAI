"""
Train a multi-aspect pronunciation assessment head.

This is the higher-ceiling model path for PronounceAI:
  WavLM utterance embedding + compact acoustic features
  -> accuracy, fluency, prosody, completeness, overall

It is intentionally a production-friendly training pipeline. The speech
foundation model supplies rich acoustic representation; the head is small,
fast to serve, and easy to evaluate. Run it when you have training time/GPU;
the backend will auto-load `checkpoints/assessment_head_best.pt` if present.

Example:
  cd backend
  source .venv/bin/activate
  python -m training.train_multitask_assessment --epochs 60 --batch-size 64
"""
from __future__ import annotations

import argparse
import logging
import os
import random
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn
import torchaudio
from torch.optim import AdamW
from torch.utils.data import DataLoader, Dataset, random_split
from transformers import AutoFeatureExtractor, AutoModel

from app.models.assessment_scorer import MultiAspectHead, extract_audio_features

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"
HF_TOKEN = os.getenv("HUGGINGFACE_TOKEN")
DEFAULT_MODEL = os.getenv("ASSESSMENT_BACKBONE", "microsoft/wavlm-large")
OUTPUT_NAMES = ("accuracy", "fluency", "prosody", "completeness", "overall")

LABEL_ALIASES = {
    "accuracy": ("accuracy", "pron_accuracy", "phone_score"),
    "fluency": ("fluency", "fluency_score"),
    "prosody": ("prosodic", "prosody", "prosody_score"),
    "completeness": ("completeness", "integrity", "integrity_score"),
    "overall": ("total_score", "total", "overall", "score"),
}


def _seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.backends.mps.is_available():
        torch.mps.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def _checkpoint_val_loss(path: Path) -> float | None:
    if not path.exists():
        return None
    try:
        checkpoint = torch.load(path, map_location="cpu", weights_only=False)
    except Exception as exc:  # pragma: no cover - defensive operational guard
        logger.warning("Could not inspect existing checkpoint %s: %s", path, exc)
        return None
    value = checkpoint.get("val_loss")
    return None if value is None else float(value)


def _pick_label(item: dict[str, Any], name: str) -> float | None:
    for key in LABEL_ALIASES[name]:
        if key in item and item[key] is not None:
            value = float(item[key])
            # Speechocean labels are commonly 0-10. Some variants use 0-100.
            return value * 10.0 if value <= 10.0 else value
    return None


def _load_samples(dataset_name: str, split_names: list[str], max_samples: int | None) -> list[dict]:
    from datasets import load_dataset

    samples: list[dict] = []
    for split in split_names:
        logger.info("Loading %s split=%s", dataset_name, split)
        ds = load_dataset(dataset_name, split=split, token=HF_TOKEN)
        for item in ds:
            labels = [_pick_label(item, name) for name in OUTPUT_NAMES]
            if all(v is None for v in labels):
                continue
            samples.append({"audio": item["audio"], "labels": labels})
            if max_samples and len(samples) >= max_samples:
                return samples
    return samples


def _resample_if_needed(audio_arr: np.ndarray, src_sr: int, target_sr: int = 16_000) -> np.ndarray:
    if src_sr == target_sr:
        return audio_arr.astype(np.float32)
    wav_t = torch.from_numpy(audio_arr.astype(np.float32)).unsqueeze(0)
    return torchaudio.functional.resample(wav_t, src_sr, target_sr).squeeze(0).numpy().astype(np.float32)


@torch.inference_mode()
def _build_feature_cache(
    cache_path: Path,
    dataset_name: str,
    splits: list[str],
    model_id: str,
    batch_size: int,
    max_samples: int | None,
) -> dict:
    if cache_path.exists():
        logger.info("Loading cached assessment features: %s", cache_path)
        return torch.load(cache_path, map_location="cpu", weights_only=False)

    samples = _load_samples(dataset_name, splits, max_samples)
    if not samples:
        raise RuntimeError("No labeled samples found.")
    logger.info("Extracting WavLM embeddings for %d samples", len(samples))

    extractor = AutoFeatureExtractor.from_pretrained(model_id, token=HF_TOKEN)
    backbone = AutoModel.from_pretrained(model_id, token=HF_TOKEN).to(DEVICE).eval()

    embeddings: list[torch.Tensor] = []
    audio_features: list[np.ndarray] = []
    labels: list[list[float]] = []
    masks: list[list[float]] = []

    for start in range(0, len(samples), batch_size):
        batch = samples[start:start + batch_size]
        wavs = []
        for item in batch:
            arr = np.asarray(item["audio"]["array"], dtype=np.float32)
            sr = int(item["audio"]["sampling_rate"])
            wav = _resample_if_needed(arr, sr)
            wavs.append(wav)
            audio_features.append(extract_audio_features(wav))
            row = [0.0 if value is None else float(value) for value in item["labels"]]
            mask = [0.0 if value is None else 1.0 for value in item["labels"]]
            labels.append(row)
            masks.append(mask)

        inputs = extractor(wavs, sampling_rate=16_000, return_tensors="pt", padding=True)
        out = backbone(inputs.input_values.to(DEVICE), attention_mask=inputs.get("attention_mask", None).to(DEVICE) if "attention_mask" in inputs else None)
        emb = out.last_hidden_state.mean(dim=1).detach().cpu()
        embeddings.extend([e for e in emb])
        if (start // batch_size + 1) % 10 == 0:
            logger.info("  embedded %d/%d", min(start + batch_size, len(samples)), len(samples))

    data = {
        "embeddings": torch.stack(embeddings),
        "audio_features": torch.from_numpy(np.stack(audio_features)).float(),
        "labels": torch.tensor(labels, dtype=torch.float32),
        "masks": torch.tensor(masks, dtype=torch.float32),
        "output_names": OUTPUT_NAMES,
        "model_id": model_id,
    }
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(data, cache_path)
    logger.info("Saved feature cache: %s", cache_path)
    return data


class AssessmentDataset(Dataset):
    def __init__(self, data: dict):
        self.X = torch.cat([data["embeddings"].float(), data["audio_features"].float()], dim=1)
        self.y = data["labels"].float()
        self.mask = data["masks"].float()

    def __len__(self):
        return len(self.X)

    def __getitem__(self, idx):
        return self.X[idx], self.y[idx], self.mask[idx]


def _masked_mse(pred: torch.Tensor, target: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    loss = torch.square(pred - target) * mask
    return loss.sum() / mask.sum().clamp_min(1.0)


def train(args: argparse.Namespace) -> None:
    split_seed = args.split_seed if args.split_seed is not None else args.seed
    init_seed = args.init_seed if args.init_seed is not None else args.seed
    _seed_everything(init_seed)
    t0 = time.time()
    cache_path = Path(args.cache)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    data = _build_feature_cache(
        cache_path=cache_path,
        dataset_name=args.dataset,
        splits=args.splits.split(","),
        model_id=args.model,
        batch_size=args.embed_batch_size,
        max_samples=args.max_samples,
    )
    dataset = AssessmentDataset(data)
    n_val = max(1, int(len(dataset) * args.val_fraction))
    n_train = len(dataset) - n_val
    split_generator = torch.Generator().manual_seed(split_seed)
    train_ds, val_ds = random_split(dataset, [n_train, n_val], generator=split_generator)
    loader_generator = torch.Generator().manual_seed(init_seed)
    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True, generator=loader_generator)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size)

    input_dim = dataset.X.shape[1]
    model = MultiAspectHead(input_dim=input_dim, output_dim=len(OUTPUT_NAMES)).to(DEVICE)
    opt = AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    existing_best = None if args.force_overwrite else _checkpoint_val_loss(out_path)
    best_val = float("inf") if existing_best is None else existing_best
    if existing_best is not None:
        logger.info(
            "Existing checkpoint val=%.3f; this run will only replace it if validation improves.",
            existing_best,
        )
    patience = 0
    saved_this_run = False
    run_best_val = float("inf")

    for epoch in range(1, args.epochs + 1):
        model.train()
        train_losses = []
        for X, y, mask in train_loader:
            X, y, mask = X.to(DEVICE), y.to(DEVICE), mask.to(DEVICE)
            opt.zero_grad(set_to_none=True)
            loss = _masked_mse(model(X), y, mask)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            train_losses.append(float(loss.item()))

        model.eval()
        val_losses = []
        abs_err = []
        with torch.no_grad():
            for X, y, mask in val_loader:
                X, y, mask = X.to(DEVICE), y.to(DEVICE), mask.to(DEVICE)
                pred = model(X)
                val_losses.append(float(_masked_mse(pred, y, mask).item()))
                abs_err.append(float((torch.abs(pred - y) * mask).sum().item() / mask.sum().clamp_min(1.0).item()))

        val_loss = float(np.mean(val_losses))
        mae = float(np.mean(abs_err))
        run_best_val = min(run_best_val, val_loss)
        logger.info(
            "epoch=%03d train=%.3f val=%.3f mae=%.2f/100 elapsed=%.1fmin",
            epoch,
            float(np.mean(train_losses)),
            val_loss,
            mae,
            (time.time() - t0) / 60,
        )

        if val_loss < best_val:
            best_val = val_loss
            patience = 0
            torch.save(
                {
                    "model_state_dict": model.state_dict(),
                    "input_dim": input_dim,
                    "embedding_dim": data["embeddings"].shape[1],
                    "audio_feature_dim": data["audio_features"].shape[1],
                    "output_names": OUTPUT_NAMES,
                    "val_loss": val_loss,
                    "val_mae": mae,
                    "backbone": args.model,
                    "dataset": args.dataset,
                    "split_seed": split_seed,
                    "init_seed": init_seed,
                },
                out_path,
            )
            saved_this_run = True
            logger.info("  saved %s", out_path)
        else:
            patience += 1
            if patience >= args.patience:
                logger.info("early stopping")
                break
    if not saved_this_run:
        logger.info("Finished without replacing existing checkpoint; best run val=%.3f", run_best_val)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="jbpark0614/speechocean762")
    parser.add_argument("--splits", default="train,test")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--cache", default="checkpoints/assessment_features.pt")
    parser.add_argument("--output", default="checkpoints/assessment_head_best.pt")
    parser.add_argument("--max-samples", type=int)
    parser.add_argument("--embed-batch-size", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--lr", type=float, default=8e-4)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--val-fraction", type=float, default=0.15)
    parser.add_argument("--patience", type=int, default=8)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--split-seed", type=int)
    parser.add_argument("--init-seed", type=int)
    parser.add_argument("--force-overwrite", action="store_true", help="Ignore any existing checkpoint at --output.")
    train(parser.parse_args())


if __name__ == "__main__":
    main()
