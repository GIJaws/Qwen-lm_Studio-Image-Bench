#!/usr/bin/env python3
"""Measure stateless LM Studio request throughput with bounded concurrency."""

from __future__ import annotations

import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from backends.lm_studio_backend import LMStudioJudge
from real_photo.images import load_real_photo
from real_photo.profile import ALL_DIMENSIONS, RealPhotoProfile, build_real_photo_user_prompt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Send the stock L1 dimension requests for one JPEG through LM Studio "
            "using locally bounded worker counts. This does not create run outputs."
        )
    )
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--model", required=True)
    parser.add_argument(
        "--workers",
        action="append",
        type=int,
        default=None,
        help="Worker count to test; repeat this flag. Default: 1 and 4.",
    )
    parser.add_argument("--lm-studio-base-url", default="http://localhost:1234/v1")
    parser.add_argument("--lm-studio-timeout", type=float, default=900.0)
    parser.add_argument("--max-new-tokens", type=int, default=4096)
    parser.add_argument("--max-long-edge", type=int, default=1024)
    parser.add_argument(
        "--dimension",
        action="append",
        choices=ALL_DIMENSIONS,
        default=None,
        help="Dimension to include; repeat. Default: all five stock dimensions.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    workers = args.workers or [1, 4]
    if any(value < 1 for value in workers):
        raise ValueError("--workers values must be at least 1")
    dimensions = tuple(dict.fromkeys(args.dimension or ALL_DIMENSIONS))
    profile = RealPhotoProfile(
        dimensions=dimensions,
        include_evidence=False,
    )
    image, preparation = load_real_photo(
        args.image,
        max_long_edge=args.max_long_edge,
    )
    try:
        print(
            f"Image prepared as {preparation.prepared_width}x"
            f"{preparation.prepared_height}; {len(dimensions)} requests per test"
        )
        for worker_count in workers:
            judge = LMStudioJudge(
                model=args.model,
                base_url=args.lm_studio_base_url,
                max_new_tokens=args.max_new_tokens,
                timeout_seconds=args.lm_studio_timeout,
            )
            started = time.perf_counter()
            failures = []
            with ThreadPoolExecutor(
                max_workers=min(worker_count, len(dimensions))
            ) as executor:
                futures = {
                    executor.submit(
                        judge.generate_batch,
                        [
                            {
                                "system_prompt": profile.application_system_prompt,
                                "user_text": build_real_photo_user_prompt(
                                    profile,
                                    dimension,
                                ),
                                "image": image,
                            }
                        ],
                    ): dimension
                    for dimension in dimensions
                }
                for future in as_completed(futures):
                    dimension = futures[future]
                    try:
                        future.result()
                        print(f"  workers={worker_count} · {dimension} complete")
                    except Exception as exc:
                        failures.append((dimension, exc))
                        print(
                            f"  workers={worker_count} · {dimension} failed: "
                            f"{type(exc).__name__}: {exc}"
                        )
            elapsed = time.perf_counter() - started
            print(
                f"workers={worker_count}: {elapsed:.2f}s wall time · "
                f"{len(dimensions) - len(failures)}/{len(dimensions)} successful"
            )
    finally:
        image.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
