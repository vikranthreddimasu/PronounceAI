"""
Phonological feature diagnostics for pronunciation feedback.

Recent mispronunciation-diagnosis work shows that phonological attributes
such as voicing, place, and manner often explain learner errors better than
plain phoneme labels. This module gives the production scorer an interpretable
version of that idea without requiring a separate attribute detector checkpoint.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PhoneFeatures:
    manner: str
    place: str
    voicing: str
    height: str = ""
    backness: str = ""
    roundness: str = ""
    length: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            k: v
            for k, v in {
                "manner": self.manner,
                "place": self.place,
                "voicing": self.voicing,
                "height": self.height,
                "backness": self.backness,
                "roundness": self.roundness,
                "length": self.length,
            }.items()
            if v
        }


# Compact ARPAbet feature inventory. The runtime model emits lowercase ARPAbet.
PHONE_FEATURES: dict[str, PhoneFeatures] = {
    # Stops / affricates
    "p": PhoneFeatures("stop", "bilabial", "voiceless"),
    "b": PhoneFeatures("stop", "bilabial", "voiced"),
    "t": PhoneFeatures("stop", "alveolar", "voiceless"),
    "d": PhoneFeatures("stop", "alveolar", "voiced"),
    "k": PhoneFeatures("stop", "velar", "voiceless"),
    "g": PhoneFeatures("stop", "velar", "voiced"),
    "ch": PhoneFeatures("affricate", "palato-alveolar", "voiceless"),
    "jh": PhoneFeatures("affricate", "palato-alveolar", "voiced"),
    # Fricatives
    "f": PhoneFeatures("fricative", "labiodental", "voiceless"),
    "v": PhoneFeatures("fricative", "labiodental", "voiced"),
    "th": PhoneFeatures("fricative", "dental", "voiceless"),
    "dh": PhoneFeatures("fricative", "dental", "voiced"),
    "s": PhoneFeatures("fricative", "alveolar", "voiceless"),
    "z": PhoneFeatures("fricative", "alveolar", "voiced"),
    "sh": PhoneFeatures("fricative", "palato-alveolar", "voiceless"),
    "zh": PhoneFeatures("fricative", "palato-alveolar", "voiced"),
    "hh": PhoneFeatures("fricative", "glottal", "voiceless"),
    # Nasals / liquids / glides
    "m": PhoneFeatures("nasal", "bilabial", "voiced"),
    "n": PhoneFeatures("nasal", "alveolar", "voiced"),
    "ng": PhoneFeatures("nasal", "velar", "voiced"),
    "l": PhoneFeatures("liquid", "alveolar", "voiced"),
    "r": PhoneFeatures("liquid", "postalveolar", "voiced"),
    "w": PhoneFeatures("glide", "labial-velar", "voiced"),
    "y": PhoneFeatures("glide", "palatal", "voiced"),
    # Vowels
    "iy": PhoneFeatures("vowel", "front", "voiced", "high", "front", "unrounded", "long"),
    "ih": PhoneFeatures("vowel", "front", "voiced", "high", "front", "unrounded", "short"),
    "ey": PhoneFeatures("vowel", "front", "voiced", "mid", "front", "unrounded", "long"),
    "eh": PhoneFeatures("vowel", "front", "voiced", "mid", "front", "unrounded", "short"),
    "ae": PhoneFeatures("vowel", "front", "voiced", "low", "front", "unrounded", "short"),
    "aa": PhoneFeatures("vowel", "back", "voiced", "low", "back", "unrounded", "long"),
    "ao": PhoneFeatures("vowel", "back", "voiced", "mid", "back", "rounded", "long"),
    "ow": PhoneFeatures("vowel", "back", "voiced", "mid", "back", "rounded", "long"),
    "uh": PhoneFeatures("vowel", "back", "voiced", "high", "back", "rounded", "short"),
    "uw": PhoneFeatures("vowel", "back", "voiced", "high", "back", "rounded", "long"),
    "ah": PhoneFeatures("vowel", "central", "voiced", "mid", "central", "unrounded", "short"),
    "ax": PhoneFeatures("vowel", "central", "voiced", "mid", "central", "unrounded", "short"),
    "er": PhoneFeatures("vowel", "central-rhotic", "voiced", "mid", "central", "unrounded", "long"),
    "aw": PhoneFeatures("diphthong", "back-front", "voiced", "low", "back-front", "rounded", "long"),
    "ay": PhoneFeatures("diphthong", "front", "voiced", "low", "front", "unrounded", "long"),
    "oy": PhoneFeatures("diphthong", "back-front", "voiced", "mid", "back-front", "rounded", "long"),
}


FEATURE_HINTS = {
    "voicing": {
        ("voiced", "voiceless"): "keep the airflow but remove vocal-fold vibration",
        ("voiceless", "voiced"): "add gentle vocal-fold vibration while keeping the same mouth shape",
    },
    "place": {
        "dental": "place the tongue tip lightly between or just behind the teeth",
        "alveolar": "move the tongue tip to the ridge behind the upper teeth",
        "palato-alveolar": "pull the tongue body slightly back and round the lips a little",
        "labiodental": "touch the upper teeth to the lower lip",
        "postalveolar": "shape the tongue back from the tooth ridge without a firm tap",
        "velar": "raise the back of the tongue toward the soft palate",
    },
    "manner": {
        "fricative": "make a narrow channel and let air continue through it",
        "stop": "make a brief full closure, then release it cleanly",
        "liquid": "keep the sound open and resonant, without blocking airflow",
        "nasal": "let the sound resonate through the nose",
        "vowel": "open the vocal tract and avoid a consonant-like closure",
    },
    "height": {
        "high": "raise the tongue body",
        "mid": "keep the tongue at a mid height",
        "low": "lower the jaw and tongue body",
    },
    "backness": {
        "front": "move the tongue body forward",
        "central": "keep the tongue centered",
        "back": "move the tongue body back",
    },
    "roundness": {
        "rounded": "round the lips more",
        "unrounded": "relax lip rounding",
    },
    "length": {
        "long": "hold the vowel slightly longer",
        "short": "keep the vowel shorter and more relaxed",
    },
}


def diagnose_substitution(predicted: str | None, expected: str | None) -> dict | None:
    """Return feature-level diagnosis for a predicted -> expected phone mismatch."""
    if not predicted or not expected:
        return None
    pred = predicted.lower().strip()
    exp = expected.lower().strip()
    if pred == exp:
        return None

    pred_feat = PHONE_FEATURES.get(pred)
    exp_feat = PHONE_FEATURES.get(exp)
    if pred_feat is None or exp_feat is None:
        return None

    pred_d = pred_feat.as_dict()
    exp_d = exp_feat.as_dict()
    changes = {
        key: {"heard": pred_d.get(key), "target": exp_d.get(key)}
        for key in sorted(set(pred_d) | set(exp_d))
        if pred_d.get(key) != exp_d.get(key)
    }
    if not changes:
        return None

    priority = ["voicing", "place", "manner", "height", "backness", "roundness", "length"]
    primary = next((k for k in priority if k in changes), next(iter(changes)))
    target_value = changes[primary]["target"]
    heard_value = changes[primary]["heard"]

    hint = None
    hint_group = FEATURE_HINTS.get(primary, {})
    if isinstance(hint_group, dict):
        hint = hint_group.get((heard_value, target_value)) or hint_group.get(target_value)

    if hint is None:
        hint = f"shift {primary} from {heard_value} toward {target_value}"

    return {
        "heard": pred,
        "target": exp,
        "primary_feature": primary,
        "changes": changes,
        "hint": hint,
    }
