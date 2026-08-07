#!/usr/bin/env python3
"""Evaluate JPEG photographs through LM Studio's stateful native chat API."""

from __future__ import annotations

import argparse
import secrets
from pathlib import Path

from backends.lm_studio_model_info import detect_parallel_limit
from real_photo.profile import ALL_DIMENSIONS, RealPhotoProfile
from real_photo.runner import RealPhotoRunSettings
from real_photo.stateful_runner import (
    StatefulLMStudioSettings,
    parse_stateful_extra_body,
    run_stateful_real_photo_evaluation,
)


REASONING_CHOICES = ("off", "low", "medium", "high", "on")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Process each JPEG once into a stored LM Studio conversation, then "
            "evaluate selected dimensions as bounded concurrent branches."
        )
    )
    parser.add_argument("--folder", required=True, type=Path)
    parser.add_argument("--sample-count", type=int, default=10)
    parser.add_argument(
        "--sample-seed",
        type=int,
        default=None,
        help=(
            "Deterministic image-sampling seed. If omitted, generate a fresh "
            "64-bit seed from OS entropy and record it."
        ),
    )
    parser.add_argument("--no-recursive", action="store_true")
    parser.add_argument("--run-dir", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=Path("local/runs"))
    parser.add_argument("--max-long-edge", type=int, default=1024)
    parser.add_argument("--no-html-report", action="store_true")

    selection = parser.add_argument_group("evaluation selection")
    selection.add_argument(
        "--dimension",
        action="append",
        choices=ALL_DIMENSIONS,
        default=None,
        help="Evaluate one stock L1 dimension; repeat to select several.",
    )
    selection.add_argument(
        "--all-dimensions",
        action="store_true",
        help="Evaluate all five stock Qwen L1 dimensions.",
    )
    selection.add_argument(
        "--no-evidence",
        action="store_true",
        help="Request the original score-only JSON shape.",
    )

    lm = parser.add_argument_group("LM Studio stateful native chat")
    lm.add_argument("--model", required=True)
    lm.add_argument(
        "--lm-studio-base-url",
        default="http://localhost:1234/v1",
        help="Server root, /v1 URL, or /api/v1 URL.",
    )
    lm.add_argument("--lm-studio-timeout", type=float, default=900.0)
    lm.add_argument("--max-new-tokens", type=int, default=4096)
    lm.add_argument("--lm-studio-temperature", type=float, default=0.0)
    lm.add_argument("--lm-studio-top-k", type=int, default=1)
    lm.add_argument("--lm-studio-top-p", type=float, default=1.0)
    lm.add_argument("--lm-studio-repeat-penalty", type=float, default=1.05)
    lm.add_argument(
        "--concurrency",
        type=int,
        default=None,
        help=(
            "Maximum branch requests simultaneously in flight. If omitted, read "
            "loaded_instances[].config.parallel from LM Studio's native model-list "
            "API. Detection failure falls back safely to 1."
        ),
    )
    lm.add_argument(
        "--reasoning",
        choices=REASONING_CHOICES,
        default="on",
        help="Reasoning mode for dimension branches (default: on).",
    )
    lm.add_argument(
        "--base-reasoning",
        choices=REASONING_CHOICES,
        default="off",
        help="Reasoning mode for the shared-context READY request (default: off).",
    )
    lm.add_argument(
        "--base-max-output-tokens",
        type=int,
        default=8,
        help="Output ceiling for the shared-context READY response (default: 8).",
    )
    lm.add_argument(
        "--context-length",
        type=int,
        default=None,
        help="Optional native /api/v1/chat context_length.",
    )
    lm.add_argument(
        "--no-stream-progress",
        action="store_true",
        help="Disable SSE progress and use one JSON response per request.",
    )
    lm.add_argument(
        "--lm-studio-image-format",
        choices=("PNG", "JPEG", "WEBP"),
        default="PNG",
    )
    lm.add_argument(
        "--lm-studio-extra-body-json",
        default=None,
        help="Optional JSON object merged into every native chat request.",
    )
    return parser


def resolve_sample_seed(explicit_seed: int | None) -> int:
    return explicit_seed if explicit_seed is not None else secrets.randbits(64)


def resolve_dimensions(args: argparse.Namespace) -> tuple[str, ...]:
    if args.all_dimensions and args.dimension:
        raise ValueError("Use either --all-dimensions or repeated --dimension, not both")
    if args.all_dimensions:
        return tuple(ALL_DIMENSIONS)
    if args.dimension:
        return tuple(dict.fromkeys(args.dimension))
    return ("Quality", "Aesthetics", "Creative Generation")


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
    sample_seed = resolve_sample_seed(args.sample_seed)
    if args.sample_seed is None:
        print(f"Generated image-sampling seed: {sample_seed}")

    dimensions = resolve_dimensions(args)
    concurrency = resolve_concurrency(
        args.concurrency,
        model=args.model,
        base_url=args.lm_studio_base_url,
    )
    extra_body = parse_stateful_extra_body(args.lm_studio_extra_body_json)
    profile = RealPhotoProfile(
        dimensions=dimensions,
        include_evidence=not args.no_evidence,
    )

    run_dir = run_stateful_real_photo_evaluation(
        settings=RealPhotoRunSettings(
            source_folder=args.folder,
            sample_count=args.sample_count,
            sample_seed=sample_seed,
            recursive=not args.no_recursive,
            max_long_edge=args.max_long_edge,
            html_report=not args.no_html_report,
        ),
        lm_studio=StatefulLMStudioSettings(
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
            stream_progress=not args.no_stream_progress,
            concurrency=concurrency,
            extra_body=extra_body,
        ),
        run_dir=args.run_dir,
        output_root=args.output_root,
        profile=profile,
    )

    print(f"Run directory: {run_dir}")
    print(f"Run metadata: {run_dir / 'run.json'}")
    print(f"Results: {run_dir / 'results.jsonl'}")
    print(f"Facet scores: {run_dir / 'facet-scores.csv'}")
    print(f"Aggregate scores: {run_dir / 'aggregate-scores.csv'}")
    report = run_dir / "report.html"
    if report.exists():
        print(f"HTML report: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
