import unittest

from app.scoring.fusion import (
    classify_phrase_match,
    ground_overall_score,
)


class GroundOverallScoreTests(unittest.TestCase):
    def test_strong_phrase_match_does_not_cap(self):
        adjusted, gate = ground_overall_score(91.0, {"phrase_match": 97.0, "wer": 0.0})
        self.assertEqual(adjusted, 91.0)
        self.assertIsNone(gate)

    def test_partial_phrase_match_no_longer_caps_score(self):
        """Partial matches used to silently cap at 85; we now surface them as
        a status flag instead so the UI can decide whether to show a warning.
        """
        adjusted, gate = ground_overall_score(91.0, {"phrase_match": 70.0, "wer": 0.3})
        self.assertEqual(adjusted, 91.0)
        self.assertIsNone(gate)

    def test_full_mismatch_caps_overall(self):
        adjusted, gate = ground_overall_score(
            91.0,
            {
                "phrase_match": 32.0,
                "wer": 1.0,
                "char_similarity": 0.2,
                "word_coverage": 0.0,
            },
        )
        self.assertEqual(adjusted, 55.0)
        self.assertIsNotNone(gate)
        self.assertEqual(gate["type"], "phrase_mismatch")


class ClassifyPhraseMatchTests(unittest.TestCase):
    def test_ok_when_match_strong(self):
        self.assertEqual(classify_phrase_match({"phrase_match": 90.0}), "ok")

    def test_partial(self):
        self.assertEqual(classify_phrase_match({"phrase_match": 70.0}), "partial")

    def test_weak(self):
        self.assertEqual(classify_phrase_match({"phrase_match": 50.0}), "weak")

    def test_mismatch(self):
        self.assertEqual(classify_phrase_match({"phrase_match": 20.0}), "mismatch")

    def test_none_when_no_metrics(self):
        self.assertIsNone(classify_phrase_match(None))


if __name__ == "__main__":
    unittest.main()
