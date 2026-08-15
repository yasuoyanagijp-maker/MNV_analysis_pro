#!/usr/bin/env python3
"""
Recompute the full ImageJ MNV export using Method B ColorMask as ROI,
then run the existing dual-read RPD adoption pipeline.

ColorMask is gated by the hand-drawn ROI used for RGB visualization.
Export masks on disk match MNV_batch_20260815_094130 (not 092019).
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from ariake_octa.mnv.color_mask import extract_color_mask  # noqa: E402
from tools.reading_center_rpd.compute_adopted_from_dual_csv import (  # noqa: E402
    MAJOR_METRICS,
    META_COLS,
    is_numeric_column,
    rpd_pct,
    to_float,
)
from tools.roi_visualization_boundary.lib.cases import (  # noqa: E402
    CASE_LABELS,
    G1_DIR,
    G2_DIR,
    INTEGRATED_DIR,
    SCALE_MM,
)
from tools.roi_visualization_boundary.lib.io import (  # noqa: E402
    detect_vessels as _detect_vessels,
    find_image as _find_image,
    find_mask as _find_mask,
    load_gray as _load_gray,
    load_roi as _load_roi,
    make_rgb as _make_rgb,
)
from src.core.mnv_pipeline import FILTER_PARAMS_SMALL, MNVPipeline  # noqa: E402
from src.utils.dual_grader_merge import match_stem, merge_dual_grader_csvs  # noqa: E402
from src.utils.mnv_imagej_csv import (  # noqa: E402
    _metrics_to_imagej_row,
    build_csv_bytes_from_imagej_rows,
)

ADOPTED_092317 = INTEGRATED_DIR / "MNV_integrated_20260815_092317_adopted_values.csv"
RECHECK_092317 = INTEGRATED_DIR / "MNV_integrated_20260815_092317_recheck_list.csv"
ADOPTED_094445 = INTEGRATED_DIR / "MNV_integrated_20260815_094445_adopted_values.csv"
RECHECK_094445 = INTEGRATED_DIR / "MNV_integrated_20260815_094445_recheck_list.csv"

G1_CSV_092019 = G1_DIR / "MNV_batch_20260815_092019.csv"
G2_CSV_092019 = G2_DIR / "MNV_batch_20260815_092019.csv"
G1_CSV_094130 = G1_DIR / "MNV_batch_20260815_094130.csv"
G2_CSV_094130 = G2_DIR / "MNV_batch_20260815_094130.csv"

OUT_DIR = Path(__file__).resolve().parent / "adoption"


def _read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _index_by_stem(rows: List[Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    return {match_stem(r.get("File", "") or r.get("ID", "")): r for r in rows}


def _case_id(filename: str) -> str:
    for token, label in CASE_LABELS.items():
        if token in filename:
            return label
    return match_stem(filename)


def _is_na(value: Any) -> bool:
    return to_float(value) is None and str(value or "").strip().upper() in {
        "NA",
        "NAN",
        "NULL",
        "",
    }


def _numeric_na_count(
    rows: List[Dict[str, str]],
    fieldnames: List[str],
    cols: Optional[List[str]] = None,
) -> Tuple[int, Dict[str, int]]:
    if cols is None:
        cols = [c for c in fieldnames if c not in META_COLS]
    by_col: Dict[str, int] = {}
    total = 0
    for row in rows:
        for col in cols:
            if col not in row:
                continue
            if str(row.get(col, "")).strip().upper() == "NA":
                by_col[col] = by_col.get(col, 0) + 1
                total += 1
    return total, by_col


def _recompute_one(
    stem: str,
    export_root: Path,
    source_row: Dict[str, str],
    idx: int,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    image_path = _find_image(export_root, stem)
    mask_path = _find_mask(export_root, stem)
    image = _load_gray(image_path)
    roi = _load_roi(mask_path, image.shape)
    binary = _detect_vessels(image)
    rgb = _make_rgb(image, binary, roi)
    reference = np.logical_and(binary > 0, roi > 0)
    choice = extract_color_mask(image, rgb, reference)
    color_u8 = (choice.mask.astype(np.uint8)) * 255

    pipeline = MNVPipeline(
        scale_mm=SCALE_MM,
        save_stages=False,
        verbose=False,
        enable_roi_refinement=False,
        filter_params=dict(FILTER_PARAMS_SMALL),
    )
    metrics = pipeline.analyze(str(image_path), roi_mask=color_u8)
    row = _metrics_to_imagej_row(
        source_row.get("File") or image_path.name,
        idx,
        str(source_row.get("Quality of analysis") or "unknown"),
        True,
        metrics,
    )
    # Keep the source session's qualitative labels so adoption of
    # Subtype/Pathophysiology is not confounded by a re-classification.
    for col in ("Subtype", "Pathophysiology"):
        if source_row.get(col):
            row[col] = source_row[col]
    info = {
        "stem": stem,
        "case": _case_id(source_row.get("File", stem)),
        "n_roi": int((roi > 0).sum()),
        "n_color": int(choice.mask.sum()),
        "dice": float(choice.dice),
        "mnv_b": float(metrics.get("mnv_area_mm2") or 0.0),
        "vsl_b": float(metrics.get("vessel_area_mm2") or 0.0),
        "dens_b": float(metrics.get("vessel_density") or 0.0),
    }
    return row, info


def _write_grader_csv(
    rows: List[Dict[str, Any]],
    analyst: str,
    session_id: str,
    path: Path,
) -> None:
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    meta = {
        "Analyst": analyst,
        "Started At": now,
        "Ended At": now,
        "Duration Sec": "",
        "Session ID": session_id,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(build_csv_bytes_from_imagej_rows(rows, meta))


def _compare_adopted(
    baseline_path: Path,
    method_b_path: Path,
    baseline_recheck: Path,
    method_b_recheck: Path,
    label: str,
) -> Dict[str, Any]:
    base_rows = _read_csv(baseline_path)
    b_rows = _read_csv(method_b_path)
    base_idx = _index_by_stem(base_rows)
    b_idx = _index_by_stem(b_rows)
    fieldnames = list(base_rows[0].keys()) if base_rows else []
    numeric_cols = [
        c
        for c in fieldnames
        if c not in META_COLS and is_numeric_column(c, base_rows, b_rows)
    ]

    base_na, base_by = _numeric_na_count(base_rows, fieldnames, numeric_cols)
    b_na, b_by = _numeric_na_count(b_rows, fieldnames, numeric_cols)
    base_major, base_major_by = _numeric_na_count(base_rows, fieldnames, MAJOR_METRICS)
    b_major, b_major_by = _numeric_na_count(b_rows, fieldnames, MAJOR_METRICS)

    base_re = _read_csv(baseline_recheck)
    b_re = _read_csv(method_b_recheck)

    per_metric: List[Dict[str, Any]] = []
    for stem, brow in b_idx.items():
        arow = base_idx.get(stem)
        if not arow:
            continue
        case = _case_id(brow.get("File", stem))
        for col in MAJOR_METRICS:
            av = to_float(arow.get(col))
            bv = to_float(brow.get(col))
            per_metric.append(
                {
                    "baseline": label,
                    "case": case,
                    "metric": col,
                    "adopted_A": av,
                    "adopted_B": bv,
                    "A_is_NA": av is None
                    and str(arow.get(col, "")).strip().upper() == "NA",
                    "B_is_NA": bv is None
                    and str(brow.get(col, "")).strip().upper() == "NA",
                }
            )

    return {
        "label": label,
        "baseline_adopted": str(baseline_path),
        "method_b_adopted": str(method_b_path),
        "recheck_cells_A": len(base_re),
        "recheck_cells_B": len(b_re),
        "recheck_files_A": len({r.get("File") for r in base_re}),
        "recheck_files_B": len({r.get("File") for r in b_re}),
        "recheck_by_metric_A": {
            m: sum(1 for r in base_re if r.get("Metric") == m) for m in MAJOR_METRICS
        },
        "recheck_by_metric_B": {
            m: sum(1 for r in b_re if r.get("Metric") == m) for m in MAJOR_METRICS
        },
        "major_na_A": base_major,
        "major_na_B": b_major,
        "major_na_by_A": base_major_by,
        "major_na_by_B": b_major_by,
        "numeric_na_A": base_na,
        "numeric_na_B": b_na,
        "numeric_na_by_A": base_by,
        "numeric_na_by_B": b_by,
        "per_metric": per_metric,
        "recheck_rows_B": b_re,
    }


def _grader_rpd_table(
    g1_rows: List[Dict[str, str]],
    g2_rows: List[Dict[str, str]],
    metrics: List[str],
) -> List[Dict[str, Any]]:
    i1 = _index_by_stem(g1_rows)
    i2 = _index_by_stem(g2_rows)
    out: List[Dict[str, Any]] = []
    for stem, r1 in i1.items():
        r2 = i2.get(stem)
        if not r2:
            continue
        case = _case_id(r1.get("File", stem))
        for col in metrics:
            a, b = to_float(r1.get(col)), to_float(r2.get(col))
            rpd = rpd_pct(a, b) if a is not None and b is not None else None
            out.append(
                {
                    "case": case,
                    "metric": col,
                    "g1": a,
                    "g2": b,
                    "rpd": rpd,
                    "adopt": rpd is not None and rpd <= 20.0,
                }
            )
    return out


def main() -> int:
    g1_src = _read_csv(G1_CSV_094130)
    g2_src = _read_csv(G2_CSV_094130)
    g1_idx = _index_by_stem(g1_src)
    g2_idx = _index_by_stem(g2_src)

    print("Export masks match 094130 MNV Area (not 092019).")
    print("Method B ColorMask is therefore gated by the 094130 hand-drawn ROIs.")

    g1_rows: List[Dict[str, Any]] = []
    g2_rows: List[Dict[str, Any]] = []
    infos: List[Dict[str, Any]] = []

    for idx, row in enumerate(g1_src):
        stem = match_stem(row["File"])
        print(f"[G1] { _case_id(row['File']) }")
        out_row, info = _recompute_one(stem, G1_DIR / "export", row, idx)
        info["grader"] = "G1"
        g1_rows.append(out_row)
        infos.append(info)
        print(
            f"  ColorMask {info['n_color']} px  MNV={info['mnv_b']:.4f}  "
            f"Vsl={info['vsl_b']:.4f}  Dens={info['dens_b']:.4f}  Dice={info['dice']:.3f}"
        )

    for idx, row in enumerate(g2_src):
        stem = match_stem(row["File"])
        if stem not in g1_idx:
            print(f"[G2] skip unmatched {stem}")
            continue
        print(f"[G2] { _case_id(row['File']) }")
        out_row, info = _recompute_one(stem, G2_DIR / "export", row, idx)
        info["grader"] = "G2"
        g2_rows.append(out_row)
        infos.append(info)
        print(
            f"  ColorMask {info['n_color']} px  MNV={info['mnv_b']:.4f}  "
            f"Vsl={info['vsl_b']:.4f}  Dens={info['dens_b']:.4f}  Dice={info['dice']:.3f}"
        )

    session_id = f"methodB_colormask_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    g1_csv = OUT_DIR / "MNV_batch_methodB_g1.csv"
    g2_csv = OUT_DIR / "MNV_batch_methodB_g2.csv"
    _write_grader_csv(g1_rows, "yasuo yanagi", session_id, g1_csv)
    _write_grader_csv(g2_rows, "YY1", session_id, g2_csv)
    print(f"Wrote {g1_csv}")
    print(f"Wrote {g2_csv}")

    summary = merge_dual_grader_csvs(
        g1_csv,
        g2_csv,
        OUT_DIR,
        first_label="Grader1",
        second_label="YY",
        prefix=f"MNV_integrated_{datetime.now().strftime('%Y%m%d_%H%M%S')}_methodB",
    )
    print(f"Adopted: {summary['adopted_csv']}")
    print(f"Recheck: {summary['recheck_csv']}")
    print(f"Summary: {summary['summary_md']}")
    print(f"Method B official recheck cells: {summary['recheck_cells']}")

    cmp_092317 = _compare_adopted(
        ADOPTED_092317,
        Path(summary["adopted_csv"]),
        RECHECK_092317,
        Path(summary["recheck_csv"]),
        "092317",
    )
    cmp_094445 = _compare_adopted(
        ADOPTED_094445,
        Path(summary["adopted_csv"]),
        RECHECK_094445,
        Path(summary["recheck_csv"]),
        "094445",
    )

    g1_b = _read_csv(g1_csv)
    g2_b = _read_csv(g2_csv)
    rpd_b = _grader_rpd_table(g1_b, g2_b, MAJOR_METRICS)
    rpd_a_092019 = _grader_rpd_table(
        _read_csv(G1_CSV_092019), _read_csv(G2_CSV_092019), MAJOR_METRICS
    )
    rpd_a_094130 = _grader_rpd_table(
        _read_csv(G1_CSV_094130), _read_csv(G2_CSV_094130), MAJOR_METRICS
    )

    payload = {
        "mask_session": "094130",
        "named_integrated": "092317",
        "same_roi_session_integrated": "094445",
        "infos": infos,
        "adoption_summary": {
            "recheck_cells": summary["recheck_cells"],
            "recheck_files": summary["recheck_files"],
            "recheck_by_metric": summary["recheck_by_metric"],
            "adopted_csv": summary["adopted_csv"],
            "recheck_csv": summary["recheck_csv"],
            "summary_md": summary["summary_md"],
        },
        "vs_092317": cmp_092317,
        "vs_094445": cmp_094445,
        "rpd_method_b": rpd_b,
        "rpd_method_a_092019": rpd_a_092019,
        "rpd_method_a_094130": rpd_a_094130,
    }
    out_json = OUT_DIR / "comparison.json"
    out_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {out_json}")

    for cmp in (cmp_092317, cmp_094445):
        print(
            f"\nvs {cmp['label']}: recheck {cmp['recheck_cells_A']} -> {cmp['recheck_cells_B']}"
            f"  major NA {cmp['major_na_A']} -> {cmp['major_na_B']}"
            f"  all numeric NA {cmp['numeric_na_A']} -> {cmp['numeric_na_B']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
