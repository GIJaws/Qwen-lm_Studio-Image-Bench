import unittest
from unittest.mock import patch

from real_photo.profile import ALL_DIMENSIONS, DEFAULT_REAL_PHOTO_DIMENSIONS
from run_real_photos import resolve_dimensions, resolve_sample_seed


class RunRealPhotosCliTests(unittest.TestCase):
    def test_explicit_sample_seed_is_used_unchanged(self):
        self.assertEqual(resolve_sample_seed(123456789), 123456789)

    @patch("run_real_photos.secrets.randbits", return_value=987654321)
    def test_missing_sample_seed_uses_fresh_64_bit_os_entropy(self, randbits):
        self.assertEqual(resolve_sample_seed(None), 987654321)
        randbits.assert_called_once_with(64)

    def test_dimensions_default_to_real_photo_baseline(self):
        self.assertEqual(
            resolve_dimensions(None, use_all_dimensions=False),
            DEFAULT_REAL_PHOTO_DIMENSIONS,
        )

    def test_dimensions_can_be_selected_explicitly(self):
        self.assertEqual(
            resolve_dimensions(
                ["Quality", "Real-world Fidelity", "Quality"],
                use_all_dimensions=False,
            ),
            ("Quality", "Real-world Fidelity"),
        )

    def test_all_dimensions_selects_the_complete_stock_taxonomy(self):
        self.assertEqual(
            resolve_dimensions(None, use_all_dimensions=True),
            ALL_DIMENSIONS,
        )

    def test_explicit_and_all_dimensions_are_mutually_exclusive(self):
        with self.assertRaisesRegex(ValueError, "cannot be used together"):
            resolve_dimensions(["Quality"], use_all_dimensions=True)


if __name__ == "__main__":
    unittest.main()
