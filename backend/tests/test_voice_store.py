import shutil
import tempfile
import time
import unittest
from pathlib import Path

import numpy as np

import app.utils.voice_store as voice_store


def _sample_take() -> np.ndarray:
    sr = 16_000
    wav = np.zeros(int(sr * 6.2), dtype=np.float32)
    t = np.arange(int(sr * 5.0), dtype=np.float32) / sr
    wav[int(sr * 0.6): int(sr * 5.6)] = 0.05 * np.sin(2 * np.pi * 180 * t)
    return wav


class VoiceStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.original_root = voice_store.ENROLL_ROOT
        voice_store.ENROLL_ROOT = self.tmp

    def tearDown(self):
        voice_store.ENROLL_ROOT = self.original_root
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_enrollment_profile_revision_and_conditioning(self):
        user_id = "test_user_123"
        ref_text = "The quick brown fox jumps over the lazy dog by the river."

        take = voice_store.add_take(user_id, _sample_take(), ref_text)
        info = voice_store.get_enrollment(user_id)

        self.assertIsNotNone(info)
        assert info is not None
        self.assertEqual(take["id"], "take_001")
        self.assertIn("revision", info)
        self.assertIn("updated_at", info)
        self.assertGreater(info["bundle_duration_s"], 4.0)
        self.assertLess(info["bundle_duration_s"], 5.6)

        first_revision = info["revision"]
        time.sleep(0.01)
        voice_store.add_take(user_id, _sample_take(), ref_text)
        updated = voice_store.get_enrollment(user_id)

        self.assertIsNotNone(updated)
        assert updated is not None
        self.assertNotEqual(first_revision, updated["revision"])
        self.assertEqual(len(updated["takes"]), 2)


if __name__ == "__main__":
    unittest.main()
