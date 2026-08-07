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

    def test_prompt_discloses_real_photo_and_has_no_reference_text(self):
        profile = RealPhotoProfile()
        prompt = build_real_photo_user_prompt(profile, "Quality")
        self.assertIn("This is a real photograph", prompt)
        self.assertIn("No generation prompt", prompt)
        self.assertIn("<image>", prompt)
        self.assertIn("# Evaluation Dimension\nQuality", prompt)
        self.assertIn("# Evaluation Checklist", prompt)


if __name__ == "__main__":
    unittest.main()
