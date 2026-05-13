import unittest

import numpy as np

from app.models.assessment_scorer import extract_audio_features


class AssessmentScorerTests(unittest.TestCase):
    def test_audio_features_are_fixed_size_and_finite(self):
        sr = 16_000
        t = np.arange(sr, dtype=np.float32) / sr
        wav = 0.1 * np.sin(2 * np.pi * 220 * t)
        features = extract_audio_features(wav, sr)
        self.assertEqual(features.shape, (12,))
        self.assertTrue(np.isfinite(features).all())

    def test_empty_audio_features_are_zero(self):
        features = extract_audio_features(np.array([], dtype=np.float32))
        self.assertEqual(features.shape, (12,))
        self.assertEqual(float(features.sum()), 0.0)


if __name__ == "__main__":
    unittest.main()
