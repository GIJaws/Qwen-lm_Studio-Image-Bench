import tempfile
import unittest
from pathlib import Path

from PIL import Image

from real_photo.sampling import create_selection, discover_jpegs, sample_up_to


class RealPhotoSamplingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "nested").mkdir()
        for relative in ["a.jpg", "B.JPEG", "nested/c.jpg", "nested/d.JPG"]:
            path = self.root / relative
            Image.new("RGB", (4, 3), "white").save(path, format="JPEG")
        (self.root / "ignore.png").write_bytes(b"not a jpeg")

    def tearDown(self):
        self.temp.cleanup()

    def test_recursive_and_non_recursive_discovery(self):
        recursive = discover_jpegs(self.root, recursive=True)
        shallow = discover_jpegs(self.root, recursive=False)
        self.assertEqual(len(recursive), 4)
        self.assertEqual(len(shallow), 2)
        self.assertTrue(
            all(path.suffix.lower() in {".jpg", ".jpeg"} for path in recursive)
        )

    def test_sample_up_to_is_deterministic_and_without_replacement(self):
        paths = discover_jpegs(self.root)
        first = sample_up_to(paths, root=self.root, maximum=3, seed=42)
        second = sample_up_to(paths, root=self.root, maximum=3, seed=42)
        self.assertEqual(first, second)
        self.assertEqual(len(first), len(set(first)))

    def test_sample_count_means_up_to_n(self):
        selection = create_selection(self.root, maximum=100, seed=42)
        self.assertEqual(selection.eligible_count, 4)
        self.assertEqual(selection.selected_count, 4)

    def test_empty_folder_fails_clearly(self):
        empty = self.root / "empty"
        empty.mkdir()
        with self.assertRaisesRegex(ValueError, "No eligible JPEG"):
            create_selection(empty, maximum=10)


if __name__ == "__main__":
    unittest.main()
