# HTTP API contract

Base URL is the backend root (e.g. `http://127.0.0.1:8000`). The Next.js frontend points `NEXT_PUBLIC_API_URL` at this origin.

Unless noted, responses are JSON. Configure browser origins with **`CORS_ORIGINS`** in `backend/.env.local` — comma-separated list of full origins (scheme + host + optional port). Use `*` to allow any origin (sets `Allow-Credentials` off). If unset, defaults to `http://localhost:3000` and `http://localhost:3001`.

---

## Health

| Method | Path | Response |
|--------|------|-----------|
| `GET` | `/health` | `{"status": "ok"}` |

---

## Scoring (`/api`)

### `POST /api/score`

Multipart form fields:

| Field | Type | Notes |
|-------|------|------|
| `audio` | file | User recording (e.g. `recording.webm`); decoded via `preprocess()` to 16 kHz mono |
| `phrase` | string | Expected text |
| `accent` | string | Target accent (`GA`, `RP`, …; see backend `_normalise_accent`) |
| `l1` | string | Optional L1 hint (may be `"unknown"`)

**Response:** `AssessmentResult` as in `frontend/src/lib/types.ts` (`phonemes`, `scores`, `overall`, optional `pitch_contour`, `transcript`, `wer`, `debug`, …).

**Errors:** `400` / `422` with `detail` string on bad audio or validation.

Behavior is controlled by backend env vars (e.g. `SCORE_ASR_MODE`, `SCORE_RESPONSE_CACHE`) — see `backend/.env.example`.

### `POST /api/prewarm`

JSON body: `{ "phrase": string, "accent": string }`.

Best-effort warms caches for scoring/TTS-related work. Safe to omit; replies quickly with `{ "status": "scheduled", ... }` or `{ "status": "ignored" }`.

---

## Reference TTS (`/api`)

### `GET /api/tts`

Query params:

| Param | Default | Notes |
|-------|---------|--------|
| `text` | required | Phrase (trimmed internally for caching) |
| `accent` | `GA` | Uppercase accent key understood by Kokoro mapping |
| `speed` | `0.9` | Clamped to ~0.5–1.5 |

**Response:** `audio/wav` (24 kHz). `Cache-Control: public, max-age=86400`.

---

## Accent conversion (`/api`)

### `POST /api/accent-convert`

Multipart:

| Field | Notes |
|-------|--------|
| `audio` | Recording blob |
| `accent` | Target accent |

**Response:** WAV stream (converted speech). Converts only when accent converter engine is loaded (lazy unless `PRELOAD_ACCENT_CONVERTER`).

Related: `accent_clone` router under `/api` for clone-specific flows — see `backend/app/api/accent_clone.py`.

---

## Voice enrollment & speak (`/api`)

Opaque `user_id` (client-generated UUID) maps to files under `data/enrollments/<user_id>/`.

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/voice/enroll` | Multipart: `audio`, `ref_text`, `user_id` → new take + summary |
| `GET` | `/api/voice/{user_id}` | Enrollment summary (`takes`, `revision`, durations, …) |
| `DELETE` | `/api/voice/{user_id}` | Remove enrollment |
| `DELETE` | `/api/voice/{user_id}/takes/{take_id}` | Remove one take |
| `POST` | `/api/voice/speak` | Multipart: `user_id`, `text`, `accent`, optional `strategy` (`target_accent` / …) → WAV |

**`POST /api/voice/speak`**: returns `FileResponse`; word timings are in response header **`X-Word-Timings`** (base64 JSON array of `{ word, start_ms, end_ms }`). Exposed headers are listed on the response for CORS clients.

Errors: `400`/`404`/`422`/`503` with `detail` when enrollment missing or engine unavailable.

---

## Frontend mapping

| Client helper | Endpoint |
|----------------|----------|
| `scoreRecording` | `POST /api/score` |
| `playNativeAudio` / `prepareNativeAudio` / `prefetchNativeAudio` | `GET /api/tts` |
| `prewarmPhrase` | `POST /api/prewarm` |
| `convertAccent` | `POST /api/accent-convert` |
| `voiceProfile` enroll / speak / delete | `/api/voice/*` |

With no `NEXT_PUBLIC_API_URL` (or `NEXT_PUBLIC_USE_MOCK=1`), the client skips HTTP for scoring/reference audio and uses local mock/Web Speech APIs.

**Cancellation:** Helpers that wrap `fetch` often accept **`AbortSignal`**. Highlights: **`scoreRecording`**; **`convertAccent`** (**`signal`** skips **`getConvertedAccent`** `WeakMap` reuse); **`playNativeAudio`** and **`prepareNativeAudio`** (**`signal`** uses a standalone **`GET /api/tts`** fetch then **`remember`**s the blob into LRU so cancellable callers do not strand shared promises); **`prefetchNativeAudio`** and **`prewarmPhrase`** (**`WarmPrefetchOptions`** / **`signal`** aborts speculative work); **`speakInVoice`** / **`getVoiceClip`** (**`signal`** skips the LRU **`voiceClipCache`** row for that **`POST /api/voice/speak`**); **`refreshVoiceSession({ force?, signal? })`** (a new **`force: true`** run aborts the previous in-flight **`GET`**, optional **`signal`** mirrors caller lifetime such as hook unmount, and **`AbortError`** resolves to the current snapshot without treating it like a backend failure); and `frontend/src/lib/voiceProfile.ts` (**`fetchVoiceProfile`**, **`addVoiceTake`**, **`cloneAccent`**, **`deleteVoiceTake`** / **`deleteVoiceProfile`** / **`deleteCurrentVoiceProfile`**). Mock-mode **`speakReference`** (**Web Speech**) also respects **`AbortSignal`**.
