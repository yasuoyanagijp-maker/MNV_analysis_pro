#!/usr/bin/env python3
"""
Method D inward + fill holes + morphological close (pilot only).

No app integration. No Pass-2. No Method C. Does not write into
method_d / method_e / method_f.

Per grader × case (ColorMask / inward computed once):

    inward          = ColorMask₁ ∩ user_roi
    filled_only     = binary_fill_holes(inward)
    closed          = morph_close(inward, disk(r_px)) ∩ user_roi
    closed_then_fill = binary_fill_holes(closed) ∩ user_roi

gap_um ∈ {0, 5, 10, 20, 30, 50}; r_px = round_half_up(gap_um * px_per_mm / 1000).
gap 0 = no close (closed == inward; closed_then_fill == filled ∩ ROI).
"""

from __future__ import annotations

import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from scipy.ndimage import binary_fill_holes

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from tools.reading_center_rpd.compute_adopted_from_dual_csv import (  # noqa: E402
    rpd_pct,
)
from ariake_octa.mnv.color_mask import extract_color_mask  # noqa: E402
from tools.roi_visualization_boundary.lib.cases import (  # noqa: E402
    CASE_LABELS,
    CASE_ORDER,
    CASE_SLUGS,
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
from tools.roi_visualization_boundary.method_d.method_d_colormask_snap import (  # noqa: E402
    _disk_kernel,
    _find_meta,
    _load_meta,
    radius_px_from_um,
)
from utils.dual_grader_merge import match_stem  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent
QA_DIR = OUT_DIR / "qa"
GAP_UM = (0, 5, 10, 20, 30, 50)
ADOPT_PCT = 20.0
DENS_TAUTOLOGY = 0.99

# BGR
COLOR_USER = (0, 200, 0)
COLOR_INWARD = (220, 220, 0)
COLOR_CLOSE = (0, 140, 255)
COLOR_HOLES = (0, 255, 255)


@dataclass
class MaskMetrics:
    n_px: int
    n_vsl: int
    mnv_mm2: float
    vsl_mm2: float
    dens: float


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


def _px_to_mm2(n_px: int, width: int, scale_mm: float) -> float:
    return float(n_px) * (float(scale_mm) / float(width)) ** 2


def _metrics(mask: np.ndarray, binary: np.ndarray, width: int, scale_mm: float) -> MaskMetrics:
    n_px = int(mask.sum())
    n_vsl = int(np.logical_and(mask, binary).sum())
    mnv = _px_to_mm2(n_px, width, scale_mm)
    vsl = _px_to_mm2(n_vsl, width, scale_mm)
    dens = (vsl / mnv) if mnv > 0 else 0.0
    return MaskMetrics(n_px=n_px, n_vsl=n_vsl, mnv_mm2=mnv, vsl_mm2=vsl, dens=dens)


def morph_close(mask: np.ndarray, radius_px: int) -> np.ndarray:
    if radius_px <= 0:
        return mask.astype(bool)
    return (
        cv2.morphologyEx(
            mask.astype(np.uint8),
            cv2.MORPH_CLOSE,
            _disk_kernel(radius_px),
        )
        > 0
    )


def _hole_cc_stats(holes: np.ndarray) -> Tuple[int, int, int]:
    """Return (n_cc, max_cc_px, n_cc_ge50)."""
    if not np.any(holes):
        return 0, 0, 0
    n_labels, labels = cv2.connectedComponents(holes.astype(np.uint8), connectivity=8)
    sizes = [(labels == lab).sum() for lab in range(1, n_labels)]
    if not sizes:
        return 0, 0, 0
    return int(n_labels - 1), int(max(sizes)), int(sum(1 for s in sizes if s >= 50))


def _blend(
    bgr: np.ndarray, mask: np.ndarray, color_bgr: Tuple[int, int, int], alpha: float
) -> None:
    sel = mask.astype(bool)
    if not np.any(sel):
        return
    c = np.array(color_bgr, dtype=np.float64)
    bgr[sel] = (bgr[sel].astype(np.float64) * (1.0 - alpha) + c * alpha).astype(np.uint8)


def _outline(
    bgr: np.ndarray, mask: np.ndarray, color_bgr: Tuple[int, int, int], thickness: int = 1
) -> None:
    contours, _ = cv2.findContours(
        mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    if contours:
        cv2.drawContours(bgr, contours, -1, color_bgr, thickness)


def _save_overlay(
    path: Path,
    image: np.ndarray,
    user: np.ndarray,
    inward: np.ndarray,
    close_added: np.ndarray,
    fill_added: np.ndarray,
    legend: str,
) -> None:
    out = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    _blend(out, user, COLOR_USER, 0.18)
    _blend(out, inward, COLOR_INWARD, 0.45)
    _blend(out, close_added, COLOR_CLOSE, 0.75)
    _blend(out, fill_added, COLOR_HOLES, 0.80)
    _outline(out, user, COLOR_USER, 1)
    cv2.putText(
        out,
        legend,
        (8, 16),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.38,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), out)


def _fmt(x: Optional[float], nd: int = 4) -> str:
    if x is None:
        return ""
    return f"{x:.{nd}f}"


def _adopt(rpd: Optional[float]) -> str:
    if rpd is None:
        return ""
    return "yes" if rpd <= ADOPT_PCT else "no"


def run_one(
    stem: str,
    grader: str,
    export_root: Path,
    csv_row: Dict[str, str],
    qa_dir: Path,
) -> List[Dict[str, Any]]:
    image_path = _find_image(export_root, stem)
    mask_path = _find_mask(export_root, stem)
    meta = _load_meta(_find_meta(export_root, stem))
    image = _load_gray(image_path)
    roi = _load_roi(mask_path, image.shape)
    user = roi > 0
    h, w = image.shape[:2]
    px_per_mm = float(meta["px_per_mm"])
    scale_mm = float(meta["fov_mm"]) if meta.get("fov_mm") else float(SCALE_MM)
    case_id = _case_id(csv_row["File"])
    slug = CASE_SLUGS.get(case_id, case_id.replace(" ", "_"))

    print(f"  vessels {grader} {case_id} ...")
    binary = _detect_vessels(image)
    bin_bool = binary > 0

    print(f"  pass-1 RGB {grader} {case_id} ...")
    rgb1 = _make_rgb(image, binary, roi)
    ref1 = np.logical_and(bin_bool, user)
    color1 = extract_color_mask(image, rgb1, ref1).mask.astype(bool)
    inward = np.logical_and(color1, user)

    filled_raw = binary_fill_holes(inward)
    filled_in_roi = np.logical_and(filled_raw, user)
    holes_only = np.logical_and(filled_raw, np.logical_not(inward))
    holes_only_in_roi = np.logical_and(holes_only, user)
    holes_outside = np.logical_and(holes_only, np.logical_not(user))
    n_cc_fill, max_cc_fill, n_cc_fill_ge50 = _hole_cc_stats(holes_only)

    m_in = _metrics(inward, bin_bool, w, scale_mm)
    m_fill = _metrics(filled_raw, bin_bool, w, scale_mm)
    n_vsl_in_holes = int(np.logical_and(holes_only, bin_bool).sum())

    empty = np.zeros_like(inward)
    _save_overlay(
        qa_dir / f"{grader}_{slug}_fill_only.png",
        image,
        user,
        inward,
        empty,
        holes_only,
        "green=user  cyan=inward  yellow=fill_holes",
    )

    rows: List[Dict[str, Any]] = []
    for gap_um in GAP_UM:
        rpx = radius_px_from_um(gap_um, px_per_mm)
        closed = np.logical_and(morph_close(inward, rpx), user)
        closed_fill = np.logical_and(binary_fill_holes(closed), user)
        close_added = np.logical_and(closed, np.logical_not(inward))
        fill_after_close = np.logical_and(closed_fill, np.logical_not(closed))
        both_added = np.logical_and(closed_fill, np.logical_not(inward))

        m_cl = _metrics(closed, bin_bool, w, scale_mm)
        m_cf = _metrics(closed_fill, bin_bool, w, scale_mm)
        n_vsl_close_added = int(np.logical_and(close_added, bin_bool).sum())
        n_vsl_fill_after = int(np.logical_and(fill_after_close, bin_bool).sum())
        n_cc_cf, max_cc_cf, n_cc_cf_ge50 = _hole_cc_stats(fill_after_close)

        if gap_um > 0:
            _save_overlay(
                qa_dir / f"{grader}_{slug}_g{gap_um:02d}um_overlay.png",
                image,
                user,
                inward,
                close_added,
                fill_after_close,
                f"g={gap_um}um ({rpx}px)  cyan=inward  orange=close  yellow=fill",
            )

        rows.append(
            {
                "case": case_id,
                "grader": grader,
                "stem": stem,
                "gap_um": gap_um,
                "gap_px": rpx,
                "px_per_mm": px_per_mm,
                "scale_mm": scale_mm,
                "device": str(meta["device"]),
                "stratum": str(meta["stratum"]),
                "width": w,
                "n_user": int(user.sum()),
                "n_color1": int(color1.sum()),
                "n_inward": m_in.n_px,
                "n_filled_only": m_fill.n_px,
                "n_filled_in_roi": int(filled_in_roi.sum()),
                "n_hole_only_px": int(holes_only.sum()),
                "n_hole_only_in_roi_px": int(holes_only_in_roi.sum()),
                "n_hole_outside_roi_px": int(holes_outside.sum()),
                "n_hole_only_cc": n_cc_fill,
                "max_hole_only_cc_px": max_cc_fill,
                "n_hole_only_cc_ge50": n_cc_fill_ge50,
                "n_vsl_in_holes_only": n_vsl_in_holes,
                "n_closed": m_cl.n_px,
                "n_closed_fill": m_cf.n_px,
                "n_close_added_px": int(close_added.sum()),
                "n_fill_after_close_px": int(fill_after_close.sum()),
                "n_closed_fill_added_px": int(both_added.sum()),
                "n_fill_after_close_cc": n_cc_cf,
                "max_fill_after_close_cc_px": max_cc_cf,
                "n_fill_after_close_cc_ge50": n_cc_cf_ge50,
                "n_vsl_in_close_added": n_vsl_close_added,
                "n_vsl_in_fill_after_close": n_vsl_fill_after,
                "mnv_inward": m_in.mnv_mm2,
                "vsl_inward": m_in.vsl_mm2,
                "dens_inward": m_in.dens,
                "mnv_filled": m_fill.mnv_mm2,
                "vsl_filled": m_fill.vsl_mm2,
                "dens_filled": m_fill.dens,
                "mnv_closed": m_cl.mnv_mm2,
                "vsl_closed": m_cl.vsl_mm2,
                "dens_closed": m_cl.dens,
                "mnv_closed_fill": m_cf.mnv_mm2,
                "vsl_closed_fill": m_cf.vsl_mm2,
                "dens_closed_fill": m_cf.dens,
                "dens_filled_below_099": m_fill.dens < DENS_TAUTOLOGY,
                "dens_closed_below_099": m_cl.dens < DENS_TAUTOLOGY,
                "dens_closed_fill_below_099": m_cf.dens < DENS_TAUTOLOGY,
                "mnv_a_csv": float(csv_row["MNV Area (mm2)"]),
                "vsl_a_csv": float(csv_row["Vsl Area (mm2)"]),
                "dens_a_csv": float(csv_row["Vsl Density (Vessel Area/MNV (%))"]),
            }
        )
    return rows


def _rpd_block(
    g1: Dict[str, Any],
    g2: Dict[str, Any],
    prefix: str,
    mnv_k: str,
    vsl_k: str,
    dens_k: str,
) -> Dict[str, Any]:
    mnv = rpd_pct(float(g1[mnv_k]), float(g2[mnv_k]))
    vsl = rpd_pct(float(g1[vsl_k]), float(g2[vsl_k]))
    dens = rpd_pct(float(g1[dens_k]), float(g2[dens_k]))
    return {
        f"rpd_mnv_{prefix}": mnv,
        f"rpd_vsl_{prefix}": vsl,
        f"rpd_dens_{prefix}": dens,
        f"adopt_mnv_{prefix}": _adopt(mnv),
        f"adopt_vsl_{prefix}": _adopt(vsl),
        f"adopt_dens_{prefix}": _adopt(dens),
        f"g1_mnv_{prefix}": g1[mnv_k],
        f"g2_mnv_{prefix}": g2[mnv_k],
        f"g1_vsl_{prefix}": g1[vsl_k],
        f"g2_vsl_{prefix}": g2[vsl_k],
        f"g1_dens_{prefix}": g1[dens_k],
        f"g2_dens_{prefix}": g2[dens_k],
    }


def write_outputs(runs: List[Dict[str, Any]], out_dir: Path) -> List[Dict[str, Any]]:
    by: Dict[Tuple[str, int], Dict[str, Dict[str, Any]]] = {}
    for row in runs:
        by.setdefault((row["case"], int(row["gap_um"])), {})[row["grader"]] = row

    rpd_rows: List[Dict[str, Any]] = []
    for case_id in CASE_ORDER:
        for gap_um in GAP_UM:
            pair = by.get((case_id, gap_um), {})
            g1, g2 = pair.get("g1"), pair.get("g2")
            if g1 is None or g2 is None:
                continue
            block_a = _rpd_block(g1, g2, "a", "mnv_a_csv", "vsl_a_csv", "dens_a_csv")
            block_in = _rpd_block(g1, g2, "inward", "mnv_inward", "vsl_inward", "dens_inward")
            block_f = _rpd_block(g1, g2, "filled", "mnv_filled", "vsl_filled", "dens_filled")
            block_c = _rpd_block(g1, g2, "closed", "mnv_closed", "vsl_closed", "dens_closed")
            block_cf = _rpd_block(
                g1, g2, "closed_fill", "mnv_closed_fill", "vsl_closed_fill", "dens_closed_fill"
            )
            rpd_rows.append(
                {
                    "case": case_id,
                    "gap_um": gap_um,
                    "gap_px": g1["gap_px"],
                    **block_a,
                    **block_in,
                    **block_f,
                    **block_c,
                    **block_cf,
                    "g1_n_hole_only_px": g1["n_hole_only_px"],
                    "g2_n_hole_only_px": g2["n_hole_only_px"],
                    "g1_n_close_added_px": g1["n_close_added_px"],
                    "g2_n_close_added_px": g2["n_close_added_px"],
                    "g1_n_fill_after_close_px": g1["n_fill_after_close_px"],
                    "g2_n_fill_after_close_px": g2["n_fill_after_close_px"],
                    "g1_n_vsl_in_close_added": g1["n_vsl_in_close_added"],
                    "g2_n_vsl_in_close_added": g2["n_vsl_in_close_added"],
                    "g1_dens_closed_fill_below_099": g1["dens_closed_fill_below_099"],
                    "g2_dens_closed_fill_below_099": g2["dens_closed_fill_below_099"],
                }
            )
            rpd_lookup = rpd_rows[-1]
            for run in (g1, g2):
                run["rpd_mnv_a"] = rpd_lookup["rpd_mnv_a"]
                run["rpd_vsl_a"] = rpd_lookup["rpd_vsl_a"]
                run["rpd_dens_a"] = rpd_lookup["rpd_dens_a"]
                run["adopt_mnv_a"] = rpd_lookup["adopt_mnv_a"]
                run["rpd_mnv_inward"] = rpd_lookup["rpd_mnv_inward"]
                run["rpd_vsl_inward"] = rpd_lookup["rpd_vsl_inward"]
                run["rpd_dens_inward"] = rpd_lookup["rpd_dens_inward"]
                run["adopt_mnv_inward"] = rpd_lookup["adopt_mnv_inward"]
                run["rpd_mnv_filled"] = rpd_lookup["rpd_mnv_filled"]
                run["rpd_vsl_filled"] = rpd_lookup["rpd_vsl_filled"]
                run["rpd_dens_filled"] = rpd_lookup["rpd_dens_filled"]
                run["adopt_mnv_filled"] = rpd_lookup["adopt_mnv_filled"]
                run["rpd_mnv_closed"] = rpd_lookup["rpd_mnv_closed"]
                run["rpd_vsl_closed"] = rpd_lookup["rpd_vsl_closed"]
                run["rpd_dens_closed"] = rpd_lookup["rpd_dens_closed"]
                run["adopt_mnv_closed"] = rpd_lookup["adopt_mnv_closed"]
                run["rpd_mnv_closed_fill"] = rpd_lookup["rpd_mnv_closed_fill"]
                run["rpd_vsl_closed_fill"] = rpd_lookup["rpd_vsl_closed_fill"]
                run["rpd_dens_closed_fill"] = rpd_lookup["rpd_dens_closed_fill"]
                run["adopt_mnv_closed_fill"] = rpd_lookup["adopt_mnv_closed_fill"]

    out_dir.mkdir(parents=True, exist_ok=True)

    result_fields = [
        "case",
        "grader",
        "gap_um",
        "gap_px",
        "device",
        "px_per_mm",
        "scale_mm",
        "n_user",
        "n_inward",
        "n_filled_only",
        "n_filled_in_roi",
        "n_hole_only_px",
        "n_hole_only_in_roi_px",
        "n_hole_outside_roi_px",
        "n_hole_only_cc",
        "max_hole_only_cc_px",
        "n_vsl_in_holes_only",
        "n_closed",
        "n_closed_fill",
        "n_close_added_px",
        "n_fill_after_close_px",
        "n_closed_fill_added_px",
        "n_fill_after_close_cc",
        "max_fill_after_close_cc_px",
        "n_vsl_in_close_added",
        "n_vsl_in_fill_after_close",
        "mnv_inward",
        "vsl_inward",
        "dens_inward",
        "mnv_filled",
        "vsl_filled",
        "dens_filled",
        "mnv_closed",
        "vsl_closed",
        "dens_closed",
        "mnv_closed_fill",
        "vsl_closed_fill",
        "dens_closed_fill",
        "dens_filled_below_099",
        "dens_closed_below_099",
        "dens_closed_fill_below_099",
        "mnv_a_csv",
        "vsl_a_csv",
        "dens_a_csv",
        "rpd_mnv_a",
        "rpd_vsl_a",
        "rpd_dens_a",
        "rpd_mnv_inward",
        "rpd_vsl_inward",
        "rpd_dens_inward",
        "adopt_mnv_inward",
        "rpd_mnv_filled",
        "rpd_vsl_filled",
        "rpd_dens_filled",
        "adopt_mnv_filled",
        "rpd_mnv_closed",
        "rpd_vsl_closed",
        "rpd_dens_closed",
        "adopt_mnv_closed",
        "rpd_mnv_closed_fill",
        "rpd_vsl_closed_fill",
        "rpd_dens_closed_fill",
        "adopt_mnv_closed_fill",
    ]
    with (out_dir / "fill_holes_results.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=result_fields, extrasaction="ignore")
        writer.writeheader()
        for case_id in CASE_ORDER:
            for gap_um in GAP_UM:
                pair = by.get((case_id, gap_um), {})
                for grader in ("g1", "g2"):
                    if grader in pair:
                        writer.writerow(pair[grader])

    rpd_fields = [
        "case",
        "gap_um",
        "gap_px",
        "rpd_mnv_a",
        "rpd_vsl_a",
        "rpd_dens_a",
        "adopt_mnv_a",
        "adopt_vsl_a",
        "adopt_dens_a",
        "rpd_mnv_inward",
        "rpd_vsl_inward",
        "rpd_dens_inward",
        "adopt_mnv_inward",
        "adopt_vsl_inward",
        "adopt_dens_inward",
        "rpd_mnv_filled",
        "rpd_vsl_filled",
        "rpd_dens_filled",
        "adopt_mnv_filled",
        "adopt_vsl_filled",
        "adopt_dens_filled",
        "rpd_mnv_closed",
        "rpd_vsl_closed",
        "rpd_dens_closed",
        "adopt_mnv_closed",
        "adopt_vsl_closed",
        "adopt_dens_closed",
        "rpd_mnv_closed_fill",
        "rpd_vsl_closed_fill",
        "rpd_dens_closed_fill",
        "adopt_mnv_closed_fill",
        "adopt_vsl_closed_fill",
        "adopt_dens_closed_fill",
        "g1_mnv_inward",
        "g2_mnv_inward",
        "g1_dens_inward",
        "g2_dens_inward",
        "g1_dens_filled",
        "g2_dens_filled",
        "g1_dens_closed",
        "g2_dens_closed",
        "g1_dens_closed_fill",
        "g2_dens_closed_fill",
        "g1_n_hole_only_px",
        "g2_n_hole_only_px",
        "g1_n_close_added_px",
        "g2_n_close_added_px",
        "g1_n_fill_after_close_px",
        "g2_n_fill_after_close_px",
        "g1_n_vsl_in_close_added",
        "g2_n_vsl_in_close_added",
        "g1_dens_closed_fill_below_099",
        "g2_dens_closed_fill_below_099",
    ]
    with (out_dir / "fill_holes_rpd.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rpd_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rpd_rows)

    devices = sorted(
        {
            (r["grader"], r["case"], r["device"], r["stratum"], r["scale_mm"], r["px_per_mm"])
            for r in runs
        }
    )
    (out_dir / "device_check.json").write_text(
        json.dumps(
            {
                "n_run_rows": len(runs),
                "gap_um": list(GAP_UM),
                "devices": [
                    {
                        "grader": g,
                        "case": c,
                        "device": d,
                        "stratum": s,
                        "fov_mm": fov,
                        "px_per_mm": px,
                    }
                    for g, c, d, s, fov, px in devices
                ],
                "unique_devices": sorted({d[2] for d in devices}),
                "cross_device_validation": False,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return rpd_rows


def main() -> int:
    g1_rows = _index_by_stem(_read_csv(G1_CSV))
    g2_rows = _index_by_stem(_read_csv(G2_CSV))
    stems = sorted(set(g1_rows) & set(g2_rows))
    if len(stems) != 3:
        raise SystemExit(f"Expected 3 paired cases, got {stems}")

    runs: List[Dict[str, Any]] = []
    for stem in stems:
        print(f"\n=== {stem} / g1 ===")
        runs.extend(run_one(stem, "g1", G1_DIR / "export", g1_rows[stem], QA_DIR))
        print(f"=== {stem} / g2 ===")
        runs.extend(run_one(stem, "g2", G2_DIR / "export", g2_rows[stem], QA_DIR))

    rpd_rows = write_outputs(runs, OUT_DIR)

    print("\n=== Density (inward / fill / close / close+fill) ===")
    for row in runs:
        if int(row["gap_um"]) not in (0, 20, 50):
            continue
        print(
            f"{row['case']:16} {row['grader']} g={row['gap_um']:2} "
            f"Din={row['dens_inward']:.4f} "
            f"Dfill={row['dens_filled']:.4f} "
            f"Dcl={row['dens_closed']:.4f} "
            f"Dcf={row['dens_closed_fill']:.4f} "
            f"hole={row['n_hole_only_px']:5} "
            f"close+={row['n_close_added_px']:5} "
            f"fill+={row['n_fill_after_close_px']:5} "
            f"vsl_close+={row['n_vsl_in_close_added']}"
        )

    print("\n=== RPD MNV (A / inward / fill / close / close+fill) ===")
    for row in rpd_rows:
        print(
            f"{row['case']:16} g={row['gap_um']:2} "
            f"A={_fmt(row['rpd_mnv_a'])} "
            f"in={_fmt(row['rpd_mnv_inward'])}/{row['adopt_mnv_inward']} "
            f"fill={_fmt(row['rpd_mnv_filled'])}/{row['adopt_mnv_filled']} "
            f"cl={_fmt(row['rpd_mnv_closed'])}/{row['adopt_mnv_closed']} "
            f"cf={_fmt(row['rpd_mnv_closed_fill'])}/{row['adopt_mnv_closed_fill']}"
        )

    print(f"\nWrote {OUT_DIR / 'fill_holes_results.csv'}")
    print(f"Wrote {OUT_DIR / 'fill_holes_rpd.csv'}")
    print(f"QA -> {QA_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
