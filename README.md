# PronounceAI

A pronunciation coach that tells you *why*. Practice a line and get phoneme-level feedback, scores (clarity-related dimensions), transcript alignment, optional pitch overlays, and a calm coaching summary. **Voice Lab** lets you enrol a short voice profile and hear arbitrary text in your timbre toward a target accent (CosyVoice + Kokoro pipelines on the backend).

## Repo layout

```
PronounceAI/
├── backend/           # FastAPI service — scoring, TTS, voice enrollment, accent tools
├── frontend/          # Next.js app (Practice, Voice Lab, Progress, Settings, …)
├── docs/              # Design / planning notes
├── API.md             # HTTP contract the frontend consumes
└── README.md
```

Older notebooks or training helpers may live under `backend/training` and `backend/evaluation`; the running product is **`backend/app`** + **`frontend`**.

## Run the frontend

```bash
cd frontend
npm install
npm run dev
```

Visit `http://localhost:3000`. With no backend configured the app runs in **demo mode** — scores are mocked, and native reference playback uses the browser’s Speech Synthesis API so the UI is usable end-to-end.

To use the live API:

```bash
cd frontend
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 npm run dev
```

Copy `frontend/.env.example` to `.env.local` and set `NEXT_PUBLIC_API_URL` there if you prefer.

## Run the backend

From `backend/` (Python env with deps installed per your setup):

```bash
# Typical local run (adjust host/port as needed)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Use `backend/.env.example` as a template for `backend/.env.local`. Model checkpoints and CUDA/MPS settings are documented in those files.

See [`API.md`](./API.md) for routes and payloads.

## Deploy

Use Vercel for the Next.js frontend and Daytona for the long-running FastAPI
backend. The backend has local PyTorch/audio models, so it should run as a
container rather than as serverless functions.

See [`docs/DEPLOYMENT.md`](./docs/DEPLOYMENT.md) for the exact backend Docker
setup, Vercel environment variables, and final-submission fallback plan.

## Main user flows

- **Practice** (`/practice`) — Pick or type a phrase, hear target TTS (`/api/tts`), record, **`POST /api/score`**, review phonemes and prosody cues. Progress is stored only in **localStorage** (no accounts).
- **Voice Lab** (`/studio`) — Enrol with **`POST /api/voice/enroll`**, then **`POST /api/voice/speak`** for playback with timings. Requires the voice-clone stack to be loaded on the server.
- **Progress / Settings** — Read and clear local session stats and preferences.

## Intentional v1 boundaries

Designed as a tight feedback loop without server-side accounts: history and voice handles live in the browser; the backend holds enrollment WAVs keyed by opaque `user_id`. Features such as synced history, teams, or multi-device profiles would need an auth and storage layer on top.
