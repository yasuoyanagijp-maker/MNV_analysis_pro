#!/usr/bin/env python3
"""
Method B' (offline): keep fully enclosed padding holes inside the hand ROI.

ColorMask is the locked Method B mask. Padding = user_roi AND NOT ColorMask.
A padding CC (8-connect) is border-touching if it is adjacent to ~user_roi.
refined_roi = user_roi minus those border-touching CCs
            = (ColorMask ∪ enclosed padding CCs) clipped to user_roi.

Does not implement anything in the app. Does not run Method C.
Does not call MNVPipeline.analyze unless enclosed holes are material.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from ariake_octa.mnv.color_mask import extract_color_mask  # noqa: E402
from tools.reading_center_rpd.compute_adopted_from_dual_csv import (  # noqa: E402
    rpd_pct,
)
from tools.roi_visualization_boundary.lib.cases import (  # noqa: E402
    CASE_LABELS,
    G1_CSV,
    G1_DIR,
    G2_CSV,
    G2_DIR,
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
from utils.dual_grader_merge import match_stem  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent
ADOPT_PCT = 20.0
# Enough enclosed-hole area to move MNV Area RPD or 20% adoption.
# ~0.5% of ColorMask, or 50 px, whichever is larger — used only as a gate
# for whether to treat B' as distinct from B.
MATERIAL_HOLE_FRAC = 0.005
MATERIAL_HOLE_PX = 50

AREA_METRICS = (
    "MNV Area (mm2)",
    "Vsl Area (mm2)",
    "Vsl Density (Vessel Area/MNV (%))",
)


def _read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _index_by_stem(rows: List[Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    return {match_stem(r["File"]): r for r in rows}


def _case_id(filename: str) -> str:
    for token, label in CASE_LABELS.items():
        if token in filename:
            return label
    return match_stem(filename)


def _px_to_mm2(n_px: int, width: int) -> float:
    return float(n_px) * (SCALE_MM / width) ** 2


def _dice(a: np.ndarray, b: np.ndarray) -> float:
    inter = np.logical_and(a, b).sum()
    denom = a.sum() + b.sum()
    if denom == 0:
        return 1.0
    return 2.0 * inter / denom


def refine_roi(
    user_roi: np.ndarray, color_mask: np.ndarray
) -> Dict[str, Any]:
    """Return refined_roi and padding-CC counts. 8-connectivity throughout."""
    roi = user_roi.astype(bool)
    color = color_mask.astype(bool)
    padding = np.logical_and(roi, np.logical_not(color))
    exterior = np.logical_not(roi)

    kernel = np.ones((3, 3), np.uint8)
    touches_exterior = cv2.dilate(exterior.astype(np.uint8), kernel, iterations=1) > 0

    n_labels, labels = cv2.connectedComponents(
        padding.astype(np.uint8), connectivity=8
    )
    enclosed = np.zeros_like(padding, dtype=bool)
    border = np.zeros_like(padding, dtype=bool)
    n_cc_border = 0
    n_cc_enclosed = 0
    enclosed_cc_sizes: List[int] = []
    border_cc_sizes: List[int] = []

    for lab in range(1, n_labels):
        cc = labels == lab
        size = int(cc.sum())
        if np.any(np.logical_and(cc, touches_exterior)):
            border[cc] = True
            n_cc_border += 1
            border_cc_sizes.append(size)
        else:
            enclosed[cc] = True
            n_cc_enclosed += 1
            enclosed_cc_sizes.append(size)

    color_in_roi = np.logical_and(color, roi)
    refined = np.logical_and(np.logical_or(color, enclosed), roi)
    # Equivalent: roi minus border-touching padding
    refined_alt = np.logical_and(roi, np.logical_not(border))
    if not np.array_equal(refined, refined_alt):
        raise RuntimeError("refined_roi definitions disagree")

    return {
        "refined": refined,
        "padding": padding,
        "enclosed": enclosed,
        "border": border,
        "n_padding": int(padding.sum()),
        "n_padding_border": int(border.sum()),
        "n_padding_enclosed": int(enclosed.sum()),
        "n_cc_padding": int(n_labels - 1),
        "n_cc_border": n_cc_border,
        "n_cc_enclosed": n_cc_enclosed,
        "enclosed_cc_sizes": enclosed_cc_sizes,
        "n_color_in_roi": int(color_in_roi.sum()),
        "n_color_outside_roi": int(np.logical_and(color, np.logical_not(roi)).sum()),
        "max_border_cc": max(border_cc_sizes) if border_cc_sizes else 0,
        "max_enclosed_cc": max(enclosed_cc_sizes) if enclosed_cc_sizes else 0,
        "n_border_cc_ge50": int(sum(1 for s in border_cc_sizes if s >= 50)),
        "n_border_cc_ge100": int(sum(1 for s in border_cc_sizes if s >= 100)),
    }


def run_one(
    stem: str,
    grader: str,
    export_root: Path,
    csv_row: Dict[str, str],
) -> Dict[str, Any]:
    image_path = _find_image(export_root, stem)
    mask_path = _find_mask(export_root, stem)
    image = _load_gray(image_path)
    roi = _load_roi(mask_path, image.shape)
    binary = _detect_vessels(image)
    rgb = _make_rgb(image, binary, roi)

    roi_bool = roi > 0
    bin_bool = binary > 0
    reference = np.logical_and(bin_bool, roi_bool)
    choice = extract_color_mask(image, rgb, reference)
    color = choice.mask
    parts = refine_roi(roi_bool, color)
    refined = parts["refined"]

    h, w = image.shape
    n_roi = int(roi_bool.sum())
    n_color = int(color.sum())
    n_refined = int(refined.sum())
    n_vsl_b = int(np.logical_and(color, bin_bool).sum())
    n_vsl_bp = int(np.logical_and(refined, bin_bool).sum())

    mnv_a = float(csv_row["MNV Area (mm2)"])
    vsl_a = float(csv_row["Vsl Area (mm2)"])
    dens_a = float(csv_row["Vsl Density (Vessel Area/MNV (%))"])
    mnv_b = _px_to_mm2(n_color, w)
    vsl_b = _px_to_mm2(n_vsl_b, w)
    dens_b = (vsl_b / mnv_b) if mnv_b > 0 else 0.0
    mnv_bp = _px_to_mm2(n_refined, w)
    vsl_bp = _px_to_mm2(n_vsl_bp, w)
    dens_bp = (vsl_bp / mnv_bp) if mnv_bp > 0 else 0.0

    return {
        "stem": stem,
        "case": _case_id(csv_row["File"]),
        "grader": grader,
        "file": csv_row["File"],
        "width": w,
        "n_roi": n_roi,
        "n_color": n_color,
        "n_refined": n_refined,
        "n_color_in_roi": parts["n_color_in_roi"],
        "n_color_outside_roi": parts["n_color_outside_roi"],
        "n_padding": parts["n_padding"],
        "n_padding_border": parts["n_padding_border"],
        "n_padding_enclosed": parts["n_padding_enclosed"],
        "n_cc_padding": parts["n_cc_padding"],
        "n_cc_border": parts["n_cc_border"],
        "n_cc_enclosed": parts["n_cc_enclosed"],
        "enclosed_cc_sizes": parts["enclosed_cc_sizes"],
        "max_border_cc": parts["max_border_cc"],
        "max_enclosed_cc": parts["max_enclosed_cc"],
        "n_border_cc_ge50": parts["n_border_cc_ge50"],
        "n_border_cc_ge100": parts["n_border_cc_ge100"],
        "frac_max_border_of_border_px": (
            parts["max_border_cc"] / parts["n_padding_border"]
            if parts["n_padding_border"]
            else 0.0
        ),
        "n_vsl_b": n_vsl_b,
        "n_vsl_bp": n_vsl_bp,
        "dice_color_vs_refined": _dice(color, refined),
        "dice_color_vs_binary_in_roi": float(choice.dice),
        "mnv_a": mnv_a,
        "vsl_a": vsl_a,
        "dens_a": dens_a,
        "mnv_b": mnv_b,
        "vsl_b": vsl_b,
        "dens_b": dens_b,
        "mnv_bp": mnv_bp,
        "vsl_bp": vsl_bp,
        "dens_bp": dens_bp,
        "holes_material": (
            parts["n_padding_enclosed"] >= MATERIAL_HOLE_PX
            and parts["n_padding_enclosed"] >= MATERIAL_HOLE_FRAC * max(n_color, 1)
        ),
    }


def _rpd_row(case: str, metric: str, g1: float, g2: float) -> Dict[str, Any]:
    rpd = rpd_pct(g1, g2)
    return {
        "case": case,
        "metric": metric,
        "g1": g1,
        "g2": g2,
        "rpd": rpd,
        "adopt": bool(rpd is not None and rpd <= ADOPT_PCT),
    }


def main() -> int:
    g1_rows = _index_by_stem(_read_csv(G1_CSV))
    g2_rows = _index_by_stem(_read_csv(G2_CSV))
    stems = sorted(set(g1_rows) & set(g2_rows))
    if len(stems) != 3:
        raise SystemExit(f"Expected 3 paired cases, got {stems}")

    runs: List[Dict[str, Any]] = []
    for stem in stems:
        print(f"\n=== {stem} / g1 ===")
        runs.append(run_one(stem, "g1", G1_DIR / "export", g1_rows[stem]))
        print(f"=== {stem} / g2 ===")
        runs.append(run_one(stem, "g2", G2_DIR / "export", g2_rows[stem]))

    by_case: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for run in runs:
        by_case.setdefault(run["case"], {})[run["grader"]] = run

    rpd_a: List[Dict[str, Any]] = []
    rpd_b: List[Dict[str, Any]] = []
    rpd_bp: List[Dict[str, Any]] = []
    for case in ("abe 20250409", "abe 20260225", "asai 20230314"):
        g1, g2 = by_case[case]["g1"], by_case[case]["g2"]
        for metric, k in (
            ("MNV Area (mm2)", "mnv"),
            ("Vsl Area (mm2)", "vsl"),
            ("Vsl Density (Vessel Area/MNV (%))", "dens"),
        ):
            rpd_a.append(_rpd_row(case, metric, g1[f"{k}_a"], g2[f"{k}_a"]))
            rpd_b.append(_rpd_row(case, metric, g1[f"{k}_b"], g2[f"{k}_b"]))
            rpd_bp.append(_rpd_row(case, metric, g1[f"{k}_bp"], g2[f"{k}_bp"]))

    n_enclosed_total = sum(r["n_padding_enclosed"] for r in runs)
    n_cc_enclosed_total = sum(r["n_cc_enclosed"] for r in runs)
    any_material = any(r["holes_material"] for r in runs)
    # Intended B' mechanism is enclosed holes. Clip of ColorMask-outside-ROI
    # is a side effect of "clipped to user_roi". holes-only RPD stays ≈ B.
    collapses_to_b = n_enclosed_total == 0
    rpd_holes_only: List[Dict[str, Any]] = []
    rpd_clip_only: List[Dict[str, Any]] = []
    for case in ("abe 20250409", "abe 20260225", "asai 20230314"):
        g1, g2 = by_case[case]["g1"], by_case[case]["g2"]
        w1, w2 = g1["width"], g2["width"]
        rpd_holes_only.append(
            _rpd_row(
                case,
                "MNV Area (mm2)",
                _px_to_mm2(g1["n_color"] + g1["n_padding_enclosed"], w1),
                _px_to_mm2(g2["n_color"] + g2["n_padding_enclosed"], w2),
            )
        )
        rpd_clip_only.append(
            _rpd_row(
                case,
                "MNV Area (mm2)",
                _px_to_mm2(g1["n_color_in_roi"], w1),
                _px_to_mm2(g2["n_color_in_roi"], w2),
            )
        )

    # Official-style area NA: RPD>20% on MNV Area and Vsl Area (3 cases each).
    def _area_na(rows: List[Dict[str, Any]]) -> Dict[str, int]:
        mnv = sum(
            1
            for r in rows
            if r["metric"] == "MNV Area (mm2)" and not r["adopt"]
        )
        vsl = sum(
            1
            for r in rows
            if r["metric"] == "Vsl Area (mm2)" and not r["adopt"]
        )
        return {"mnv_na": mnv, "vsl_na": vsl, "area_na": mnv + vsl}

    summary = {
        "definition": (
            "Method B': refined_roi = user_roi minus 8-connected padding CCs "
            "that touch ~user_roi. ColorMask is locked Method B. "
            "Interior enclosed holes stay in MNV Area."
        ),
        "mask_session": "094130",
        "method_a_baseline": "MNV_batch_20260815_094130 + integrated 094445",
        "n_runs": len(runs),
        "n_padding_enclosed_total_px": n_enclosed_total,
        "n_cc_enclosed_total": n_cc_enclosed_total,
        "any_holes_material": any_material,
        "b_prime_collapses_to_b": collapses_to_b,
        "pipeline_analyze_ran": False,
        "pipeline_analyze_reason": (
            "skipped: enclosed holes are tiny (0–236 px; max CC 137 px) and "
            "do not change MNV Area adoption vs B. asai Vsl Area 20% cross "
            "is from clipping ColorMask-outside-ROI, not from holes. "
            "No topology pipeline.analyze."
        ),
        "rpd_mnv_holes_only": rpd_holes_only,
        "rpd_mnv_clip_only": rpd_clip_only,
        "area_na_official_style": {
            "A_094445": {"mnv_na": 3, "vsl_na": 3, "area_na": 6},
            "B": _area_na(rpd_b),
            "B_prime": _area_na(rpd_bp),
        },
        "runs": runs,
        "rpd_method_a_094130": rpd_a,
        "rpd_method_b": rpd_b,
        "rpd_method_b_prime": rpd_bp,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / "method_b_prime_comparison.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    csv_path = OUT_DIR / "method_b_prime_per_run.csv"
    fieldnames = [
        "case",
        "grader",
        "n_roi",
        "n_color",
        "n_refined",
        "n_color_in_roi",
        "n_color_outside_roi",
        "n_padding",
        "n_padding_border",
        "n_padding_enclosed",
        "n_cc_padding",
        "n_cc_border",
        "n_cc_enclosed",
        "max_border_cc",
        "max_enclosed_cc",
        "frac_max_border_of_border_px",
        "dice_color_vs_refined",
        "mnv_a",
        "vsl_a",
        "dens_a",
        "mnv_b",
        "vsl_b",
        "dens_b",
        "mnv_bp",
        "vsl_bp",
        "dens_bp",
        "holes_material",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(runs)

    rpd_csv = OUT_DIR / "method_b_prime_rpd.csv"
    rpd_fields = [
        "case",
        "metric",
        "g1_a",
        "g2_a",
        "rpd_a",
        "adopt_a",
        "g1_b",
        "g2_b",
        "rpd_b",
        "adopt_b",
        "g1_bp",
        "g2_bp",
        "rpd_bp",
        "adopt_bp",
    ]
    with rpd_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rpd_fields)
        writer.writeheader()
        for a, b, bp in zip(rpd_a, rpd_b, rpd_bp):
            writer.writerow(
                {
                    "case": a["case"],
                    "metric": a["metric"],
                    "g1_a": a["g1"],
                    "g2_a": a["g2"],
                    "rpd_a": a["rpd"],
                    "adopt_a": a["adopt"],
                    "g1_b": b["g1"],
                    "g2_b": b["g2"],
                    "rpd_b": b["rpd"],
                    "adopt_b": b["adopt"],
                    "g1_bp": bp["g1"],
                    "g2_bp": bp["g2"],
                    "rpd_bp": bp["rpd"],
                    "adopt_bp": bp["adopt"],
                }
            )

    print("\n=== Per-run padding / refined ===")
    for run in runs:
        print(
            f"{run['case']} {run['grader']}: "
            f"ROI={run['n_roi']} Color={run['n_color']} Refined={run['n_refined']} "
            f"pad={run['n_padding']} border={run['n_padding_border']} "
            f"enclosed={run['n_padding_enclosed']} "
            f"(cc_border={run['n_cc_border']} cc_enclosed={run['n_cc_enclosed']}) "
            f"dice={run['dice_color_vs_refined']:.6f} "
            f"color_out={run['n_color_outside_roi']}"
        )

    print("\n=== RPD A / B / B' ===")
    for a, b, bp in zip(rpd_a, rpd_b, rpd_bp):
        print(
            f"{a['case']:16} {a['metric'][:28]:28} "
            f"A={a['rpd']:.4f} adopt={a['adopt']}  "
            f"B={b['rpd']:.4f} adopt={b['adopt']}  "
            f"B'={bp['rpd']:.4f} adopt={bp['adopt']}"
        )

    print(
        f"\nEnclosed hole px total={n_enclosed_total}  "
        f"material={any_material}  collapses_to_B={collapses_to_b}"
    )
    print(f"Wrote {json_path}")
    print(f"Wrote {csv_path}")
    print(f"Wrote {rpd_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
