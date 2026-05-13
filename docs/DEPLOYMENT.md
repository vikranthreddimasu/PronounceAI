# Local Container Runbook

This project has a stable local Docker path for reproducible demos and review.
Production hosting is intentionally not documented here because that setup is
still evolving.

## What Docker Runs

- `backend/Dockerfile` builds the FastAPI ML service.
- `frontend/Dockerfile` builds a Next.js development server.
- `docker-compose.yml` runs both services together on localhost.

The backend image defaults to CPU-safe settings:

- phoneme scoring enabled through the public wav2vec2 phoneme model
- Kokoro reference TTS enabled
- Whisper transcript grounding disabled by default
- WavLM accent-distance loading disabled by default
- CosyVoice voice cloning disabled by default

This keeps the first run reproducible from a clean checkout. Optional checkpoints
and heavier models can still be enabled through environment variables.

## Run Everything

From the repository root:

```bash
docker compose up --build
```

Open:

```text
http://localhost:3000
```

The frontend calls the backend at:

```text
http://localhost:8000
```

Health check:

```bash
curl http://localhost:8000/health
```

## Backend-Only Docker

```bash
cd backend
docker build -t pronounceai-backend .
docker run --rm -p 8000:8000 --env-file .env.production.example pronounceai-backend
```

If you use the backend-only command, set `CORS_ORIGINS=http://localhost:3000`
when running the frontend separately.

## Persistent Runtime Data

The compose file uses named volumes for:

- Hugging Face and model caches: `/app/.cache/huggingface`
- native pitch contour cache: `/app/cache/native_f0`
- local voice enrollments: `/app/data/enrollments`

These volumes avoid repeated model downloads and preserve local voice profiles
between container restarts.

## Optional Heavier Modes

Enable transcript/WER grounding:

```bash
LOAD_WHISPER=1
SCORE_ASR_MODE=fast
```

Enable formant extraction:

```bash
SCORE_INCLUDE_FORMANTS=1
```

Enable WavLM embedding/accent-distance work only when centroids or learned
assessment checkpoints are available:

```bash
SCORE_WAVLM_MODE=auto
FORCE_WAVLM_ENGINE=1
```

Enable CosyVoice voice cloning only in a compatible local macOS/Python setup.
The slim Docker image intentionally leaves it off because the voice clone path
depends on `mlx-audio-plus`, which is Apple Silicon oriented and not part of the
portable CPU container.
