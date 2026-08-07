import argparse
import unittest
from unittest.mock import patch

from backends.lm_studio_model_info import ParallelLimitDetection
from run_stateful_photos import (
    build_parser,
    resolve_concurrency,
    resolve_dimensions,
)


class StatefulCliTests(unittest.TestCase):
    def test_concurrency_defaults_to_autodetect_and_no_request_seed_exists(self):
        parser = build_parser()
        args = parser.parse_args(
            [
                "--folder",
                "/tmp/photos",
                "--model",
                "test-model",
            ]
        )
        self.assertIsNone(args.concurrency)
        self.assertFalse(hasattr(args, "lm_studio_seed"))

    def test_explicit_concurrency_is_used_without_detection(self):
        with patch("run_stateful_photos.detect_parallel_limit") as detect:
            self.assertEqual(
                resolve_concurrency(
                    3,
                    model="test-model",
                    base_url="http://localhost:1234/v1",
                ),
                3,
            )
        detect.assert_not_called()

    @patch(
        "run_stateful_photos.detect_parallel_limit",
        return_value=ParallelLimitDetection(
            parallel=4,
            model_key="test-model",
            instance_id="test-model",
        ),
    )
    def test_concurrency_is_detected_from_loaded_instance(self, detect):
        self.assertEqual(
            resolve_concurrency(
                None,
                model="test-model",
                base_url="http://localhost:1234/v1",
            ),
            4,
        )
        detect.assert_called_once()

    @patch(
        "run_stateful_photos.detect_parallel_limit",
        return_value=ParallelLimitDetection(
            parallel=None,
            model_key=None,
            instance_id=None,
            error="not available",
        ),
    )
    def test_detection_failure_falls_back_to_one(self, detect):
        self.assertEqual(
            resolve_concurrency(
                None,
                model="test-model",
                base_url="http://localhost:1234/v1",
            ),
            1,
        )
        detect.assert_called_once()

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
