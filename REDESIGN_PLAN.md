# PronounceAI — Ground-Up Redesign for Accent-Targeted Coaching

## Context

The current system's core limitation is **granularity**. It operates at word level (Whisper F1) and global utterance acoustics (MFCC mean/std), but pronunciation errors happen at the **phoneme level**. A German learner says /d/ instead of /θ/ — Whisper transcribes "the" correctly because context fills the gap, and the 86-dim MFCC aggregate doesn't resolve which phoneme caused the dip. The system can tell you something is wrong; it cannot tell you *what* is wrong or *how* to fix it.

Beyond that, the training data uses synthetic degradation (pitch-shift, noise, stretch) as "bad speech" — a proxy that bears little resemblance to real L2 errors (formant shifts, VOT errors, stress misplacement, prosodic interference from L1 tone systems). The combined meta-model was consequently miscalibrated: real TTS speech scoring 73% acoustic quality gets only 22% from the RF.

The goal of the redesign is to build a product that knows **which accent you're targeting**, diagnoses errors at **phoneme resolution**, and generates **actionable corrective guidance** — not just a score.

---

## What Competitors Get Wrong (Why There's Space)

| App | What it does | What it misses |
|---|---|---|
| ELSA Speak | Phoneme-level scoring on fixed content | No accent targeting; opaque scoring; no prosody |
| Duolingo Pronunciation | Pass/fail per word via ASR | No acoustic feedback whatsoever |
| Rosetta Stone | Waveform comparison | Visual only; no phoneme labels |
| Speechling | Human coaches via recording exchange | Not scalable, slow feedback loop |

**The gap**: Nobody gives you *accent-specific phoneme-level* feedback with *formant visualization* and *LLM-generated corrective guidance*, in real time.

---

## Architecture Overview

```
User Audio (48kHz, stereo)
       │
       ▼
┌──────────────────────────────────────────────────────┐
│  LAYER 1 — Signal Processing                         │
│  Silero VAD → trim silence                           │
│  Resampled to 16kHz mono for models                  │
│  Parselmouth (Praat) → formant tracks F1/F2/F3       │
│  CREPE neural pitch → F0 contour (frame-level)       │
└────────────────────┬─────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────┐
│  LAYER 2 — Phoneme Engine                            │
│  wav2vec2-large-robust-L2 (slplab/HuggingFace)       │
│    → CTC alignment: audio frames ↔ phoneme sequence  │
│    → GOP score per phoneme: log P(ph|frames)         │
│    → Substitution detection: predicted vs. expected  │
│  Fine-tuned on speechocean762 + L2-ARCTIC            │
└────────────────────┬─────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────┐
│  LAYER 3 — Prosody Engine                            │
│  Pitch: CREPE F0 → DTW vs. native contour            │
│  Stress: energy envelope per syllable from alignment │
│  Rhythm: nPVI (normalized Pairwise Variability Index)│
│  Rate: syllable/second from CTC timestamps           │
└────────────────────┬─────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────┐
│  LAYER 4 — Accent Distance                           │
│  WavLM-Large → speaker-normalized embedding          │
│  Fine-tuned on VCTK (native, multi-accent) +         │
│              L2-ARCTIC (24 non-native speakers)      │
│  Cosine distance to target accent centroid           │
│  → "How far from General American / RP British / AU" │
└────────────────────┬─────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────┐
│  LAYER 5 — LLM Feedback Generator                    │
│  Structured error report → Claude API                │
│  Prompt: target accent + L1 + phoneme errors +       │
│          prosody deviations + formant positions       │
│  Output: 2-3 specific, corrective, articulatory tips │
└──────────────────────────────────────────────────────┘
```

---

## Layer-by-Layer Detail

### Layer 1 — Signal Processing

**Why**: Upstream noise kills downstream model quality. Validate the audio before scoring.

- **VAD**: [Silero VAD](https://github.com/snakers4/silero-vad) — 1MB, runs in browser via ONNX, trims silence in real time
- **Quality gate**: SNR check, clipping detection, duration check (0.5s – 30s). Reject gracefully.
- **Formant tracking**: Parselmouth (Python Praat API) — extract F1, F2, F3 per voiced frame. Segment by vowel from alignment timestamps. Average F1/F2 per vowel token → plot on IPA vowel quadrilateral.
- **Pitch**: [CREPE](https://github.com/marl/crepe) — CNN-based pitch estimator; dramatically more robust than pYIN on non-native/noisy speech. Returns frame-level F0 with confidence. Compare to reference via DTW after speaker normalization (z-score within voiced frames).

### Layer 2 — Phoneme Engine (The Core)

This is the piece the current system entirely lacks.

**Model**: `slplab/wav2vec2-large-robust-L2-english-phoneme-recognition` (HuggingFace, 1.6K downloads, trained specifically for L2 English)

**What it does**:
- CTC decoder: maps audio frames → phoneme probability distributions at each time step
- Forced alignment: given reference text, use CTC alignment algorithm to find most likely start/end frame for each phoneme in the utterance
- GOP (Goodness of Pronunciation) per phoneme:
  ```
  GOP(ph, t_s, t_e) = (1/(t_e-t_s)) × Σ log P(ph | frame_t)
  ```
  Higher = more confident the phoneme is correctly articulated.
- Substitution detection: if the Viterbi path through the CTC outputs yields phoneme X when the reference expected phoneme Y → flag as substitution error (e.g., /θ/ → /d/, /r/ → /l/)

**Training data for fine-tuning**:
- speechocean762 (`jbpark0614/speechocean762` on HuggingFace): 5,000 utterances from 250 non-native speakers, human-rated at phoneme/word/utterance level on accuracy, fluency, prosody, and total score. The gold benchmark.
- L2-ARCTIC (24 non-native speakers, 6 L1 backgrounds, ~7,200 utterances). Phoneme-annotated.
- VCTK (109 native speakers, UK/US/AU/Scottish/Irish accents) — native side.

**Output per utterance**:
```json
{
  "phonemes": [
    { "phoneme": "ð", "expected": "ð", "gop": -0.3, "correct": true, "start_ms": 120, "end_ms": 200 },
    { "phoneme": "d", "expected": "ð", "gop": -2.1, "correct": false, "substitution": "d→ð", "start_ms": 200, "end_ms": 280 }
  ],
  "word_scores": [...],
  "accuracy_score": 0.78
}
```

### Layer 3 — Prosody Engine

**Why**: Prosody (stress, rhythm, intonation) is what makes an accent feel native. The current system collapses this into two numbers (pitch mean, pitch std) over the whole utterance.

| Dimension | Method | What it catches |
|---|---|---|
| Intonation | CREPE F0 + DTW vs. native contour | Rising/falling pattern errors, tonal L1 interference |
| Lexical stress | Energy per syllable from CTC alignment | Stress on wrong syllable ("reCORD" vs "REcord") |
| Rhythm | nPVI on inter-vowel intervals | Syllable-timed L1 (Spanish, French) vs. stress-timed English |
| Rate | Syllables/second from CTC timestamps | Too fast/slow; consonant cluster reduction |
| Pausing | Silence durations from VAD | Disfluency, breath group errors |

### Layer 4 — Accent Distance

**Why**: The user picked a *target* accent. Every score should be relative to that accent, not a generic "good English."

**Approach**:
- Encoder: WavLM-Large (SOTA on SUPERB benchmark, handles noise well)
- Fine-tune a speaker/accent head on VCTK (accent-labeled native) + Common Voice (accent-tagged)
- For each target accent (General American, RP British, Australian, Scottish, Irish, Indian English), compute a centroid embedding from 20+ native speakers
- Learner's utterance gets embedded → cosine distance to target centroid = accent distance score
- Track this over time: the embedding should drift toward the target cluster as the learner improves

**Accent targets (v1)**:
- General American (GA) — neutral US
- Received Pronunciation (RP) — BBC British
- General Australian (AuE)
- Irish English
- Scottish English
- Indian English (as a *target*, not just a source)

### Layer 5 — LLM Feedback Generator

**Why**: Scores without explanation don't change behavior. "Clarity: 72%" teaches nothing. "Your /θ/ in 'the' sounds like /d/ — press your tongue against your upper front teeth, not the gum ridge" teaches something.

**Design**:
- Assemble structured error report: top 3 phoneme errors (with substitution info), prosody deviations, formant positions for key vowels
- Send to Claude API (`claude-sonnet-4-6`) with a system prompt encoding:
  - The target accent's phonological profile
  - The learner's declared L1 (enables L1-specific guidance: "Japanese speakers often merge /r/ and /l/...")
  - Output format: 2-3 tips max, each with: what's wrong, why it matters for the target accent, how to fix it (articulatory instruction)
- Cache feedback by (error_type, L1, target_accent) to reduce API calls for common errors
- Examples of generated feedback:
  - *"Your /θ/ in 'the' (0:00.12) sounds like /d/. In General American, place your tongue tip between your upper and lower front teeth and push air — don't touch the gum ridge. This is the most common error for Spanish and Italian speakers."*
  - *"Your vowel in 'TRAP' is too close to /e/ (F1 too low, F2 too high). In RP British, lower your jaw slightly and keep the tongue more central."*

---

## Scoring Model: Multi-Dimensional (not a single score)

| Dimension | Range | Method | Weight for "Overall" |
|---|---|---|---|
| Phoneme Accuracy | 0–100 | Mean GOP across phonemes, normalized | 35% |
| Prosody — Intonation | 0–100 | DTW distance of F0 contour vs. native | 20% |
| Prosody — Stress/Rhythm | 0–100 | nPVI + syllable stress accuracy | 15% |
| Vowel Quality | 0–100 | F1/F2 Euclidean dist to target vowel space | 20% |
| Accent Distance | 0–100 | 1 − cosine_dist to target accent centroid | 10% |

The weighted overall is shown, but each dimension shown individually with a label. No single number hides which dimension is the bottleneck.

---

## Content & Curriculum System

### Content Tiers

1. **Minimal Pairs** — pairs differing by one phoneme: ship/sheep, bed/bad, right/light, three/free, this/dis. Targeted at specific phoneme contrasts the learner's L1 struggles with.
2. **Phoneme Drills** — isolated practice of one sound across multiple word positions (initial, medial, final).
3. **Phrases & Sentences** — connected speech with natural coarticulation, stress groups, intonation patterns.
4. **Authentic Clips** — 10–30 second excerpts from podcasts, speeches, films. Learner shadows; system scores alignment.
5. **Free Recording** — user inputs any text; system generates native reference via accent-specific TTS and scores it.

### L1-Aware Curriculum

User declares their native language on signup. The system loads a known L1→L2 error matrix:

| L1 | Known English errors |
|---|---|
| Japanese | /r-l/ merger, vowel epenthesis, pitch accent → stress-timing mismatch |
| Spanish | /b-v/, /s-z/, no consonant clusters, syllable-timed rhythm |
| German | Final devoicing, /w-v/, tense/lax vowel confusion |
| Mandarin | /r-l/, /n-l/, /ʃ-s/, tonal pitch interference on prosody |
| Arabic | /p-b/, /v-f/, heavy syllable preference |
| French | Nasalized vowels, syllable-timed rhythm, /h/ deletion |

This seeds the curriculum: start with the phonemes and prosodic patterns the learner is statistically most likely to struggle with, rather than teaching everything in alphabetical IPA order.

### Adaptive Spaced Repetition

Per phoneme, per learner: FSRS algorithm (better than SM-2, open-source).
- Each phoneme has a stability and retrievability estimate.
- After each session, phonemes not yet mastered are scheduled for review at optimal interval.
- Mastery definition: GOP > threshold on 3 consecutive attempts, at least 48 hours apart.
- Dashboard shows phoneme IPA chart colored by mastery state (red → yellow → green).

---

## Reference Audio System

**Native recordings**: 5 native speakers per target accent for each piece of curated content. Recorded at 48kHz in acoustic booth. Speaker-matched to learner by F0 range + speaking rate (compare closest native speaker, not arbitrary one).

**TTS for unlimited phrases**: Fine-tuned accent-specific TTS using StyleTTS2 or XTTS v2, trained on VCTK per accent. Used when user inputs custom text. Quality is clearly labeled as "AI reference" vs. "Human reference."

**Streaming accent conversion** (stretch goal): Based on the 2025 Emformer-based streaming conversion paper, let the user hear their own recording converted to the target accent. The most powerful pedagogical tool — "this is what you said; this is what it would sound like native."

---

## Frontend / UX

### Core View (Post-Recording)
```
[Phrase]  "The quick brown fox jumps over the lazy dog"

[Native ▶]  [You ▶]  [Side-by-side waveform comparison]

[Phoneme timeline — colored by accuracy]
 ð  ə  k  w  ɪ  k  b  r  aʊ  n  f  ɑ  k  s ...
🟢 🟢 🟢 🟢 🟢 🟢 🟢 🟡 🟢  🟢 🔴 🟢  🟢 🟢
          r slightly    fox: /f/ weak

[Scores]
  Phoneme Accuracy    88%  ████████░░
  Intonation          74%  ███████░░░
  Stress & Rhythm     81%  ████████░░
  Vowel Quality       70%  ███████░░░
  Accent Match (RP)   65%  ██████░░░░

[Feedback — from Claude]
  1. Your /f/ in "fox" is weak — the upper teeth should press the lower lip harder. (0:01.3)
  2. Your rhythm is syllable-timed. Drop the vowels in unstressed syllables: "the" → /ðə/, "of" → /əv/.
  3. Your intonation falls too early. In RP, keep the pitch level through "brown fox" before the drop on "dog."

[Try again]  [Slow it down 0.75×]  [Next phrase →]
```

### Additional Views
- **Vowel Space Plot**: F1/F2 scatter of your vowels vs. target accent vowel norms. See exactly where /æ/ vs /ɑ/ is for your voice.
- **Pitch Contour**: F0 overlay (you = red, native = blue) with phoneme labels below.
- **IPA Heatmap**: Your full phoneme accuracy map — click any phoneme to go to drills for it.
- **Progress Graph**: Accent distance over time — watch your embedding drift toward the target cluster.
- **Session Summary**: Phonemes improved, phonemes that need work, minutes practiced, streak.

### Study Modes
1. **Listen** — study native audio, slow it to 0.5×, see spectrogram + phoneme labels
2. **Record** — standard assessment mode
3. **Shadow** — listen and record simultaneously; auto-align; compare waveforms
4. **Drill** — rapid-fire minimal pairs targeting one phoneme contrast
5. **Free Talk** — open mic, continuous scoring; receive a report at the end (fluency/accent focused)

---

## Tech Stack

### ML Models
| Component | Model | Source |
|---|---|---|
| Phoneme aligner & GOP | wav2vec2-large-robust-L2-english-phoneme | [slplab/HuggingFace](https://hf.co/slplab/wav2vec2-large-robust-L2-english-phoneme-recognition) |
| Accent embedding | WavLM-Large (fine-tuned on VCTK + L2-ARCTIC) | [microsoft/wavlm-large](https://hf.co/microsoft/wavlm-large) |
| Pitch extraction | CREPE (CNN-based, robust to non-native) | marl/crepe (PyPI) |
| Formant tracking | Parselmouth (Python Praat) | parselmouth (PyPI) |
| VAD | Silero VAD (ONNX, browser-capable) | silero-vad |
| TTS reference | StyleTTS2 / XTTS v2 (accent fine-tuned) | HuggingFace |
| Feedback | Claude API (claude-sonnet-4-6) | Anthropic |
| ASR fallback | Whisper-large-v3 | openai/whisper-large-v3 |

### Training Data
| Dataset | Size | Role |
|---|---|---|
| speechocean762 | 5K utterances, phoneme-rated | Fine-tune phoneme scorer, SOTA benchmark |
| L2-ARCTIC | 7.2K utterances, 24 L2 speakers | Real L2 error patterns for training |
| VCTK | 109 speakers, multi-accent native | Native accent embeddings + reference audio |
| Common Voice | Massive, accent-tagged | Accent classifier training |
| Speech Accent Archive | 2K+ speakers, 214 L1s | L1-specific error mapping |
| LibriSpeech | 1K hours, clean native | ASR backbone, pre-training |

### Backend
- FastAPI + WebSocket for streaming audio processing
- TorchServe or Triton Inference Server for model serving
- GPU: A100 for WavLM-Large + batch inference; H100 for real-time streaming paths
- Redis for session state + feedback caching
- PostgreSQL for user data, phoneme progress, session history
- S3 for reference audio (CDN-served)
- Celery for async heavy jobs (accent embedding computation, long recordings)

### Frontend
- Next.js (current stack, keep it)
- WebAudio API for real-time waveform + RMS meter
- Tone.js for playback rate control (0.5×, 0.75×)
- Canvas/WebGL for spectrogram and formant plot rendering
- Framer Motion for score animations (already in current system)

### Mobile (Phase 2)
- React Native for cross-platform
- On-device: quantized wav2vec2-small (INT8) for instant phoneme feedback < 200ms
- Cloud: full WavLM-Large + Claude for detailed session report

---

## Phased Delivery

### Phase 1 — Core Engine (MVP, ~3 months)
- Phoneme aligner + GOP scorer (wav2vec2-L2 fine-tuned on speechocean762)
- 4 pronunciation dimensions (accuracy, intonation, stress, vowel quality)
- 2 target accents (General American, RP British)
- Claude-generated feedback per session
- 50 curated phrases with human-recorded native audio (2 accents)
- Basic IPA timeline visualization
- User accounts + session history

### Phase 2 — Accent Depth (~2 months)
- WavLM accent distance tracking
- 4 more accent targets (Australian, Irish, Scottish, Indian English)
- L1-aware curriculum (6 L1 backgrounds)
- Vowel space F1/F2 plot
- FSRS spaced repetition per phoneme

### Phase 3 — Content & Engagement (~2 months)
- Minimal pairs drill system
- Authentic clip library (podcast/speech excerpts)
- Shadow mode (simultaneous listen + record)
- Phoneme IPA heatmap dashboard
- Free recording (custom text → TTS reference → score)

### Phase 4 — Streaming & Scale (~2 months)
- Streaming assessment (partial feedback before recording ends)
- On-device quantized model for mobile
- Accent conversion demo ("hear yourself native")
- Curriculum analytics + A/B testing framework

---

## Key Differences from Current System

| | Current PronounceAI | Redesign |
|---|---|---|
| Granularity | Word + utterance-global | Phoneme-level with timestamps |
| Training data for "bad" | Synthetic augmentation (pitch shift, noise) | Real L2 speech (speechocean762, L2-ARCTIC) |
| Scoring | 2-axis (word accuracy + acoustic global) | 5-axis (phoneme, intonation, stress, vowel, accent distance) |
| Accent awareness | None — one generic English target | 6 specific accent targets, per-accent norms |
| Feedback | 1-line rule-based | 2-3 LLM-generated articulatory instructions |
| Visualization | 3 bars (clarity/pitch/energy) | Phoneme timeline, vowel plot, pitch contour overlay |
| Curriculum | 20 fixed phrases, stateless | Adaptive spaced repetition per phoneme, L1-aware |
| Combined meta-model | Miscalibrated RF on M1+M2 | No meta-model needed — scores are interpretable |
| Formant analysis | None | F1/F2/F3 per vowel, compared to target accent vowel space |
