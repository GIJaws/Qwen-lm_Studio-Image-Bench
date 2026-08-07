import unittest

from real_photo.profile import RealPhotoProfile, build_real_photo_user_prompt


class RealPhotoProfileTests(unittest.TestCase):
    def test_default_dimensions_match_real_photo_baseline(self):
        profile = RealPhotoProfile()
        self.assertEqual(
            profile.dimensions,
            ("Quality", "Aesthetics", "Creative Generation"),
        )
        self.assertEqual(
            profile.disabled_dimensions,
            ("Alignment", "Real-world Fidelity"),
        )
        self.assertIsNone(profile.application_system_prompt)
        self.assertTrue(profile.include_evidence)
        self.assertEqual(profile.output_schema_id, "score_evidence_v1")

    def test_prompt_discloses_real_photo_and_requests_evidence(self):
        profile = RealPhotoProfile()
        prompt = build_real_photo_user_prompt(profile, "Quality")
        self.assertIn("This is a real photograph", prompt)
        self.assertIn("No generation prompt", prompt)
        self.assertIn("<image>", prompt)
        self.assertIn("# Evaluation Dimension\nQuality", prompt)
        self.assertIn("# Evaluation Checklist", prompt)
        self.assertIn('"evidence": "brief concrete evidence"', prompt)

    def test_score_only_profile_keeps_original_output_shape_available(self):
        profile = RealPhotoProfile(include_evidence=False)
        prompt = build_real_photo_user_prompt(profile, "Quality")
        self.assertEqual(profile.output_schema_id, "qwen_score_only_v1")
        self.assertNotIn("# Evidence Rules", prompt)
        self.assertNotIn('"evidence"', prompt)


if __name__ == "__main__":
    unittest.main()
