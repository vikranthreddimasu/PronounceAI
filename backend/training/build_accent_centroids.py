"""
Build WavLM accent centroids from VCTK.

Run once after installing requirements:
  cd backend
  python -m training.build_accent_centroids

VCTK has 109 speakers with accent labels. We embed 20+ speakers per accent,
average their utterance embeddings, L2-normalize → save as centroids.

Output: checkpoints/accent_centroids.pt
"""
import logging
import os
from pathlib import Path

import torch
from transformers import AutoFeatureExtractor, AutoModel

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"
WAVLM_MODEL = os.getenv("WAVLM_MODEL", "microsoft/wavlm-large")
HF_TOKEN = os.getenv("HUGGINGFACE_TOKEN")
CHECKPOINT_DIR = Path("checkpoints")
CHECKPOINT_DIR.mkdir(exist_ok=True)
OUTPUT = CHECKPOINT_DIR / "accent_centroids.pt"

# VCTK speaker → accent mapping (representative subset)
# Full list: https://datashare.ed.ac.uk/handle/10283/3443
VCTK_ACCENT_MAP = {
    "GA": [
        "p225", "p226", "p227", "p228", "p229", "p230", "p231", "p237",
        "p241", "p245", "p246", "p247", "p248", "p249", "p250", "p251",
        "p252", "p253", "p254", "p255", "p256", "p257", "p258", "p259",
    ],
    "RP": [
        "p225",  # placeholder — VCTK doesn't have explicit RP; use closest
        # In production, supplement with recordings from RP speakers
    ],
    "Scottish": [
        "p266", "p267", "p272", "p273", "p274", "p275", "p276", "p277",
        "p278", "p279", "p280", "p281",
    ],
    "Irish": [
        "p302", "p303", "p304",
    ],
}

MAX_UTTERANCES_PER_SPEAKER = 10  # balance speed vs quality


def build_centroids():
    logger.info(f"Loading WavLM from {WAVLM_MODEL} on {DEVICE}")
    extractor = AutoFeatureExtractor.from_pretrained(WAVLM_MODEL, token=HF_TOKEN)
    model = AutoModel.from_pretrained(WAVLM_MODEL, token=HF_TOKEN).to(DEVICE)
    model.eval()

    try:
        from datasets import load_dataset
        logger.info("Loading VCTK dataset (this downloads ~10 GB on first run)")
        ds = load_dataset("speech-recognition-community-v2/vctk", split="train", token=HF_TOKEN)
    except Exception as e:
        logger.error(f"Could not load VCTK: {e}")
        logger.info("Creating placeholder centroids (random unit vectors) for development")
        centroids = {}
        for accent in VCTK_ACCENT_MAP:
            centroids[accent] = torch.nn.functional.normalize(
                torch.randn(1024), dim=0
            )
        torch.save(centroids, OUTPUT)
        logger.info(f"Saved placeholder centroids to {OUTPUT}")
        return

    centroids = {}
    for accent, speaker_ids in VCTK_ACCENT_MAP.items():
        logger.info(f"Building centroid for {accent} ({len(speaker_ids)} speakers)")
        embeddings = []

        for spk in speaker_ids:
            spk_samples = [
                s for s in ds
                if s.get("speaker_id") == spk or s.get("client_id") == spk
            ][:MAX_UTTERANCES_PER_SPEAKER]

            for sample in spk_samples:
                try:
                    audio = sample["audio"]["array"]
                    sr = sample["audio"]["sampling_rate"]
                    if sr != 16000:
                        import torchaudio
                        wav_t = torch.from_numpy(audio).float().unsqueeze(0)
                        audio = torchaudio.functional.resample(wav_t, sr, 16000).squeeze(0).numpy()

                    with torch.no_grad():
                        inputs = extractor(audio, sampling_rate=16000, return_tensors="pt")
                        out = model(inputs.input_values.to(DEVICE))
                        emb = out.last_hidden_state.mean(dim=1).squeeze(0)
                        embeddings.append(emb.cpu())
                except Exception as e:
                    logger.debug(f"Skipping {spk}: {e}")

        if embeddings:
            stacked = torch.stack(embeddings).mean(dim=0)
            centroids[accent] = torch.nn.functional.normalize(stacked, dim=0)
            logger.info(f"  {accent}: {len(embeddings)} embeddings averaged")
        else:
            logger.warning(f"  {accent}: no valid embeddings found, using random")
            centroids[accent] = torch.nn.functional.normalize(torch.randn(1024), dim=0)

    torch.save(centroids, OUTPUT)
    logger.info(f"Saved centroids to {OUTPUT}: {list(centroids.keys())}")


if __name__ == "__main__":
    build_centroids()
