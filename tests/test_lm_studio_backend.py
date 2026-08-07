import json
import unittest
from unittest.mock import patch

from PIL import Image

from backends.lm_studio_backend import LMStudioJudge


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self._payload).encode("utf-8")


class LMStudioJudgeTests(unittest.TestCase):
    def test_build_payload_inserts_image_at_qwen_marker(self):
        judge = LMStudioJudge(model="qwen-image-bench-test")
        payload = judge._build_payload({
            "system_prompt": "system text",
            "user_text": "before image\n<image>\nafter image",
            "image": Image.new("RGB", (2, 3), "white"),
        })

        self.assertEqual(payload["model"], "qwen-image-bench-test")
        self.assertEqual(payload["temperature"], 0.0)
        self.assertEqual(payload["top_k"], 1)
        self.assertEqual(payload["top_p"], 1.0)
        self.assertEqual(payload["repeat_penalty"], 1.05)
        self.assertEqual(payload["seed"], 42)
        self.assertFalse(payload["stream"])
        self.assertEqual(
            payload["messages"][0],
            {"role": "system", "content": "system text"},
        )

        user_content = payload["messages"][1]["content"]
        self.assertEqual(
            user_content[0],
            {"type": "text", "text": "before image\n"},
        )
        self.assertTrue(
            user_content[1]["image_url"]["url"].startswith(
                "data:image/png;base64,"
            )
        )
        self.assertEqual(
            user_content[2],
            {"type": "text", "text": "\nafter image"},
        )
        self.assertNotIn("<image>", json.dumps(user_content))

    def test_build_payload_appends_image_when_marker_is_absent(self):
        judge = LMStudioJudge(model="qwen-image-bench-test")
        payload = judge._build_payload({
            "system_prompt": "system text",
            "user_text": "checklist text",
            "image": Image.new("RGB", (2, 3), "white"),
        })

        user_content = payload["messages"][1]["content"]
        self.assertEqual(
            user_content[0],
            {"type": "text", "text": "checklist text"},
        )
        self.assertTrue(
            user_content[1]["image_url"]["url"].startswith(
                "data:image/png;base64,"
            )
        )

    def test_build_payload_omits_empty_application_system_prompt(self):
        judge = LMStudioJudge(model="qwen-image-bench-test")
        payload = judge._build_payload({
            "system_prompt": None,
            "user_text": "before image\n<image>\nafter image",
            "image": Image.new("RGB", (2, 3), "white"),
        })

        self.assertEqual(
            [message["role"] for message in payload["messages"]],
            ["user"],
        )
        user_content = payload["messages"][0]["content"]
        self.assertEqual(
            user_content[0],
            {"type": "text", "text": "before image\n"},
        )
        self.assertEqual(user_content[1]["type"], "image_url")
        self.assertEqual(
            user_content[2],
            {"type": "text", "text": "\nafter image"},
        )

    def test_generate_batch_returns_outputs_in_request_order(self):
        judge = LMStudioJudge(model="qwen-image-bench-test")
        items = [
            {
                "system_prompt": "system 1",
                "user_text": "task 1",
                "image": Image.new("RGB", (1, 1), "white"),
            },
            {
                "system_prompt": "system 2",
                "user_text": "task 2",
                "image": Image.new("RGB", (1, 1), "black"),
            },
        ]
        responses = [
            _FakeResponse({"choices": [{"message": {"content": "result 1"}}]}),
            _FakeResponse({"choices": [{"message": {"content": "result 2"}}]}),
        ]

        with patch(
            "backends.lm_studio_backend.urlopen",
            side_effect=responses,
        ) as urlopen:
            self.assertEqual(
                judge.generate_batch(items),
                ["result 1", "result 2"],
            )

        self.assertEqual(urlopen.call_count, 2)

    def test_extra_body_is_merged_into_payload(self):
        judge = LMStudioJudge(
            model="qwen-image-bench-test",
            seed=None,
            extra_body={"response_format": {"type": "json_object"}},
        )
        payload = judge._build_payload({
            "system_prompt": "system text",
            "user_text": "checklist text",
            "image": Image.new("RGB", (1, 1), "white"),
        })

        self.assertNotIn("seed", payload)
        self.assertEqual(
            payload["response_format"],
            {"type": "json_object"},
        )


if __name__ == "__main__":
    unittest.main()
