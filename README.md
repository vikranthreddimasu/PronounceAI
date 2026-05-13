# PronounceAI

PronounceAI is an AI pronunciation and voice-coaching system for English accent practice. It combines a Next.js frontend with a FastAPI speech backend to score spoken phrases at phoneme level, compare pitch movement against a native reference, track local progress, and generate accent-targeted reference audio.

The project is designed as a reproducible local AI product: the frontend can run in demo mode without a backend, while the live backend loads speech models for scoring, TTS, enrollment, and optional voice/accent workflows.

## Core Capabilities

- **Phoneme-level pronunciation scoring** using a wav2vec2 CTC phoneme model and forced alignment.
- **Prosody analysis** for intonation, rhythm, speech rate, and optional vowel formants.
- **Native reference audio** through Kokoro TTS for target-accent playback.
- **Pitch contour overlays** comparing learner F0 against a synthesized native reference.
- **Transcript grounding** with optional faster-whisper phrase matching and WER gates.
- **Voice Lab** for multi-take voice enrollment and target-accent speech generation.
- **Local progress tracking** for sessions, streaks, and per-phoneme mastery.
- **Dockerized local run path** for reproducible review by TAs, professors, and contributors.

## Architecture

```text
Browser / Next.js
  - Practice UI, Voice Lab, Progress, Settings
  - MediaRecorder audio capture
  - localStorage profile, sessions, streaks, voice handle
  - API client caches and demo-mode fallback

FastAPI Backend
  - /api/score pronunciation assessment
  - /api/tts native reference TTS
  - /api/voice/* voice enrollment and speech
  - /api/accent-convert and /api/accent-clone optional accent tools

Speech / ML Runtime
  - wav2vec2 phoneme CTC + forced alignment
  - g2p-en text-to-phoneme conversion
  - Parselmouth/librosa prosody analysis
  - Kokoro TTS native references
  - optional faster-whisper, WavLM, learned assessment heads, kNN-VC, CosyVoice
```

## Tech Stack

| Layer | Implementation |
| --- | --- |
| Frontend | Next.js 16, React 19, TypeScript, CSS/Tailwind v4 tooling |
| Audio capture | Browser `MediaRecorder`, WebAudio level metering |
| Backend API | FastAPI, Uvicorn, Pydantic, python-multipart |
| Core speech model | `slplab/wav2vec2-large-robust-L2-english-phoneme-recognition` |
| Text to phonemes | `g2p-en`, CMUdict/NLTK, optional phonemizer/espeak-ng |
| ASR | optional `faster-whisper` |
| TTS | Kokoro 82M |
| Prosody | Parselmouth/Praat, librosa, scipy/numpy |
| Embeddings | optional WavLM Large |
| Voice/accent tools | optional kNN-VC and CosyVoice path |
| Storage | Browser localStorage plus backend filesystem voice enrollment store |
| Containers | Dockerfile for backend, Dockerfile for frontend, root `docker-compose.yml` |

## Repository Structure

```text
PronounceAI/
|-- README.md
|-- report.md
|-- API.md
|-- docker-compose.yml
|-- docs/
|   |-- DEPLOYMENT.md          # Stable local container runbook
|   `-- REDESIGN_PLAN.md       # Historical design/research notes
|-- backend/
|   |-- Dockerfile
|   |-- requirements.txt
|   |-- requirements.prod.txt
|   |-- setup.sh
|   |-- app/
|   |   |-- main.py            # FastAPI app, CORS, lifespan model loading
|   |   |-- api/               # HTTP routes
|   |   |-- models/            # Speech, scoring, TTS/voice model wrappers
|   |   `-- utils/             # Audio, text metrics, voice store, native F0 cache
|   |-- training/              # Speechocean/WavLM training utilities
|   |-- evaluation/            # Local score API evaluator
|   |-- scripts/               # VCTK/kNN-VC pool builder
|   `-- tests/                 # Backend unit tests
`-- frontend/
    |-- Dockerfile
    |-- package.json
    |-- next.config.ts
    `-- src/
        |-- app/               # App Router pages
        |-- components/        # Practice, scoring, voice, visualization UI
        `-- lib/               # API client, recorder, store, voice profile logic
```

## Quick Start With Docker

Docker is the most reproducible path for review.

```bash
docker compose up --build
```

Open:

```text
http://localhost:3000
```

Backend health check:

```bash
curl http://localhost:8000/health
```

Notes:

- The first backend run may take several minutes while public speech models download.
- Compose uses named volumes for model caches, native F0 cache, and local voice enrollments.
- The default container mode keeps Whisper, WavLM, and CosyVoice voice cloning disabled for CPU-safe reproducibility.
- See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for the stable local container runbook.

## Local Development

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Visit `http://localhost:3000`.

If `NEXT_PUBLIC_API_URL` is empty, the app runs in demo mode with mock scoring and browser speech synthesis:

```bash
cp .env.example .env.local
```

To connect to a live backend:

```bash
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 npm run dev
```

### Backend

Python 3.11 is recommended.

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install torch==2.5.1 torchaudio==2.5.1
pip install -r requirements.txt
cp .env.example .env.local
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

On Apple Silicon, `backend/setup.sh` automates the local MPS-oriented setup.

## Environment Variables

### Frontend

| Variable | Purpose |
| --- | --- |
| `NEXT_PUBLIC_API_URL` | Backend origin, for example `http://127.0.0.1:8000`. Empty means demo mode. |
| `NEXT_PUBLIC_USE_MOCK` | Set to `1` to force mock mode even when an API URL is present. |

### Backend

| Variable | Default / Example | Purpose |
| --- | --- | --- |
| `DEVICE` | `mps`, `cuda`, or `cpu` | Torch device for core models. |
| `CORS_ORIGINS` | `http://localhost:3000` | Browser origins allowed to call the API. |
| `WAV2VEC2_MODEL` | `slplab/wav2vec2-large-robust-L2-english-phoneme-recognition` | Phoneme CTC model. |
| `WHISPER_MODEL` | `large-v3-turbo` locally, `small.en` in Docker defaults | faster-whisper model. |
| `LOAD_WHISPER` | `1` locally, `0` in Docker defaults | Enables transcript/WER grounding. |
| `LOAD_VOICE_CLONE` | `1` locally, `0` in Docker defaults | Enables CosyVoice voice cloning when dependencies are available. |
| `SCORE_ASR_MODE` | `off`, `fast`, or `words` | Controls transcript path in `/api/score`. |
| `SCORE_INCLUDE_FORMANTS` | `0` or `1` | Enables slower vowel formant extraction. |
| `SCORE_WAVLM_MODE` | `auto` or `off` | Controls optional WavLM embedding/accent work. |
| `PHONEME_SCORER_CHECKPOINT` | `checkpoints/phoneme_scorer_best.pt` | Optional GOP calibration head. |
| `ASSESSMENT_SCORER_CHECKPOINT` | `checkpoints/assessment_head_best.pt` | Optional multi-aspect assessment head. |
| `ACCENT_CENTROIDS_PATH` | `checkpoints/accent_centroids.pt` | Optional WavLM accent centroids. |
| `ENROLLMENT_DIR` | `data/enrollments` | Filesystem store for voice profiles. |
| `NATIVE_F0_CACHE_DIR` | `cache/native_f0` | Disk cache for native pitch references. |

## Usage Guide

### Voice Lab

`/studio` is the default entry route. Users can enroll a short voice sample, choose General American or Received Pronunciation, write arbitrary English text, and render speech. When CosyVoice is unavailable, the backend can fall back to Kokoro target-accent audio.

### Practice

`/practice` provides phrase-based and custom-line recording. The flow is:

1. Select or type a phrase.
2. Optionally hear the target accent reference.
3. Record a take in the browser.
4. Submit to `POST /api/score`.
5. Review overall score, score dimensions, phoneme timeline, pitch overlay, transcript evidence, and coaching notes.

### Progress

`/progress` reads local session history and phoneme statistics from `localStorage`. There is no server-side account or cloud-synced progress layer.

### Settings

`/settings` controls target accent, native-language hint, theme, sound effects, voice profile management, and local reset.

## API Summary

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Backend health check. |
| `POST` | `/api/score` | Multipart recording assessment. |
| `POST` | `/api/prewarm` | Best-effort phrase/model cache warmup. |
| `GET` | `/api/tts` | Kokoro native reference WAV. |
| `POST` | `/api/accent-convert` | Optional kNN-VC accent conversion. |
| `POST` | `/api/accent-clone` | Optional personal accent clone flow. |
| `POST` | `/api/voice/enroll` | Add a voice enrollment take. |
| `GET` | `/api/voice/{user_id}` | Fetch enrollment summary. |
| `DELETE` | `/api/voice/{user_id}` | Delete enrollment. |
| `DELETE` | `/api/voice/{user_id}/takes/{take_id}` | Delete one take. |
| `POST` | `/api/voice/speak` | Render text through the voice workflow. |

See [API.md](API.md) for request fields and response details.

## Model Overview

The core scoring path is implemented in `backend/app/api/score.py`.

- Audio is decoded, quality-checked, resampled to 16 kHz mono, trimmed, and peak-normalized.
- `PhonemeEngine` converts reference text to ARPAbet phoneme IDs and aligns wav2vec2 CTC outputs to the expected phoneme sequence.
- GOP scores are mapped into phoneme accuracy, optionally through a learned calibration head.
- `ProsodyEngine` extracts F0, compares intonation with a Kokoro native pitch reference, estimates rhythm with nPVI, and can extract vowel formants.
- Optional faster-whisper transcript matching adds phrase-match and WER grounding gates.
- Optional WavLM embeddings support accent distance and the learned multi-aspect scorer when checkpoints are available.

Checkpoint files under `backend/checkpoints/` are intentionally gitignored except `.gitkeep`. A clean checkout still runs with public model downloads and deterministic fallbacks, but learned heads and accent centroids require local checkpoint files.

## Training And Evaluation

Implemented training utilities live under `backend/training/`:

- `train_phoneme_scorer.py` trains a small GOP regression head on `jbpark0614/speechocean762`.
- `train_multitask_assessment.py` trains a WavLM embedding plus acoustic-feature head for accuracy, fluency, prosody, completeness, and overall score.
- `build_accent_centroids.py` builds WavLM accent centroids from VCTK when available.

Evaluation support lives under `backend/evaluation/`:

```bash
cd backend
python -m evaluation.evaluate_score_api --manifest evaluation/score_manifest.jsonl
```

The evaluator is manifest-based and tracks latency, WER, phrase match, gates, and expected score bounds.

## Build, Test, Rebuild

Frontend:

```bash
cd frontend
npm run lint
npm run build
```

Backend:

```bash
cd backend
source .venv/bin/activate
PYTHONPATH=. python -m unittest discover -s tests
```

Docker rebuild:

```bash
docker compose build --no-cache
docker compose up
```

## Performance Notes

The codebase uses several practical latency controls:

- Backend model instances are loaded once in FastAPI lifespan and reused through `app.state`.
- `/api/score` runs independent phoneme, native-F0, Whisper, and WavLM work concurrently with `asyncio.to_thread`.
- Response, transcript, embedding, phrase-token, TTS, and native-F0 caches reduce repeated work.
- Frontend API helpers use small LRU caches and `AbortSignal` support to cancel stale playback/scoring work.
- Docker defaults disable the heaviest optional paths for reliable CPU demos.

Formal benchmark numbers are not committed. Use the evaluation manifest workflow for repeatable local measurement.

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Frontend says demo scorer | `NEXT_PUBLIC_API_URL` is empty or mock mode is forced | Set `NEXT_PUBLIC_API_URL=http://127.0.0.1:8000` and restart the frontend. |
| Browser CORS error | Backend `CORS_ORIGINS` does not include the frontend origin | Set `CORS_ORIGINS=http://localhost:3000`. |
| First backend request is slow | Model download or first model warmup | Let the request finish once; caches make later runs faster. |
| Audio decode fails | Missing FFmpeg or unsupported browser encoding | Install FFmpeg locally or use Docker. |
| Voice cloning unavailable | `LOAD_VOICE_CLONE=0` or CosyVoice dependencies unavailable | Use the Kokoro fallback path or enable voice clone in a compatible local environment. |
| No transcript/WER | Whisper disabled or `SCORE_ASR_MODE=off` | Set `LOAD_WHISPER=1` and `SCORE_ASR_MODE=fast`. |

## Current Boundaries

- No server-side accounts or authentication.
- No relational database or remote object storage.
- Frontend target-accent controls currently expose GA and RP.
- Voice enrollment audio is stored on the backend filesystem by opaque browser-generated user ID.
- Production deployment details are intentionally omitted because that infrastructure is still evolving.
- Some model paths are optional and degrade gracefully when checkpoints are absent.

## Future Improvements

- Add authenticated multi-device user profiles.
- Move enrollment audio and session history to durable storage.
- Add formal CI for backend tests, frontend lint/build, and Docker smoke checks.
- Expand target accent support beyond GA/RP in the frontend.
- Add reproducible benchmark manifests with recorded fixtures.
- Improve learned assessment calibration with larger held-out evaluation sets.
- Package optional heavy voice-clone dependencies behind a separate container profile.

## License

See [LICENSE](LICENSE).
