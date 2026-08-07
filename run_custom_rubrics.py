#!/usr/bin/env python3
"""Evaluate one real photograph with versioned custom rubric packs."""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backends.lm_studio_model_info import detect_parallel_limit
from backends.lm_studio_stateful_backend import StatefulLMStudioJudge
from score_utils import extract_json_from_response

from real_photo.custom_rubrics import (
    build_custom_dimension_prompt,
    load_custom_rubric,
    parse_custom_dimension_response,
)
from real_photo.images import load_real_photo
from real_photo.profile import RealPhotoProfile
from real_photo.sampling import sha256_file
from real_photo.stateful_runner import ConsoleProgress, build_shared_context_prompt


REASONING_CHOICES = ("off", "low", "medium", "high", "on")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Process one JPEG into a stateful LM Studio context and evaluate every "
            "dimension in one or more custom rubric JSON packs."
        )
    )
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument(
        "--rubric",
        required=True,
        action="append",
        type=Path,
        help="Custom rubric JSON path; repeat to combine packs in one experiment.",
    )
    parser.add_argument("--model", required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("local/custom-runs"))
    parser.add_argument("--max-long-edge", type=int, default=1024)
    parser.add_argument(
        "--concurrency",
        type=int,
        default=None,
        help=(
            "Maximum branch requests simultaneously in flight. If omitted, "
            "detect loaded_instances[].config.parallel from LM Studio; detection "
            "failure falls back safely to 1."
        ),
    )
    parser.add_argument("--lm-studio-base-url", default="http://localhost:1234/v1")
    parser.add_argument("--lm-studio-timeout", type=float, default=900.0)
    parser.add_argument("--max-new-tokens", type=int, default=4096)
    parser.add_argument("--lm-studio-temperature", type=float, default=0.0)
    parser.add_argument("--lm-studio-top-k", type=int, default=1)
    parser.add_argument("--lm-studio-top-p", type=float, default=1.0)
    parser.add_argument("--lm-studio-repeat-penalty", type=float, default=1.05)
    parser.add_argument("--reasoning", choices=REASONING_CHOICES, default="on")
    parser.add_argument("--base-reasoning", choices=REASONING_CHOICES, default="off")
    parser.add_argument("--base-max-output-tokens", type=int, default=8)
    parser.add_argument("--context-length", type=int, default=None)
    parser.add_argument("--no-evidence", action="store_true")
    parser.add_argument("--no-stream-progress", action="store_true")
    parser.add_argument(
        "--lm-studio-image-format",
        choices=("PNG", "JPEG", "WEBP"),
        default="PNG",
    )
    return parser


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_concurrency(
    explicit: int | None,
    *,
    model: str,
    base_url: str,
) -> int:
    if explicit is not None:
        if explicit < 1:
            raise ValueError("--concurrency must be at least 1")
        print(f"Using explicit concurrency: {explicit}")
        return explicit

    detection = detect_parallel_limit(model=model, base_url=base_url)
    if detection.parallel is not None:
        print(
            "Detected LM Studio Max Concurrent Predictions: "
            f"{detection.parallel} (instance {detection.instance_id})"
        )
        return detection.parallel

    print(
        "Could not detect LM Studio Max Concurrent Predictions; using safe "
        f"concurrency 1. Detection detail: {detection.error}"
    )
    return 1


def main() -> int:
    args = build_parser().parse_args()
    concurrency = resolve_concurrency(
        args.concurrency,
        model=args.model,
        base_url=args.lm_studio_base_url,
    )

    packs = [load_custom_rubric(path) for path in args.rubric]
    image_path = args.image.expanduser().resolve()
    image, preparation = load_real_photo(
        image_path,
        max_long_edge=args.max_long_edge,
    )
    profile = RealPhotoProfile(
        dimensions=("Quality",),
        include_evidence=not args.no_evidence,
    )
    judge = StatefulLMStudioJudge(
        model=args.model,
        base_url=args.lm_studio_base_url,
        max_output_tokens=args.max_new_tokens,
        temperature=args.lm_studio_temperature,
        top_k=args.lm_studio_top_k,
        top_p=args.lm_studio_top_p,
        repeat_penalty=args.lm_studio_repeat_penalty,
        timeout_seconds=args.lm_studio_timeout,
        image_format=args.lm_studio_image_format,
        reasoning=args.reasoning,
        base_reasoning=args.base_reasoning,
        base_max_output_tokens=args.base_max_output_tokens,
        context_length=args.context_length,
        stream=not args.no_stream_progress,
    )
    progress = ConsoleProgress(enabled=not args.no_stream_progress)

    try:
        print(f"Preparing shared image context: {image_path.name}")
        shared = judge.create_shared_context(
            system_prompt=profile.application_system_prompt,
            user_text=build_shared_context_prompt(profile),
            image=image,
            label="Shared context",
            progress=progress,
        )
    finally:
        image.close()

    assert shared.response_id is not None
    tasks = [
        (pack, dimension)
        for pack in packs
        for dimension in pack.dimensions
    ]
    started = time.perf_counter()
    results: dict[str, Any] = {}

    def evaluate(pack, dimension):
        label = f"{pack.identity} / {dimension.label}"
        response = judge.evaluate_branch(
            previous_response_id=shared.response_id,
            user_text=build_custom_dimension_prompt(
                pack,
                dimension,
                include_evidence=not args.no_evidence,
                stateful_branch=True,
            ),
            label=label,
            progress=progress,
        )
        parsed = extract_json_from_response(response.message)
        normalized = parse_custom_dimension_response(
            pack,
            dimension,
            parsed,
        )
        return pack, dimension, response, normalized, parsed is not None

    with ThreadPoolExecutor(max_workers=min(concurrency, len(tasks))) as executor:
        futures = {
            executor.submit(evaluate, pack, dimension): (pack, dimension)
            for pack, dimension in tasks
        }
        for future in as_completed(futures):
            pack, dimension = futures[future]
            key = f"{pack.identity}:{dimension.id}"
            try:
                _, _, response, normalized, parsed = future.result()
                results[key] = {
                    "status": "completed" if parsed else "parse_failed",
                    "raw_response": response.message,
                    "reasoning_response": response.reasoning,
                    "inference_stats": response.stats,
                    "normalized": normalized,
                    "error": None,
                }
                score = normalized["score"]
                score_text = "N/A" if score is None else f"{score:.2f}"
                print(f"{key}: {score_text}")
            except Exception as exc:
                results[key] = {
                    "status": "request_failed",
                    "raw_response": None,
                    "reasoning_response": None,
                    "inference_stats": None,
                    "normalized": None,
                    "error": f"{type(exc).__name__}: {exc}",
                }
                print(f"{key}: failed · {type(exc).__name__}: {exc}")

    elapsed = time.perf_counter() - started
    output_root = args.output_dir.expanduser().resolve()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    run_dir = output_root / f"{timestamp}-custom-rubrics"
    run_dir.mkdir(parents=True, exist_ok=False)
    payload = {
        "schema_version": 1,
        "classification": "custom_experimental",
        "created_at": utc_now(),
        "image": {
            "source_path": str(image_path),
            "source_uri": image_path.as_uri(),
            "image_id": sha256_file(image_path),
            "preparation": preparation.to_dict(),
        },
        "model": {
            "id": args.model,
            "runtime": "lm-studio",
            "api_mode": "stateful_native_chat_branching",
            "request_seed": None,
        },
        "execution": {
            "concurrency": concurrency,
            "stream_progress": not args.no_stream_progress,
            "elapsed_branch_seconds": elapsed,
            "shared_context": {
                "response_id": shared.response_id,
                "message": shared.message,
                "reasoning": shared.reasoning,
                "stats": shared.stats,
            },
        },
        "rubric_packs": [pack.to_metadata() for pack in packs],
        "results": results,
    }
    output_path = run_dir / "result.json"
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Custom rubric result: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
