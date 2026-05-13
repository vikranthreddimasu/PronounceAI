"""Generate the audio + JSON samples linked from README.md.

Outputs land under ``docs/samples/`` (relative to the repo root). Each artifact
is generated from a deterministic source so the README gallery stays in sync
with the code:

  * tts_<accent>_<slug>.wav      — Kokoro native reference
  * voice_<emotion>_<accent>.wav — CosyVoice 3 voice clone
  * score_<slug>.json            — /api/score response (Kokoro audio in)

Each WAV is also encoded as an MP4 (waveform visualisation + audio track) so
the README gallery plays inline on github.com — only ``<video>`` tags render
inline in GitHub-flavoured Markdown.

Run from ``backend/``:

    source .venv/bin/activate
    python scripts/generate_readme_samples.py

Idempotent: re-running overwrites existing samples. ffmpeg must be on PATH.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import soundfile as sf

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_ROOT = REPO_ROOT / "backend"
SAMPLES_DIR = REPO_ROOT / "docs" / "samples"
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(BACKEND_ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("samples")

from app.utils.kokoro_speaker import synth_wav_bytes, synth_array  # noqa: E402

TTS_LINES = [
    ("GA", "Ship or sheep?",                                "ship_or_sheep"),
    ("RP", "Ship or sheep?",                                "ship_or_sheep"),
    ("GA", "She sells seashells by the seashore.",          "seashells"),
    ("GA", "The quick brown fox jumps over the lazy dog.",  "quick_brown_fox"),
    ("RP", "Could you show me the fastest route to the station?", "fastest_route"),
]

VOICE_CLONE_LINES = [
    {"emotion": "happy",   "accent": "GA",
     "text": "I just got promoted today. I am so excited for the future!"},
    {"emotion": "sad",     "accent": "RP",
     "text": "The old photograph brought back so many precious memories."},
    {"emotion": "angry",   "accent": "GA",
     "text": "This is completely unacceptable. I demand to speak to the manager."},
    {"emotion": "calm",    "accent": "RP",
     "text": "Close your eyes. Breathe in slowly. Let the tension fade away."},
    {"emotion": "whisper", "accent": "GA",
     "text": "I need to tell you a secret, but you must promise not to tell anyone."},
]

# Phrases passed through /api/score against the Kokoro rendition itself.
SCORE_FIXTURES = [
    ("GA", "Ship or sheep?",                                "ship_or_sheep"),
    ("GA", "She sells seashells by the seashore.",          "seashells"),
    ("RP", "The quick brown fox jumps over the lazy dog.",  "quick_brown_fox_rp"),
]

# Default Whisper grounding so the JSON shows phrase_match_status: "ok"
import os
os.environ.setdefault("SCORE_ASR_MODE", "fast")
os.environ.setdefault("LOAD_WHISPER", "1")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _write_wav(path: Path, wav: np.ndarray, sr: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), wav, sr, subtype="PCM_16")
    logger.info("wrote %s (%.1fs)", path.relative_to(REPO_ROOT), len(wav) / sr)


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    logger.info("wrote %s (%d bytes)", path.relative_to(REPO_ROOT), len(data))


def gen_tts_samples() -> list[dict]:
    out: list[dict] = []
    for accent, text, slug in TTS_LINES:
        wav_bytes = synth_wav_bytes(text, accent, 0.9)
        path = SAMPLES_DIR / f"tts_{accent.lower()}_{slug}.wav"
        _write_bytes(path, wav_bytes)
        out.append({
            "kind": "tts",
            "accent": accent,
            "text": text,
            "path": str(path.relative_to(REPO_ROOT)),
        })
    return out


def gen_voice_clone_samples() -> list[dict]:
    """Render each emotion clip via CosyVoice. Falls back to Kokoro if VC fails."""
    try:
        from app.models.voice_clone import VoiceClone
        from app.models.whisper_engine import WhisperEngine
    except Exception as e:
        logger.warning("voice_clone import failed: %s — skipping", e)
        return []

    # Seed a synthetic enrollment so VoiceClone has a ref wav.
    enrollment_dir = BACKEND_ROOT / "data" / "enrollments" / "samples_demo"
    enrollment_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = enrollment_dir / "bundle.wav"
    if not bundle_path.exists():
        seed_text = (
            "Hi, this is my voice sample for the PronounceAI demo. "
            "I speak clearly at a natural pace, with calm energy."
        )
        wav = synth_array(seed_text, "GA", 0.95)
        # Concat GA + RP for richer prosody coverage
        wav_rp = synth_array(seed_text, "RP", 0.95)
        bundle = np.concatenate([wav, wav_rp]).astype(np.float32)
        from app.utils.voice_store import TARGET_SR
        import resampy
        bundle_16k = resampy.resample(bundle, 24_000, TARGET_SR).astype(np.float32)
        _write_wav(bundle_path, bundle_16k, TARGET_SR)
    seed_text = (
        "Hi, this is my voice sample for the PronounceAI demo. "
        "I speak clearly at a natural pace, with calm energy."
    )

    try:
        whisper = WhisperEngine()
    except Exception as e:
        logger.warning("Whisper init failed: %s — voice clone validation will be empty", e)
        whisper = None

    vc = VoiceClone(whisper_engine=whisper)
    vc.warmup()

    out: list[dict] = []
    for clip in VOICE_CLONE_LINES:
        try:
            t0 = time.perf_counter()
            result = vc.speak(
                text=clip["text"],
                ref_audio_path=bundle_path,
                accent=clip["accent"],
                ref_text=seed_text,
                strategy="target_accent",
                emotion=clip["emotion"],
            )
            elapsed = time.perf_counter() - t0
        except Exception as e:
            logger.warning("voice clone failed for emotion=%s accent=%s: %s",
                           clip["emotion"], clip["accent"], e)
            continue
        dest = SAMPLES_DIR / f"voice_{clip['emotion']}_{clip['accent'].lower()}.wav"
        try:
            data = Path(result.path).read_bytes()
            _write_bytes(dest, data)
            try:
                Path(result.path).unlink(missing_ok=True)
            except Exception:
                pass
        except Exception as e:
            logger.warning("could not copy voice clone output: %s", e)
            continue
        out.append({
            "kind": "voice_clone",
            "accent": clip["accent"],
            "emotion": clip["emotion"],
            "text": clip["text"],
            "mode": result.mode,
            "metrics": result.metrics,
            "elapsed_s": round(elapsed, 2),
            "path": str(dest.relative_to(REPO_ROOT)),
        })
    return out


def gen_score_samples() -> list[dict]:
    """Run /api/score against Kokoro-synth audio to produce reference JSON."""
    try:
        from app.models.phoneme_engine import PhonemeEngine
        from app.models.prosody_engine import ProsodyEngine
        from app.models.whisper_engine import WhisperEngine
        from app.scoring.pipeline import run_score
    except Exception as e:
        logger.warning("scoring imports failed: %s", e)
        return []

    logger.info("loading PhonemeEngine + ProsodyEngine + Whisper for score samples …")
    device = os.getenv("DEVICE", "cpu")
    phoneme = PhonemeEngine(
        model_id=os.getenv("WAV2VEC2_MODEL", "slplab/wav2vec2-large-robust-L2-english-phoneme-recognition"),
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

    out: list[dict] = []
    for accent, phrase, slug in SCORE_FIXTURES:
        wav_bytes = synth_wav_bytes(phrase, accent, 0.9)
        result = asyncio.run(
            run_score(app, raw=wav_bytes, phrase=phrase, accent=accent, l1="unknown")
        )
        # Strip the verbose pitch_contour arrays so the JSON sample stays readable
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
        # Drop noisy debug entries the README sample doesn't need
        debug = dict(slim.get("debug", {}))
        for k in ("phoneme_alignment", "phonological_diagnostics", "formants"):
            debug.pop(k, None)
        slim["debug"] = debug

        dest = SAMPLES_DIR / f"score_{accent.lower()}_{slug}.json"
        _write_bytes(dest, json.dumps(slim, indent=2).encode("utf-8"))
        out.append({
            "kind": "score",
            "accent": accent,
            "phrase": phrase,
            "overall": slim["overall"],
            "phrase_match_status": slim.get("phrase_match_status"),
            "scores": slim["scores"],
            "path": str(dest.relative_to(REPO_ROOT)),
        })
    return out


def wav_to_mp4(wav_path: Path) -> Path | None:
    """Encode WAV → MP4 with a violet waveform overlay so the README plays it inline."""
    if shutil.which("ffmpeg") is None:
        logger.warning("ffmpeg not on PATH — skipping MP4 conversion for %s", wav_path.name)
        return None
    mp4_path = wav_path.with_suffix(".mp4")
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(wav_path),
        "-filter_complex",
        "color=c=0x0D1117:s=1280x200:r=25[bg];"
        "[0:a]showwaves=s=1280x200:mode=line:colors=0xA78BFA:rate=25,format=yuva420p[waves];"
        "[bg][waves]overlay=shortest=1,format=yuv420p[v]",
        "-map", "[v]", "-map", "0:a",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-movflags", "+faststart",
        str(mp4_path),
    ]
    res = subprocess.run(cmd, capture_output=True)
    if res.returncode != 0:
        logger.warning("ffmpeg failed for %s: %s", wav_path.name, res.stderr.decode(errors="ignore")[:200])
        return None
    logger.info("wrote %s", mp4_path.relative_to(REPO_ROOT))
    return mp4_path


def main() -> None:
    print(">>> Generating TTS samples")
    tts = gen_tts_samples()
    print(f"    {len(tts)} TTS clips")

    print(">>> Generating /api/score samples")
    scores = gen_score_samples()
    print(f"    {len(scores)} score JSON files")

    print(">>> Generating voice-clone samples (CosyVoice 3, slow)")
    voice = gen_voice_clone_samples()
    print(f"    {len(voice)} voice-clone clips")

    print(">>> Encoding WAV → MP4 (waveform overlay) for GitHub inline playback")
    mp4_count = 0
    for wav in sorted(SAMPLES_DIR.glob("*.wav")):
        if wav_to_mp4(wav) is not None:
            mp4_count += 1
    print(f"    {mp4_count} MP4 files")

    manifest = {
        "generated_by": "backend/scripts/generate_readme_samples.py",
        "tts": sorted(p.name for p in SAMPLES_DIR.glob("tts_*.wav")),
        "voice_clone": sorted(p.name for p in SAMPLES_DIR.glob("voice_*.wav")),
        "score": sorted(p.name for p in SAMPLES_DIR.glob("score_*.json")),
        "mp4": sorted(p.name for p in SAMPLES_DIR.glob("*.mp4")),
    }
    manifest_path = SAMPLES_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"\nManifest: {manifest_path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
