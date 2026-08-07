import unittest

from real_photo.profile import ALL_DIMENSIONS, RealPhotoProfile
from real_photo.records import facet_rows


class RealPhotoRecordTests(unittest.TestCase):
    def test_facet_export_preserves_evidence_without_changing_score(self):
        profile = RealPhotoProfile(dimensions=("Quality",))
        dimensions = {
            dimension: {
                "request_status": "not_evaluated",
                "parse_status": "not_evaluated",
                "score_json": None,
            }
            for dimension in ALL_DIMENSIONS
        }
        dimensions["Quality"] = {
            "request_status": "completed",
            "parse_status": "parsed",
            "score_json": {
                "Realism": {
                    "Physical Logic": {
                        "score": 1,
                        "evidence": "Reflections and gravity are visually coherent.",
                    }
                }
            },
        }
        record = {
            "run_id": "run",
            "image_id": "image",
            "sample_item_id": "sample",
            "sample_index": 0,
            "source_relative_path": "photo.jpg",
            "profile_id": profile.id,
            "profile_version": profile.version,
            "condition_digest": "condition",
            "rubric": {
                "id": profile.rubric_id,
                "version": profile.rubric_version,
                "classification": profile.rubric_classification,
            },
            "actual_provenance": profile.actual_provenance,
            "presented_provenance": profile.presented_provenance,
            "reference": {
                "id": None,
                "digest": None,
                "actual_role": "none",
                "presented_role": "none",
            },
            "dimensions": dimensions,
        }

        row = next(
            item
            for item in facet_rows(record, profile)
            if item["facet_label"] == "Physical Logic"
        )
        self.assertEqual(row["raw_score"], 1)
        self.assertEqual(row["mapped_score"], 60.0)
        self.assertEqual(
            row["evidence"],
            "Reflections and gravity are visually coherent.",
        )


if __name__ == "__main__":
    unittest.main()
