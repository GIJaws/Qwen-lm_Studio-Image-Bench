"""Versioned custom rubric packs for experimental photographic dimensions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from score_utils import map_score


class CustomRubricError(ValueError):
    """Raised when a custom rubric pack is invalid."""


@dataclass(frozen=True)
class CustomFacet:
    id: str
    label: str
    prompt: str


@dataclass(frozen=True)
class CustomGroup:
    id: str
    label: str
    facets: tuple[CustomFacet, ...]


@dataclass(frozen=True)
class CustomDimension:
    id: str
    label: str
    description: str
    groups: tuple[CustomGroup, ...]

    def checklist_text(self) -> str:
        lines: list[str] = []
        for group in self.groups:
            lines.append(f"## {group.label}")
            for facet in group.facets:
                lines.append(f"- {facet.label}: {facet.prompt}")
        return "\n".join(lines)


@dataclass(frozen=True)
class CustomRubricPack:
    schema_version: int
    id: str
    version: int
    name: str
    classification: str
    description: str
    dimensions: tuple[CustomDimension, ...]

    @property
    def identity(self) -> str:
        return f"{self.id}_v{self.version}"

    def dimension(self, dimension_id: str) -> CustomDimension:
        for value in self.dimensions:
            if value.id == dimension_id:
                return value
        raise KeyError(f"Unknown dimension {dimension_id!r} in {self.identity}")

    def to_metadata(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "version": self.version,
            "identity": self.identity,
            "name": self.name,
            "classification": self.classification,
            "description": self.description,
            "dimensions": [
                {
                    "id": dimension.id,
                    "label": dimension.label,
                    "description": dimension.description,
                    "groups": [
                        {
                            "id": group.id,
                            "label": group.label,
                            "facets": [
                                {"id": facet.id, "label": facet.label}
                                for facet in group.facets
                            ],
                        }
                        for group in dimension.groups
                    ],
                }
                for dimension in self.dimensions
            ],
        }


def load_custom_rubric(path: str | Path) -> CustomRubricPack:
    source = Path(path).expanduser().resolve()
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except json.JSONDecodeError as exc:
        raise CustomRubricError(f"Invalid JSON in {source}: {exc}") from exc
    if not isinstance(raw, dict):
        raise CustomRubricError("Rubric root must be a JSON object")

    pack = CustomRubricPack(
        schema_version=_required_int(raw, "schema_version"),
        id=_required_id(raw, "id"),
        version=_required_int(raw, "version"),
        name=_required_text(raw, "name"),
        classification=_required_text(raw, "classification"),
        description=str(raw.get("description", "")).strip(),
        dimensions=tuple(
            _parse_dimension(value)
            for value in _required_list(raw, "dimensions")
        ),
    )
    validate_custom_rubric(pack)
    return pack


def _parse_dimension(raw: Any) -> CustomDimension:
    if not isinstance(raw, dict):
        raise CustomRubricError("Each dimension must be an object")
    return CustomDimension(
        id=_required_id(raw, "id"),
        label=_required_text(raw, "label"),
        description=str(raw.get("description", "")).strip(),
        groups=tuple(
            _parse_group(value)
            for value in _required_list(raw, "groups")
        ),
    )


def _parse_group(raw: Any) -> CustomGroup:
    if not isinstance(raw, dict):
        raise CustomRubricError("Each L2 group must be an object")
    return CustomGroup(
        id=_required_id(raw, "id"),
        label=_required_text(raw, "label"),
        facets=tuple(
            _parse_facet(value)
            for value in _required_list(raw, "facets")
        ),
    )


def _parse_facet(raw: Any) -> CustomFacet:
    if not isinstance(raw, dict):
        raise CustomRubricError("Each facet must be an object")
    return CustomFacet(
        id=_required_id(raw, "id"),
        label=_required_text(raw, "label"),
        prompt=_required_text(raw, "prompt"),
    )


def _required_list(raw: dict[str, Any], key: str) -> list[Any]:
    value = raw.get(key)
    if not isinstance(value, list) or not value:
        raise CustomRubricError(f"{key} must be a non-empty array")
    return value


def _required_text(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CustomRubricError(f"{key} must be a non-empty string")
    return value.strip()


def _required_id(raw: dict[str, Any], key: str) -> str:
    value = _required_text(raw, key)
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789_-")
    if any(character not in allowed for character in value):
        raise CustomRubricError(
            f"{key}={value!r} must use lowercase letters, numbers, '_' or '-'"
        )
    return value


def _required_int(raw: dict[str, Any], key: str) -> int:
    value = raw.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise CustomRubricError(f"{key} must be a positive integer")
    return value


def validate_custom_rubric(pack: CustomRubricPack) -> None:
    if pack.classification != "custom":
        raise CustomRubricError(
            "User-authored packs must use classification='custom'"
        )
    _assert_unique(
        [dimension.id for dimension in pack.dimensions],
        "dimension IDs",
    )
    _assert_unique(
        [dimension.label for dimension in pack.dimensions],
        "dimension labels",
    )
    for dimension in pack.dimensions:
        if not dimension.groups:
            raise CustomRubricError(
                f"Dimension {dimension.id!r} has no groups"
            )
        _assert_unique(
            [group.id for group in dimension.groups],
            f"group IDs in {dimension.id}",
        )
        _assert_unique(
            [group.label for group in dimension.groups],
            f"group labels in {dimension.id}",
        )
        all_facet_ids: list[str] = []
        all_facet_labels: list[str] = []
        for group in dimension.groups:
            if not group.facets:
                raise CustomRubricError(
                    f"Group {dimension.id}.{group.id} has no facets"
                )
            all_facet_ids.extend(facet.id for facet in group.facets)
            all_facet_labels.extend(facet.label for facet in group.facets)
        _assert_unique(all_facet_ids, f"facet IDs in {dimension.id}")
        _assert_unique(all_facet_labels, f"facet labels in {dimension.id}")


def _assert_unique(values: Iterable[str], label: str) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    if duplicates:
        raise CustomRubricError(
            f"Duplicate {label}: {sorted(duplicates)}"
        )


def build_custom_dimension_prompt(
    pack: CustomRubricPack,
    dimension: CustomDimension,
    *,
    include_evidence: bool = True,
    stateful_branch: bool = True,
) -> str:
    context = (
        "Evaluate the real photograph already stored in the shared conversation "
        "context."
        if stateful_branch
        else "Evaluate the attached real photograph."
    )
    if include_evidence:
        evidence_rules = """
# Evidence Rules
- Include one brief, concrete evidence statement for every facet.
- Base evidence only on visible image content and supplied context.
- For N/A, state why the criterion does not apply.
- Evidence is diagnostic metadata and does not change the score.
"""
        output = """{
  "{level2_group}": {
    "{facet}": {
      "score": 0|1|2|"N/A",
      "evidence": "brief concrete evidence"
    }
  }
}"""
    else:
        evidence_rules = ""
        output = """{
  "{level2_group}": {
    "{facet}": {"score": 0|1|2|"N/A"}
  }
}"""

    return f"""# Custom Rubric
Pack: {pack.identity}
Classification: custom experimental judgment
Dimension: {dimension.label}

{context}

# Scoring Rules
- **0 (Fail)**: The visible execution clearly fails this criterion.
- **1 (Pass)**: The criterion is adequately met.
- **2 (Excel)**: The criterion is exceptionally well executed.
- **N/A**: The criterion is not visible or does not apply.
{evidence_rules}
# Evaluation Checklist
{dimension.checklist_text()}

# Output Format
Return only one valid JSON object using the exact displayed group and facet labels:
{output}"""


def parse_custom_dimension_response(
    pack: CustomRubricPack,
    dimension: CustomDimension,
    parsed_json: dict[str, Any] | None,
) -> dict[str, Any]:
    """Normalize scores/evidence and compute nested custom aggregates."""
    groups: dict[str, Any] = {}
    applicable_group_scores: list[float] = []
    raw = parsed_json if isinstance(parsed_json, dict) else {}

    for group in dimension.groups:
        raw_group = raw.get(group.label)
        raw_group = raw_group if isinstance(raw_group, dict) else {}
        facets: dict[str, Any] = {}
        group_scores: list[float] = []
        for facet in group.facets:
            raw_value = raw_group.get(facet.label)
            if isinstance(raw_value, dict):
                raw_score = raw_value.get("score")
                evidence = raw_value.get("evidence")
            else:
                raw_score = raw_value
                evidence = None
            mapped = map_score(raw_score)
            if isinstance(raw_score, str) and raw_score.upper() == "N/A":
                applicability = "na"
            elif mapped is None:
                applicability = "missing"
            else:
                applicability = "applicable"
                group_scores.append(mapped)
            facets[facet.id] = {
                "facet_id": (
                    f"{pack.id}.v{pack.version}.{dimension.id}."
                    f"{group.id}.{facet.id}"
                ),
                "facet_concept_id": (
                    f"custom.{pack.id}.{dimension.id}.{group.id}.{facet.id}"
                ),
                "label": facet.label,
                "raw_score": raw_score,
                "mapped_score": mapped,
                "evidence": evidence if isinstance(evidence, str) else None,
                "applicability": applicability,
            }
        group_score = (
            sum(group_scores) / len(group_scores)
            if group_scores
            else None
        )
        if group_score is not None:
            applicable_group_scores.append(group_score)
        groups[group.id] = {
            "label": group.label,
            "score": group_score,
            "facets": facets,
        }

    dimension_score = (
        sum(applicable_group_scores) / len(applicable_group_scores)
        if applicable_group_scores
        else None
    )
    return {
        "pack": pack.to_metadata(),
        "dimension_id": dimension.id,
        "dimension_label": dimension.label,
        "classification": "custom",
        "score": dimension_score,
        "aggregation_method": "mean_non_na_facets_to_groups_to_dimension",
        "groups": groups,
    }