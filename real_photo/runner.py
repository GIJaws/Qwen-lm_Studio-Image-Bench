"""Durable real-photo evaluation orchestration."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backends.lm_studio_backend import LMStudioJudge
from score_utils import extract_json_from_response, fix_score_json

from .images import load_real_photo
from .profile import ALL_DIMENSIONS, RealPhotoProfile, build_real_photo_user_prompt
from .records import SCHEMA_VERSION, build_result_record, digest_json
from .report import render_minimal_report
from .sampling import create_selection, sha256_file, stable_sample_item_id
from .storage import RunStore


SAFE_EXPORT_INTERVAL = 10


@dataclass(frozen=True)
class LMStudioSettings:
    model: str
    base_url: str = "http://localhost:1234/v1"
    max_new_tokens: int = 4096
    temperature: float = 0.0
    top_k: int = 1
    top_p: float = 1.0
    repeat_penalty: float = 1.05
    seed: int | None = 42
    timeout_seconds: float = 300.0
    image_format: str = "PNG"
    extra_body: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def create_judge(self) -> LMStudioJudge:
        return LMStudioJudge(
            model=self.model,
            base_url=self.base_url,
            max_new_tokens=self.max_new_tokens,
            temperature=self.temperature,
            top_k=self.top_k,
            top_p=self.top_p,
            repeat_penalty=self.repeat_penalty,
            seed=self.seed,
            timeout_seconds=self.timeout_seconds,
            image_format=self.image_format,
            extra_body=self.extra_body,
        )


@dataclass(frozen=True)
class RealPhotoRunSettings:
    source_folder: Path
    sample_count: int = 10
    sample_seed: int = 42
    recursive: bool = True
    max_long_edge: int = 1024
    html_report: bool = True


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_real_photo_evaluation(
    *,
    settings: RealPhotoRunSettings,
    lm_studio: LMStudioSettings,
    run_dir: str | Path | None = None,
    output_root: str | Path = "local/runs",
    profile: RealPhotoProfile | None = None,
) -> Path:
    """Create or resume one deterministic real-photo evaluation run."""
    profile = profile or RealPhotoProfile()
    profile.validate()
    source_folder = settings.source_folder.expanduser().resolve()

    condition = {
        "evaluation_profile": profile.to_dict(),
        "model": {
            "id": lm_studio.model,
            "runtime": "lm-studio",
            "api_mode": "stateless_chat_completions",
        },
        "inference_settings": lm_studio.to_dict(),
        "preprocessing": {
            "format": "jpeg",
            "exif_orientation": True,
            "resize": "preserve_aspect_ratio",
            "max_long_edge": settings.max_long_edge,
        },
    }
    condition_digest = digest_json(condition)

    target = _resolve_run_dir(run_dir, output_root, condition_digest)
    store = RunStore(target)
    if store.exists():
        run_data, manifest = _load_and_validate_resume(
            store,
            condition_digest=condition_digest,
            source_folder=source_folder,
        )
    else:
        selection = create_selection(
            source_folder,
            recursive=settings.recursive,
            maximum=settings.sample_count,
            seed=settings.sample_seed,
        )
        manifest = _build_sample_manifest(selection)
        run_data = _build_run_data(
            run_id=target.name,
            manifest=manifest,
            profile=profile,
            condition=condition,
            condition_digest=condition_digest,
        )
        store.initialize(run_data, manifest)

    results = store.load_results()
    completed_ids = {record["sample_item_id"] for record in results}
    judge = lm_studio.create_judge()

    print(
        f"Run {run_data['run_id']}: {manifest['selected_count']} selected "
        f"from {manifest['eligible_count']} eligible JPEGs "
        f"(seed {manifest['sample_seed']})"
    )
    if completed_ids:
        print(f"Resuming with {len(completed_ids)} completed image result(s)")

    run_data["status"] = "running"
    run_data["updated_at"] = utc_now()
    store.write_run(run_data)

    interrupted = False
    try:
        for selected in manifest["selected_items"]:
            sample_item_id = selected["sample_item_id"]
            if sample_item_id in completed_ids:
                continue

            print(
                f"[{selected['sample_index'] + 1}/{manifest['selected_count']}] "
                f"{selected['source_relative_path']}"
            )
            result = _evaluate_selected_item(
                store=store,
                run_data=run_data,
                manifest=manifest,
                selected=selected,
                profile=profile,
                judge=judge,
                max_long_edge=settings.max_long_edge,
            )
            store.append_result(result)
            aggregate = result["official_scores"]["active_dimension_aggregate"]
            aggregate_text = "N/A" if aggregate is None else f"{aggregate:.2f}"
            print(f"  Result: {result['status']} · active aggregate {aggregate_text}")
            results.append(result)
            completed_ids.add(sample_item_id)
            _update_counts(run_data, results, manifest)
            run_data["updated_at"] = utc_now()
            store.write_run(run_data)

            if len(results) % SAFE_EXPORT_INTERVAL == 0:
                store.rebuild_analysis_exports(results, profile)
                if settings.html_report:
                    store.write_report(render_minimal_report(run_data, manifest, results))
    except KeyboardInterrupt:
        interrupted = True
        run_data["status"] = "interrupted"
    except Exception:
        run_data["status"] = "failed"
        run_data["updated_at"] = utc_now()
        store.write_run(run_data)
        store.rebuild_analysis_exports(results, profile)
        if settings.html_report:
            store.write_report(render_minimal_report(run_data, manifest, results))
        raise

    _update_counts(run_data, results, manifest)
    if not interrupted:
        run_data["status"] = "completed"
        run_data["completed_at"] = utc_now()
    run_data["updated_at"] = utc_now()
    store.write_run(run_data)
    store.rebuild_analysis_exports(results, profile)
    if settings.html_report:
        store.write_report(render_minimal_report(run_data, manifest, results))

    return store.run_dir


def _resolve_run_dir(
    run_dir: str | Path | None,
    output_root: str | Path,
    condition_digest: str,
) -> Path:
    if run_dir is not None:
        return Path(run_dir).expanduser().resolve()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    return (
        Path(output_root).expanduser().resolve()
        / f"{timestamp}-real-photo-{condition_digest[:8]}"
    )


def _build_sample_manifest(selection: Any) -> dict[str, Any]:
    base = {
        "schema_version": SCHEMA_VERSION,
        "source_folder": str(selection.root),
        "recursive": selection.recursive,
        "extensions": [".jpg", ".jpeg"],
        "sampling": "without_replacement",
        "sampling_algorithm": "sha256_seeded_relative_path_order_v1",
        "sample_seed": selection.seed,
        "requested_maximum": selection.requested_maximum,
        "eligible_count": selection.eligible_count,
        "selected_count": selection.selected_count,
        "selection_order": "stored_array_order",
        "created_at": utc_now(),
        "selected_relative_paths": [
            path.relative_to(selection.root).as_posix()
            for path in selection.selected_paths
        ],
    }
    identity_payload = {
        key: base[key]
        for key in (
            "source_folder",
            "recursive",
            "extensions",
            "sampling",
            "sampling_algorithm",
            "sample_seed",
            "requested_maximum",
            "selected_relative_paths",
        )
    }
    manifest_id = digest_json(identity_payload)
    base["sample_manifest_id"] = manifest_id
    base["selected_items"] = [
        {
            "sample_index": index,
            "sample_item_id": stable_sample_item_id(manifest_id, relative),
            "source_path": str(selection.root / relative),
            "source_relative_path": relative,
        }
        for index, relative in enumerate(base["selected_relative_paths"])
    ]
    return base


def _build_run_data(
    *,
    run_id: str,
    manifest: dict[str, Any],
    profile: RealPhotoProfile,
    condition: dict[str, Any],
    condition_digest: str,
) -> dict[str, Any]:
    now = utc_now()
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "status": "running",
        "created_at": now,
        "started_at": now,
        "updated_at": now,
        "completed_at": None,
        "sample_manifest_id": manifest["sample_manifest_id"],
        "condition_digest": condition_digest,
        "evaluation_profile": profile.to_dict(),
        "actual_provenance": profile.actual_provenance,
        "presented_provenance": profile.presented_provenance,
        "reference_policy": {
            "source": profile.reference_source,
            "actual_role": profile.reference_actual_role,
            "presented_role": profile.reference_presented_role,
        },
        "rubric": {
            "id": profile.rubric_id,
            "version": profile.rubric_version,
            "classification": profile.rubric_classification,
        },
        "system_instruction_source": profile.system_instruction_source,
        "model": condition["model"],
        "inference_settings": condition["inference_settings"],
        "preprocessing": condition["preprocessing"],
        "counts": {
            "selected": manifest["selected_count"],
            "result_records": 0,
            "completed": 0,
            "completed_with_parse_errors": 0,
            "request_failed": 0,
        },
    }


def _load_and_validate_resume(
    store: RunStore,
    *,
    condition_digest: str,
    source_folder: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    run_data = store.load_run()
    manifest = store.load_manifest()
    if run_data.get("condition_digest") != condition_digest:
        raise ValueError(
            "Run configuration does not match the existing run directory. "
            "Use the original model/settings or create a new run directory."
        )
    if Path(manifest["source_folder"]).resolve() != source_folder:
        raise ValueError("Source folder does not match the existing sample manifest")
    return run_data, manifest


def _new_checkpoint(
    *,
    run_data: dict[str, Any],
    manifest: dict[str, Any],
    selected: dict[str, Any],
    profile: RealPhotoProfile,
) -> dict[str, Any]:
    dimensions: dict[str, dict[str, Any]] = {}
    for dimension in ALL_DIMENSIONS:
        if dimension in profile.dimensions:
            dimensions[dimension] = {
                "request_status": "pending",
                "parse_status": "not_started",
                "raw_response": None,
                "score_json": None,
                "repair_applied": False,
                "error": None,
            }
        else:
            dimensions[dimension] = {
                "request_status": "not_evaluated",
                "parse_status": "not_evaluated",
                "raw_response": None,
                "score_json": None,
                "repair_applied": False,
                "error": None,
            }

    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_data["run_id"],
        "sample_manifest_id": manifest["sample_manifest_id"],
        "sample_item_id": selected["sample_item_id"],
        "image_id": None,
        "sample_index": selected["sample_index"],
        "source_path": selected["source_path"],
        "source_relative_path": selected["source_relative_path"],
        "source_uri": Path(selected["source_path"]).resolve().as_uri(),
        "image": None,
        "profile_id": profile.id,
        "profile_version": profile.version,
        "condition_digest": run_data["condition_digest"],
        "rubric": run_data["rubric"],
        "actual_provenance": profile.actual_provenance,
        "presented_provenance": profile.presented_provenance,
        "reference": {
            "id": None,
            "digest": None,
            "source": profile.reference_source,
            "actual_role": profile.reference_actual_role,
            "presented_role": profile.reference_presented_role,
            "text": None,
        },
        "dimensions": dimensions,
        "updated_at": utc_now(),
    }


def _evaluate_selected_item(
    *,
    store: RunStore,
    run_data: dict[str, Any],
    manifest: dict[str, Any],
    selected: dict[str, Any],
    profile: RealPhotoProfile,
    judge: LMStudioJudge,
    max_long_edge: int,
) -> dict[str, Any]:
    checkpoint = store.load_checkpoint(selected["sample_item_id"]) or _new_checkpoint(
        run_data=run_data,
        manifest=manifest,
        selected=selected,
        profile=profile,
    )
    source_path = Path(selected["source_path"])

    try:
        if checkpoint["image_id"] is None:
            checkpoint["image_id"] = sha256_file(source_path)
        image, preparation = load_real_photo(source_path, max_long_edge=max_long_edge)
        checkpoint["image"] = preparation.to_dict()
        checkpoint["updated_at"] = utc_now()
        store.write_checkpoint(checkpoint)
    except Exception as exc:
        for dimension in profile.dimensions:
            state = checkpoint["dimensions"][dimension]
            state.update(
                {
                    "request_status": "request_failed",
                    "parse_status": "not_started",
                    "error": f"Image preparation failed: {exc}",
                }
            )
        if checkpoint["image_id"] is None:
            checkpoint["image_id"] = digest_json(
                {"source_path": checkpoint["source_path"], "error": str(exc)}
            )
        checkpoint["updated_at"] = utc_now()
        store.write_checkpoint(checkpoint)
        return build_result_record(checkpoint, profile)

    try:
        for dimension in profile.dimensions:
            state = checkpoint["dimensions"][dimension]
            if state.get("request_status") == "completed":
                continue

            print(f"  {dimension}...")
            try:
                user_text = build_real_photo_user_prompt(profile, dimension)
                raw_response = judge.generate_batch(
                    [
                        {
                            "system_prompt": profile.application_system_prompt,
                            "user_text": user_text,
                            "image": image,
                        }
                    ]
                )[0]
                extracted = extract_json_from_response(raw_response)
                fixed = (
                    fix_score_json(extracted, dimension)
                    if extracted is not None
                    else None
                )
                state.update(
                    {
                        "request_status": "completed",
                        "parse_status": "parsed" if fixed is not None else "parse_failed",
                        "raw_response": raw_response,
                        "score_json": fixed,
                        "repair_applied": extracted is not None and fixed != extracted,
                        "error": None,
                    }
                )
            except Exception as exc:
                print(f"    Request failed: {type(exc).__name__}: {exc}")
                state.update(
                    {
                        "request_status": "request_failed",
                        "parse_status": "not_started",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )

            checkpoint["updated_at"] = utc_now()
            store.write_checkpoint(checkpoint)
    finally:
        image.close()

    return build_result_record(checkpoint, profile)


def _update_counts(
    run_data: dict[str, Any],
    results: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> None:
    run_data["counts"] = {
        "selected": manifest["selected_count"],
        "result_records": len(results),
        "completed": sum(record["status"] == "completed" for record in results),
        "completed_with_parse_errors": sum(
            record["status"] == "completed_with_parse_errors"
            for record in results
        ),
        "request_failed": sum(
            record["status"] == "request_failed" for record in results
        ),
    }


def parse_extra_body(raw: str | None) -> dict[str, Any] | None:
    if raw is None:
        return None
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("LM Studio extra body must be a JSON object")
    return value
