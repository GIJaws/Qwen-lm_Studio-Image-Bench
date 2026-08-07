import unittest
from unittest.mock import patch

from run_real_photos import resolve_sample_seed


class RunRealPhotosCliTests(unittest.TestCase):
    def test_explicit_sample_seed_is_used_unchanged(self):
        self.assertEqual(resolve_sample_seed(123456789), 123456789)

    @patch("run_real_photos.secrets.randbits", return_value=987654321)
    def test_missing_sample_seed_uses_fresh_64_bit_os_entropy(self, randbits):
        self.assertEqual(resolve_sample_seed(None), 987654321)
        randbits.assert_called_once_with(64)


if __name__ == "__main__":
    unittest.main()
