#!/usr/bin/env python3
"""Regenerate the minimal static report from a stored real-photo run."""

from __future__ import annotations

import argparse
from pathlib import Path

from real_photo.report import render_minimal_report
from real_photo.storage import RunStore


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path, help="Existing real-photo run directory")
    args = parser.parse_args()

    store = RunStore(args.run_dir)
    if not store.exists():
        parser.error(f"Not a real-photo run directory: {store.run_dir}")
    run_data = store.load_run()
    manifest = store.load_manifest()
    results = store.load_results()
    store.write_report(render_minimal_report(run_data, manifest, results))
    print(store.report_html)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
