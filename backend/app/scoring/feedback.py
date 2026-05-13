"""Tip + diagnostic builders for the score response.

`build_feedback` returns up to three actionable tips for the UI.
`phonological_diagnostics` returns the top phone substitutions as feature-level
diagnoses so the practice UI can show "what changed and how to fix it" hints.
"""
from __future__ import annotations

from typing import Optional

from app.models.phonology import diagnose_substitution


def build_feedback(
    phoneme_results: list,
    scores: dict,
    phrase_metrics: Optional[dict],
    gates: list[dict],
) -> list[dict]:
    tips: list[dict] = []
    if phrase_metrics and phrase_metrics["phrase_match"] < 65:
        tips.append({
            "text": "Repeat the assigned words first; the scorer detected a phrase mismatch.",
        })

    weak = sorted(
        [r for r in phoneme_results if not r.correct],
        key=lambda r: r.gop,
    )
    if weak:
        worst = weak[0]
        diagnosis = diagnose_substitution(worst.phoneme, worst.expected)
        if diagnosis is not None:
            tips.append({
                "text": (
                    f"Your /{worst.expected}/ is drifting toward /{worst.phoneme}/; "
                    f"{diagnosis['hint']}."
                ),
                "timestamp_ms": worst.start_ms,
            })
        else:
            tips.append({
                "text": f"Focus on /{worst.expected}/; your closest detected sound was /{worst.phoneme}/.",
                "timestamp_ms": worst.start_ms,
            })

    lowest_dim = min(scores.items(), key=lambda kv: kv[1])
    if lowest_dim[1] < 70:
        labels = {
            "phoneme_accuracy": "sound accuracy",
            "intonation": "pitch movement",
            "stress_rhythm": "stress and rhythm",
            "vowel_quality": "vowel placement",
        }
        tips.append({"text": f"Next pass: prioritize {labels.get(lowest_dim[0], lowest_dim[0])}."})

    if not tips and gates:
        tips.append({"text": "The main score was adjusted because transcript evidence was uncertain."})

    return tips[:3]


def phonological_diagnostics(phoneme_results: list) -> list[dict]:
    diagnostics = []
    for r in phoneme_results:
        diagnosis = diagnose_substitution(r.phoneme, r.expected)
        if diagnosis is None:
            continue
        diagnostics.append({
            **diagnosis,
            "start_ms": r.start_ms,
            "end_ms": r.end_ms,
            "gop": r.gop,
        })
    diagnostics.sort(key=lambda d: d["gop"])
    return diagnostics[:8]
