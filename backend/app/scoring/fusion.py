"""Score blending and grounding gates.

Two reconciliations happen here:

  * the optional WavLM multi-task assessment head is blended per-dimension
    with the deterministic acoustic scores when a checkpoint is present
  * Whisper phrase-match drives a single discrete gate; the score is capped
    only when phrase recognition is unambiguously wrong, and the same metric
    is classified into a status string the frontend can render explicitly
"""
from __future__ import annotations

from typing import Optional

PHRASE_MATCH_OK = 78          # >= 78 → ok
PHRASE_MATCH_PARTIAL = 65     # 65-77 → partial
PHRASE_MATCH_WEAK = 45        # 45-64 → weak; < 45 → mismatch


def classify_phrase_match(phrase_metrics: Optional[dict]) -> Optional[str]:
    """Map ``phrase_match_metrics`` output to a discrete UI-facing state.

    Returns None when ASR did not run (no transcript). The frontend can use
    this to show a single warning chip instead of inferring intent from a
    silently-capped score.
    """
    if not phrase_metrics:
        return None
    match = phrase_metrics["phrase_match"]
    if match >= PHRASE_MATCH_OK:
        return "ok"
    if match >= PHRASE_MATCH_PARTIAL:
        return "partial"
    if match >= PHRASE_MATCH_WEAK:
        return "weak"
    return "mismatch"


def ground_overall_score(overall: float, phrase_metrics: Optional[dict]) -> tuple[float, Optional[dict]]:
    """Cap the overall score when Whisper says the spoken phrase doesn't match."""
    if not phrase_metrics:
        return overall, None

    match = phrase_metrics["phrase_match"]
    adjusted = overall
    reason: Optional[str] = None
    # Single cap: only the unambiguous "wrong phrase" case clamps the score.
    # Partial/weak matches are surfaced via ``classify_phrase_match`` so the
    # UI can show a warning chip without the score silently moving.
    if match < PHRASE_MATCH_WEAK:
        adjusted = min(adjusted, 55.0)
        reason = "phrase_mismatch"

    gate = None
    if adjusted != overall:
        gate = {
            "type": reason,
            "raw": round(overall, 1),
            "adjusted": round(adjusted, 1),
            **phrase_metrics,
        }
    return round(adjusted, 1), gate


def blend_learned_scores(scores: dict, learned: Optional[dict]) -> tuple[dict, Optional[float]]:
    """Blend deterministic per-dimension scores with optional learned APA outputs.

    The learned WavLM head captures global speech-quality cues; the deterministic
    scorer keeps local interpretability. A conservative 0.60/0.40 weighting on
    overlapping dimensions improves quality when a checkpoint is installed
    without making the product opaque.
    """
    if not learned:
        return scores, None

    blended = dict(scores)
    mapping = {
        "accuracy": "phoneme_accuracy",
        "prosody": "intonation",
        "fluency": "stress_rhythm",
    }
    for learned_key, score_key in mapping.items():
        if learned_key in learned and score_key in blended:
            blended[score_key] = round(blended[score_key] * 0.60 + learned[learned_key] * 0.40, 1)

    learned_overall = learned.get("overall")
    return blended, learned_overall
