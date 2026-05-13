import unittest

from app.api.score import _ctc_grounded_phoneme_score, _ground_overall_score


class ScoreGateTests(unittest.TestCase):
    def test_overall_score_is_not_changed_for_strong_phrase_match(self):
        adjusted, gate = _ground_overall_score(91.0, {"phrase_match": 97.0, "wer": 0.0})
        self.assertEqual(adjusted, 91.0)
        self.assertIsNone(gate)

    def test_overall_score_is_capped_for_phrase_mismatch(self):
        adjusted, gate = _ground_overall_score(
            91.0,
            {
                "phrase_match": 32.0,
                "wer": 1.0,
                "char_similarity": 0.2,
                "word_coverage": 0.0,
            },
        )
        self.assertEqual(adjusted, 55.0)
        self.assertEqual(gate["type"], "phrase_mismatch")

    def test_ctc_phone_sequence_caps_phoneme_score_only_when_weak(self):
        adjusted, gate = _ctc_grounded_phoneme_score(
            88.0,
            {"phone_error_rate": 0.7, "ctc_sequence_score": 30.0},
        )
        self.assertEqual(adjusted, 60.0)
        self.assertEqual(gate["type"], "ctc_phone_sequence_mismatch")

    def test_ctc_phone_sequence_soft_caps_borderline_score(self):
        adjusted, gate = _ctc_grounded_phoneme_score(
            88.0,
            {"phone_error_rate": 0.5, "ctc_sequence_score": 50.0},
        )
        self.assertEqual(adjusted, 75.0)
        self.assertEqual(gate["type"], "ctc_phone_sequence_weak")

    def test_ctc_phone_sequence_leaves_clean_score_alone(self):
        adjusted, gate = _ctc_grounded_phoneme_score(
            88.0,
            {"phone_error_rate": 0.05, "ctc_sequence_score": 95.0},
        )
        self.assertEqual(adjusted, 88.0)
        self.assertIsNone(gate)


if __name__ == "__main__":
    unittest.main()
