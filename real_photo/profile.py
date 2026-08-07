"""Real-photo evaluation profile and prompt construction."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from checklists import DIM_TO_CHECKLIST


ALL_DIMENSIONS = tuple(DIM_TO_CHECKLIST)
DEFAULT_REAL_PHOTO_DIMENSIONS = (
    "Quality",
    "Aesthetics",
    "Creative Generation",
)


@dataclass(frozen=True)
class RealPhotoProfile:
    """Immutable run-level configuration for the stock-rubric real-photo baseline."""

    id: str = "real-photo-stock-no-reference"
    version: int = 2
    name: str = "Real photograph, stock Qwen rubric, no reference text"
    actual_provenance: str = "real"
    presented_provenance: str = "real"
    reference_source: str = "none"
    reference_actual_role: str = "none"
    reference_presented_role: str = "none"
    rubric_id: str = "qwen_stock"
    rubric_version: str = "upstream"
    rubric_classification: str = "stock_qwen"
    system_instruction_source: str = "lm_studio_preset"
    application_system_prompt: str | None = None
    dimensions: tuple[str, ...] = DEFAULT_REAL_PHOTO_DIMENSIONS

    def validate(self) -> None:
        unknown = [dimension for dimension in self.dimensions if dimension not in DIM_TO_CHECKLIST]
        if unknown:
            raise ValueError(f"Unknown evaluation dimensions: {unknown}")
        if len(set(self.dimensions)) != len(self.dimensions):
            raise ValueError("Evaluation dimensions must not contain duplicates")
        if not self.dimensions:
            raise ValueError("At least one evaluation dimension is required")

    @property
    def disabled_dimensions(self) -> tuple[str, ...]:
        enabled = set(self.dimensions)
        return tuple(dimension for dimension in ALL_DIMENSIONS if dimension not in enabled)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["dimensions"] = list(self.dimensions)
        data["disabled_dimensions"] = list(self.disabled_dimensions)
        return data


def build_real_photo_user_prompt(profile: RealPhotoProfile, level1_dimension: str) -> str:
    """Build one stateless request using the exact stock checklist text."""
    profile.validate()
    if level1_dimension not in profile.dimensions:
        raise ValueError(
            f"Dimension {level1_dimension!r} is not active in profile {profile.id!r}"
        )

    checklist = DIM_TO_CHECKLIST[level1_dimension]
    return f"""# Image Provenance
This is a real photograph. It was not generated from a text prompt.

# Reference Text
No generation prompt, candidate prompt, image description, or photographic-intent text is provided.

# Photograph
<image>

# Evaluation Dimension
{level1_dimension}

# Scoring Rules
- **0 (Fail)**: Clear defect present. Would noticeably reduce image quality.
- **1 (Pass)**: No defect. Meets baseline expectations.
- **2 (Excel)**: Exceptionally executed. Only when concrete excellence is observable.
- **N/A**: This criterion does not apply to this photograph or cannot be assessed without reference text.

# Evidence Rules
- Include one brief, concrete evidence statement for every facet.
- Base evidence only on visible image content and the supplied context.
- For N/A, state why the criterion cannot be assessed or does not apply.
- Evidence is diagnostic metadata and does not change the official score.

# Evaluation Checklist
{checklist}

# Output Format
Respond with a valid JSON object only (no markdown code blocks):
{{
  "{{level2_dim}}": {{
    "{{level3_dim}}": {{
      "score": 0|1|2|"N/A",
      "evidence": "brief concrete evidence"
    }}
  }}
}}"""
