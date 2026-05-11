"""
Fine-tune: frozen wav2vec2-large-robust-L2 backbone + 2-layer MLP regression head
trained on speechocean762 utterance-level accuracy ratings.

Dataset note: the HuggingFace version of speechocean762 (jbpark0614/speechocean762)
provides utterance-level scores only — accuracy, fluency, prosodic, total_score (all 0-10).
Per-phoneme scores were omitted from this upload. We train on utterance-level `accuracy`.

What the regression head learns:
  GOP feature vector (top-N mean log-probs from the CTC backbone)
  → predicted utterance accuracy score (0-100)

This calibrates raw GOP log-probabilities against human judgement (speechocean762
was human-rated by trained annotators). Without this calibration, raw GOP values
need hand-tuned thresholds; after training, scores correlate with actual human ratings.

Run on M5 Pro (~2-3 hours):
  cd backend
  source .venv/bin/activate
  python -m training.train_phoneme_scorer
"""
import logging
import os
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.optim import AdamW
from torch.utils.data import DataLoader, Dataset, random_split
from transformers import AutoProcessor, AutoModelForCTC

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"
MODEL_ID = os.getenv("WAV2VEC2_MODEL", "slplab/wav2vec2-large-robust-L2-english-phoneme-recognition")
HF_TOKEN = os.getenv("HUGGINGFACE_TOKEN")  # not required — dataset is public

CHECKPOINT_DIR = Path("checkpoints")
CHECKPOINT_DIR.mkdir(exist_ok=True)
BEST_CHECKPOINT = CHECKPOINT_DIR / "phoneme_scorer_best.pt"
FEATURE_CACHE = CHECKPOINT_DIR / "speechocean762_features.pt"

BATCH_SIZE = 32
EPOCHS = 40
LR = 1e-3
WEIGHT_DECAY = 1e-4
PATIENCE = 6
VAL_FRACTION = 0.15
GOP_FEATURE_DIM = None    # set at runtime from actual vocab size (typically ~44 for phoneme models)


# ---------------------------------------------------------------------------
# Feature extraction (run once, cached to disk)
# ---------------------------------------------------------------------------
def extract_features_cached(processor, model, device: str) -> tuple[torch.Tensor, torch.Tensor]:
    """
    Return (features [N, GOP_FEATURE_DIM], targets [N]) from speechocean762.
    Features are cached to FEATURE_CACHE so subsequent runs are instant.
    """
    global GOP_FEATURE_DIM  # resolved from vocab size on first forward pass, or from cache

    if FEATURE_CACHE.exists():
        logger.info(f"Loading cached features from {FEATURE_CACHE}")
        data = torch.load(FEATURE_CACHE, map_location="cpu")
        GOP_FEATURE_DIM = data.get("feat_dim", data["features"].shape[1])
        logger.info(f"Feature dim from cache: {GOP_FEATURE_DIM}")
        return data["features"], data["targets"]

    from datasets import load_dataset
    logger.info("Loading speechocean762 (public dataset, ~620 MB)…")
    ds_train = load_dataset("jbpark0614/speechocean762", split="train", token=HF_TOKEN)
    ds_test  = load_dataset("jbpark0614/speechocean762", split="test",  token=HF_TOKEN)
    all_samples = list(ds_train) + list(ds_test)
    logger.info(f"Total samples: {len(all_samples)}")

    model.eval()
    features, targets = [], []
    n_skipped = 0
    feat_dim_set = False

    for i, item in enumerate(all_samples):
        try:
            audio_arr = np.array(item["audio"]["array"], dtype=np.float32)
            sr = item["audio"]["sampling_rate"]

            if sr != 16000:
                import torchaudio
                wav_t = torch.from_numpy(audio_arr).unsqueeze(0)
                audio_arr = torchaudio.functional.resample(wav_t, sr, 16000).squeeze(0).numpy()

            accuracy = float(item["accuracy"]) / 10.0

            with torch.no_grad():
                inputs = processor(
                    audio_arr,
                    sampling_rate=16000,
                    return_tensors="pt",
                    padding=True,
                )
                logits = model(inputs.input_values.to(device)).logits  # [1, T, vocab]
                log_probs = torch.log_softmax(logits[0], dim=-1)       # [T, vocab]

            vocab_size = log_probs.shape[-1]
            if not feat_dim_set:
                GOP_FEATURE_DIM = vocab_size
                feat_dim_set = True
                logger.info(f"Vocab size detected: {vocab_size} → feature dim = {vocab_size}")

            # Mean log-prob over frames for each phoneme class = GOP feature vector
            feat = log_probs.mean(dim=0).cpu().numpy().astype(np.float32)  # [vocab]

            features.append(feat)
            targets.append(np.float32(accuracy))

            if (i + 1) % 200 == 0:
                logger.info(f"  Processed {i+1}/{len(all_samples)} ({n_skipped} skipped)")

        except Exception as e:
            n_skipped += 1
            if n_skipped <= 5:
                logger.warning(f"Skipping sample {i}: {e}")

    logger.info(f"Extraction done: {len(features)} features, {n_skipped} skipped")

    feat_tensor = torch.from_numpy(np.stack(features))
    tgt_tensor  = torch.from_numpy(np.array(targets, dtype=np.float32))

    torch.save({"features": feat_tensor, "targets": tgt_tensor, "feat_dim": GOP_FEATURE_DIM}, FEATURE_CACHE)
    logger.info(f"Cached features to {FEATURE_CACHE} (dim={GOP_FEATURE_DIM})")
    return feat_tensor, tgt_tensor


# ---------------------------------------------------------------------------
# Dataset wrapper
# ---------------------------------------------------------------------------
class GOPDataset(Dataset):
    def __init__(self, features: torch.Tensor, targets: torch.Tensor):
        self.X = features
        self.y = targets

    def __len__(self):
        return len(self.X)

    def __getitem__(self, idx):
        return self.X[idx], self.y[idx]


# ---------------------------------------------------------------------------
# MLP regression head
# ---------------------------------------------------------------------------
class MLPHead(nn.Module):
    def __init__(self, input_dim: int = GOP_FEATURE_DIM):
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
        return self.net(x).squeeze(-1)  # [B] in [0, 1]


# ---------------------------------------------------------------------------
# Training loop
# ---------------------------------------------------------------------------
def train():
    logger.info(f"Device: {DEVICE}")
    if DEVICE == "mps":
        logger.info("Apple Silicon MPS backend active")

    # Load frozen backbone
    logger.info(f"Loading backbone: {MODEL_ID}")
    processor = AutoProcessor.from_pretrained(MODEL_ID, token=HF_TOKEN)
    backbone  = AutoModelForCTC.from_pretrained(MODEL_ID, token=HF_TOKEN).to(DEVICE)
    backbone.eval()
    for p in backbone.parameters():
        p.requires_grad = False
    n_params = sum(p.numel() for p in backbone.parameters()) / 1e6
    logger.info(f"Backbone frozen ({n_params:.0f}M params)")

    # Extract / load features
    features, targets = extract_features_cached(processor, backbone, DEVICE)
    logger.info(f"Feature shape: {features.shape}, feat_dim: {GOP_FEATURE_DIM}, target range: [{targets.min():.2f}, {targets.max():.2f}]")

    # Train / val split
    n_val = max(1, int(len(features) * VAL_FRACTION))
    n_train = len(features) - n_val
    full_ds = GOPDataset(features, targets)
    train_ds, val_ds = random_split(full_ds, [n_train, n_val],
                                     generator=torch.Generator().manual_seed(42))

    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True,  num_workers=0, pin_memory=False)
    val_loader   = DataLoader(val_ds,   batch_size=BATCH_SIZE, shuffle=False, num_workers=0, pin_memory=False)
    logger.info(f"Train: {n_train} | Val: {n_val}")

    # Model + optimiser (feat_dim resolved after extract_features_cached sets GOP_FEATURE_DIM)
    head = MLPHead(input_dim=GOP_FEATURE_DIM).to(DEVICE)
    optimizer = AdamW(head.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
    scheduler = torch.optim.lr_scheduler.OneCycleLR(
        optimizer, max_lr=LR, epochs=EPOCHS, steps_per_epoch=len(train_loader)
    )
    criterion = nn.MSELoss()

    best_val_loss = float("inf")
    patience_ctr  = 0
    t_start       = time.time()

    for epoch in range(1, EPOCHS + 1):
        # --- Train ---
        head.train()
        train_losses = []
        for X, y in train_loader:
            X, y = X.to(DEVICE), y.to(DEVICE)
            optimizer.zero_grad()
            loss = criterion(head(X), y)
            loss.backward()
            nn.utils.clip_grad_norm_(head.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            train_losses.append(loss.item())

        # --- Validate ---
        head.eval()
        val_losses, abs_errs = [], []
        with torch.no_grad():
            for X, y in val_loader:
                X, y = X.to(DEVICE), y.to(DEVICE)
                preds = head(X)
                val_losses.append(criterion(preds, y).item())
                abs_errs.append((preds - y).abs().mean().item())

        tl = np.mean(train_losses)
        vl = np.mean(val_losses)
        mae_pts = np.mean(abs_errs) * 10   # convert 0-1 → 0-10 scale (matches original rating)
        elapsed = (time.time() - t_start) / 60

        logger.info(
            f"Epoch {epoch:2d}/{EPOCHS} | "
            f"train={tl:.4f} val={vl:.4f} | "
            f"MAE={mae_pts:.2f}pts/10 | "
            f"{elapsed:.1f}min elapsed"
        )

        if vl < best_val_loss:
            best_val_loss = vl
            patience_ctr  = 0
            torch.save(
                {
                    "model_state_dict": head.state_dict(),
                    "input_dim": GOP_FEATURE_DIM,
                    "val_loss": vl,
                    "mae_pts": mae_pts,
                    "epoch": epoch,
                    "model_id": MODEL_ID,
                },
                BEST_CHECKPOINT,
            )
            logger.info(f"  ✓ Saved checkpoint (val={vl:.4f}, MAE={mae_pts:.2f}pts)")
        else:
            patience_ctr += 1
            if patience_ctr >= PATIENCE:
                logger.info(f"Early stopping at epoch {epoch} (patience={PATIENCE})")
                break

    total_min = (time.time() - t_start) / 60
    logger.info(f"Training done in {total_min:.1f}min. Best val_loss={best_val_loss:.4f}")
    logger.info(f"Checkpoint saved to: {BEST_CHECKPOINT}")


if __name__ == "__main__":
    train()
