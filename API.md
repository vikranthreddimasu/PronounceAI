# PronounceAI — Backend API contract (v1)

The frontend (in `/frontend`) talks to a single backend service. This document is the contract: as long as the backend matches it, the frontend works without changes.

Until the backend exists, the frontend runs in **mock mode** (default — when `NEXT_PUBLIC_API_URL` is unset). Mock mode fabricates plausible `ScoreResponse`s and uses the browser's TTS for native playback so the full UI is exercisable end-to-end.

## Base URL

All endpoints are mounted at the root of `NEXT_PUBLIC_API_URL`. Example:

```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

CORS must allow the frontend origin (e.g. `http://localhost:3000`) for both `GET` and `POST`.

---

## `POST /score`

The single endpoint the product depends on. Takes the user's recording + a phrase id, returns the dimensional pronunciation breakdown.

**Request**: `multipart/form-data`

| Field       | Type   | Required | Notes                                                    |
| ----------- | ------ | -------- | -------------------------------------------------------- |
| `audio`     | File   | yes      | Browser-recorded audio. MIME is typically `audio/webm;codecs=opus` (Chrome/Firefox) or `audio/mp4` (Safari). Backend must accept whatever the browser produces — recommend `ffmpeg` to normalise to mono 16 kHz wav before model inference. |
| `phrase_id` | string | yes      | Matches an `id` in `frontend/src/lib/phrases.ts` (e.g. `"m1"`). |

**Response 200**: `application/json`

```json
{
  "transcript": "the quick brown fox jumps over the lazy dog",
  "finalScore": 78,
  "mfccScore": 82,
  "pitchScore": 64,
  "energyScore": 79,
  "feedback": "Pitch was flatter than the native version. Match the rise and fall."
}
```

| Field         | Type     | Range  | Source (notebooks)                                      |
| ------------- | -------- | ------ | ------------------------------------------------------- |
| `transcript`  | string   | —      | Module 1 (Whisper) output for the user's audio.         |
| `finalScore`  | int      | 0–100  | `0.6 * featureScore + 0.4 * modelScore`.                |
| `mfccScore`   | int      | 0–100  | `MFCC_similarity * 100` (cosine sim, user vs reference). |
| `pitchScore`  | int      | 0–100  | `Pitch_similarity * 100`.                                |
| `energyScore` | int      | 0–100  | `Energy_similarity * 100`.                               |
| `feedback`    | string   | 1 line | Keyed off the weakest dimension. See feedback rules below. |

**Note on naming**: notebook 3 calls these `Feature Score`, `Model Score`, `MFCC similarity`, etc. The wire format uses camelCase; you can map however you like server-side. The single-line `feedback` is what the UI shows — pick the *worst* dimension and emit one of the strings from the `feedbackFor()` function in `frontend/src/lib/api.ts` (or your own equivalents) so the messaging stays consistent.

**Errors**

| Status | When                                              | Body                              |
| ------ | ------------------------------------------------- | --------------------------------- |
| 400    | Missing/invalid `audio` or unknown `phrase_id`    | `{ "error": "<message>" }`        |
| 415    | Unsupported audio MIME the backend can't decode   | `{ "error": "<message>" }`        |
| 500    | Model load / inference failure                    | `{ "error": "<message>" }`        |

The frontend surfaces `error` text directly, so make it user-readable.

**Latency target**: end-to-end ≤ 1.2s for a 5s recording. If you can't hit that, the UI will still work but the product will feel broken.

---

## `GET /reference/:phrase_id`  *(optional in v1)*

Serves the native reference audio for a phrase, used for "Listen to native" playback.

- `200`: returns the audio file (any browser-decodable format; `audio/wav`, `audio/mpeg`, or `audio/ogg` recommended).
- `404`: phrase id unknown.

If this endpoint is not implemented, the frontend falls back to `SpeechSynthesis` (browser TTS). Real native audio is strongly preferred — the per-dimension scores reference *that file*, so users should hear the exact thing they're being compared to.

---

## Phrase set

The 20 phrases the UI exposes are defined in `frontend/src/lib/phrases.ts`. Backend must be able to score against any of those `id`s. Each phrase needs a stored reference audio file on the backend (LibriSpeech `test-clean` is a clean source — pick clips that contain each phrase exactly, or record a single native speaker reading all 20).

---

## Local dev

```bash
# Frontend
cd frontend
npm run dev               # runs at http://localhost:3000 in mock mode

# When the backend is up
cd frontend
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```
