"""
Layer 5 — LLM Feedback Generator.

Uses Fireworks.ai (OpenAI-compatible API) with Llama 3.3 70B.
Falls back to a rule-based response if the API call fails.
Results cached by (error_fingerprint, l1, accent) — >70% hit rate for common errors.
"""
import json
import logging
import os

from openai import AsyncOpenAI

from app.utils.cache import get_cached_feedback, set_cached_feedback

logger = logging.getLogger(__name__)

FIREWORKS_BASE_URL = "https://api.fireworks.ai/inference/v1"
MODEL = os.getenv("FIREWORKS_MODEL_ID", "accounts/fireworks/models/llama-v3p3-70b-instruct")

L1_NOTES = {
    "japanese": "Japanese speakers often merge /r/ and /l/, add vowels between consonants, and transfer pitch-accent prosody to English.",
    "spanish":  "Spanish speakers often devoice /v/ to /b/, merge /s/ and /z/, use syllable-timed rhythm, and struggle with consonant clusters.",
    "mandarin": "Mandarin speakers often merge /r/ and /l/, /n/ and /l/, add tonal pitch interference, and struggle with /ʃ/ vs /s/.",
    "german":   "German speakers often apply final devoicing, merge /w/ and /v/, and confuse tense/lax vowel pairs.",
    "arabic":   "Arabic speakers often merge /p/ and /b/, /v/ and /f/, prefer heavy syllables, and struggle with consonant clusters.",
    "french":   "French speakers often nasalize vowels, use syllable-timed rhythm, delete /h/, and have difficulty with /æ/ and /ɪ/ distinctions.",
    "korean":   "Korean speakers often devoice word-final consonants, aspirate stops inconsistently, and struggle with /r/ vs /l/ and /f/ vs /p/.",
    "hindi":    "Hindi speakers often retroflex /t/ and /d/, struggle with /v/ vs /w/, and transfer retroflex consonants.",
}

ACCENT_PROFILES = {
    "GA":       "General American — rhotic /r/, flap T intervocalically (butter→budder), low-back merger, reduced unstressed vowels to schwa.",
    "RP":       "Received Pronunciation (BBC British) — non-rhotic, TRAP-BATH split, FOOT-STRUT split, distinct /ɒ/, /t/ not flapped.",
    "AuE":      "General Australian — non-rhotic, raised /æ/ close to /e/, distinctive FACE and GOAT diphthongs.",
    "Irish":    "Irish English — rhotic, clear /l/ everywhere, distinct short vowels, no LOT-THOUGHT merger.",
    "Scottish": "Scottish English — rhotic, Scottish Vowel Length Rule, monophthong FACE and GOAT.",
    "IndianE":  "Indian English — retroflex consonants, syllable-timed, dental stops for /θ/ and /ð/.",
}

SYSTEM_PROMPT = """You are an expert pronunciation coach specialising in accent acquisition.
Given a structured analysis of a learner's pronunciation errors, produce 2-3 concise coaching tips.

Each tip must:
1. Name the specific phoneme or prosody issue
2. Explain why it matters for the target accent
3. Give a precise articulatory instruction (tongue/lip/teeth placement, airflow)

Rules:
- Maximum 3 tips, at least 1
- Prioritise the most impactful errors first
- Be specific and concrete, not generic
- Each tip is 1-2 sentences max

Respond with valid JSON only — no markdown, no prose outside JSON:
{"tips": [{"text": "...", "phoneme": "...", "timestamp_ms": <int or null>}]}"""


class FeedbackGenerator:
    def __init__(self):
        api_key = os.environ.get("FIREWORKS_API_KEY")
        if not api_key:
            logger.warning("FIREWORKS_API_KEY not set — feedback will use rule-based fallback")
        self.client = AsyncOpenAI(
            api_key=api_key or "not-set",
            base_url=FIREWORKS_BASE_URL,
        )

    async def generate(
        self,
        phoneme_errors: list[dict],
        prosody_issues: dict,
        target_accent: str,
        l1_lang: str = "unknown",
    ) -> list[dict]:
        error_pattern = {
            "top_errors": [
                {"expected": e["expected"], "got": e.get("phoneme", e["expected"])}
                for e in phoneme_errors[:5]
            ],
            "prosody_low": [k for k, v in prosody_issues.items() if isinstance(v, (int, float)) and v < 65],
        }

        cached = get_cached_feedback(error_pattern, l1_lang, target_accent)
        if cached:
            logger.debug("Feedback cache hit")
            return cached

        prompt = self._build_prompt(phoneme_errors, prosody_issues, target_accent, l1_lang)

        try:
            response = await self.client.chat.completions.create(
                model=MODEL,
                max_tokens=512,
                temperature=0.4,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": prompt},
                ],
            )
            text = response.choices[0].message.content.strip()
            # Strip accidental markdown fences
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            parsed = json.loads(text)
            tips = parsed.get("tips", [])
            logger.info(f"Fireworks feedback: {len(tips)} tips via {MODEL}")
        except Exception as e:
            logger.error(f"Fireworks feedback failed: {e}")
            tips = self._fallback_tips(phoneme_errors, prosody_issues)

        set_cached_feedback(error_pattern, l1_lang, target_accent, tips)
        return tips

    def _build_prompt(
        self,
        phoneme_errors: list[dict],
        prosody_issues: dict,
        target_accent: str,
        l1_lang: str,
    ) -> str:
        accent_profile = ACCENT_PROFILES.get(target_accent, ACCENT_PROFILES["GA"])
        l1_note = L1_NOTES.get(l1_lang.lower(), "")

        error_lines = []
        for e in phoneme_errors[:6]:
            sub = e.get("substitution")
            gop = e.get("gop", -3)
            t_ms = e.get("start_ms")
            if sub:
                error_lines.append(f"  - Substitution: {sub} (GOP {gop:.1f}) at {t_ms}ms")
            else:
                error_lines.append(f"  - /{e['expected']}/ poorly articulated (GOP {gop:.1f}) at {t_ms}ms")

        prosody_lines = [
            f"  - {k}: {v:.0f}/100"
            for k, v in prosody_issues.items()
            if isinstance(v, (int, float)) and v < 70
        ]

        parts = [
            f"Target accent: {target_accent} — {accent_profile}",
            "",
            "Phoneme errors (worst first):",
            *(error_lines or ["  - No major phoneme errors"]),
            "",
            "Prosody issues:",
            *(prosody_lines or ["  - No major prosody issues"]),
        ]
        if l1_note:
            parts += ["", f"Learner L1 context: {l1_note}"]

        return "\n".join(parts)

    def _fallback_tips(self, phoneme_errors: list[dict], prosody_issues: dict) -> list[dict]:
        tips = []
        if phoneme_errors:
            e = phoneme_errors[0]
            tips.append({
                "text": f"Focus on your /{e['expected']}/ — practice it in isolation first, then in minimal pairs.",
                "phoneme": e["expected"],
                "timestamp_ms": e.get("start_ms"),
            })
        if prosody_issues.get("intonation", 100) < 70:
            tips.append({
                "text": "Work on your intonation — record yourself and compare against a native speaker recording.",
                "phoneme": None,
                "timestamp_ms": None,
            })
        return tips or [{"text": "Good attempt! Keep practising for fluency.", "phoneme": None, "timestamp_ms": None}]
