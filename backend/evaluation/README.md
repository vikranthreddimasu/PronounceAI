# Backend Evaluation

This folder holds lightweight checks for the scoring API. It is designed for
small local fixture sets, not benchmark chasing or model training.

Create a JSONL manifest with one recording per line:

```json
{"audio_path":"fixtures/ship_or_sheep.wav","phrase":"Ship or sheep?","accent":"GA","min_phrase_match":90,"max_wer":0.1}
{"audio_path":"fixtures/wrong_phrase.wav","phrase":"The right light is bright","accent":"GA","max_overall":70}
```

With the backend running:

```bash
python -m evaluation.evaluate_score_api --manifest evaluation/score_manifest.jsonl
```

The report includes latency, WER, phrase-match score, scoring gates, and any
expectation failures.
