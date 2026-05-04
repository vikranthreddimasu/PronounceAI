# Module 2 — Acoustic Feature Analysis

## Overview

Module 2 of **PronounceAI** analyzes the acoustic quality of speech at the audio level — independent of the text transcript. It extracts features like pitch, tone, energy, and pronunciation texture (MFCCs), then compares a user's speech against a native reference to generate a **Pronunciation Score (0–100)**.

This module works alongside **Module 1** (Whisper speech-to-text): Module 1 tells you *what* was said; Module 2 tells you *how well* it was pronounced.

---

## Features Extracted

| Feature | Tool | What it captures |
|---|---|---|
| **MFCC** (Mel-Frequency Cepstral Coefficients) | `librosa` | Vocal tract shape, articulation texture |
| **Pitch / F0** | `librosa.pyin` | Intonation, tone, naturalness |
| **Energy (RMS)** | `librosa` | Loudness, stress, rhythm |
| **Spectral Centroid** | `librosa` | Brightness / clarity of speech |

Each sample is represented as an **86-dimensional feature vector** (40 MFCC means + 40 MFCC stds + 6 scalar features).

---

## Folder Structure

```
model/
└── module_2/
    ├── notebooks/
    │   ├── notebook1_feature_extraction_training.ipynb
    │   ├── notebook2_evaluation.ipynb
    │   └── notebook3_demo.ipynb
    ├── models/
    │   ├── random_forest.joblib        ← trained after Notebook 1
    │   ├── pronunciation_net.pt        ← PyTorch neural network weights
    │   ├── scaler.joblib               ← feature normalizer
    │   ├── feature_config.json         ← stores n_mfcc, input_dim, sample_rate
    │   ├── training_curve.png
    │   └── feature_importance.png
    └── README.md
```

---

## Dataset Setup

Module 2 reuses the **LibriSpeech** dataset from Module 1. It must be extracted at:

```
NLP_project/
├── librispeech/
│   └── LibriSpeech/
│       ├── train-clean-100/   ← used for training
│       └── test-clean/        ← used for evaluation & demo
└── PronounceAI/
    └── model/
        └── module_2/
```

If `librispeech/` does not exist, run **Module 1 — Notebook 1** first (it extracts the archives automatically).

---

## Dependencies

Run in the first cell of any notebook, or install manually:

```bash
pip install librosa numpy pandas matplotlib scikit-learn torch torchaudio \
            soundfile joblib seaborn scipy ipywidgets
```

| Package | Purpose |
|---|---|
| `librosa` | Audio loading, MFCC, pitch, energy extraction |
| `scikit-learn` | Random Forest classifier, StandardScaler |
| `torch` | PyTorch neural network |
| `scipy` | Cosine distance for similarity scoring |
| `seaborn` | Confusion matrix heatmaps |
| `joblib` | Save/load sklearn models |
| `ipywidgets` | Interactive file upload in demo notebook |

---

## How to Run

### Notebook 1 — Feature Extraction + Training

1. Open `notebooks/notebook1_feature_extraction_training.ipynb`
2. Adjust constants near the top if needed:
   ```python
   MAX_SAMPLES = 300    # samples per class (increase for better accuracy)
   N_MFCC      = 40     # number of MFCC coefficients
   ```
3. Run all cells. The notebook will:
   - Collect `.flac` files from `train-clean-100`
   - Extract 86-dim feature vectors from each
   - Synthesize "degraded" samples via pitch shift, noise, and time stretch
   - Train a **Random Forest** (200 trees) and a **3-layer PyTorch MLP**
   - Save all model artifacts to `models/`

**Expected runtime:** ~5–15 min for 300 samples on CPU.

---

### Notebook 2 — Evaluation

1. **Prerequisite:** Notebook 1 must have been run
2. Open `notebooks/notebook2_evaluation.ipynb`
3. Run all cells to:
   - Load saved models from `models/`
   - Build an evaluation set from `test-clean`
   - Print classification report (Accuracy, Precision, Recall, F1)
   - Display confusion matrices
   - Plot MFCC heatmaps, pitch curves, and energy comparisons

---

### Notebook 3 — End-to-End Demo

1. **Prerequisite:** Notebook 1 must have been run
2. Open `notebooks/notebook3_demo.ipynb`
3. Set your audio files:
   ```python
   USER_AUDIO = "/path/to/user_recording.wav"
   REF_AUDIO  = "/path/to/reference_audio.flac"
   ```
4. Run all cells to get:
   - Feature Score, Model Score, and Final Score (all 0–100)
   - Per-feature similarity breakdown (MFCC, Pitch, Energy)
   - RF and NN model predictions (P(good))
   - Human-readable feedback for each dimension
   - MFCC heatmaps, pitch curves, energy plots
   - 3-panel score breakdown chart

**Alternative:** Use the interactive file-upload widget (Step 14) to upload files directly in the notebook.

**Batch scoring:** Use `batch_score(user_files, ref_file)` in Step 15 to score multiple recordings at once.

---

## How the Model Works

### Training (Notebook 1)

Since LibriSpeech contains only clean native speech, "bad" pronunciation samples are synthesized by applying one of:
- **Pitch shift** (±5–6 semitones) — unnatural intonation
- **White noise** (σ = 0.035) — unclear articulation
- **Time stretch** (rate 0.6–1.6×) — abnormal speaking rate

This creates a balanced binary classification dataset: `1 = good`, `0 = degraded`.

### Evaluation (Notebook 2)

Two models are compared:

| Model | Type | Notes |
|---|---|---|
| Random Forest | Ensemble classifier | Faster, interpretable, feature importance |
| PronunciationNet | 3-layer PyTorch MLP | Slightly better on non-linear patterns |

### Scoring (Notebook 3) — Hybrid Pipeline

Notebook 3 uses a **two-track hybrid approach** that combines feature-based and model-based scoring.

#### Why two tracks?

| Track | Strength | Limitation |
|---|---|---|
| Feature-based | Transparent — you can see which feature is off | Purely mathematical; no concept of "good pronunciation" |
| Model-based | Learned from training data; catches patterns feature comparison misses | Less interpretable |

Combining both gives a score that is both explainable and robust.

#### Track 1 — Feature Score (weight: 60%)

Directly compares the user's audio to the reference using cosine similarity:

```
Feature Score = ( 0.50 × MFCC_similarity
               + 0.30 × Pitch_similarity
               + 0.20 × Energy_similarity ) × 100
```

#### Track 2 — Model Score (weight: 40%)

Passes the user's features through both trained models and averages their quality predictions:

```
Model Score = ( 0.50 × RF_P(good)
              + 0.50 × NN_P(good) ) × 100
```

The scaler from training is applied before any model inference.

#### Final Score

```
Final Score = 0.6 × Feature Score  +  0.4 × Model Score
```

#### Feedback

Each dimension generates a specific message:

| Condition | Feedback |
|---|---|
| MFCC similarity < 0.60 | "Pronunciation clarity issue" |
| MFCC similarity 0.60–0.75 | "Articulation could improve" |
| Pitch similarity < 0.60 | "Pitch/intonation needs improvement" |
| Energy similarity < 0.60 | "Speaking volume inconsistency" |
| Model score < 50 | "Model detects significant pronunciation issues" |

#### Score Interpretation

| Score | Meaning |
|---|---|
| 90–100 | Excellent — near-native pronunciation |
| 70–89  | Good — minor improvements needed |
| 50–69  | Fair — noticeable pronunciation issues |
| < 50   | Needs practice — significant mismatch |

---

## Expected Outputs

| Notebook | Output Files | Console Output |
|---|---|---|
| Notebook 1 | `random_forest.joblib`, `pronunciation_net.pt`, `scaler.joblib`, `feature_config.json`, `training_curve.png`, `feature_importance.png` | Accuracy, classification report |
| Notebook 2 | `confusion_matrices.png`, `mfcc_comparison.png`, `pitch_comparison.png`, `energy_comparison.png` | Accuracy, classification report |
| Notebook 3 | `score_breakdown.png`, `demo_comparison.png` | Feature Score, Model Score, Final Score, feedback per dimension |

---

## Integration with Module 1

Module 1 provides the text transcript. Module 2 provides the acoustic quality score.
To build a complete pronunciation tutor, combine both:

```
Audio Input
    ├── Module 1 (Whisper) → What did the user say?
    └── Module 2 (Acoustic) → How well did they pronounce it?
                                ├── Feature Score (60%)
                                │     ├── MFCC similarity
                                │     ├── Pitch similarity
                                │     └── Energy similarity
                                ├── Model Score (40%)
                                │     ├── Random Forest P(good)
                                │     └── Neural Network P(good)
                                └── Final Score + Per-dimension Feedback
```
