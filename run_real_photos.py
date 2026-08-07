#!/usr/bin/env python3
"""Evaluate a sample of local JPEG photographs through LM Studio."""

from __future__ import annotations

import argparse
import secrets
from pathlib import Path

from real_photo.profile import ALL_DIMENSIONS, DEFAULT_REAL_PHOTO_DIMENSIONS, RealPhotoProfile
from real_photo.runner import (
    LMStudioSettings,
    RealPhotoRunSettings,
    parse_extra_body,
    run_real_photo_evaluation,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Sample up to N JPEGs from a folder and evaluate them with the stock "
            "Qwen-Image-Bench rubric through LM Studio."
        )
    )
    parser.add_argument("--folder", required=True, type=Path, help="Source JPEG folder")
    parser.add_argument(
        "--sample-count",
        type=int,
        default=10,
        help="Maximum number of JPEGs to sample (default: 10)",
    )
    parser.add_argument(
        "--sample-seed",
        type=int,
        default=None,
        help=(
            "Deterministic image-sampling seed. If omitted, a fresh 64-bit seed "
            "is generated from OS entropy and recorded in the run manifest."
        ),
    )
    parser.add_argument(
        "--dimension",
        dest="dimensions",
        action="append",
        choices=ALL_DIMENSIONS,
        default=None,
        help=(
            "Stock Qwen L1 dimension to evaluate. Repeat to select multiple. "
            "If omitted, defaults to: " + ", ".join(DEFAULT_REAL_PHOTO_DIMENSIONS)
        ),
    )
    parser.add_argument(
        "--all-dimensions",
        action="store_true",
        help="Evaluate all five stock Qwen L1 dimensions",
    )
    parser.add_argument(
        "--no-evidence",
        action="store_true",
        help=(
            "Request the original score-only JSON shape instead of adding one "
            "brief evidence string per facet"
        ),
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="Do not search subfolders",
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=None,
        help="Explicit run directory; an existing compatible directory resumes",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("local/runs"),
        help="Root for generated run directories (default: local/runs)",
    )
    parser.add_argument(
        "--max-long-edge",
        type=int,
        default=1024,
        help="Aspect-preserving model-input long edge (default: 1024)",
    )
    parser.add_argument(
        "--no-html-report",
        action="store_true",
        help="Skip generation of the minimal static HTML report",
    )

    parser.add_argument(
        "--model",
        required=True,
        help="Model identifier exposed by LM Studio",
    )
    parser.add_argument(
        "--lm-studio-base-url",
        default="http://localhost:1234/v1",
    )
    parser.add_argument("--lm-studio-timeout", type=float, default=300.0)
    parser.add_argument("--max-new-tokens", type=int, default=4096)
    parser.add_argument("--lm-studio-temperature", type=float, default=0.0)
    parser.add_argument("--lm-studio-top-k", type=int, default=1)
    parser.add_argument("--lm-studio-top-p", type=float, default=1.0)
    parser.add_argument("--lm-studio-repeat-penalty", type=float, default=1.05)
    parser.add_argument("--lm-studio-seed", type=int, default=42)
    parser.add_argument("--lm-studio-no-seed", action="store_true")
    parser.add_argument(
        "--lm-studio-image-format",
        choices=("PNG", "JPEG", "WEBP"),
        default="PNG",
    )
    parser.add_argument(
        "--lm-studio-extra-body-json",
        default=None,
        help="Optional JSON object merged into each LM Studio request body",
    )
    return parser


def resolve_sample_seed(explicit_seed: int | None) -> int:
    """Return the requested seed or generate a fresh recorded sampling seed."""
    return explicit_seed if explicit_seed is not None else secrets.randbits(64)


def resolve_dimensions(
    explicit_dimensions: list[str] | None,
    *,
    use_all_dimensions: bool,
) -> tuple[str, ...]:
    """Resolve one homogeneous set of stock Qwen L1 dimensions for the run."""
    if explicit_dimensions and use_all_dimensions:
        raise ValueError("--dimension and --all-dimensions cannot be used together")
    if use_all_dimensions:
        return tuple(ALL_DIMENSIONS)
    if explicit_dimensions:
        return tuple(dict.fromkeys(explicit_dimensions))
    return tuple(DEFAULT_REAL_PHOTO_DIMENSIONS)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    extra_body = parse_extra_body(args.lm_studio_extra_body_json)
    lm_seed = None if args.lm_studio_no_seed else args.lm_studio_seed
    sample_seed = resolve_sample_seed(args.sample_seed)

    try:
        dimensions = resolve_dimensions(
            args.dimensions,
            use_all_dimensions=args.all_dimensions,
        )
    except ValueError as exc:
        parser.error(str(exc))

    if args.sample_seed is None:
        print(f"Generated image-sampling seed: {sample_seed}")

    profile_name = "Real photograph, stock Qwen rubric, no reference text"
    if dimensions != DEFAULT_REAL_PHOTO_DIMENSIONS:
        profile_name += " · " + ", ".join(dimensions)
    if not args.no_evidence:
        profile_name += " · per-facet evidence"

    profile = RealPhotoProfile(
        name=profile_name,
        dimensions=dimensions,
        include_evidence=not args.no_evidence,
    )

    run_dir = run_real_photo_evaluation(
        settings=RealPhotoRunSettings(
            source_folder=args.folder,
            sample_count=args.sample_count,
            sample_seed=sample_seed,
            recursive=not args.no_recursive,
            max_long_edge=args.max_long_edge,
            html_report=not args.no_html_report,
        ),
        lm_studio=LMStudioSettings(
            model=args.model,
            base_url=args.lm_studio_base_url,
            max_new_tokens=args.max_new_tokens,
            temperature=args.lm_studio_temperature,
            top_k=args.lm_studio_top_k,
            top_p=args.lm_studio_top_p,
            repeat_penalty=args.lm_studio_repeat_penalty,
            seed=lm_seed,
            timeout_seconds=args.lm_studio_timeout,
            image_format=args.lm_studio_image_format,
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
