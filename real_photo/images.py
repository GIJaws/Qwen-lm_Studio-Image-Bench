"""Real-photo JPEG decoding and aspect-ratio-preserving preprocessing."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps


@dataclass(frozen=True)
class ImagePreparation:
    source_width: int
    source_height: int
    source_aspect_ratio: float
    prepared_width: int
    prepared_height: int
    prepared_aspect_ratio: float
    max_long_edge: int
    orientation_applied: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_real_photo(
    path: str | Path,
    *,
    max_long_edge: int = 1024,
) -> tuple[Image.Image, ImagePreparation]:
    """Decode a JPEG, apply EXIF orientation, and preserve its aspect ratio."""
    if max_long_edge < 1:
        raise ValueError("max_long_edge must be at least 1")

    source_path = Path(path)
    with Image.open(source_path) as opened:
        if opened.format not in {"JPEG", "MPO"}:
            raise ValueError(f"Expected a JPEG image, got {opened.format!r}: {source_path}")
        orientation = opened.getexif().get(274, 1)
        transposed = ImageOps.exif_transpose(opened)
        orientation_applied = orientation not in (None, 1)
        rgb = transposed.convert("RGB")
        source_width, source_height = rgb.size

        if max(rgb.size) > max_long_edge:
            scale = max_long_edge / max(rgb.size)
            prepared_size = (
                max(1, round(source_width * scale)),
                max(1, round(source_height * scale)),
            )
            prepared = rgb.resize(prepared_size, Image.Resampling.LANCZOS)
        else:
            prepared = rgb.copy()

    prepared.load()
    prepared_width, prepared_height = prepared.size
    metadata = ImagePreparation(
        source_width=source_width,
        source_height=source_height,
        source_aspect_ratio=source_width / source_height,
        prepared_width=prepared_width,
        prepared_height=prepared_height,
        prepared_aspect_ratio=prepared_width / prepared_height,
        max_long_edge=max_long_edge,
        orientation_applied=orientation_applied,
    )
    return prepared, metadata
