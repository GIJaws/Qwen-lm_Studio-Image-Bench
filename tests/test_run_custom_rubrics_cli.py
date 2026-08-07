import unittest
from unittest.mock import patch

from backends.lm_studio_model_info import ParallelLimitDetection
from run_custom_rubrics import build_parser, resolve_concurrency


class CustomRubricCliTests(unittest.TestCase):
    def test_concurrency_defaults_to_autodetect_and_rubrics_are_repeatable(self):
        args = build_parser().parse_args(
            [
                "--image",
                "/tmp/photo.jpg",
                "--rubric",
                "rubrics/one.json",
                "--rubric",
                "rubrics/two.json",
                "--model",
                "test-model",
            ]
        )
        self.assertIsNone(args.concurrency)
        self.assertEqual(len(args.rubric), 2)
        self.assertFalse(args.no_evidence)
        self.assertFalse(args.no_stream_progress)

    @patch(
        "run_custom_rubrics.detect_parallel_limit",
        return_value=ParallelLimitDetection(
            parallel=4,
            model_key="test-model",
            instance_id="test-model",
        ),
    )
    def test_concurrency_autodetects_loaded_instance_limit(self, detect):
        self.assertEqual(
            resolve_concurrency(
                None,
                model="test-model",
                base_url="http://localhost:1234/v1",
            ),
            4,
        )
        detect.assert_called_once()

    def test_explicit_concurrency_must_be_positive(self):
        with self.assertRaises(ValueError):
            resolve_concurrency(
                0,
                model="test-model",
                base_url="http://localhost:1234/v1",
            )


if __name__ == "__main__":
    unittest.main()
