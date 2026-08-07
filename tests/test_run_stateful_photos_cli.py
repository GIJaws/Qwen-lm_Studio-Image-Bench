import argparse
import unittest

from run_stateful_photos import build_parser, resolve_dimensions


class StatefulCliTests(unittest.TestCase):
    def test_default_concurrency_is_four_and_no_request_seed_option_exists(self):
        parser = build_parser()
        args = parser.parse_args(
            [
                "--folder",
                "/tmp/photos",
                "--model",
                "test-model",
            ]
        )
        self.assertEqual(args.concurrency, 4)
        self.assertFalse(hasattr(args, "lm_studio_seed"))

    def test_dimensions_default_and_repeat(self):
        defaults = argparse.Namespace(all_dimensions=False, dimension=None)
        self.assertEqual(
            resolve_dimensions(defaults),
            ("Quality", "Aesthetics", "Creative Generation"),
        )
        selected = argparse.Namespace(
            all_dimensions=False,
            dimension=["Quality", "Aesthetics", "Quality"],
        )
        self.assertEqual(resolve_dimensions(selected), ("Quality", "Aesthetics"))

    def test_all_dimensions_conflicts_with_explicit_dimensions(self):
        args = argparse.Namespace(
            all_dimensions=True,
            dimension=["Quality"],
        )
        with self.assertRaises(ValueError):
            resolve_dimensions(args)


if __name__ == "__main__":
    unittest.main()
