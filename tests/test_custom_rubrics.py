import json
import tempfile
import unittest
from pathlib import Path

from real_photo.custom_rubrics import (
    CustomRubricError,
    build_custom_dimension_prompt,
    load_custom_rubric,
    parse_custom_dimension_response,
)


ROOT = Path(__file__).resolve().parents[1]


class CustomRubricTests(unittest.TestCase):
    def test_starter_real_photo_and_icm_packs_load(self):
        real_photo = load_custom_rubric(
            ROOT / "rubrics" / "birds_of_stone_real_photo_v1.json"
        )
        icm = load_custom_rubric(
            ROOT / "rubrics" / "birds_of_stone_icm_v1.json"
        )

        self.assertEqual(real_photo.identity, "birds_of_stone_real_photo_v1")
        self.assertEqual(real_photo.classification, "custom")
        self.assertEqual(
            real_photo.dimensions[0].label,
            "Photographic Effectiveness",
        )
        self.assertEqual(icm.identity, "birds_of_stone_icm_v1")
        self.assertEqual(icm.dimensions[0].label, "Intentional Motion")

    def test_prompt_identifies_custom_pack_and_requests_evidence(self):
        pack = load_custom_rubric(
            ROOT / "rubrics" / "birds_of_stone_icm_v1.json"
        )
        prompt = build_custom_dimension_prompt(
            pack,
            pack.dimensions[0],
            include_evidence=True,
            stateful_branch=True,
        )

        self.assertIn("Pack: birds_of_stone_icm_v1", prompt)
        self.assertIn("Classification: custom experimental judgment", prompt)
        self.assertIn("Motion Structure", prompt)
        self.assertIn('"evidence": "brief concrete evidence"', prompt)
        self.assertIn("already stored in the shared conversation context", prompt)

    def test_response_normalization_maps_scores_and_preserves_evidence(self):
        pack = load_custom_rubric(
            ROOT / "rubrics" / "birds_of_stone_real_photo_v1.json"
        )
        dimension = pack.dimensions[0]
        parsed = {
            "Visual Structure": {
                "Subject or Visual Anchor": {
                    "score": 2,
                    "evidence": "A bright face anchors the frame.",
                },
                "Composition and Flow": {"score": 1},
                "Layer Separation": {"score": "N/A"},
            }
        }

        normalized = parse_custom_dimension_response(pack, dimension, parsed)
        group = normalized["groups"]["visual_structure"]
        anchor = group["facets"]["visual_anchor"]
        flow = group["facets"]["composition_flow"]
        separation = group["facets"]["layer_separation"]

        self.assertEqual(anchor["raw_score"], 2)
        self.assertEqual(anchor["mapped_score"], 100.0)
        self.assertEqual(anchor["evidence"], "A bright face anchors the frame.")
        self.assertEqual(flow["mapped_score"], 60.0)
        self.assertIsNone(separation["mapped_score"])
        self.assertEqual(separation["applicability"], "na")
        self.assertEqual(group["score"], 80.0)
        self.assertTrue(anchor["facet_id"].startswith("birds_of_stone_real_photo.v1."))
        self.assertTrue(
            anchor["facet_concept_id"].startswith(
                "custom.birds_of_stone_real_photo."
            )
        )
        self.assertEqual(normalized["classification"], "custom")

    def test_duplicate_facet_ids_are_rejected(self):
        invalid = {
            "schema_version": 1,
            "id": "test_pack",
            "version": 1,
            "name": "Test Pack",
            "classification": "custom",
            "dimensions": [
                {
                    "id": "dimension",
                    "label": "Dimension",
                    "groups": [
                        {
                            "id": "group",
                            "label": "Group",
                            "facets": [
                                {"id": "same", "label": "One", "prompt": "One?"},
                                {"id": "same", "label": "Two", "prompt": "Two?"},
                            ],
                        }
                    ],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "invalid.json"
            path.write_text(json.dumps(invalid), encoding="utf-8")
            with self.assertRaises(CustomRubricError):
                load_custom_rubric(path)


if __name__ == "__main__":
    unittest.main()
