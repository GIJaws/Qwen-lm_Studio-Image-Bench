"""Crash-tolerant local run storage for long real-photo evaluations."""

from __future__ import annotations

import csv
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable

from .profile import RealPhotoProfile
from .records import (
    AGGREGATE_FIELDNAMES,
    FACET_FIELDNAMES,
    aggregate_rows,
    facet_rows,
)


class RunStore:
    """Own one local run directory and its durable artifacts."""

    def __init__(self, run_dir: str | Path) -> None:
        self.run_dir = Path(run_dir).expanduser().resolve()
        self.run_json = self.run_dir / "run.json"
        self.sample_manifest_json = self.run_dir / "sample-manifest.json"
        self.results_jsonl = self.run_dir / "results.jsonl"
        self.facet_scores_csv = self.run_dir / "facet-scores.csv"
        self.aggregate_scores_csv = self.run_dir / "aggregate-scores.csv"
        self.report_html = self.run_dir / "report.html"
        self.checkpoints_dir = self.run_dir / "checkpoints"

    def initialize(self, run_data: dict[str, Any], manifest: dict[str, Any]) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=False)
        self.checkpoints_dir.mkdir()
        atomic_write_json(self.run_json, run_data)
        atomic_write_json(self.sample_manifest_json, manifest)
        self.results_jsonl.touch()
        _fsync_path(self.results_jsonl)

    def exists(self) -> bool:
        return self.run_json.exists() and self.sample_manifest_json.exists()

    def load_run(self) -> dict[str, Any]:
        return load_json(self.run_json)

    def load_manifest(self) -> dict[str, Any]:
        return load_json(self.sample_manifest_json)

    def write_run(self, run_data: dict[str, Any]) -> None:
        atomic_write_json(self.run_json, run_data)

    def checkpoint_path(self, sample_item_id: str) -> Path:
        return self.checkpoints_dir / f"{sample_item_id}.json"

    def load_checkpoint(self, sample_item_id: str) -> dict[str, Any] | None:
        path = self.checkpoint_path(sample_item_id)
        return load_json(path) if path.exists() else None

    def write_checkpoint(self, checkpoint: dict[str, Any]) -> None:
        atomic_write_json(
            self.checkpoint_path(checkpoint["sample_item_id"]),
            checkpoint,
        )

    def append_result(self, result: dict[str, Any]) -> None:
        encoded = json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n"
        with self.results_jsonl.open("a", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())

    def load_results(self, *, repair_trailing_partial_line: bool = True) -> list[dict[str, Any]]:
        if not self.results_jsonl.exists():
            return []

        lines = [
            line
            for line in self.results_jsonl.read_text(encoding="utf-8").splitlines(keepends=True)
            if line.strip()
        ]
        results: list[dict[str, Any]] = []
        for index, line in enumerate(lines):
            try:
                results.append(json.loads(line))
            except json.JSONDecodeError as exc:
                is_final_line = index == len(lines) - 1
                if not repair_trailing_partial_line or not is_final_line:
                    raise ValueError(
                        f"Invalid JSONL record {index + 1} in {self.results_jsonl}"
                    ) from exc
                atomic_write_text(self.results_jsonl, "".join(lines[:index]))
                break

        return results

    def rebuild_analysis_exports(
        self,
        results: Iterable[dict[str, Any]],
        profile: RealPhotoProfile,
    ) -> None:
        ordered = sorted(results, key=lambda record: record["sample_index"])
        all_facet_rows = [row for record in ordered for row in facet_rows(record, profile)]
        all_aggregate_rows = [
            row for record in ordered for row in aggregate_rows(record, profile)
        ]
        atomic_write_csv(self.facet_scores_csv, FACET_FIELDNAMES, all_facet_rows)
        atomic_write_csv(
            self.aggregate_scores_csv,
            AGGREGATE_FIELDNAMES,
            all_aggregate_rows,
        )

    def write_report(self, html: str) -> None:
        atomic_write_text(self.report_html, html)


def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def atomic_write_json(path: str | Path, value: Any) -> None:
    atomic_write_text(
        path,
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    )


def atomic_write_text(path: str | Path, content: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=target.parent,
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        _fsync_directory(target.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def atomic_write_csv(
    path: str | Path,
    fieldnames: list[str],
    rows: Iterable[dict[str, Any]],
) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=target.parent,
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        _fsync_directory(target.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def _fsync_path(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())
    _fsync_directory(path.parent)


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
