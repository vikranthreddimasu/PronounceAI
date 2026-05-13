import unittest

from app.utils.text_metrics import (
    normalize_text,
    phrase_match_metrics,
    sequence_similarity,
    word_error_rate,
)


class TextMetricTests(unittest.TestCase):
    def test_normalizes_punctuation_case_and_small_numbers(self):
        self.assertEqual(normalize_text("Ship or sheep?"), "ship or sheep")
        self.assertEqual(normalize_text("3 free throws."), "three free throws")

    def test_word_error_rate_ignores_punctuation(self):
        self.assertEqual(word_error_rate("This is a thin thing.", "This is a thin thing"), 0.0)

    def test_phrase_match_keeps_short_asr_variants_reasonable(self):
        metrics = phrase_match_metrics("3 free throws", "Three free throws")
        self.assertEqual(metrics["wer"], 0.0)
        self.assertGreaterEqual(metrics["phrase_match"], 95.0)

    def test_phrase_match_penalizes_wrong_phrase(self):
        metrics = phrase_match_metrics("red or red red or red", "The right light is bright")
        self.assertGreater(metrics["wer"], 0.7)
        self.assertLess(metrics["phrase_match"], 45.0)

    def test_sequence_similarity_is_normalized(self):
        self.assertGreater(sequence_similarity("ship or sheep", "ship or sheep?"), 0.98)


if __name__ == "__main__":
    unittest.main()
