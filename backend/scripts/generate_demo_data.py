"""
Generate demo voice enrollment data and sample clips for the README showcase.

Usage:
    cd backend
    source .venv/bin/activate
    python scripts/generate_demo_data.py

This creates:
  - data/enrollments/demo_user/bundle.wav   (synthetic voice reference)
  - data/enrollments/demo_user/meta.json    (enrollment metadata)
  - cache/voice_synth/                      (pre-warmed demo clips)

The synthetic enrollment uses Kokoro TTS so voice-clone demos work even
without a human recording. The generated clips showcase different emotions
and accents for the README gallery.
"""
from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

# Ensure app imports work
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.api.tts import _synthesize, VOICE_MAP
from app.utils.voice_store import TARGET_SR, ENROLL_ROOT

DEMO_USER_ID = "demo_user"
DEMO_PHRASE = (
    "Hi, this is my voice sample for PronounceAI. I speak clearly at a natural pace, "
    "with calm energy. The weather today feels bright, fresh, and easy."
)

# Emotion showcase lines
DEMO_LINES: list[dict] = [
    {"text": "I just got promoted today. I am so excited for the future!", "accent": "GA", "emotion": "happy", "label": "Happy — General American"},
    {"text": "The old photograph brought back so many precious memories.", "accent": "RP", "emotion": "sad", "label": "Sad — Received Pronunciation"},
    {"text": "This is completely unacceptable. I demand to speak to the manager.", "accent": "GA", "emotion": "angry", "label": "Angry — General American"},
    {"text": "We are launching the product in three, two, one... lift off!", "accent": "GA", "emotion": "excited", "label": "Excited — General American"},
    {"text": "Close your eyes. Breathe in slowly. Let the tension fade away.", "accent": "RP", "emotion": "calm", "label": "Calm — Received Pronunciation"},
    {"text": "I need to tell you a secret, but you must promise not to tell anyone.", "accent": "GA", "emotion": "whisper", "label": "Whisper — General American"},
]

# Practice studio showcase lines
PRACTICE_LINES: list[dict] = [
    {"text": "Ship or sheep?", "focus": "sh-vs-s", "category": "minimal-pair"},
    {"text": "She sells seashells by the seashore.", "focus": " consonant-cluster", "category": "phoneme-drill"},
    {"text": "The quick brown fox jumps over the lazy dog.", "focus": "full-prosody", "category": "connected-speech"},
    {"text": "Could you show me the fastest route to the station?", "focus": "weak-forms", "category": "authentic"},
]


def _write_demo_enrollment() -> Path:
    user_dir = ENROLL_ROOT / DEMO_USER_ID
    user_dir.mkdir(parents=True, exist_ok=True)

    # Generate a synthetic enrollment take with both accents for variety
    parts: list[np.ndarray] = []
    for accent in ("GA", "RP"):
        lang_code, voice = VOICE_MAP[accent]
        wav_bytes = _synthesize(DEMO_PHRASE, lang_code, voice, 0.92)
        wav, sr = sf.read(io.BytesIO(wav_bytes), dtype="float32")
        if wav.ndim > 1:
            wav = wav.mean(axis=1)
        if sr != TARGET_SR:
            import resampy

            wav = resampy.resample(wav, sr, TARGET_SR).astype(np.float32)
        parts.append(wav)

        # Also save as a standalone take file
        take_path = user_dir / f"take_{'001' if accent == 'GA' else '002'}.wav"
        sf.write(str(take_path), wav, TARGET_SR, subtype="PCM_16")

    bundle = np.concatenate(parts).astype(np.float32)
    bundle_path = user_dir / "bundle.wav"
    sf.write(str(bundle_path), bundle, TARGET_SR, subtype="PCM_16")

    meta = {
        "takes": [
            {
                "id": "take_001",
                "ref_text": DEMO_PHRASE,
                "duration_s": round(len(parts[0]) / TARGET_SR, 2),
                "peak": 0.85,
                "rms": 0.075,
                "created_at": 1700000000.0,
            },
            {
                "id": "take_002",
                "ref_text": DEMO_PHRASE,
                "duration_s": round(len(parts[1]) / TARGET_SR, 2),
                "peak": 0.85,
                "rms": 0.075,
                "created_at": 1700000100.0,
            },
        ]
    }
    (user_dir / "meta.json").write_text(json.dumps(meta, indent=2))

    bundle_info = {
        "source_take_ids": ["take_001", "take_002"],
        "total_duration_s": round(len(bundle) / TARGET_SR, 2),
        "ref_text": DEMO_PHRASE + " " + DEMO_PHRASE,
        "sample_rate": TARGET_SR,
        "built_at": 1700000200.0,
    }
    (user_dir / "bundle.json").write_text(json.dumps(bundle_info, indent=2))
    print(f"Demo enrollment written to {user_dir}")
    return bundle_path


def _warm_demo_clips() -> list[Path]:
    from app.models.voice_clone import VoiceClone

    vc = VoiceClone()
    cache_dir = Path("cache/voice_synth")
    cache_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = ENROLL_ROOT / DEMO_USER_ID / "bundle.wav"

    generated: list[Path] = []
    for demo in DEMO_LINES:
        result = vc.speak(
            text=demo["text"],
            ref_audio_path=bundle_path,
            accent=demo["accent"],
            ref_text=DEMO_PHRASE,
            strategy="target_accent",
            emotion=demo["emotion"],
        )
        # Rename into a stable showcase path
        dest = cache_dir / f"demo_{demo['emotion']}_{demo['accent']}.wav"
        result.path.rename(dest)
        generated.append(dest)
        print(f"  {demo['label']} → {dest}")
    return generated


def _main() -> None:
    print("Building demo enrollment...")
    _write_demo_enrollment()

    print("\nGenerating showcase voice clips...")
    try:
        clips = _warm_demo_clips()
        print(f"\nGenerated {len(clips)} showcase clips.")
    except Exception as e:
        print(f"Warning: Could not generate CosyVoice showcase clips ({e}).")
        print("The demo enrollment is still usable with the Kokoro fallback.")

    # Write a JSON manifest for the README gallery
    manifest = {
        "enrollment_user_id": DEMO_USER_ID,
        "enrollment_phrase": DEMO_PHRASE,
        "voice_lab_showcase": DEMO_LINES,
        "practice_showcase": PRACTICE_LINES,
    }
    manifest_path = Path("cache/demo_manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"\nDemo manifest written to {manifest_path}")


if __name__ == "__main__":
    _main()
