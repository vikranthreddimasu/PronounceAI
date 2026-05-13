import hashlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

from app.models.voice_clone import VoiceClone
from app.api.voice_enroll import (
    _trim_wav_bytes,
    _voice_synth_cache_dir,
    _voice_synth_cache_key,
    _voice_synth_cache_paths,
    _voice_synth_cache_read,
    _voice_synth_cache_write,
)


class SilenceTrimTests(unittest.TestCase):
    def test_trim_silence_removes_leading_and_trailing(self):
        sr = 24_000
        wav = np.zeros(sr, dtype=np.float32)
        # Put speech in the middle 0.4s
        wav[int(sr * 0.3) : int(sr * 0.7)] = 0.5
        trimmed = VoiceClone._trim_silence(wav, sr=sr)
        self.assertLess(len(trimmed), len(wav))
        self.assertGreater(len(trimmed), sr // 2)

    def test_trim_silence_preserves_short_clips(self):
        wav = np.array([0.0, 0.1, 0.2, 0.0], dtype=np.float32)
        trimmed = VoiceClone._trim_silence(wav, sr=16_000)
        # Very short clips are returned as-is
        np.testing.assert_array_equal(trimmed, wav)


class InstructTagStripTests(unittest.TestCase):
    def test_strips_single_word_emotion_tags(self):
        tag = "American accent. Happy."
        transcript = "Hello world happy"
        clean = VoiceClone._strip_instruct_tag_from_transcript(tag, transcript)
        self.assertEqual(clean, "Hello world")

    def test_strips_accent_and_emotion(self):
        tag = "British accent. Sad."
        transcript = "It is a sad day today british accent"
        clean = VoiceClone._strip_instruct_tag_from_transcript(tag, transcript)
        # "sad" and "british" and "accent" should be stripped
        self.assertNotIn("sad", clean.lower())
        self.assertNotIn("british", clean.lower())
        self.assertNotIn("accent", clean.lower())

    def test_noop_when_tag_empty(self):
        transcript = "Hello world"
        clean = VoiceClone._strip_instruct_tag_from_transcript("", transcript)
        self.assertEqual(clean, transcript)


class TrimWavBytesTests(unittest.TestCase):
    def test_trims_leading_silence_from_wav_bytes(self):
        sr = 16_000
        wav = np.zeros(sr, dtype=np.float32)
        wav[int(sr * 0.3) : int(sr * 0.7)] = 0.5
        buf = io.BytesIO()
        sf.write(buf, wav, sr, format="WAV", subtype="PCM_16")
        trimmed_bytes = _trim_wav_bytes(buf.getvalue())
        trimmed, out_sr = sf.read(io.BytesIO(trimmed_bytes), dtype="float32")
        self.assertEqual(out_sr, sr)
        self.assertLess(len(trimmed), len(wav))
        # Peak should still be present
        self.assertAlmostEqual(float(np.abs(trimmed).max()), 0.5, places=2)

    def test_noop_on_garbage(self):
        garbage = b"not a wav file"
        self.assertEqual(_trim_wav_bytes(garbage), garbage)


class VoiceSynthCacheTests(unittest.TestCase):
    def test_cache_key_is_stable_and_unique(self):
        k1 = _voice_synth_cache_key("u1", "hello", "GA", "target_accent", "happy", "rev1")
        k2 = _voice_synth_cache_key("u1", "hello", "GA", "target_accent", "happy", "rev1")
        k3 = _voice_synth_cache_key("u1", "hello", "RP", "target_accent", "happy", "rev1")
        self.assertEqual(k1, k2)
        self.assertNotEqual(k1, k3)
        self.assertEqual(len(k1), 64)  # sha256 hex

    def test_cache_roundtrip(self):
        key = hashlib.sha256(b"test-key").hexdigest()
        wav = b"fake-wav-data"
        words = [{"word": "hello", "start_ms": 0, "end_ms": 200}]
        _voice_synth_cache_write(key, wav, words)
        result = _voice_synth_cache_read(key)
        self.assertIsNotNone(result)
        self.assertEqual(result[0], wav)
        self.assertEqual(result[1], words)

    def test_cache_expires_after_max_age(self):
        key = hashlib.sha256(b"expiring-key").hexdigest()
        wav = b"old-wav"
        _voice_synth_cache_write(key, wav, [])
        # Manually backdate the file by 48 hours
        wav_path, meta_path = _voice_synth_cache_paths(key)
        if wav_path.exists():
            old_time = wav_path.stat().st_mtime - 48 * 3600
            os.utime(str(wav_path), (old_time, old_time))
            os.utime(str(meta_path), (old_time, old_time))
            result = _voice_synth_cache_read(key)
            self.assertIsNone(result)

    def tearDown(self):
        # Clean up cache dir after each test to avoid side effects
        d = _voice_synth_cache_dir()
        for p in d.glob("*"):
            try:
                p.unlink()
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
