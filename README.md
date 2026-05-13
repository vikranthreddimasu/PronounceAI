# PronounceAI

> A pronunciation coach that hears every phoneme, sees every pitch curve, and renders your own voice in the accent you want to master.

[![tests](https://img.shields.io/badge/tests-34%2F34%20passing-22C55E)](backend/tests)
[![python](https://img.shields.io/badge/python-3.11-3776AB)](backend/requirements.prod.txt)
[![nextjs](https://img.shields.io/badge/Next.js-16-000000)](frontend/package.json)
[![license](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![samples](https://img.shields.io/badge/▶_listen_to_samples-A78BFA?logoColor=fff)](https://vikranthreddimasu.github.io/PronounceAI/)

**Listen to every sample inline →** <https://vikranthreddimasu.github.io/PronounceAI/>

---

## Hear it before you read about it

A learner's enrolled voice, then the same speaker rendered in a long American-English sentence they never recorded — produced by the pipeline in this repository.

**Their natural voice (enrolment recording)**

[![Play the enrolment recording](docs/samples/voice_user_original_thumb.png)](https://vikranthreddimasu.github.io/PronounceAI/#user-original)

> *"Hello, my name is Alex. The quick brown fox jumps over the lazy dog by the river…"*

**Their voice — rendered by PronounceAI in General American**

[![Play the General American clone](docs/samples/voice_user_clone_ga_thumb.png)](https://vikranthreddimasu.github.io/PronounceAI/#user-clone-ga)

> *"The renewable energy transition will define the next half-century, and the engineers who solve the storage problem will reshape every industry from agriculture to artificial intelligence."*

Identity preserved. New sentence. Target accent locked in.

---

## Why

Most pronunciation tools grade speech with one opaque number, then tell you to *try again*. Two beliefs change the design:

1. **Feedback should point at the sound, not at the speaker.** When a learner's `/r/` drifts toward `/l/`, the system should say so — at the millisecond it happened.
2. **The learner's voice is theirs.** Accent practice shouldn't replace their timbre with a generic native speaker's; it should render the same words in the target accent with the speaker still recognisably themselves.

---

## How

One audio recording fans out across four independent, explainable signals. Nothing silently overrides anything else.

```mermaid
flowchart LR
  A["Browser MediaRecorder"] -->|"webm / opus"| B["POST /api/score"]
  B --> C["preprocess: VAD + resample 16k + normalise"]
  C --> D["Phoneme alignment<br/>wav2vec2 + forced_align"]
  C --> E["Prosody<br/>Parselmouth F0 + nPVI"]
  C --> F["Phrase grounding<br/>faster-whisper int8"]
  C --> G["Holistic head<br/>WavLM multi-aspect"]
  D --> H[["fusion<br/>0.55 / 0.20 / 0.15 / 0.10"]]
  E --> H
  F --> H
  G --> H
  H --> I["Score + per-phoneme tape<br/>+ pitch overlay + actionable tip"]
```

| Signal | Answers |
| --- | --- |
| **Phoneme alignment** (wav2vec2 + CTC forced alignment) | Where in time did each phone happen? How confident is the model you produced it? (GOP log-prob.) |
| **Prosody** (Parselmouth · librosa) | Did your pitch contour move like a native speaker's? Was your timing stress-timed or syllable-timed? (nPVI.) |
| **Phrase grounding** (faster-whisper int8) | Did you actually say the right words? Surfaced as a discrete `phrase_match_status`, not a silent cap on the score. |
| **Holistic head** (WavLM multi-aspect, optional) | A learned second opinion calibrated against speechocean762 human ratings. Bounded blend weight when its checkpoint is loaded. |

The score on screen is a transparent sum:

```
overall = 0.55 · phoneme_accuracy
        + 0.20 · intonation
        + 0.15 · stress_rhythm
        + 0.10 · vowel_quality
```

For voice cloning we picked **one** pipeline (no fallback chain): CosyVoice 3 voice conversion, with the target-accent source rendered by Kokoro TTS. Accent stays deterministic. Speaker identity stays the learner's.

```mermaid
flowchart LR
  T["Target text"] --> K["Kokoro TTS<br/>in target accent"]
  R["Learner enrolment ~10s"] --> CV["CosyVoice 3 VC"]
  K -->|"accent source"| CV
  CV --> O["Output WAV<br/>learner voice + target accent + emotion"]
  O --> V["Whisper STT<br/>word timings + validation"]
  V --> RES["Response + X-Word-Timings header"]
```

---

## What you get

### 1 · Voice cloning across emotions and accents

CosyVoice 3 voice conversion. The learner records once. The same speaker can be rendered across emotional styles (happy, sad, angry, calm, whisper) in both General American and Received Pronunciation.

→ **[Listen to the variants in the sample gallery](https://vikranthreddimasu.github.io/PronounceAI/#happy-ga)**.

### 2 · Pronunciation scoring

Three score JSON fixtures are committed so the response shape is inspectable without running the server:

| Phrase · Accent | Overall | Phrase match | JSON |
| --- | :-: | :-: | --- |
| "Ship or sheep?" · GA | **84.5** | `ok` | [score_ga_ship_or_sheep.json](docs/samples/score_ga_ship_or_sheep.json) |
| "She sells seashells by the seashore." · GA | **92.4** | `ok` | [score_ga_seashells.json](docs/samples/score_ga_seashells.json) |
| "The quick brown fox jumps over the lazy dog." · GA | **92.3** | `ok` | [score_rp_quick_brown_fox_rp.json](docs/samples/score_rp_quick_brown_fox_rp.json) |

Each fixture carries per-phoneme GOP with timestamps, the four scoring dimensions, the discrete `phrase_match_status`, the pitch overlay, and a `debug` block exposing weights and raw scores. The native-accent references that drive the pitch overlay are in the [gallery](https://vikranthreddimasu.github.io/PronounceAI/#tts-ship) too.

### 3 · The product UI

| Route | What it does |
| --- | --- |
| `/practice` | Phrase library + free-text recording → score + per-phoneme tape + pitch overlay + actionable tip. |
| `/studio` | Voice Lab — enrol, manage takes, type text, render in your voice + chosen accent + emotion. |
| `/progress` | Local session history, streak, per-phoneme mastery (`localStorage`, no accounts). |
| `/settings` | Target accent, theme, sound effects, profile reset. |

---

## Run it

**Docker (reviewer path)**

```bash
docker compose up --build
# UI: http://localhost:3000  ·  API: http://localhost:8000
```

**Local (Apple Silicon, full feature set)**

```bash
# Backend
cd backend && ./setup.sh && source .venv/bin/activate
uvicorn app.main:app --reload --port 8000

# Frontend (new terminal)
cd frontend && npm install
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 npm run dev
```

CosyVoice voice cloning needs `mlx-audio-plus` (Apple Silicon only). On other platforms the system falls back to Kokoro TTS in the requested accent.

**Regenerate the samples**

```bash
cd backend && source .venv/bin/activate
python scripts/generate_readme_samples.py     # idempotent; needs ffmpeg on PATH
```

---

## System architecture

```mermaid
flowchart TB
  subgraph Browser["Browser - Next.js 16 / React 19"]
    UI["Practice · Voice Lab · Progress · Settings"]
    REC["MediaRecorder"]
  end

  subgraph FastAPI["FastAPI backend"]
    R1["POST /api/score"]
    R2["POST /api/voice/speak"]
    R3["POST /api/accent-clone"]
    R4["POST /api/voice/enroll"]
    R5["GET /api/tts"]
    SC["app/scoring/<br/>async pipeline + fusion + feedback"]
    VS["app/services/voice_synth.py<br/>shared synth service"]
    R1 --> SC
    R2 --> VS
    R3 --> VS
  end

  subgraph Models["Speech / ML runtime"]
    M1["wav2vec2 phoneme CTC"]
    M2["faster-whisper int8"]
    M3["Parselmouth · librosa"]
    M4["Kokoro 82M TTS"]
    M5["CosyVoice 3 voice conversion"]
    M6["WavLM Large + assessment head"]
  end

  Browser -->|"multipart audio"| FastAPI
  SC --> M1
  SC --> M2
  SC --> M3
  SC --> M6
  VS --> M4
  VS --> M5
  VS --> M2
  R4 --> FS[("filesystem voice store")]
  R5 --> M4
```

Key design decisions live in [docs/REDESIGN_PLAN.md](docs/REDESIGN_PLAN.md). API contracts in [API.md](API.md). Stable container runbook in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

---

## What's inside

```
backend/app/
├── main.py             FastAPI lifespan + CORS + router wiring
├── api/                thin HTTP routers (score · tts · voice_enroll · accent_clone)
├── scoring/            async pipeline · fusion · pitch_contour · vowel_quality · feedback
├── services/           voice_synth — shared by /voice/speak and /accent-clone
├── models/             phoneme · prosody · whisper · voice_clone · assessment_scorer · emotion · phonology
├── cache/              shared LRU + atomic disk cache (tmp+rename, TTL)
└── utils/              audio preprocess · kokoro_speaker · voice_store · native_pitch · text_metrics

backend/training/       speechocean762 + WavLM head training utilities
backend/tests/          pytest, no network (34 tests, all green)
docs/                   index.html (sample gallery served via GitHub Pages)
docs/samples/           audio + JSON fixtures
frontend/src/           App Router pages + practice/voice UI + API client
```

---

## Tests + CI

```bash
cd backend && pytest tests/ -q          # 34 tests
cd frontend && npx tsc --noEmit && npm run build
```

Manifest-driven evaluation against recorded fixtures:

```bash
cd backend && python -m evaluation.evaluate_score_api --manifest evaluation/score_manifest.jsonl
```

---

## License

[MIT](LICENSE).
