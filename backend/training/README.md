# Training Paths

PronounceAI now has two model-training tracks:

- `train_phoneme_scorer.py`: calibrates raw CTC/GOP evidence against human pronunciation accuracy ratings.
- `train_multitask_assessment.py`: trains the higher-ceiling multi-aspect scorer used by the backend when `checkpoints/assessment_head_best.pt` exists.

Recommended run for the multi-aspect scorer:

```bash
cd backend
source .venv/bin/activate
python -m training.train_multitask_assessment --epochs 60 --batch-size 64
```

For a quick smoke run:

```bash
python -m training.train_multitask_assessment --max-samples 128 --epochs 2 --embed-batch-size 4
```

The backend loads the resulting checkpoint automatically through
`ASSESSMENT_SCORER_CHECKPOINT`.
