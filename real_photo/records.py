"""Canonical result records and normalized analysis exports."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable

from score_utils import (
    CHECKLIST_L3_TO_L2,
    aggregate_total_score,
    compute_dimension_score,
    map_score,
)

from .profile import ALL_DIMENSIONS, RealPhotoProfile


SCHEMA_VERSION = 1


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def slug(value: str) -> str:
    normalized = value.casefold().replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")


def compute_official_scores(
    dimensions: dict[str, dict[str, Any]],
    active_dimensions: Iterable[str],
) -> dict[str, Any]:
    dimension_results: dict[str, dict[str, Any]] = {}
    for dimension in active_dimensions:
        state = dimensions.get(dimension, {})
        score_json = state.get("score_json")
        if state.get("parse_status") == "parsed" and isinstance(score_json, dict):
            dimension_results[dimension] = compute_dimension_score(score_json)

    return {
        "level1": {
            dimension: result["level1_score"]
            for dimension, result in dimension_results.items()
        },
        "level2": {
            dimension: result["level2_scores"]
            for dimension, result in dimension_results.items()
        },
        "level3_mapped": {
            dimension: result["level3_scores"]
            for dimension, result in dimension_results.items()
        },
        "active_dimension_aggregate": aggregate_total_score(dimension_results),
        "active_dimension_count": sum(
            1
            for result in dimension_results.values()
            if result.get("level1_score") is not None
        ),
        "aggregation_method": "qwen_nested_mean_l3_to_l2_to_l1_to_active_dimensions",
    }


def build_result_record(
    checkpoint: dict[str, Any],
    profile: RealPhotoProfile,
) -> dict[str, Any]:
    dimensions = checkpoint["dimensions"]
    official_scores = compute_official_scores(dimensions, profile.dimensions)
    parse_failures = [
        dimension
        for dimension in profile.dimensions
        if dimensions[dimension].get("parse_status") == "parse_failed"
    ]
    request_failures = [
        dimension
        for dimension in profile.dimensions
        if dimensions[dimension].get("request_status") == "request_failed"
    ]

    status = "completed"
    if request_failures:
        status = "request_failed"
    elif parse_failures:
        status = "completed_with_parse_errors"

    record = {
        key: checkpoint[key]
        for key in (
            "schema_version",
            "run_id",
            "sample_manifest_id",
            "sample_item_id",
            "image_id",
            "sample_index",
            "source_path",
            "source_relative_path",
            "source_uri",
            "image",
            "profile_id",
            "profile_version",
            "condition_digest",
            "rubric",
            "actual_provenance",
            "presented_provenance",
            "reference",
        )
    }
    record.update(
        {
            "status": status,
            "dimensions": dimensions,
            "official_scores": official_scores,
            "request_failures": request_failures,
            "parse_failures": parse_failures,
        }
    )
    return record


def _lookup_raw_score(score_json: dict[str, Any], l2: str, facet: str) -> Any:
    l2_values = score_json.get(l2)
    if not isinstance(l2_values, dict):
        return None
    score_object = l2_values.get(facet)
    if isinstance(score_object, dict):
        return score_object.get("score")
    return score_object


def facet_rows(record: dict[str, Any], profile: RealPhotoProfile) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    active = set(profile.dimensions)
    reference = record["reference"]

    for l1 in ALL_DIMENSIONS:
        state = record["dimensions"].get(l1, {})
        request_status = state.get("request_status", "not_evaluated")
        parse_status = state.get("parse_status", "not_evaluated")
        score_json = state.get("score_json") if isinstance(state.get("score_json"), dict) else {}

        for facet, l2 in CHECKLIST_L3_TO_L2[l1].items():
            raw_score: Any = None
            mapped_score: float | None = None
            if l1 not in active:
                applicability = "not_evaluated"
            elif request_status == "request_failed":
                applicability = "request_failed"
            elif parse_status == "parse_failed":
                applicability = "parse_failed"
            else:
                raw_score = _lookup_raw_score(score_json, l2, facet)
                if raw_score is None:
                    applicability = "missing"
                elif isinstance(raw_score, str) and raw_score.upper() == "N/A":
                    applicability = "na"
                else:
                    mapped_score = map_score(raw_score)
                    applicability = "applicable" if mapped_score is not None else "missing"

            rows.append(
                {
                    "schema_version": SCHEMA_VERSION,
                    "run_id": record["run_id"],
                    "image_id": record["image_id"],
                    "sample_item_id": record["sample_item_id"],
                    "sample_index": record["sample_index"],
                    "source_relative_path": record["source_relative_path"],
                    "profile_id": record["profile_id"],
                    "profile_version": record["profile_version"],
                    "condition_digest": record["condition_digest"],
                    "rubric_id": record["rubric"]["id"],
                    "rubric_version": record["rubric"]["version"],
                    "rubric_classification": record["rubric"]["classification"],
                    "actual_provenance": record["actual_provenance"],
                    "presented_provenance": record["presented_provenance"],
                    "reference_id": reference.get("id"),
                    "reference_digest": reference.get("digest"),
                    "reference_actual_role": reference.get("actual_role"),
                    "reference_presented_role": reference.get("presented_role"),
                    "l1_id": slug(l1),
                    "l1_label": l1,
                    "l2_id": f"{slug(l1)}.{slug(l2)}",
                    "l2_label": l2,
                    "facet_id": f"qwen_stock.{slug(l1)}.{slug(l2)}.{slug(facet)}",
                    "facet_concept_id": f"{slug(l1)}.{slug(l2)}.{slug(facet)}",
                    "facet_label": facet,
                    "raw_score": raw_score,
                    "mapped_score": mapped_score,
                    "applicability": applicability,
                    "parse_status": parse_status,
                    "request_status": request_status,
                }
            )
    return rows


def aggregate_rows(record: dict[str, Any], profile: RealPhotoProfile) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    active = set(profile.dimensions)
    official = record["official_scores"]

    for l1 in ALL_DIMENSIONS:
        state = record["dimensions"].get(l1, {})
        request_status = state.get("request_status", "not_evaluated")
        parse_status = state.get("parse_status", "not_evaluated")
        l2_scores = official["level2"].get(l1, {})
        l3_scores = official["level3_mapped"].get(l1, {})

        if l1 not in active:
            applicability = "not_evaluated"
        elif request_status == "request_failed":
            applicability = "request_failed"
        elif parse_status == "parse_failed":
            applicability = "parse_failed"
        else:
            applicability = "applicable"

        expected_l2 = list(dict.fromkeys(CHECKLIST_L3_TO_L2[l1].values()))
        for l2 in expected_l2:
            score = l2_scores.get(l2)
            applicable_count = sum(
                1 for value in l3_scores.get(l2, {}).values() if value is not None
            )
            rows.append(
                _aggregate_row(
                    record,
                    score_level="l2",
                    l1=l1,
                    l2=l2,
                    score_id=f"{slug(l1)}.{slug(l2)}",
                    score_label=l2,
                    score=score,
                    applicable_count=applicable_count,
                    applicability=(
                        "applicable" if score is not None
                        else "missing" if applicability == "applicable"
                        else applicability
                    ),
                    aggregation_method="mean_non_na_l3",
                )
            )

        l1_score = official["level1"].get(l1)
        rows.append(
            _aggregate_row(
                record,
                score_level="l1",
                l1=l1,
                l2=None,
                score_id=slug(l1),
                score_label=l1,
                score=l1_score,
                applicable_count=sum(1 for value in l2_scores.values() if value is not None),
                applicability=(
                    "applicable" if l1_score is not None
                    else "missing" if applicability == "applicable"
                    else applicability
                ),
                aggregation_method="mean_non_na_l2",
            )
        )

    total = official["active_dimension_aggregate"]
    rows.append(
        _aggregate_row(
            record,
            score_level="active_dimension_aggregate",
            l1=None,
            l2=None,
            score_id="active_dimension_aggregate",
            score_label="Qwen aggregate, active dimensions",
            score=total,
            applicable_count=official["active_dimension_count"],
            applicability="applicable" if total is not None else "missing",
            aggregation_method=official["aggregation_method"],
        )
    )
    return rows


def _aggregate_row(
    record: dict[str, Any],
    *,
    score_level: str,
    l1: str | None,
    l2: str | None,
    score_id: str,
    score_label: str,
    score: float | None,
    applicable_count: int,
    applicability: str,
    aggregation_method: str,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": record["run_id"],
        "image_id": record["image_id"],
        "sample_item_id": record["sample_item_id"],
        "sample_index": record["sample_index"],
        "score_level": score_level,
        "l1_id": slug(l1) if l1 else None,
        "l2_id": f"{slug(l1)}.{slug(l2)}" if l1 and l2 else None,
        "score_id": score_id,
        "score_label": score_label,
        "score": score,
        "applicable_count": applicable_count,
        "applicability": applicability,
        "aggregation_method": aggregation_method,
    }


FACET_FIELDNAMES = [
    "schema_version", "run_id", "image_id", "sample_item_id", "sample_index",
    "source_relative_path", "profile_id", "profile_version", "condition_digest",
    "rubric_id", "rubric_version", "rubric_classification", "actual_provenance",
    "presented_provenance", "reference_id", "reference_digest",
    "reference_actual_role", "reference_presented_role", "l1_id", "l1_label",
    "l2_id", "l2_label", "facet_id", "facet_concept_id", "facet_label",
    "raw_score", "mapped_score", "applicability", "parse_status", "request_status",
]

AGGREGATE_FIELDNAMES = [
    "schema_version", "run_id", "image_id", "sample_item_id", "sample_index",
    "score_level", "l1_id", "l2_id", "score_id", "score_label", "score",
    "applicable_count", "applicability", "aggregation_method",
]
