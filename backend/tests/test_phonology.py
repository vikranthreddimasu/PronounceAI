import unittest

from app.models.phonology import diagnose_substitution


class PhonologyTests(unittest.TestCase):
    def test_voicing_diagnosis_for_p_b_pair(self):
        result = diagnose_substitution("b", "p")
        self.assertIsNotNone(result)
        self.assertEqual(result["primary_feature"], "voicing")
        self.assertIn("vocal-fold", result["hint"])

    def test_place_diagnosis_for_s_sh_pair(self):
        result = diagnose_substitution("s", "sh")
        self.assertIsNotNone(result)
        self.assertIn("place", result["changes"])

    def test_no_diagnosis_for_same_phone(self):
        self.assertIsNone(diagnose_substitution("iy", "iy"))


if __name__ == "__main__":
    unittest.main()
