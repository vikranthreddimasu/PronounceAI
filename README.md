# PronounceAI

A pronunciation coach that tells you *why*. Record a phrase; see a transcript, a 0–100 score, and which of three dimensions — clarity, pitch, energy — to fix.

## Repo layout

```
PronounceAI/
├── model/
│   ├── module_1/   # Whisper STT (transcript)
│   └── module_2/   # Acoustic feature scoring (per-dimension)
├── frontend/       # Next.js single-screen app (this is what users see)
├── API.md          # Backend contract the frontend expects
└── README.md
```

The two `model/` modules document the ML pipeline (notebooks). The `frontend/` is the deployable product surface.

## Run the frontend

```bash
cd frontend
npm install
npm run dev
```

Visit `http://localhost:3000`. With no backend configured the app runs in **demo mode** — scores are fabricated but plausible, and native playback uses the browser's TTS so the full UI is exercisable end-to-end.

To wire it to the real backend (Module 1 + Module 2 served as one HTTP service):

```bash
cd frontend
NEXT_PUBLIC_API_URL=http://<host>:<port> npm run dev
```

See [`API.md`](./API.md) for the exact contract the backend must implement.

## What v1 is — and isn't

**Is**: one screen. Pick a phrase, hear native, record yourself, see score + three dimension bars + one line of feedback. 20 built-in phrases, easy to hard.

**Isn't**: accounts, history, streaks, custom phrases, multi-language, waveform visualisations. Cut intentionally; can be added when the loop is proven.
