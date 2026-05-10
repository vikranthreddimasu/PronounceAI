# PronounceAI — Combined Module

Integrates Module 1 (Whisper ASR) and Module 2 (Acoustic Analysis) into a single
pronunciation assessment pipeline, trains a meta-model over both scores, and
exposes everything via a FastAPI backend for the PronounceAI web application.

---

## Purpose

| Module | Role | Output |
|---|---|---|
| **Module 1** | Speech-to-text (Whisper) | Word accuracy vs. reference text |
| **Module 2** | Acoustic quality (RF + NN) | Pronunciation quality score |
| **Combined** | Meta-model + API | Three scores + feedback |

---

## Folder Structure

```
combined_module/
├── notebooks/
│   ├── notebook1_combined_feature_generation.ipynb  # generate training CSV
│   ├── notebook2_combined_model_training.ipynb      # train meta-model
│   ├── notebook3_combined_evaluation.ipynb          # evaluate all scorers
│   └── notebook4_combined_demo.ipynb                # end-to-end demo
├── models/                                          # saved by notebook 2
│   ├── combined_rf.joblib
│   ├── combined_scaler.joblib
│   ├── combined_net.pt
│   ├── combined_config.json
│   └── combined_features.csv                        # saved by notebook 1
├── utils/
│   ├── load_module1.py    # Module1Scorer (Whisper wrapper)
│   ├── load_module2.py    # Module2Scorer (RF + NN wrapper)
│   ├── scoring.py         # combine scores, generate feedback, CombinedScorer
│   └── data_utils.py      # LibriSpeech helpers, augmentation
├── api/
│   ├── app.py             # FastAPI application
│   └── schemas.py         # Pydantic response models
└── README.md
```

---

## How Module 1 and Module 2 Are Combined

```
User Audio
    │
    ├─► Module 1 (Whisper ASR)
    │       Transcribe audio → compare to reference_text via word-level F1
    │       module1_score = F1 × 100  ∈ [0, 100]
    │
    └─► Module 2 (RF + NN)
            Extract 86-dim acoustic features
            Average RF P(good) and NN P(good)
            module2_score = average × 100  ∈ [0, 100]

                         ↓
    ┌─────────────────────────────────────────────────────┐
    │  Weighted Score  = w1 × module1 + w2 × module2      │
    │  (default w1=0.5, w2=0.5; configurable per request) │
    └─────────────────────────────────────────────────────┘
                         ↓
    ┌─────────────────────────────────────────────────────┐
    │  Combined Model Score                               │
    │  Trained RF on [module1_score, module2_score]       │
    │  → P(good) × 100  ∈ [0, 100]                       │
    └─────────────────────────────────────────────────────┘
```

---

## `final_combined_score` vs `combined_model_score`

These two fields both express overall pronunciation quality on a 0–100 scale but
are computed in completely different ways.

### `final_combined_score` — No Training Required

```
final_combined_score = w1 × module1_score + w2 × module2_score
                     = 0.5 × 87.5 + 0.5 × 72.3
                     = 79.9
```

- **Pure arithmetic** — just a weighted average, no model involved
- **Always available** from the first API call
- **Weights are adjustable** per request via `w1` and `w2`
- **Linear** — assumes module1 and module2 contribute equally and independently

### `combined_model_score` — Requires Training

```
combined_model_score = RandomForest([module1_score, module2_score]) → P(good) × 100
                     = 81.2
```

- **Learned from data** — trained on LibriSpeech samples in notebooks 1 & 2
- **Non-linear** — the RF can learn patterns a simple average cannot, e.g.
  "very low module2 means bad pronunciation regardless of how high module1 is"
- **Not available** (`null`) until notebooks 1 & 2 have been run
- **Fixed after training** — weights cannot be changed per request

### Where They Differ — Concrete Example

Suppose a speaker says the right words but sounds very unnatural:

| Score | Value | Reasoning |
|---|---|---|
| `module1_score` | 95 | Words match the reference closely |
| `module2_score` | 30 | Acoustic quality is poor |
| `final_combined_score` | **62.5** | `0.5×95 + 0.5×30` — treats both equally |
| `combined_model_score` | **~35** | RF learned that very low module2 strongly signals bad pronunciation, so it down-weights the high module1 |

### Quick Comparison Table

| | `final_combined_score` | `combined_model_score` |
|---|---|---|
| **Method** | Weighted average (arithmetic) | Trained Random Forest |
| **Training needed** | No | Yes (notebooks 1 & 2) |
| **Non-linear** | No | Yes |
| **Weights configurable** | Yes (`w1`, `w2` per request) | No (fixed after training) |
| **Always available** | Yes | Only after training (`null` otherwise) |
| **Best for** | Quick baseline, always works | More nuanced prediction after training |

---

## How to Run Notebooks

### Prerequisites
- Module 1 weights saved at `model/module_1/weights/whisper-base-librispeech/`
- Module 2 models saved at `model/module_2/models/`
- LibriSpeech extracted at `PronounceAI/librispeech/LibriSpeech/`

### Order

```bash
# 1. Generate combined training features (~10–15 min on CPU with MAX_FILES=30)
jupyter notebook notebooks/notebook1_combined_feature_generation.ipynb

# 2. Train the combined meta-model (<1 min)
jupyter notebook notebooks/notebook2_combined_model_training.ipynb

# 3. Evaluate performance
jupyter notebook notebooks/notebook3_combined_evaluation.ipynb

# 4. Interactive demo
jupyter notebook notebooks/notebook4_combined_demo.ipynb
```

### Where Models Are Saved

All trained artifacts go to `combined_module/models/`:

| File | Description |
|---|---|
| `combined_features.csv` | Feature table generated by notebook 1 |
| `combined_rf.joblib` | Primary Random Forest meta-classifier |
| `combined_scaler.joblib` | StandardScaler for `[m1, m2]` input |
| `combined_net.pt` | Optional PyTorch MLP meta-classifier |
| `combined_config.json` | Training metadata |

---

## API

### Start the Server

```bash
# From PronounceAI/model/
uvicorn combined_module.api.app:app --reload --port 8000
```

The API loads Module 1 (Whisper) and Module 2 models at startup.
First boot takes 20–30 seconds on CPU.

### Health Check

```bash
curl http://localhost:8000/
```

Response:
```json
{
  "status": "ok",
  "module1_loaded": true,
  "module2_loaded": true,
  "combined_model_available": true
}
```

### POST /predict

**curl example:**

```bash
curl -X POST http://localhost:8000/predict \
  -F "audio=@/path/to/recording.wav" \
  -F "reference_text=the quick brown fox" \
  -F "w1=0.5" \
  -F "w2=0.5"
```

**Python example:**

```python
import requests

with open("recording.wav", "rb") as f:
    response = requests.post(
        "http://localhost:8000/predict",
        files={"audio": ("recording.wav", f, "audio/wav")},
        data={
            "reference_text": "the quick brown fox",
            "w1": 0.5,
            "w2": 0.5,
        },
    )

result = response.json()
print(result)
```

**Response JSON:**

```json
{
  "module1_score": 87.5,
  "module2_score": 72.3,
  "final_combined_score": 79.9,
  "combined_model_score": 81.2,
  "feedback": "Good pronunciation.",
  "transcript": "the quick brown fox"
}
```

| Field | Range | Meaning |
|---|---|---|
| `module1_score` | 0–100 | How well the spoken words match the reference |
| `module2_score` | 0–100 | Intrinsic acoustic/pronunciation quality |
| `final_combined_score` | 0–100 | Weighted average (w1+w2=1.0) |
| `combined_model_score` | 0–100 or null | Trained meta-model prediction |
| `feedback` | string | One-line human-readable assessment |
| `transcript` | string | Raw Whisper transcription |

### Feedback Rules

| Condition | Feedback |
|---|---|
| `module1_score < 50` | "Words do not match the expected sentence." |
| `module2_score < 50` | "Pronunciation/acoustic quality needs improvement." |
| `final_score >= 80` | "Good pronunciation." |
| `final_score >= 60` | "Pronunciation is mostly correct with minor issues." |
| otherwise | "Pronunciation needs improvement in both accuracy and quality." |

### Integration with Web App

The frontend should:
1. Capture audio (MediaRecorder API or file upload)
2. `POST /predict` with the audio blob and the reference sentence
3. Display the four scores and feedback string

CORS is enabled for all origins (`allow_origins=["*"]`).
Restrict this in `api/app.py` for production deployments.

---

## Required Packages

```bash
pip install fastapi uvicorn[standard] python-multipart \
            transformers torch librosa soundfile \
            joblib scikit-learn numpy pandas matplotlib seaborn tqdm
```
