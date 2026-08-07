"""JPEG discovery, deterministic sampling, and source identity helpers."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


JPEG_EXTENSIONS = frozenset({".jpg", ".jpeg"})


@dataclass(frozen=True)
class SampleSelection:
    root: Path
    recursive: bool
    seed: int
    requested_maximum: int
    eligible_paths: tuple[Path, ...]
    selected_paths: tuple[Path, ...]

    @property
    def eligible_count(self) -> int:
        return len(self.eligible_paths)

    @property
    def selected_count(self) -> int:
        return len(self.selected_paths)


def discover_jpegs(folder: str | Path, *, recursive: bool = True) -> list[Path]:
    """Return eligible JPEG paths in stable relative-path order."""
    root = Path(folder).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"Source folder does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Source path is not a folder: {root}")

    candidates: Iterable[Path]
    candidates = root.rglob("*") if recursive else root.iterdir()
    paths = [
        path.resolve()
        for path in candidates
        if path.is_file() and path.suffix.lower() in JPEG_EXTENSIONS
    ]
    paths.sort(key=lambda path: path.relative_to(root).as_posix().casefold())
    return paths


def sample_up_to(
    paths: Iterable[Path],
    *,
    root: str | Path,
    maximum: int,
    seed: int = 42,
) -> list[Path]:
    """Select up to ``maximum`` unique paths with stable seeded ordering.

    A SHA-256 ordering is used rather than ``random.sample`` so selection remains
    stable across Python implementations and versions for the same relative
    paths and seed.
    """
    if maximum < 1:
        raise ValueError("sample maximum must be at least 1")

    root_path = Path(root).expanduser().resolve()
    unique_paths = list(dict.fromkeys(Path(path).resolve() for path in paths))
    if not unique_paths:
        raise ValueError(f"No eligible JPEG files found under: {root_path}")

    def seeded_key(path: Path) -> tuple[bytes, str]:
        relative = path.relative_to(root_path).as_posix()
        digest = hashlib.sha256(f"{seed}\0{relative}".encode("utf-8")).digest()
        return digest, relative.casefold()

    ordered = sorted(unique_paths, key=seeded_key)
    return ordered[: min(maximum, len(ordered))]


def create_selection(
    folder: str | Path,
    *,
    recursive: bool = True,
    maximum: int,
    seed: int = 42,
) -> SampleSelection:
    root = Path(folder).expanduser().resolve()
    eligible = discover_jpegs(root, recursive=recursive)
    selected = sample_up_to(eligible, root=root, maximum=maximum, seed=seed)
    return SampleSelection(
        root=root,
        recursive=recursive,
        seed=seed,
        requested_maximum=maximum,
        eligible_paths=tuple(eligible),
        selected_paths=tuple(selected),
    )


def sha256_file(path: str | Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def stable_sample_item_id(manifest_id: str, relative_path: str) -> str:
    payload = f"{manifest_id}\0{relative_path}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
