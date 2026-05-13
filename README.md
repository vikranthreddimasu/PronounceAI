# PronounceAI

> Specific, fast, and respectful of your voice. Pronunciation coaching that hears every phoneme, sees every pitch curve, and never tells you "good job, try again."

![status](https://img.shields.io/badge/status-final%20project-7C3AED)
![tests](https://img.shields.io/badge/tests-34%2F34%20passing-22C55E)
![python](https://img.shields.io/badge/python-3.11-3776AB)
![nextjs](https://img.shields.io/badge/Next.js-16-000)
![license](https://img.shields.io/badge/license-MIT-blue)

---

## Why this exists

Most pronunciation apps grade speech with a single number. The number is opaque, and the feedback collapses into "try again." Learners can hear they sounded *wrong* but never learn *what was wrong* or *how to fix it*.

PronounceAI exists because two beliefs are non-negotiable in our work:

1. **Feedback must point at the sound, not at the speaker.** When the `/r/` drifts toward `/l/`, we want the system to say so — at the millisecond it happened.
2. **Your voice is yours.** Accent coaching shouldn't replace your timbre with a generic native speaker's. We should be able to render the *same words* in the target accent while keeping the voice recognizably you.

Everything else — the architecture, the model choices, the cache layers — exists to serve those two beliefs.

---

## How we deliver it

We chain four independent, explainable signals through one async pipeline. Each signal answers a different question, and no signal can silently override another. Together they form a per-phoneme + per-utterance picture of what the learner said and how it differs from a native reference.

| Signal | Model | What it answers |
| --- | --- | --- |
| **Phoneme alignment** | wav2vec2-large-robust-L2 + CTC forced alignment | "Where in time did each phone happen, and how confident was the model that you produced it?" (Goodness-of-Pronunciation log-prob per phone.) |
| **Prosody** | Parselmouth + librosa | "Did your pitch contour move like a native speaker's? Was your stress timing English-like (nPVI), or syllable-timed?" |
| **Phrase grounding** | faster-whisper (CTranslate2, int8) | "Did you actually say the words you were asked to say?" — surfaced as a discrete `phrase_match_status`, not a silent score cap. |
| **Holistic assessment** | WavLM multi-aspect head (optional) | A learned second opinion calibrated against human ratings (speechocean762 utterance scores). Blended at a bounded weight when its checkpoint is present. |

The score the user sees is a transparent weighted sum:

```
overall = 0.55 · phoneme_accuracy
       + 0.20 · intonation
       + 0.15 · stress_rhythm
       + 0.10 · vowel_quality      ← diagnostic, lightly weighted
```

For the voice clone side, we deliberately picked **one pipeline** rather than blending several: CosyVoice 3 Voice Conversion, with the target-accent source rendered by Kokoro TTS. That keeps the accent deterministic while the speaker identity stays the learner's.

---

## What you actually get

### A. Pronunciation scoring — `POST /api/score`

Upload audio + the expected phrase. Get back per-phoneme GOP scores with start/end timestamps, four scoring dimensions, a phrase-match status, the pitch overlay, and an actionable tip drawn from a phonological-feature substitution table.

**Live samples** (Kokoro-synth audio scored against the same phrase — close to a "perfect" baseline):

| Phrase | Accent | Overall | Phrase match | Sample |
| --- | --- | :-: | :-: | --- |
| "Ship or sheep?" | GA | **84.5** | `ok` | [`score_ga_ship_or_sheep.json`](docs/samples/score_ga_ship_or_sheep.json) |
| "She sells seashells by the seashore." | GA | **92.4** | `ok` | [`score_ga_seashells.json`](docs/samples/score_ga_seashells.json) |
| "The quick brown fox jumps over the lazy dog." | RP | **92.3** | `ok` | [`score_rp_quick_brown_fox_rp.json`](docs/samples/score_rp_quick_brown_fox_rp.json) |

Each JSON file is the exact shape the frontend receives, including `phonemes[]` with timestamps, `scores`, `pitch_contour`, the `debug` block with raw scores + weights, and the new `phrase_match_status` discrete state.

### B. Voice clone in a selected accent — `POST /api/voice/speak` and `POST /api/accent-clone`

Record one short enrollment (~10s). Then any text you type is rendered in **your timbre** + the **target accent** — General American or Received Pronunciation — with optional emotional styling. The same endpoint accepts text directly (`/voice/speak`) or audio that gets Whisper-transcribed first (`/accent-clone`).

**Live samples** (synthetic enrollment built from Kokoro, then CosyVoice 3 voice conversion):

<table>
  <tr><th>Emotion</th><th>Accent</th><th>Line</th><th>Sample</th></tr>
  <tr>
    <td>Happy</td><td>GA</td>
    <td><em>"I just got promoted today. I am so excited for the future!"</em></td>
    <td><a href="docs/samples/voice_happy_ga.wav"><code>voice_happy_ga.wav</code></a></td>
  </tr>
  <tr>
    <td>Sad</td><td>RP</td>
    <td><em>"The old photograph brought back so many precious memories."</em></td>
    <td><a href="docs/samples/voice_sad_rp.wav"><code>voice_sad_rp.wav</code></a></td>
  </tr>
  <tr>
    <td>Angry</td><td>GA</td>
    <td><em>"This is completely unacceptable. I demand to speak to the manager."</em></td>
    <td><a href="docs/samples/voice_angry_ga.wav"><code>voice_angry_ga.wav</code></a></td>
  </tr>
  <tr>
    <td>Calm</td><td>RP</td>
    <td><em>"Close your eyes. Breathe in slowly. Let the tension fade away."</em></td>
    <td><a href="docs/samples/voice_calm_rp.wav"><code>voice_calm_rp.wav</code></a></td>
  </tr>
  <tr>
    <td>Whisper</td><td>GA</td>
    <td><em>"I need to tell you a secret, but you must promise not to tell anyone."</em></td>
    <td><a href="docs/samples/voice_whisper_ga.wav"><code>voice_whisper_ga.wav</code></a></td>
  </tr>
</table>

> GitHub renders `<audio controls>` tags inline when the README is browsed on github.com. The samples above are also playable directly in VS Code's markdown preview.

### C. Native target-accent TTS — `GET /api/tts`

Kokoro 82M produces clean reference audio for the practice flow. Same phrase, two accents, no learner enrollment required.

| Phrase | GA reference | RP reference |
| --- | --- | --- |
| "Ship or sheep?" | [`tts_ga_ship_or_sheep.wav`](docs/samples/tts_ga_ship_or_sheep.wav) | [`tts_rp_ship_or_sheep.wav`](docs/samples/tts_rp_ship_or_sheep.wav) |
| "She sells seashells by the seashore." | [`tts_ga_seashells.wav`](docs/samples/tts_ga_seashells.wav) | — |
| "The quick brown fox jumps over the lazy dog." | [`tts_ga_quick_brown_fox.wav`](docs/samples/tts_ga_quick_brown_fox.wav) | — |
| "Could you show me the fastest route to the station?" | — | [`tts_rp_fastest_route.wav`](docs/samples/tts_rp_fastest_route.wav) |

### D. Practice UI, Voice Lab, Progress, Settings

| Route | Purpose |
| --- | --- |
| `/practice` | Phrase library + custom-text recording → live score + pitch overlay + per-phoneme tape + actionable tip. |
| `/studio` | Voice Lab — enroll, manage takes, type any text, render it in your voice + chosen accent + emotion. |
| `/progress` | Local session history, streak, per-phoneme mastery (browser-only, no account). |
| `/settings` | Target accent, theme, sound effects, profile reset. |

---

## Architecture at a glance

```
Browser / Next.js 16
  └── MediaRecorder  ─►  POST /api/score
                         POST /api/voice/enroll
                         POST /api/voice/speak           ◄── text in user's voice + accent
                         POST /api/accent-clone          ◄── audio → ASR → same path
                         GET  /api/tts                   ◄── Kokoro reference

FastAPI backend
  ├── app/scoring/        async pipeline: phoneme + prosody + whisper + (wavlm)
  │     ├── pipeline.py      orchestrator (asyncio.to_thread fan-out)
  │     ├── fusion.py        score blend + single discrete phrase-match gate
  │     ├── pitch_contour.py F0 onset-aligned z-score for the overlay
  │     ├── vowel_quality.py formant comparison vs accent norms
  │     └── feedback.py      phonology hint generation
  ├── app/services/
  │     └── voice_synth.py   shared by /voice/speak + /accent-clone
  ├── app/models/         engines: phoneme, prosody, whisper, voice_clone, ...
  ├── app/utils/
  │     ├── kokoro_speaker.py  single Kokoro pipeline (used 4 places)
  │     ├── audio.py           VAD + resample + quality gate
  │     ├── voice_store.py     multi-take enrollment + lazy bundle
  │     └── native_pitch.py    cached F0 reference (mem + disk)
  └── app/cache/
        ├── memory.py    shared LRU
        └── disk.py      atomic write + TTL
```

Key design decisions, with the reason in one line:

| Decision | Why |
| --- | --- |
| One Kokoro pipeline singleton instead of four duplicates | Eliminates redundant model load + locks; single VOICE_MAP. |
| Three score caches share one `LRUCache` class | One LRU implementation, one eviction policy, fewer surprises. |
| Disk cache uses tmp + rename | Atomic on POSIX — concurrent readers never see a half-written WAV. |
| Score cache key includes checkpoint fingerprint | Swapping `assessment_head_best.pt` invalidates stale cached responses automatically. |
| `phrase_match_status` is a discrete field, not a silent cap | UI can choose to show a chip; the score doesn't move mysteriously. |
| VoiceClone picks one mode upfront | Predictable latency, no retry chain; STT runs once. |

---

## Quick start

### Option 1 — Docker (recommended for review)

```bash
docker compose up --build
```

Then open `http://localhost:3000`. First run downloads ~2 GB of public speech models; subsequent runs are instant.

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

The Docker compose profile runs a CPU-safe subset by default (Kokoro + phoneme scoring + prosody). To enable Whisper grounding and CosyVoice voice cloning, see the env table below.

### Option 2 — Local dev (Apple Silicon recommended)

```bash
# Backend
cd backend
./setup.sh                            # creates .venv, installs PyTorch MPS, downloads NLTK data
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000

# Frontend (new terminal)
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 npm run dev
```

Local default config enables Whisper + WavLM + CosyVoice 3 when `mlx-audio-plus` is installed (Apple Silicon only).

### Regenerate the README samples

```bash
cd backend
source .venv/bin/activate
python scripts/generate_readme_samples.py
```

Outputs land under `docs/samples/`. The script is idempotent and writes a `manifest.json`.

---

## Tech stack

| Layer | Implementation |
| --- | --- |
| Frontend | Next.js 16, React 19, TypeScript, Tailwind v4 tooling |
| Audio capture | Browser `MediaRecorder`, WebAudio level metering |
| Backend API | FastAPI, Uvicorn, Pydantic, python-multipart |
| Phoneme model | `slplab/wav2vec2-large-robust-L2-english-phoneme-recognition` |
| Text→phonemes | `g2p-en` (CMUdict/NLTK) with `phonemizer-fork` + `espeak-ng` fallback |
| ASR | `faster-whisper` (CTranslate2 int8) |
| TTS | Kokoro 82M |
| Voice clone | CosyVoice 3 via `mlx-audio-plus` (Apple Silicon) |
| Prosody | Parselmouth/Praat, librosa, scipy/numpy |
| Embeddings | WavLM Large (optional, for the multi-aspect head + accent distance) |
| Storage | Browser `localStorage` + backend filesystem voice store |
| Container | `docker-compose.yml` at repo root |

---

## API reference

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Liveness. |
| `POST` | `/api/score` | Multipart pronunciation assessment. |
| `POST` | `/api/prewarm` | Best-effort phrase + model cache warmup. |
| `GET` | `/api/tts` | Kokoro native reference WAV. |
| `POST` | `/api/voice/enroll` | Append a voice-enrollment take. |
| `GET` | `/api/voice/{user_id}` | Fetch enrollment summary. |
| `DELETE` | `/api/voice/{user_id}` | Delete enrollment. |
| `DELETE` | `/api/voice/{user_id}/takes/{take_id}` | Delete one take. |
| `POST` | `/api/voice/speak` | Render text in user's voice + target accent (+ emotion). |
| `POST` | `/api/accent-clone` | Audio → ASR → same synthesis path. |

See [API.md](API.md) for request fields, response details, and the `X-Word-Timings` header.

### `/api/score` response shape (top-level fields)

```jsonc
{
  "phonemes":  [ { "phoneme": "sh", "expected": "sh", "gop": -0.12, "correct": true, "start_ms": 80, "end_ms": 200, ... }, ... ],
  "scores":    { "phoneme_accuracy": 91.8, "intonation": 99.5, "stress_rhythm": 100.0, "vowel_quality": 70.0 },
  "overall":   92.4,
  "feedback":  [ { "text": "Focus on /r/; your closest detected sound was /l/.", "timestamp_ms": 320 } ],
  "transcript": { "text": "She sells seashells by the seashore.", "language_probability": 0.99 },
  "wer": 0.0,
  "phrase_match_status": "ok",                // ← new: "ok" | "partial" | "weak" | "mismatch" | null
  "pitch_contour": { "user": [...], "native": [...], "duration_ms": 2270 },
  "debug": {
    "elapsed_ms": 1483,
    "stage_ms": { "phoneme": 307, "native_f0": 942, "prosody": 4, "whisper": 230 },
    "weights": { "phoneme_accuracy": 0.55, "intonation": 0.20, "stress_rhythm": 0.15, "vowel_quality": 0.10, "learned_overall_blend": 0.35 },
    "raw_overall": 92.4,
    "raw_phoneme_accuracy": 91.8,
    "score_gates": [],
    "phrase_match": { "wer": 0.0, "phrase_match": 100.0, ... },
    "speech_rate_sps": 4.85
  }
}
```

---

## Configuration

### Frontend env

| Variable | Purpose |
| --- | --- |
| `NEXT_PUBLIC_API_URL` | Backend origin, e.g. `http://127.0.0.1:8000`. Empty → demo/mock mode. |
| `NEXT_PUBLIC_USE_MOCK` | `1` forces mock mode even with an API URL set. |

### Backend env

| Variable | Default / Example | Purpose |
| --- | --- | --- |
| `DEVICE` | `mps`, `cuda`, `cpu` | Torch device for core models. |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated browser origins allowed to call the API. |
| `WAV2VEC2_MODEL` | `slplab/wav2vec2-large-robust-L2-english-phoneme-recognition` | Phoneme CTC backbone. |
| `WHISPER_MODEL` / `WHISPER_FALLBACK_MODEL` | `large-v3-turbo` / `large-v3` | faster-whisper model + fallback. |
| `LOAD_WHISPER` | `1` locally, `0` in Docker default | Enables transcript / phrase-match grounding. |
| `LOAD_VOICE_CLONE` | `1` locally, `0` in Docker default | Enables CosyVoice 3 (requires `mlx-audio-plus`). |
| `SCORE_ASR_MODE` | `off`, `fast`, `words` | Transcript path: `off` = no ASR; `fast` = greedy text; `words` = full beam + per-word timestamps. |
| `SCORE_INCLUDE_FORMANTS` | `0`, `1` | Enable formant extraction (slower; lights up vowel-quality scoring). |
| `SCORE_WAVLM_MODE` | `auto`, `off` | WavLM embedding pass for assessment head + accent distance. |
| `ASSESSMENT_SCORER_CHECKPOINT` | `checkpoints/assessment_head_best.pt` | Optional multi-aspect WavLM head. |
| `ACCENT_CENTROIDS_PATH` | `checkpoints/accent_centroids.pt` | Optional WavLM accent centroids. |
| `ENROLLMENT_DIR` | `data/enrollments` | Filesystem voice-store root. |
| `NATIVE_F0_CACHE_DIR` | `cache/native_f0` | Disk cache for native pitch references. |
| `VOICE_SYNTH_CACHE_DIR` | `cache/voice_synth` | Disk cache for `/voice/speak` outputs. |
| `VOICE_SYNTH_CACHE_MAX_AGE_HOURS` | `24` | TTL for voice-synth cache entries. |

---

## Build, test, deploy

```bash
# Backend tests (34 tests)
cd backend && source .venv/bin/activate
python -m pytest tests/ -q

# Frontend type-check + build
cd frontend
npx tsc --noEmit
npm run build

# Docker rebuild
docker compose build --no-cache && docker compose up
```

The evaluation harness lives in `backend/evaluation/`:

```bash
cd backend
python -m evaluation.evaluate_score_api --manifest evaluation/score_manifest.jsonl
```

It tracks latency, WER, phrase match, score gates, and expected-score bounds against a manifest of recorded fixtures.

---

## Repository layout

```
PronounceAI/
├── README.md  API.md  docker-compose.yml  LICENSE
├── docs/
│   ├── DEPLOYMENT.md
│   ├── REDESIGN_PLAN.md
│   └── samples/                      ← audio + JSON the README links to
├── backend/
│   ├── Dockerfile  setup.sh
│   ├── requirements.txt  requirements.prod.txt
│   ├── app/
│   │   ├── main.py                   FastAPI lifespan + CORS
│   │   ├── api/                      thin routers (score, tts, voice_enroll, accent_clone)
│   │   ├── scoring/                  async scoring pipeline + fusion + feedback
│   │   ├── services/                 voice_synth (shared by /voice/speak + /accent-clone)
│   │   ├── models/                   model wrappers (phoneme, prosody, whisper, voice_clone, ...)
│   │   ├── cache/                    shared LRU + atomic disk cache
│   │   └── utils/                    audio, kokoro_speaker, voice_store, native_pitch
│   ├── training/                     speechocean762 + WavLM training utilities
│   ├── evaluation/                   manifest-driven score-API evaluator
│   ├── scripts/                      sample generators
│   └── tests/                        unit tests (pytest, no network)
└── frontend/
    ├── Dockerfile  package.json  next.config.ts
    └── src/{app,components,lib}      App Router pages + practice/voice UI + API client
```

---

## Performance notes

- All engines loaded once in FastAPI `lifespan` and reused via `app.state`.
- `/api/score` fans out phoneme, native-F0, Whisper, and WavLM work concurrently with `asyncio.to_thread`.
- `/api/voice/speak` and `/api/accent-clone` run CosyVoice + STT inside `asyncio.to_thread` so concurrent score requests stay responsive.
- Disk + memory caches share one set of primitives (`app/cache/`); atomic writes prevent half-written WAVs.
- Frontend cancels stale playback / scoring with `AbortSignal`.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Frontend says "demo scorer" | `NEXT_PUBLIC_API_URL` empty or mock mode forced | Set `NEXT_PUBLIC_API_URL=http://127.0.0.1:8000` and restart. |
| Browser CORS error | `CORS_ORIGINS` doesn't include the frontend origin | Set `CORS_ORIGINS=http://localhost:3000`. |
| First backend request is slow | Public model download + warmup | Let the first request finish; caches kick in after. |
| Audio decode fails | Missing FFmpeg | Install FFmpeg locally (`brew install ffmpeg`) or use Docker. |
| Voice cloning unavailable | `LOAD_VOICE_CLONE=0` or `mlx-audio-plus` missing | Install `mlx-audio-plus` on Apple Silicon, or accept the Kokoro fallback path. |
| `phrase_match_status` is `null` | Whisper disabled | Set `LOAD_WHISPER=1` and `SCORE_ASR_MODE=fast`. |

---

## Boundaries

- No server-side accounts or auth; voice enrollments are keyed by an opaque browser-generated user ID.
- No relational database; progress lives in `localStorage` and voice store on the filesystem.
- Target accents currently exposed in the frontend: General American (GA), Received Pronunciation (RP).
- Voice cloning requires `mlx-audio-plus` (Apple Silicon). Other platforms fall back to Kokoro TTS in the requested accent.

---

## Roadmap

- Multi-device profiles backed by a durable store.
- Expand accent coverage beyond GA/RP in the frontend (AuE, Irish, Scottish, IndianE already supported by TTS).
- Reproducible benchmark manifests with recorded human fixtures.
- Larger held-out evaluation set for the WavLM multi-aspect head.
- CI for backend pytest, frontend lint/build, and a Docker smoke test.

---

## License

See [LICENSE](LICENSE).
