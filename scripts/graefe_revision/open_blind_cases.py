#!/usr/bin/env python3
"""Open / print paths for blind grading without copying large image files.

Usage:
  .venv/bin/python scripts/graefe_revision/open_blind_cases.py
  .venv/bin/python scripts/graefe_revision/open_blind_cases.py --blind-id B001
  .venv/bin/python scripts/graefe_revision/open_blind_cases.py --print-only
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = REPO_ROOT / "documentation" / "graefe_revision" / "grading" / "grading_manifest.csv"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--blind-id", type=str, default=None)
    parser.add_argument("--print-only", action="store_true")
    args = parser.parse_args()

    df = pd.read_csv(args.manifest)
    if args.blind_id:
        df = df.loc[df["blind_id"] == args.blind_id]
        if df.empty:
            print(f"No row for {args.blind_id}", file=sys.stderr)
            sys.exit(1)

    for _, row in df.iterrows():
        path = Path(row["image_path"])
        print(f"{row['blind_id']}\t{path}\texists={path.is_file()}")
        if args.print_only:
            continue
        if not path.is_file():
            print(f"  SKIP missing: {path}", file=sys.stderr)
            continue
        # macOS Preview / default app; does not reveal original folder in the blind CSV
        subprocess.run(["open", str(path)], check=False)


if __name__ == "__main__":
    main()
