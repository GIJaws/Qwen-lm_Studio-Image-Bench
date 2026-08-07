import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from backends.lm_studio_stateful_backend import StatefulChatResult
from real_photo.profile import ALL_DIMENSIONS, RealPhotoProfile
from real_photo.runner import RealPhotoRunSettings
from real_photo.stateful_runner import (
    StatefulLMStudioSettings,
    build_dimension_branch_prompt,
    build_shared_context_prompt,
    run_stateful_real_photo_evaluation,
)


def _chat_result(message, response_id=None):
    return StatefulChatResult(
        message=message,
        reasoning="",
        response_id=response_id,
        model_instance_id="test-model",
        stats={},
        raw_result={},
    )


class _ConcurrentFakeJudge:
    def __init__(self):
        self.shared_calls = 0
        self.branch_calls = []
        self.active = 0
        self.max_active = 0
        self.lock = threading.Lock()

    def create_shared_context(self, **kwargs):
        self.shared_calls += 1
        return _chat_result("READY", response_id="resp_base")

    def evaluate_branch(self, *, previous_response_id, user_text, label, progress):
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            time.sleep(0.02)
            self.branch_calls.append(label)
            return _chat_result(json.dumps({"Any": {"Any": {"score": 1}}}))
        finally:
            with self.lock:
                self.active -= 1


class StatefulRunnerTests(unittest.TestCase):
    def test_prompt_split_keeps_image_only_in_shared_context(self):
        profile = RealPhotoProfile(
            dimensions=("Quality",),
            include_evidence=True,
        )
        shared = build_shared_context_prompt(profile)
        branch = build_dimension_branch_prompt(profile, "Quality")
        self.assertIn("<image>", shared)
        self.assertNotIn("<image>", branch)
        self.assertIn("# Evaluation Dimension\nQuality", branch)
        self.assertIn("# Evidence Rules", branch)

    def test_branch_requests_are_bounded_and_run_concurrently(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            photos = root / "photos"
            photos.mkdir()
            Image.new("RGB", (20, 10), "white").save(photos / "one.jpg")
            run_dir = root / "run"
            fake = _ConcurrentFakeJudge()
            settings = RealPhotoRunSettings(
                source_folder=photos,
                sample_count=1,
                sample_seed=42,
                max_long_edge=20,
                html_report=False,
            )
            lm = StatefulLMStudioSettings(
                model="test-model",
                stream_progress=False,
                concurrency=2,
            )
            profile = RealPhotoProfile(
                dimensions=tuple(ALL_DIMENSIONS),
                include_evidence=False,
            )

            with patch.object(
                StatefulLMStudioSettings,
                "create_judge",
                return_value=fake,
            ):
                run_stateful_real_photo_evaluation(
                    settings=settings,
                    lm_studio=lm,
                    run_dir=run_dir,
                    profile=profile,
                )

            self.assertEqual(fake.shared_calls, 1)
            self.assertEqual(set(fake.branch_calls), set(ALL_DIMENSIONS))
            self.assertGreater(fake.max_active, 1)
            self.assertLessEqual(fake.max_active, 2)


if __name__ == "__main__":
    unittest.main()
