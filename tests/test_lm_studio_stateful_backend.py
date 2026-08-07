import json
import unittest
from unittest.mock import patch

from PIL import Image

from backends.lm_studio_stateful_backend import (
    StatefulLMStudioJudge,
    native_chat_url,
)


class _FakeJSONResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class _FakeSSEResponse:
    def __init__(self, events):
        self.lines = []
        for event_name, data in events:
            self.lines.extend(
                [
                    f"event: {event_name}\n".encode(),
                    f"data: {json.dumps(data)}\n".encode(),
                    b"\n",
                ]
            )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def __iter__(self):
        return iter(self.lines)


def _result(message="READY", response_id="resp_base"):
    return {
        "model_instance_id": "test-model",
        "output": [{"type": "message", "content": message}],
        "stats": {
            "input_tokens": 10,
            "total_output_tokens": 2,
            "reasoning_output_tokens": 0,
            "tokens_per_second": 20.0,
            "time_to_first_token_seconds": 0.1,
        },
        "response_id": response_id,
    }


class StatefulLMStudioBackendTests(unittest.TestCase):
    def test_native_chat_url_accepts_root_and_openai_base(self):
        self.assertEqual(
            native_chat_url("http://localhost:1234"),
            "http://localhost:1234/api/v1/chat",
        )
        self.assertEqual(
            native_chat_url("http://localhost:1234/v1"),
            "http://localhost:1234/api/v1/chat",
        )
        self.assertEqual(
            native_chat_url("http://localhost:1234/api/v1"),
            "http://localhost:1234/api/v1/chat",
        )

    def test_shared_context_payload_stores_image_and_has_no_seed(self):
        judge = StatefulLMStudioJudge(
            model="test-model",
            stream=False,
            base_reasoning="off",
        )
        response = _FakeJSONResponse(_result())
        with patch(
            "backends.lm_studio_stateful_backend.urlopen",
            return_value=response,
        ) as open_mock:
            result = judge.create_shared_context(
                system_prompt=None,
                user_text="before\n<image>\nafter",
                image=Image.new("RGB", (2, 3), "white"),
            )

        request = open_mock.call_args.args[0]
        payload = json.loads(request.data.decode())
        self.assertEqual(request.full_url, "http://localhost:1234/api/v1/chat")
        self.assertTrue(payload["store"])
        self.assertFalse(payload["stream"])
        self.assertEqual(payload["reasoning"], "off")
        self.assertNotIn("seed", payload)
        self.assertEqual(payload["input"][0], {"type": "message", "content": "before\n"})
        self.assertEqual(payload["input"][1]["type"], "image")
        self.assertTrue(payload["input"][1]["data_url"].startswith("data:image/png;base64,"))
        self.assertEqual(payload["input"][2], {"type": "message", "content": "\nafter"})
        self.assertEqual(result.response_id, "resp_base")

    def test_branch_uses_previous_response_and_does_not_resend_image(self):
        judge = StatefulLMStudioJudge(model="test-model", stream=False)
        response = _FakeJSONResponse(_result(message='{"score": 1}', response_id=None))
        with patch(
            "backends.lm_studio_stateful_backend.urlopen",
            return_value=response,
        ) as open_mock:
            result = judge.evaluate_branch(
                previous_response_id="resp_base",
                user_text="Quality checklist",
                label="Quality",
            )

        request = open_mock.call_args.args[0]
        payload = json.loads(request.data.decode())
        self.assertEqual(payload["previous_response_id"], "resp_base")
        self.assertFalse(payload["store"])
        self.assertEqual(payload["input"], "Quality checklist")
        self.assertNotIn("image", json.dumps(payload))
        self.assertEqual(result.message, '{"score": 1}')

    def test_streaming_returns_chat_end_and_emits_progress(self):
        events = [
            ("chat.start", {"type": "chat.start", "model_instance_id": "test-model"}),
            ("prompt_processing.start", {"type": "prompt_processing.start"}),
            (
                "prompt_processing.progress",
                {"type": "prompt_processing.progress", "progress": 0.5},
            ),
            ("message.start", {"type": "message.start"}),
            ("message.delta", {"type": "message.delta", "content": "READY"}),
            ("message.end", {"type": "message.end"}),
            ("chat.end", {"type": "chat.end", "result": _result()}),
        ]
        progress = []
        judge = StatefulLMStudioJudge(model="test-model", stream=True)
        with patch(
            "backends.lm_studio_stateful_backend.urlopen",
            return_value=_FakeSSEResponse(events),
        ):
            result = judge.create_shared_context(
                system_prompt=None,
                user_text="<image>",
                image=Image.new("RGB", (1, 1), "white"),
                progress=lambda label, event, data: progress.append((label, event)),
            )

        self.assertEqual(result.message, "READY")
        self.assertIn(("Shared context", "prompt_processing.progress"), progress)
        self.assertEqual(progress[-1], ("Shared context", "chat.end"))


if __name__ == "__main__":
    unittest.main()
