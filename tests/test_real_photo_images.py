import tempfile
import unittest
from pathlib import Path

from PIL import Image

from real_photo.images import load_real_photo


class RealPhotoImageTests(unittest.TestCase):
    def test_resize_preserves_landscape_aspect_ratio(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "landscape.jpg"
            Image.new("RGB", (400, 200), "white").save(path, format="JPEG")
            image, metadata = load_real_photo(path, max_long_edge=100)
            self.assertEqual(image.size, (100, 50))
            self.assertAlmostEqual(metadata.source_aspect_ratio, 2.0)
            self.assertAlmostEqual(metadata.prepared_aspect_ratio, 2.0)
            image.close()

    def test_resize_preserves_portrait_aspect_ratio(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "portrait.jpeg"
            Image.new("RGB", (200, 400), "white").save(path, format="JPEG")
            image, metadata = load_real_photo(path, max_long_edge=100)
            self.assertEqual(image.size, (50, 100))
            self.assertAlmostEqual(metadata.prepared_aspect_ratio, 0.5)
            image.close()


if __name__ == "__main__":
    unittest.main()
