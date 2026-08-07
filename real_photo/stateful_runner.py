"""Experimental stateful real-photo runner with bounded concurrent branches."""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from backends.lm_studio_stateful_backend import (
    StatefulChatResult,
    StatefulLMStudioJudge,
)
from score_utils import extract_json_from_response, fix_score_json

from .images import load_real_photo
from .profile import RealPhotoProfile, build_real_photo_user_prompt
from .records import build_result_record, digest_json
from .report import render_minimal_report
from .runner import (
    SAFE_EXPORT_INTERVAL,
    RealPhotoRunSettings,
    _build_run_data,
    _build_sample_manifest,
    _load_and_validate_resume,
    _new_checkpoint,
    _resolve_run_dir,
    _update_counts,
    utc_now,
)
from .sampling import create_selection, sha256_file
from .storage import RunStore


@dataclass(frozen=True)
class StatefulLMStudioSettings:
    """Native `/api/v1/chat` settings used by the stateful experiment."""

    model: str
    base_url: str = "http://localhost:1234/v1"
    max_output_tokens: int = 4096
    temperature: float = 0.0
    top_k: int = 1
    top_p: float = 1.0
    repeat_penalty: float = 1.05
    timeout_seconds: float = 900.0
    image_format: str = "PNG"
    reasoning: str | None = "on"
    base_reasoning: str | None = "off"
    base_max_output_tokens: int = 8
    context_length: int | None = None
    stream_progress: bool = True
    concurrency: int = 4
    extra_body: dict[str, Any] | None = None

    def validate(self) -> None:
        if self.concurrency < 1:
            raise ValueError("concurrency must be at least 1")
        if self.base_max_output_tokens < 1:
            raise ValueError("base_max_output_tokens must be at least 1")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.update(
            {
                "api_mode": "stateful_native_chat_branching",
                "request_seed": None,
                "seed_configuration": (
                    "The native /api/v1/chat request schema does not expose seed; "
                    "configure it in LM Studio if required."
                ),
                "bounded_concurrency": True,
            }
        )
        return data

    def create_judge(self) -> StatefulLMStudioJudge:
        self.validate()
        return StatefulLMStudioJudge(
            model=self.model,
            base_url=self.base_url,
            max_output_tokens=self.max_output_tokens,
            temperature=self.temperature,
            top_k=self.top_k,
            top_p=self.top_p,
            repeat_penalty=self.repeat_penalty,
            timeout_seconds=self.timeout_seconds,
            image_format=self.image_format,
            reasoning=self.reasoning,
            base_reasoning=self.base_reasoning,
            base_max_output_tokens=self.base_max_output_tokens,
            context_length=self.context_length,
            stream=self.stream_progress,
            extra_body=self.extra_body,
        )


class ConsoleProgress:
    """Thread-safe concise progress for concurrent SSE streams."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self._lock = threading.Lock()
        self._last_prompt_bucket: dict[str, int] = {}

    def __call__(
        self,
        label: str,
        event_type: str,
        data: dict[str, Any],
    ) -> None:
        if not self.enabled:
            return
        message: str | None = None
        if event_type == "prompt_processing.start":
            message = "prompt processing started"
        elif event_type == "prompt_processing.progress":
            progress = data.get("progress")
            if isinstance(progress, (int, float)):
                bucket = min(100, int(float(progress) * 4) * 25)
                if bucket > self._last_prompt_bucket.get(label, -1):
                    self._last_prompt_bucket[label] = bucket
                    message = f"prompt processing {bucket}%"
        elif event_type == "prompt_processing.end":
            message = "prompt processing complete"
        elif event_type == "reasoning.start":
            message = "reasoning"
        elif event_type == "message.start":
            message = "writing response"
        elif event_type == "chat.end":
            result = data.get("result")
            stats = result.get("stats", {}) if isinstance(result, dict) else {}
            tps = stats.get("tokens_per_second")
            output_tokens = stats.get("total_output_tokens")
            if isinstance(tps, (int, float)) and isinstance(output_tokens, int):
                message = f"complete · {output_tokens} tokens · {tps:.2f} tok/s"
            else:
                message = "complete"
        elif event_type == "error":
            error = data.get("error")
            message = f"error · {error}"

        if message is not None:
            with self._lock:
                print(f"    [{label}] {message}", flush=True)


def build_shared_context_prompt(profile: RealPhotoProfile) -> str:
    """Build the common image/context prefix used by every branch."""
    full_prompt = build_real_photo_user_prompt(profile, profile.dimensions[0])
    prefix, separator, _ = full_prompt.partition("# Evaluation Dimension")
    if not separator:
        raise ValueError("Real-photo prompt is missing Evaluation Dimension marker")
    return (
        prefix.rstrip()
        + "\n\n# Stateful Shared Context\n"
        + "Retain the photograph and supplied context for independent follow-up "
        + "evaluation requests. Do not evaluate any rubric yet. Reply exactly READY."
    )


def build_dimension_branch_prompt(
    profile: RealPhotoProfile,
    dimension: str,
) -> str:
    """Build only the dimension-specific suffix for a stateful branch."""
    full_prompt = build_real_photo_user_prompt(profile, dimension)
    _, separator, suffix = full_prompt.partition("# Evaluation Dimension")
    if not separator:
        raise ValueError("Real-photo prompt is missing Evaluation Dimension marker")
    return (
        "Evaluate the photograph already stored in the shared conversation context.\n\n"
        "# Evaluation Dimension"
        + suffix
    )


def run_stateful_real_photo_evaluation(
    *,
    settings: RealPhotoRunSettings,
    lm_studio: StatefulLMStudioSettings,
    run_dir: str | Path | None = None,
    output_root: str | Path = "local/runs",
    profile: RealPhotoProfile | None = None,
) -> Path:
    """Create or resume an experimental stateful real-photo run."""
    profile = profile or RealPhotoProfile()
    profile.validate()
    lm_studio.validate()
    source_folder = settings.source_folder.expanduser().resolve()

    condition = {
        "evaluation_profile": profile.to_dict(),
        "model": {
            "id": lm_studio.model,
            "runtime": "lm-studio",
            "api_mode": "stateful_native_chat_branching",
        },
        "inference_settings": lm_studio.to_dict(),
        "stateful_branching": {
            "shared_context_prompt_version": 1,
            "base_acknowledgement": "READY",
            "one_shared_context_per_image": True,
            "branches_are_independent": True,
            "max_in_flight_branch_requests": lm_studio.concurrency,
            "cache_reuse_claim": (
                "Not assumed. LM Studio state storage/branching is used; actual "
                "vision/KV cache reuse must be measured."
            ),
        },
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
        run_data["stateful_branching"] = condition["stateful_branching"]
        store.initialize(run_data, manifest)

    results = store.load_results()
    completed_ids = {record["sample_item_id"] for record in results}
    judge = lm_studio.create_judge()
    progress = ConsoleProgress(enabled=lm_studio.stream_progress)

    print(
        f"Run {run_data['run_id']}: {manifest['selected_count']} selected "
        f"from {manifest['eligible_count']} eligible JPEGs "
        f"(seed {manifest['sample_seed']})"
    )
    print(
        f"Stateful native chat · branch concurrency {lm_studio.concurrency} · "
        f"stream progress {'on' if lm_studio.stream_progress else 'off'}"
    )
    print(
        "Native stateful requests do not send a seed; configure seed in LM Studio "
        "if deterministic request sampling is required."
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
            result = _evaluate_selected_item_stateful(
                store=store,
                run_data=run_data,
                manifest=manifest,
                selected=selected,
                profile=profile,
                judge=judge,
                concurrency=lm_studio.concurrency,
                max_long_edge=settings.max_long_edge,
                progress=progress,
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


def _evaluate_selected_item_stateful(
    *,
    store: RunStore,
    run_data: dict[str, Any],
    manifest: dict[str, Any],
    selected: dict[str, Any],
    profile: RealPhotoProfile,
    judge: StatefulLMStudioJudge,
    concurrency: int,
    max_long_edge: int,
    progress: ConsoleProgress,
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
        checkpoint["updated_at"] = utc_now()
        store.write_checkpoint(checkpoint)
        return build_result_record(checkpoint, profile)

    pending = [
        dimension
        for dimension in profile.dimensions
        if checkpoint["dimensions"][dimension].get("request_status") != "completed"
    ]
    if not pending:
        image.close()
        result = build_result_record(checkpoint, profile)
        result["stateful_context"] = checkpoint.get("stateful_context")
        return result

    try:
        print("  Shared image context...")
        shared = judge.create_shared_context(
            system_prompt=profile.application_system_prompt,
            user_text=build_shared_context_prompt(profile),
            image=image,
            label="Shared context",
            progress=progress,
        )
        checkpoint["stateful_context"] = {
            "response_id": shared.response_id,
            "message": shared.message,
            "reasoning": shared.reasoning,
            "stats": shared.stats,
            "model_instance_id": shared.model_instance_id,
            "created_at": utc_now(),
        }
        checkpoint["updated_at"] = utc_now()
        store.write_checkpoint(checkpoint)
    except Exception as exc:
        for dimension in pending:
            checkpoint["dimensions"][dimension].update(
                {
                    "request_status": "request_failed",
                    "parse_status": "not_started",
                    "error": f"Shared context failed: {type(exc).__name__}: {exc}",
                }
            )
        checkpoint["updated_at"] = utc_now()
        store.write_checkpoint(checkpoint)
        result = build_result_record(checkpoint, profile)
        result["stateful_context"] = checkpoint.get("stateful_context")
        return result
    finally:
        image.close()

    assert shared.response_id is not None

    def evaluate(dimension: str) -> tuple[str, StatefulChatResult]:
        result = judge.evaluate_branch(
            previous_response_id=shared.response_id,
            user_text=build_dimension_branch_prompt(profile, dimension),
            label=dimension,
            progress=progress,
        )
        return dimension, result

    max_workers = min(concurrency, len(pending))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_dimension = {
            executor.submit(evaluate, dimension): dimension
            for dimension in pending
        }
        for future in as_completed(future_to_dimension):
            dimension = future_to_dimension[future]
            state = checkpoint["dimensions"][dimension]
            try:
                _, response = future.result()
                extracted = extract_json_from_response(response.message)
                fixed = (
                    fix_score_json(extracted, dimension)
                    if extracted is not None
                    else None
                )
                state.update(
                    {
                        "request_status": "completed",
                        "parse_status": "parsed" if fixed is not None else "parse_failed",
                        "raw_response": response.message,
                        "reasoning_response": response.reasoning,
                        "inference_stats": response.stats,
                        "score_json": fixed,
                        "repair_applied": extracted is not None and fixed != extracted,
                        "error": None,
                    }
                )
            except Exception as exc:
                print(f"    [{dimension}] failed: {type(exc).__name__}: {exc}")
                state.update(
                    {
                        "request_status": "request_failed",
                        "parse_status": "not_started",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
            checkpoint["updated_at"] = utc_now()
            store.write_checkpoint(checkpoint)

    result = build_result_record(checkpoint, profile)
    result["stateful_context"] = checkpoint.get("stateful_context")
    return result


def parse_stateful_extra_body(raw: str | None) -> dict[str, Any] | None:
    if raw is None:
        return None
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("LM Studio stateful extra body must be a JSON object")
    return value
