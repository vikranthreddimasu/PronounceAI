#!/usr/bin/env bash
# One-time backend setup for M5 Pro (Apple Silicon).
# Run from the backend/ directory: ./setup.sh

set -euo pipefail
echo "==> PronounceAI backend setup (Apple Silicon)"

# 1. Python env
if ! command -v python3 &>/dev/null; then
  echo "ERROR: python3 not found. Install via: brew install python@3.11"
  exit 1
fi

PYTHON=$(command -v python3.11 || command -v python3)
echo "Using Python: $($PYTHON --version)"

if [ ! -d .venv ]; then
  $PYTHON -m venv .venv
fi
source .venv/bin/activate

# 2. Install PyTorch for Apple Silicon first (MPS backend)
pip install --quiet --upgrade pip
echo "==> Installing PyTorch (MPS/Apple Silicon)..."
pip install --quiet torch==2.5.1 torchaudio==2.5.1

# 3. Install everything else
echo "==> Installing dependencies..."
pip install --quiet -r requirements.txt

# 4. Install g2p-en (ARPAbet G2P) + NLTK data + phonemizer
echo "==> Installing phonemizer..."
pip install --quiet g2p-en phonemizer
# Download required NLTK data for g2p-en
python3 -c "import nltk; nltk.download('averaged_perceptron_tagger_eng', quiet=True); nltk.download('cmudict', quiet=True)"
if ! command -v espeak-ng &>/dev/null; then
  echo "  espeak-ng not found — installing via Homebrew (used by phonemizer fallback)"
  brew install espeak-ng || echo "  WARNING: espeak-ng install failed; g2p-en is the primary anyway"
fi

# 5. Download silero-vad ONNX model
echo "==> Downloading Silero VAD..."
python3 -c "
import os, urllib.request, hashlib
url = 'https://models.silero.ai/models/en/en_v6.jit'
dst = 'checkpoints/silero_vad.jit'
os.makedirs('checkpoints', exist_ok=True)
if not os.path.exists(dst):
    print('  Downloading silero-vad...')
    urllib.request.urlretrieve(url, dst)
    print(f'  Saved to {dst}')
else:
    print(f'  Already exists: {dst}')
" 2>/dev/null || echo "  Silero download skipped (will use onnxruntime fallback)"

# 6. Copy env file if not present
if [ ! -f .env.local ]; then
  cp .env.example .env.local
  echo "==> Created .env.local — fill in your API keys before running the server"
fi

echo ""
echo "==> Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Fill in .env.local if you need a HuggingFace token for private downloads"
echo "  2. Start the server:  source .venv/bin/activate && uvicorn app.main:app --reload --port 8000"
echo "  3. Fine-tune (optional, ~3h): python -m training.train_phoneme_scorer"
echo "  4. Build accent centroids: python -m training.build_accent_centroids"
