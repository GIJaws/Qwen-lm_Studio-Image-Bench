import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from real_photo.runner import (
    LMStudioSettings,
    RealPhotoRunSettings,
    run_real_photo_evaluation,
)


class _FakeJudge:
    def __init__(self, manifest_path: Path):
        self.manifest_path = manifest_path
        self.calls = []

    def generate_batch(self, items):
        self.assert_manifest_exists()
        self.calls.extend(items)
        prompt = items[0]["user_text"]
        if "# Evaluation Dimension\nQuality" in prompt:
            payload = {
                "Realism": {"Physical Logic": {"score": 2}},
                "Detail": {"Edge Clarity": {"score": 1}},
            }
        elif "# Evaluation Dimension\nAesthetics" in prompt:
            payload = {"Composition": {"Composition": {"score": 2}}}
        else:
            payload = {"Imagination": {"Imagination": {"score": 1}}}
        return [json.dumps(payload)]

    def assert_manifest_exists(self):
        if not self.manifest_path.exists():
            raise AssertionError("sample manifest was not written before inference")


class RealPhotoRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.photos = self.root / "photos"
        self.photos.mkdir()
        Image.new("RGB", (400, 200), "white").save(
            self.photos / "one.jpg",
            format="JPEG",
        )
        Image.new("RGB", (200, 400), "black").save(
            self.photos / "two.jpeg",
            format="JPEG",
        )
        self.run_dir = self.root / "run"
        self.lm = LMStudioSettings(model="test-model")
        self.settings = RealPhotoRunSettings(
            source_folder=self.photos,
            sample_count=10,
            sample_seed=42,
            max_long_edge=100,
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_runner_writes_manifest_before_inference_and_analysis_outputs(self):
        fake = _FakeJudge(self.run_dir / "sample-manifest.json")
        with patch.object(LMStudioSettings, "create_judge", return_value=fake):
            result_dir = run_real_photo_evaluation(
                settings=self.settings,
                lm_studio=self.lm,
                run_dir=self.run_dir,
            )

        self.assertEqual(result_dir, self.run_dir.resolve())
        self.assertEqual(len(fake.calls), 6)
        self.assertTrue(all(item["system_prompt"] is None for item in fake.calls))

        manifest = json.loads((self.run_dir / "sample-manifest.json").read_text())
        self.assertEqual(manifest["requested_maximum"], 10)
        self.assertEqual(manifest["selected_count"], 2)
        self.assertEqual(
            len({item["source_path"] for item in manifest["selected_items"]}),
            2,
        )

        run = json.loads((self.run_dir / "run.json").read_text())
        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["counts"]["completed"], 2)

        result_lines = [
            json.loads(line)
            for line in (self.run_dir / "results.jsonl").read_text().splitlines()
        ]
        self.assertEqual(len(result_lines), 2)
        self.assertEqual(
            {record["image"]["prepared_aspect_ratio"] for record in result_lines},
            {2.0, 0.5},
        )
        self.assertTrue((self.run_dir / "facet-scores.csv").exists())
        self.assertTrue((self.run_dir / "aggregate-scores.csv").exists())
        self.assertTrue((self.run_dir / "report.html").exists())

    def test_resume_skips_completed_images(self):
        first = _FakeJudge(self.run_dir / "sample-manifest.json")
        with patch.object(LMStudioSettings, "create_judge", return_value=first):
            run_real_photo_evaluation(
                settings=self.settings,
                lm_studio=self.lm,
                run_dir=self.run_dir,
            )
        self.assertEqual(len(first.calls), 6)

        second = _FakeJudge(self.run_dir / "sample-manifest.json")
        with patch.object(LMStudioSettings, "create_judge", return_value=second):
            run_real_photo_evaluation(
                settings=self.settings,
                lm_studio=self.lm,
                run_dir=self.run_dir,
            )
        self.assertEqual(second.calls, [])
        self.assertEqual(
            len((self.run_dir / "results.jsonl").read_text().splitlines()),
            2,
        )


if __name__ == "__main__":
    unittest.main()
