import json
import unittest
from unittest.mock import patch

from backends.lm_studio_model_info import (
    detect_parallel_limit,
    native_models_url,
)


class _FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class LMStudioModelInfoTests(unittest.TestCase):
    def test_native_models_url_accepts_common_base_urls(self):
        expected = "http://localhost:1234/api/v1/models"
        self.assertEqual(native_models_url("http://localhost:1234"), expected)
        self.assertEqual(native_models_url("http://localhost:1234/v1"), expected)
        self.assertEqual(native_models_url("http://localhost:1234/api/v1"), expected)
        self.assertEqual(
            native_models_url("http://localhost:1234/api/v1/chat"),
            expected,
        )

    def test_detect_parallel_limit_prefers_exact_loaded_instance(self):
        payload = {
            "models": [
                {
                    "key": "catalog/model-key",
                    "loaded_instances": [
                        {
                            "id": "qwen-image-bench-mlx",
                            "config": {"parallel": 4},
                        }
                    ],
                }
            ]
        }
        with patch(
            "backends.lm_studio_model_info.urlopen",
            return_value=_FakeResponse(payload),
        ):
            detected = detect_parallel_limit(model="qwen-image-bench-mlx")

        self.assertEqual(detected.parallel, 4)
        self.assertEqual(detected.model_key, "catalog/model-key")
        self.assertEqual(detected.instance_id, "qwen-image-bench-mlx")
        self.assertIsNone(detected.error)

    def test_missing_parallel_value_returns_advisory_error(self):
        payload = {
            "models": [
                {
                    "key": "test-model",
                    "loaded_instances": [
                        {"id": "test-model", "config": {}}
                    ],
                }
            ]
        }
        with patch(
            "backends.lm_studio_model_info.urlopen",
            return_value=_FakeResponse(payload),
        ):
            detected = detect_parallel_limit(model="test-model")

        self.assertIsNone(detected.parallel)
        self.assertIn("config.parallel", detected.error)


if __name__ == "__main__":
    unittest.main()
