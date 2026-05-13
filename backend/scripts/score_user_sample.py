"""Score the committed user enrolment WAV through the same pipeline the
practice screen uses, and write the result as a gallery-ready JSON fixture.

Reads ``docs/samples/voice_user_original.wav`` (the 13.1 s enrolment that
already ships in the repo), feeds it into ``run_score`` against a known
phrase, and writes the slim response to
``docs/samples/score_user_recording.json``.

Run from ``backend/``:

    source .venv/bin/activate
    python scripts/score_user_sample.py
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_ROOT = REPO_ROOT / "backend"
SAMPLES_DIR = REPO_ROOT / "docs" / "samples"

sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("SCORE_ASR_MODE", "fast")
os.environ.setdefault("LOAD_WHISPER", "1")

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("score_user")

USER_WAV = SAMPLES_DIR / "voice_user_original.wav"
OUT_JSON = SAMPLES_DIR / "score_user_recording.json"

# Transcribed from the recording itself (faster-whisper base.en).
PHRASE = (
    "Hello, my name is Alex. "
    "The quick brown fox jumps over the lazy dog by the river. "
    "She sells seashells by the seashore "
    "while three thoughtful tourists thought through all new problems."
)
ACCENT = "GA"


def main() -> None:
    from app.models.phoneme_engine import PhonemeEngine
    from app.models.prosody_engine import ProsodyEngine
    from app.models.whisper_engine import WhisperEngine
    from app.scoring.pipeline import run_score

    logger.info("loading engines …")
    device = os.getenv("DEVICE", "cpu")
    phoneme = PhonemeEngine(
        model_id=os.getenv(
            "WAV2VEC2_MODEL",
            "slplab/wav2vec2-large-robust-L2-english-phoneme-recognition",
        ),
        device=device,
    )
    prosody = ProsodyEngine()
    whisper = WhisperEngine()

    state = SimpleNamespace(
        phoneme_engine=phoneme,
        prosody_engine=prosody,
        whisper=whisper,
        accent_engine=None,
        assessment_scorer=None,
    )
    app = SimpleNamespace(state=state)

    raw = USER_WAV.read_bytes()
    logger.info("scoring %s (%d bytes) against phrase: %s", USER_WAV.name, len(raw), PHRASE)
    result = asyncio.run(
        run_score(app, raw=raw, phrase=PHRASE, accent=ACCENT, l1="unknown")
    )

    slim = {
        **result,
        "pitch_contour": {
            **result.get("pitch_contour", {}),
            "user": "<{} z-scored values, see backend response>".format(
                len(result.get("pitch_contour", {}).get("user", []))
            ),
            "native": "<{} z-scored values, see backend response>".format(
                len(result.get("pitch_contour", {}).get("native", []))
            ),
        },
        "transcript": {
            "text": result["transcript"].get("text", ""),
            "language_probability": result["transcript"].get("language_probability"),
        },
    }
    debug = dict(slim.get("debug", {}))
    for k in ("phoneme_alignment", "phonological_diagnostics", "formants"):
        debug.pop(k, None)
    slim["debug"] = debug

    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_bytes(json.dumps(slim, indent=2).encode("utf-8"))
    logger.info("wrote %s (overall=%s)", OUT_JSON.relative_to(REPO_ROOT), slim.get("overall"))


if __name__ == "__main__":
    main()
