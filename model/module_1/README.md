# Module 1 — Speech-to-Text using Whisper

## Overview

Module 1 of **PronounceAI** implements an automatic speech recognition (ASR) pipeline using [OpenAI Whisper](https://openai.com/research/whisper) fine-tuned on the [LibriSpeech](https://www.openslr.org/12) corpus.

The pipeline covers:
- Fine-tuning the pretrained `whisper-base` model on `train-clean-100`
- Evaluating on `dev-clean` (during training) and `test-clean` (final evaluation)
- Computing Word Error Rate (WER) and Character Error Rate (CER)
- A live demo notebook for transcribing any audio file

---

## Folder Structure

```
model/
└── module_1/
    ├── notebooks/
    │   ├── notebook1_train_test_save.ipynb   # Training, validation, testing, saving
    │   ├── notebook2_evaluation.ipynb        # Evaluation on new/test data
    │   └── notebook3_demo.ipynb              # End-to-end demo
    ├── weights/
    │   └── whisper-base-librispeech/         # Saved model (created after Notebook 1)
    └── README.md                             # This file
```

---

## Dataset Setup

Place the LibriSpeech `.tar.gz` files in the **NLP_project root** (one level above `PronounceAI/`):

```
NLP_project/
├── train-clean-100.tar.gz
├── dev-clean.tar.gz
├── test-clean.tar.gz
└── PronounceAI/
    └── model/
        └── module_1/
```

The notebooks will automatically extract these archives into `NLP_project/librispeech/`.

---

## Requirements

Install all dependencies by running the first cell of any notebook, or manually:

```bash
pip install transformers datasets torch torchaudio accelerate evaluate jiwer \
            soundfile librosa pandas ipywidgets
```

**Key packages:**
| Package | Purpose |
|---|---|
| `transformers` | Whisper model & processor |
| `datasets` | Dataset loading & preprocessing |
| `torch` / `torchaudio` | Deep learning backend |
| `evaluate` / `jiwer` | WER / CER metrics |
| `librosa` | Audio loading & resampling |
| `soundfile` | .flac / .wav I/O |

A CUDA-capable GPU is recommended but not required (CPU training will be slow).

---

## How to Run

### Notebook 1 — Train, Test, Save

1. Open `notebooks/notebook1_train_test_save.ipynb`
2. Run all cells in order
3. The notebook will:
   - Extract LibriSpeech archives automatically
   - Fine-tune `whisper-base` for 200 steps (adjust `max_steps` for longer training)
   - Evaluate on `test-clean`
   - Save the model to `weights/whisper-base-librispeech/`

> **Quick smoke-test:** `MAX_TRAIN_SAMPLES = 500` is set by default. Set it to `None` to use the full dataset.

---

### Notebook 2 — Evaluate on New Data

1. **Prerequisite:** Notebook 1 must have been run (model weights must exist)
2. Open `notebooks/notebook2_evaluation.ipynb`
3. Run all cells to:
   - Load the saved model
   - Run inference on `test-clean` (or set a custom folder)
   - Print WER and CER scores
   - Display a table of predictions vs. ground truth

To evaluate a **custom dataset**, edit the `EVAL_SPLIT` variable or uncomment the custom-folder cell at the end.

---

### Notebook 3 — End-to-End Demo

1. **Prerequisite:** Notebook 1 must have been run
2. Open `notebooks/notebook3_demo.ipynb`
3. Options:
   - **File path:** Edit `AUDIO_FILE` to point to any `.flac`, `.wav`, or `.mp3` file
   - **File upload:** Use the interactive uploader widget in Step 6
   - **Microphone:** Uncomment Step 7 and install `sounddevice` + `scipy`

---

## Training Details

| Setting | Value |
|---|---|
| Base model | `openai/whisper-base` |
| Dataset | LibriSpeech `train-clean-100` |
| Optimizer | AdamW |
| Learning rate | 1e-5 |
| Batch size | 4 (effective: 8 with gradient accumulation) |
| Steps | 200 (default, increase for better accuracy) |
| Evaluation | Every 50 steps on `dev-clean` |
| Metric | Word Error Rate (WER) |

---

## Expected Outputs

| Notebook | Output |
|---|---|
| Notebook 1 | Training loss curve, final WER on test-clean, saved weights in `weights/` |
| Notebook 2 | WER & CER scores, predictions table |
| Notebook 3 | Text transcription of the provided audio file |

---

## Notes

- Whisper is already a powerful pretrained model. Even with 200 fine-tuning steps on a subset, WER on LibriSpeech clean sets should be in the 3–10% range.
- For production-quality results, train for more steps using the full `train-clean-100` split.
- All paths in the notebooks are relative to their location inside `notebooks/`, so keep the folder structure intact.
