"""Vowel-quality scoring from formant centroids.

Compares the learner's mean F1/F2 per vowel against accent-specific norms
(Peterson & Barney 1952 for GA, Hillenbrand 1995-style RP values). Returns
0-100; falls back to 70 when no formant data is available.
"""
from __future__ import annotations

import numpy as np


_GA_NORMS = {
    "IY": (437, 2761), "IH": (483, 2365), "EY": (536, 2530),
    "EH": (611, 1952), "AE": (669, 1843), "AH": (753, 1426),
    "AA": (936, 1551), "AO": (781, 1136), "OW": (555, 1035),
    "UH": (469, 1122), "UW": (459, 1105), "ER": (474, 1379),
}
_RP_NORMS = {
    "IY": (280, 2620), "IH": (390, 2090), "EY": (450, 2360),
    "EH": (580, 1950), "AE": (720, 1730), "AH": (710, 1220),
    "AA": (700, 1220), "AO": (600, 920),  "OW": (450, 900),
    "UH": (430, 1020), "UW": (310, 940),  "ER": (490, 1350),
}


def vowel_quality_score(formants: dict, accent: str) -> float:
    """Return 0-100. Falls back to 70 if no formant data."""
    norms = _RP_NORMS if accent == "RP" else _GA_NORMS

    if not formants:
        return 70.0

    distances = []
    for vowel, fvals in formants.items():
        if vowel in norms:
            target_f1, target_f2 = norms[vowel]
            dist = np.sqrt((fvals["f1"] - target_f1) ** 2 + (fvals["f2"] - target_f2) ** 2)
            score = max(0.0, 100 - dist / 5)
            distances.append(score)

    if not distances:
        return 70.0
    return round(float(np.mean(distances)), 1)
