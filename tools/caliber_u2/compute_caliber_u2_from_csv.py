#!/usr/bin/env python3
"""
Standalone: compute Caliber Uniformity (U2) and Maturity from an MNV batch CSV.

Inserts columns immediately to the right of existing Caliber Uniformity Score /
Maturity Index (or appends if missing):

  - Caliber Uniformity Score (U2)
  - Maturity Index (U2)   [= 50 + (U2 − Network Complexity) / 2]

Usage
-----
  python scripts/compute_caliber_u2_from_csv.py INPUT.csv [-o OUTPUT.csv]
  python scripts/compute_caliber_u2_from_csv.py INPUT.csv --inplace

Size class is inferred from the File column (3x3 → small_3mm, Optovue → small,
PlexElite → large). Override with --size-class.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from src.core.caliber_u2 import (  # noqa: E402
    calculate_caliber_u2_score,
    calculate_maturity_index,
    infer_size_class_from_filename,
    load_caliber_u2_device_ref,
)

NV_COL = "NV Diameter (CV)"
DIL_COL = "Dilated vessel (%)"
COMPLEXITY_COL = "Network Complexity Score"
CALIBER_COL = "Caliber Uniformity Score"
MATURITY_COL = "Maturity Index"
U2_COL = "Caliber Uniformity Score (U2)"
MAT_U2_COL = "Maturity Index (U2)"
FILE_COL = "File"


def _read_csv(path: Path) -> tuple[List[str], List[Dict[str, str]]]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise SystemExit(f"No header in {path}")
        fieldnames = list(reader.fieldnames)
        rows = [dict(r) for r in reader]
    return fieldnames, rows


def _insert_after(fieldnames: List[str], after: str, new_cols: List[str]) -> List[str]:
    out = list(fieldnames)
    for col in new_cols:
        if col in out:
            out.remove(col)
    if after in out:
        i = out.index(after) + 1
        for j, col in enumerate(new_cols):
            out.insert(i + j, col)
    else:
        out.extend(new_cols)
    return out


def process_rows(
    fieldnames: List[str],
    rows: List[Dict[str, str]],
    size_class_override: Optional[str] = None,
) -> tuple[List[str], List[Dict[str, Any]]]:
    ref = load_caliber_u2_device_ref()
    if ref is None:
        raise SystemExit(
            "Could not load resources/reference_metrics/caliber_u2_device_ref.json"
        )

    for col in (NV_COL, DIL_COL, COMPLEXITY_COL):
        if col not in fieldnames:
            raise SystemExit(f"Missing required column: {col}")

    out_fields = list(fieldnames)
    # Insert U2 next to Caliber; Maturity U2 next to Maturity
    if CALIBER_COL in out_fields:
        out_fields = _insert_after(out_fields, CALIBER_COL, [U2_COL])
    else:
        out_fields.append(U2_COL)
    if MATURITY_COL in out_fields:
        out_fields = _insert_after(out_fields, MATURITY_COL, [MAT_U2_COL])
    else:
        out_fields.append(MAT_U2_COL)

    out_rows: List[Dict[str, Any]] = []
    n_ok = 0
    for row in rows:
        r = dict(row)
        fname = r.get(FILE_COL, "")
        sc = size_class_override or infer_size_class_from_filename(fname)
        try:
            nv = float(r.get(NV_COL, ""))
            dil = float(r.get(DIL_COL, ""))
            cx = float(r.get(COMPLEXITY_COL, ""))
        except (TypeError, ValueError):
            r[U2_COL] = ""
            r[MAT_U2_COL] = ""
            out_rows.append(r)
            continue
        u2, _ = calculate_caliber_u2_score(nv, dil, size_class=sc, ref=ref)
        mat = calculate_maturity_index(u2, cx)
        r[U2_COL] = "" if u2 != u2 else f"{u2:.6g}"  # NaN check
        r[MAT_U2_COL] = "" if mat != mat else f"{mat:.6g}"
        if u2 == u2:
            n_ok += 1
        out_rows.append(r)

    print(f"U2 computed for {n_ok}/{len(rows)} rows", file=sys.stderr)
    return out_fields, out_rows


def _write_csv(path: Path, fieldnames: List[str], rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Insert Caliber U2 + Maturity U2 into MNV CSV")
    p.add_argument("input_csv", type=Path)
    p.add_argument("-o", "--output", type=Path, default=None)
    p.add_argument("--inplace", action="store_true", help="Overwrite input CSV")
    p.add_argument(
        "--size-class",
        choices=["small", "large", "small_3mm"],
        default=None,
        help="Force size_class for all rows (default: infer from File)",
    )
    args = p.parse_args(argv)

    if not args.input_csv.is_file():
        raise SystemExit(f"Not found: {args.input_csv}")

    fieldnames, rows = _read_csv(args.input_csv)
    out_fields, out_rows = process_rows(fieldnames, rows, args.size_class)

    if args.inplace:
        out_path = args.input_csv
    elif args.output is not None:
        out_path = args.output
    else:
        out_path = args.input_csv.with_name(args.input_csv.stem + "_u2.csv")

    _write_csv(out_path, out_fields, out_rows)
    print(f"Wrote {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
