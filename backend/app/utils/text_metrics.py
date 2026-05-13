"""
Lightweight text matching helpers used for transcript validation.

These functions intentionally avoid LLMs. For a pronunciation coach, the
question is narrow: did the audio contain the words the learner was asked to
say? Normalized edit distance plus character similarity is more predictable
and easier to evaluate than generated judgement text.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Sequence

_WORD_RE = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)?")
_NUMBER_WORDS = {
    "0": "zero",
    "1": "one",
    "2": "two",
    "3": "three",
    "4": "four",
    "5": "five",
    "6": "six",
    "7": "seven",
    "8": "eight",
    "9": "nine",
    "10": "ten",
    "11": "eleven",
    "12": "twelve",
    "13": "thirteen",
    "14": "fourteen",
    "15": "fifteen",
    "16": "sixteen",
    "17": "seventeen",
    "18": "eighteen",
    "19": "nineteen",
    "20": "twenty",
}


def normalize_text(text: str) -> str:
    """Lowercase, strip punctuation, and collapse whitespace."""
    text = (text or "").lower().replace("’", "'")
    tokens = _WORD_RE.findall(text)
    return " ".join(_NUMBER_WORDS.get(tok, tok) for tok in tokens)


def word_tokens(text: str) -> list[str]:
    return normalize_text(text).split()


def edit_distance(source: Sequence[object], target: Sequence[object]) -> int:
    """Levenshtein distance using O(min(n, m)) memory."""
    if len(source) < len(target):
        source, target = target, source
    previous = list(range(len(target) + 1))
    for i, src in enumerate(source, start=1):
        current = [i]
        for j, tgt in enumerate(target, start=1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (0 if src == tgt else 1),
                )
            )
        previous = current
    return previous[-1]


def word_error_rate(hypothesis: str, reference: str) -> float:
    ref = word_tokens(reference)
    if not ref:
        return 0.0
    hyp = word_tokens(hypothesis)
    return round(edit_distance(hyp, ref) / len(ref), 3)


def sequence_similarity(hypothesis: str, reference: str) -> float:
    hyp = normalize_text(hypothesis)
    ref = normalize_text(reference)
    if not hyp and not ref:
        return 1.0
    return round(SequenceMatcher(None, hyp, ref).ratio(), 3)


def word_coverage(hypothesis: str, reference: str) -> float:
    ref_words = set(word_tokens(reference))
    if not ref_words:
        return 1.0
    hyp_words = set(word_tokens(hypothesis))
    return round(len(ref_words & hyp_words) / len(ref_words), 3)


def phrase_match_metrics(hypothesis: str, reference: str) -> dict:
    """
    Conservative phrase-match score in [0, 100].

    WER catches missing or substituted words. Character similarity softens
    harsh WER behavior on very short phrases, where one ASR tokenization error
    can otherwise dominate. Coverage ensures a transcript that is merely a
    similar-looking fragment does not score too highly.
    """
    wer = word_error_rate(hypothesis, reference)
    wer_score = max(0.0, 1.0 - min(1.0, wer))
    char_sim = sequence_similarity(hypothesis, reference)
    coverage = word_coverage(hypothesis, reference)
    score = 100.0 * (0.55 * wer_score + 0.30 * char_sim + 0.15 * coverage)
    return {
        "wer": wer,
        "char_similarity": char_sim,
        "word_coverage": coverage,
        "phrase_match": round(max(0.0, min(100.0, score)), 1),
    }
