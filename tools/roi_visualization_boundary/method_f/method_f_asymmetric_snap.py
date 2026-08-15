#!/usr/bin/env python3
"""
Method F (pilot verification only): asymmetric hybrid of D inward + E outward.

Pilot only. Parallel to Method D and Method E. Does not write into
method_d/ or method_e/. No production flag, no default ON,
no intelligent_roi, no schemas, no mnv_wizard, no MNVPipeline.analyze.

Pipeline (per grader × case)
----------------------------
1. user_roi = hand-drawn mask
2. Full-field vessel binary via ``_detect_vessels`` (no ROI clip)
3. Pass-1 RGB with lesion_mask=user_roi, add_overlays=False
4. ColorMask₁ = locked Method B extract (NO Pass-2 seed dilate)
5. inward = ColorMask₁ ∩ user_roi
     Uncapped shrink. Same as Method D radius 0. Can only shrink
     because Pass-1 coloring is ROI-gated (ColorMask ⊆ ROI aside
     from Gaussian bleed).
6. Contours = ALL RETR_EXTERNAL of **inward** (not user_roi).
   Each is CHAIN_APPROX_NONE, densified to 1.0 px.
7. If displacement_um > 0:
     displacement_px = round_half_up(displacement_um * px_per_mm / 1000)
     each inward-contour point moves at most displacement_px along
     its local normal toward ColorMask₁ (Method E snap; ColorMask
     attraction; first-hit; inward on a tie).
     Hard cap: |move| <= displacement_px. No Pass-2. No region
     growing. No ROIEnclosure as ROI.
8. refined = fillPoly(nudged inward contours)   (displacement 0 = inward)
9. MNV Area = refined px × (scale_mm / width)²
10. Vsl Area = (binary ∩ refined) px × scale

Outward-added (QA orange) = refined − inward, not refined − user_roi.
"""

from __future__ import annotations

import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from ariake_octa.mnv.color_mask import extract_color_mask  # noqa: E402
from tools.reading_center_rpd.compute_adopted_from_dual_csv import (  # noqa: E402
    rpd_pct,
)
from tools.roi_visualization_boundary.lib.cases import (  # noqa: E402
    G1_CSV,
    G1_DIR,
    G2_CSV,
    G2_DIR,
)
from tools.roi_visualization_boundary.lib.io import (  # noqa: E402
    detect_vessels as _detect_vessels,
    find_image as _find_image,
    find_mask as _find_mask,
    load_gray as _load_gray,
    load_roi as _load_roi,
    make_rgb as _make_rgb,
)
from tools.roi_visualization_boundary.lib.paths import PILOT_ROOT  # noqa: E402
from tools.roi_visualization_boundary.method_e.method_e_contour_snap import (  # noqa: E402
    ADOPT_PCT,
    CASE_ORDER,
    CASE_SLUGS,
    COLOR_ADDED,
    COLOR_REFINED,
    COLOR_USER,
    DENSIFY_SPACING_PX,
    _blend,
    _case_id,
    _fmt,
    _index_by_stem,
    _label,
    _layer_overlay,
    _load_meta,
    _find_meta,
    _max_dist_from_mask,
    _method_a_rpd,
    _method_b_rpd,
    _method_d_rpd,
    _outline,
    _px_to_mm2,
    _read_csv,
    densify_contour,
    displacement_px_from_um,
    extract_all_external_contours,
    fill_contour,
    outward_normals,
    snap_all_contours,
    snap_contour_to_colormask,
)

OUT_DIR = Path(__file__).resolve().parent
QA_DIR = OUT_DIR / "qa"
METHOD_D_DIR = PILOT_ROOT / "method_d"
METHOD_D_QA = METHOD_D_DIR / "qa"
METHOD_D_SWEEP = METHOD_D_DIR / "radius_sweep_results.csv"
METHOD_E_DIR = PILOT_ROOT / "method_e"
METHOD_E_QA = METHOD_E_DIR / "qa"
METHOD_E_SWEEP = METHOD_E_DIR / "displacement_sweep_results.csv"
DISPLACEMENT_UM = (0, 5, 10, 20, 30, 50)

COLOR_INWARD = (220, 220, 0)  # BGR cyan, same as Method D inward / E ColorMask


@dataclass
class DisplacementRun:
    case_id: str
    grader: str
    stem: str
    displacement_um: int
    displacement_px: int
    px_per_mm: float
    scale_mm: float
    device: str
    stratum: str
    fov_mm: float
    n_user: int
    n_color1: int
    n_color_outside_roi: int
    n_inward: int
    n_fillpoly_inward: int
    n_external_cc: int
    n_contour_pts: int
    n_moved: int
    mean_move_px: float
    max_move_px: float
    n_added: int
    n_removed: int
    max_added_dist_px: float
    n_jitter_compared: int
    n_jitter_mismatch: int
    n_binary_fallback_hits: int
    n_refined: int
    n_vsl: int
    mnv_mm2: float
    vsl_mm2: float
    dens: float


def _method_e_rpd(path: Path) -> Dict[Tuple[str, int], Dict[str, str]]:
    out: Dict[Tuple[str, int], Dict[str, str]] = {}
    if not path.is_file():
        return out
    for row in _read_csv(path):
        key = (row["case"], int(row["displacement_um"]))
        out[key] = row
    return out


def _on_mask(mask: np.ndarray, xy: np.ndarray) -> bool:
    h, w = mask.shape[:2]
    ix = int(round(float(xy[0])))
    iy = int(round(float(xy[1])))
    if 0 <= iy < h and 0 <= ix < w:
        return bool(mask[iy, ix])
    return False


def _round_xy(xy: np.ndarray) -> np.ndarray:
    return np.array(
        [round(float(xy[0])), round(float(xy[1]))], dtype=np.float64
    )


def nearest_hit_along_normal(
    point: np.ndarray,
    normal: np.ndarray,
    color_mask: np.ndarray,
    displacement_px: int,
) -> Optional[np.ndarray]:
    """All t=1..dpx on ±normal; pick min Euclidean ColorMask landing."""
    if displacement_px <= 0:
        return None
    if normal[0] == 0.0 and normal[1] == 0.0:
        return None
    if _on_mask(color_mask, point):
        return None
    best_q: Optional[np.ndarray] = None
    best_d = float("inf")
    best_sign = 0
    for t in range(1, int(displacement_px) + 1):
        for sign in (-1, 1):
            q = point + sign * t * normal
            if not _on_mask(color_mask, q):
                continue
            q_round = _round_xy(q)
            actual = float(np.sqrt(((q_round - point) ** 2).sum()))
            closer = actual < best_d - 1e-9
            tie_inward = abs(actual - best_d) <= 1e-9 and sign < best_sign
            if closer or tie_inward:
                best_d = actual
                best_q = q_round
                best_sign = sign
    return best_q


def count_attraction_jitter(
    contours: List[np.ndarray],
    color_mask: np.ndarray,
    displacement_px: int,
    shape: Tuple[int, int],
) -> Tuple[int, int]:
    """
    Compare Method E first-hit vs nearest-along-normal landing pixels.
    Returns (n_points_that_hit, n_mismatch).
    """
    if displacement_px <= 0:
        return 0, 0
    n_hit = 0
    n_mismatch = 0
    for raw in contours:
        if len(raw) < 3:
            continue
        dens = densify_contour(raw, DENSIFY_SPACING_PX)
        if len(dens) < 3:
            continue
        own = fill_contour(raw, shape)
        if not np.any(own):
            own = fill_contour(dens, shape)
        normals = outward_normals(dens, own)
        first, _ = snap_contour_to_colormask(
            dens, normals, color_mask, displacement_px
        )
        for i in range(len(dens)):
            if normals[i][0] == 0.0 and normals[i][1] == 0.0:
                continue
            if _on_mask(color_mask, dens[i]):
                continue
            nearest = nearest_hit_along_normal(
                dens[i], normals[i], color_mask, displacement_px
            )
            if nearest is None:
                continue
            n_hit += 1
            if not np.allclose(first[i], nearest):
                n_mismatch += 1
    return n_hit, n_mismatch


def count_binary_fallback_hits(
    contours: List[np.ndarray],
    color_mask: np.ndarray,
    binary: np.ndarray,
    displacement_px: int,
    shape: Tuple[int, int],
) -> int:
    """
    Points that miss ColorMask within dpx but would hit vessel binary
    along the same ±normal. Diagnostic only — not used for refined.
    """
    if displacement_px <= 0:
        return 0
    n = 0
    for raw in contours:
        if len(raw) < 3:
            continue
        dens = densify_contour(raw, DENSIFY_SPACING_PX)
        if len(dens) < 3:
            continue
        own = fill_contour(raw, shape)
        if not np.any(own):
            own = fill_contour(dens, shape)
        normals = outward_normals(dens, own)
        moved, _ = snap_contour_to_colormask(
            dens, normals, color_mask, displacement_px
        )
        for i in range(len(dens)):
            if np.linalg.norm(moved[i] - dens[i]) > 1e-6:
                continue
            if _on_mask(color_mask, dens[i]):
                continue
            if nearest_hit_along_normal(
                dens[i], normals[i], binary, displacement_px
            ) is not None:
                n += 1
    return n


def _composite_overlay(
    image: np.ndarray,
    user: np.ndarray,
    inward: np.ndarray,
    added: np.ndarray,
    refined: np.ndarray,
) -> np.ndarray:
    out = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    _blend(out, user, COLOR_USER, 0.18)
    _blend(out, inward, COLOR_INWARD, 0.45)
    _blend(out, added, COLOR_ADDED, 0.70)
    _outline(out, user, COLOR_USER, 1)
    _outline(out, refined, COLOR_REFINED, 1)
    cv2.putText(
        out,
        "green=user  cyan=inward  orange=outward-nudge  magenta=refined",
        (8, 16),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.36,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    return out


def _panel(
    image: np.ndarray,
    user: np.ndarray,
    inward: np.ndarray,
    added: np.ndarray,
    refined: np.ndarray,
) -> np.ndarray:
    tiles = [
        _label(_layer_overlay(image, user, COLOR_USER), "1 user_roi"),
        _label(_layer_overlay(image, inward, COLOR_INWARD), "2 inward ColorMask∩ROI"),
        _label(
            _layer_overlay(image, added, COLOR_ADDED, 0.75),
            "3 outward-nudge added",
        ),
        _label(_layer_overlay(image, refined, COLOR_REFINED), "4 refined (metrics)"),
    ]
    top = np.hstack([tiles[0], tiles[1]])
    bot = np.hstack([tiles[2], tiles[3]])
    return np.vstack([top, bot])


def _vs_de_panel(
    image: np.ndarray,
    added_f: np.ndarray,
    refined_f: np.ndarray,
    d_outward_path: Path,
    e_refined_path: Path,
) -> Optional[np.ndarray]:
    if not d_outward_path.is_file() or not e_refined_path.is_file():
        return None
    d_out = cv2.imread(str(d_outward_path), cv2.IMREAD_COLOR)
    e_ref = cv2.imread(str(e_refined_path), cv2.IMREAD_COLOR)
    if d_out is None or e_ref is None:
        return None
    f_add = _label(
        _layer_overlay(image, added_f, COLOR_ADDED, 0.75), "F added (nudge of inward)"
    )
    f_ref = _label(_layer_overlay(image, refined_f, COLOR_REFINED), "F refined")
    d_out = _label(d_out, "D outward-added (same um)")
    e_ref = _label(e_ref, "E refined (same um)")
    top = np.hstack([f_add, d_out])
    bot = np.hstack([f_ref, e_ref])
    return np.vstack([top, bot])


def _save_qa(
    qa_dir: Path,
    prefix: str,
    image: np.ndarray,
    user: np.ndarray,
    inward: np.ndarray,
    added: np.ndarray,
    refined: np.ndarray,
    vs_de: Optional[np.ndarray],
) -> None:
    qa_dir.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(qa_dir / f"{prefix}_user_roi.png"), _layer_overlay(image, user, COLOR_USER))
    cv2.imwrite(
        str(qa_dir / f"{prefix}_inward.png"),
        _layer_overlay(image, inward, COLOR_INWARD),
    )
    cv2.imwrite(
        str(qa_dir / f"{prefix}_outward_added.png"),
        _layer_overlay(image, added, COLOR_ADDED, 0.75),
    )
    cv2.imwrite(
        str(qa_dir / f"{prefix}_refined.png"),
        _layer_overlay(image, refined, COLOR_REFINED),
    )
    cv2.imwrite(
        str(qa_dir / f"{prefix}_overlay.png"),
        _composite_overlay(image, user, inward, added, refined),
    )
    cv2.imwrite(
        str(qa_dir / f"{prefix}_panel.png"),
        _panel(image, user, inward, added, refined),
    )
    if vs_de is not None:
        cv2.imwrite(str(qa_dir / f"{prefix}_vs_de.png"), vs_de)


def run_grader_case(
    stem: str,
    grader: str,
    export_root: Path,
    csv_row: Dict[str, str],
    displacements_um: Tuple[int, ...],
    qa_dir: Path,
) -> List[DisplacementRun]:
    image_path = _find_image(export_root, stem)
    mask_path = _find_mask(export_root, stem)
    meta = _load_meta(_find_meta(export_root, stem))
    image = _load_gray(image_path)
    roi = _load_roi(mask_path, image.shape)
    user = roi > 0
    h, w = image.shape[:2]
    px_per_mm = float(meta["px_per_mm"])
    scale_mm = float(meta["fov_mm"])
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
    n_color_out = int(np.logical_and(color1, np.logical_not(user)).sum())

    raw_contours = extract_all_external_contours(inward)
    n_raw = sum(len(c) for c in raw_contours)
    fillpoly_inward, _, _ = snap_all_contours(raw_contours, color1, 0, (h, w))
    n_fillpoly_inward = int(fillpoly_inward.sum())
    print(
        f"  inward contour {grader} {case_id}: n_cc={len(raw_contours)} "
        f"NONE_pts={n_raw} inward_px={int(inward.sum())} "
        f"fillpoly_inward_px={n_fillpoly_inward} "
        f"color_outside_roi={n_color_out}"
    )

    runs: List[DisplacementRun] = []
    for displacement_um in displacements_um:
        dpx = displacement_px_from_um(displacement_um, px_per_mm)
        if displacement_um == 0:
            refined = inward.copy()
            _, move_d, n_contour = snap_all_contours(
                raw_contours, color1, 0, (h, w)
            )
            move_d = np.zeros_like(move_d)
            n_jitter_compared = 0
            n_jitter_mismatch = 0
            n_bin_fb = 0
        else:
            print(
                f"  snap {grader} {case_id} d={displacement_um}um ({dpx}px) "
                f"n_cc={len(raw_contours)} ..."
            )
            refined, move_d, n_contour = snap_all_contours(
                raw_contours, color1, dpx, (h, w)
            )
            n_jitter_compared, n_jitter_mismatch = count_attraction_jitter(
                raw_contours, color1, dpx, (h, w)
            )
            n_bin_fb = count_binary_fallback_hits(
                raw_contours, color1, bin_bool, dpx, (h, w)
            )

        added = np.logical_and(refined, np.logical_not(inward))
        removed = np.logical_and(inward, np.logical_not(refined))
        n_refined = int(refined.sum())
        n_vsl = int(np.logical_and(bin_bool, refined).sum())
        mnv = _px_to_mm2(n_refined, w, scale_mm)
        vsl = _px_to_mm2(n_vsl, w, scale_mm)
        dens = (vsl / mnv) if mnv > 0 else 0.0
        max_added = _max_dist_from_mask(added, inward)

        prefix = f"{grader}_{slug}_d{displacement_um:02d}um"
        d_out_path = METHOD_D_QA / f"{grader}_{slug}_r{displacement_um:02d}um_outward_added.png"
        e_ref_path = METHOD_E_QA / f"{grader}_{slug}_d{displacement_um:02d}um_refined.png"
        vs_de = _vs_de_panel(image, added, refined, d_out_path, e_ref_path)
        _save_qa(qa_dir, prefix, image, user, inward, added, refined, vs_de)

        runs.append(
            DisplacementRun(
                case_id=case_id,
                grader=grader,
                stem=stem,
                displacement_um=int(displacement_um),
                displacement_px=dpx,
                px_per_mm=px_per_mm,
                scale_mm=scale_mm,
                device=str(meta["device"]),
                stratum=str(meta["stratum"]),
                fov_mm=float(meta["fov_mm"]),
                n_user=int(user.sum()),
                n_color1=int(color1.sum()),
                n_color_outside_roi=n_color_out,
                n_inward=int(inward.sum()),
                n_fillpoly_inward=n_fillpoly_inward,
                n_external_cc=len(raw_contours),
                n_contour_pts=n_contour,
                n_moved=int(np.count_nonzero(move_d > 0)),
                mean_move_px=float(move_d.mean()) if len(move_d) else 0.0,
                max_move_px=float(move_d.max()) if len(move_d) else 0.0,
                n_added=int(added.sum()),
                n_removed=int(removed.sum()),
                max_added_dist_px=max_added,
                n_jitter_compared=n_jitter_compared,
                n_jitter_mismatch=n_jitter_mismatch,
                n_binary_fallback_hits=n_bin_fb,
                n_refined=n_refined,
                n_vsl=n_vsl,
                mnv_mm2=mnv,
                vsl_mm2=vsl,
                dens=dens,
            )
        )
    return runs


def write_outputs(
    runs: List[DisplacementRun],
    method_a: Dict[Tuple[str, str], float],
    method_b: Dict[Tuple[str, str], float],
    method_d: Dict[Tuple[str, int], Dict[str, str]],
    method_e: Dict[Tuple[str, int], Dict[str, str]],
    out_dir: Path,
) -> List[Dict[str, str]]:
    by: Dict[Tuple[str, int], Dict[str, DisplacementRun]] = {}
    for run in runs:
        by.setdefault((run.case_id, run.displacement_um), {})[run.grader] = run

    sweep_rows: List[Dict[str, str]] = []
    for case_id in CASE_ORDER:
        for displacement_um in DISPLACEMENT_UM:
            pair = by.get((case_id, displacement_um), {})
            g1, g2 = pair.get("g1"), pair.get("g2")
            if g1 is None or g2 is None:
                continue
            mnv_rpd = rpd_pct(g1.mnv_mm2, g2.mnv_mm2)
            vsl_rpd = rpd_pct(g1.vsl_mm2, g2.vsl_mm2)
            dens_rpd = rpd_pct(g1.dens, g2.dens)
            a_mnv = method_a.get((case_id, "MNV Area (mm2)"))
            a_vsl = method_a.get((case_id, "Vsl Area (mm2)"))
            b_mnv = method_b.get((case_id, "MNV Area (mm2)"))
            b_vsl = method_b.get((case_id, "Vsl Area (mm2)"))
            drow = method_d.get((case_id, displacement_um), {})
            erow = method_e.get((case_id, displacement_um), {})
            sweep_rows.append(
                {
                    "case": case_id,
                    "displacement_um": str(displacement_um),
                    "displacement_px": str(g1.displacement_px),
                    "px_per_mm": f"{g1.px_per_mm:.6g}",
                    "scale_mm": f"{g1.scale_mm:.6g}",
                    "device": g1.device,
                    "stratum": g1.stratum,
                    "fov_mm": f"{g1.fov_mm:.6g}",
                    "g1_mnv_mm2": f"{g1.mnv_mm2:.8g}",
                    "g2_mnv_mm2": f"{g2.mnv_mm2:.8g}",
                    "mnv_rpd_pct": _fmt(mnv_rpd),
                    "mnv_adopted": (
                        ""
                        if mnv_rpd is None
                        else ("yes" if mnv_rpd <= ADOPT_PCT else "no")
                    ),
                    "g1_vsl_mm2": f"{g1.vsl_mm2:.8g}",
                    "g2_vsl_mm2": f"{g2.vsl_mm2:.8g}",
                    "vsl_rpd_pct": _fmt(vsl_rpd),
                    "vsl_adopted": (
                        ""
                        if vsl_rpd is None
                        else ("yes" if vsl_rpd <= ADOPT_PCT else "no")
                    ),
                    "g1_dens": f"{g1.dens:.8g}",
                    "g2_dens": f"{g2.dens:.8g}",
                    "dens_rpd_pct": _fmt(dens_rpd),
                    "g1_n_external_cc": str(g1.n_external_cc),
                    "g2_n_external_cc": str(g2.n_external_cc),
                    "g1_n_contour_pts": str(g1.n_contour_pts),
                    "g2_n_contour_pts": str(g2.n_contour_pts),
                    "g1_mean_move_px": f"{g1.mean_move_px:.6g}",
                    "g2_mean_move_px": f"{g2.mean_move_px:.6g}",
                    "g1_max_move_px": f"{g1.max_move_px:.6g}",
                    "g2_max_move_px": f"{g2.max_move_px:.6g}",
                    "g1_n_moved": str(g1.n_moved),
                    "g2_n_moved": str(g2.n_moved),
                    "g1_added_px": str(g1.n_added),
                    "g2_added_px": str(g2.n_added),
                    "g1_removed_px": str(g1.n_removed),
                    "g2_removed_px": str(g2.n_removed),
                    "g1_max_added_dist_px": f"{g1.max_added_dist_px:.6g}",
                    "g2_max_added_dist_px": f"{g2.max_added_dist_px:.6g}",
                    "g1_n_jitter_compared": str(g1.n_jitter_compared),
                    "g2_n_jitter_compared": str(g2.n_jitter_compared),
                    "g1_n_jitter_mismatch": str(g1.n_jitter_mismatch),
                    "g2_n_jitter_mismatch": str(g2.n_jitter_mismatch),
                    "g1_n_binary_fallback_hits": str(g1.n_binary_fallback_hits),
                    "g2_n_binary_fallback_hits": str(g2.n_binary_fallback_hits),
                    "g1_refined_px": str(g1.n_refined),
                    "g2_refined_px": str(g2.n_refined),
                    "g1_inward_px": str(g1.n_inward),
                    "g2_inward_px": str(g2.n_inward),
                    "g1_fillpoly_inward_px": str(g1.n_fillpoly_inward),
                    "g2_fillpoly_inward_px": str(g2.n_fillpoly_inward),
                    "g1_user_px": str(g1.n_user),
                    "g2_user_px": str(g2.n_user),
                    "g1_color1_px": str(g1.n_color1),
                    "g2_color1_px": str(g2.n_color1),
                    "g1_color_outside_roi_px": str(g1.n_color_outside_roi),
                    "g2_color_outside_roi_px": str(g2.n_color_outside_roi),
                    "method_a_mnv_rpd": _fmt(a_mnv),
                    "method_a_vsl_rpd": _fmt(a_vsl),
                    "method_b_mnv_rpd": _fmt(b_mnv),
                    "method_b_vsl_rpd": _fmt(b_vsl),
                    "method_d_mnv_rpd": drow.get("mnv_rpd_pct", ""),
                    "method_d_vsl_rpd": drow.get("vsl_rpd_pct", ""),
                    "method_d_mnv_adopted": drow.get("mnv_adopted", ""),
                    "method_d_g1_mnv_mm2": drow.get("g1_mnv_mm2", ""),
                    "method_d_g2_mnv_mm2": drow.get("g2_mnv_mm2", ""),
                    "method_d_g1_outward_px": drow.get("g1_outward_px", ""),
                    "method_d_g2_outward_px": drow.get("g2_outward_px", ""),
                    "method_e_mnv_rpd": erow.get("mnv_rpd_pct", ""),
                    "method_e_vsl_rpd": erow.get("vsl_rpd_pct", ""),
                    "method_e_mnv_adopted": erow.get("mnv_adopted", ""),
                    "method_e_g1_mnv_mm2": erow.get("g1_mnv_mm2", ""),
                    "method_e_g2_mnv_mm2": erow.get("g2_mnv_mm2", ""),
                    "method_e_g1_added_px": erow.get("g1_added_px", ""),
                    "method_e_g2_added_px": erow.get("g2_added_px", ""),
                    "g1_device": g1.device,
                    "g2_device": g2.device,
                    "g1_px_per_mm": f"{g1.px_per_mm:.6g}",
                    "g2_px_per_mm": f"{g2.px_per_mm:.6g}",
                }
            )

    out_dir.mkdir(parents=True, exist_ok=True)
    sweep_path = out_dir / "displacement_sweep_results.csv"
    with sweep_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(sweep_rows[0].keys()))
        writer.writeheader()
        writer.writerows(sweep_rows)

    devices = sorted(
        {
            (r.grader, r.case_id, r.device, r.stratum, r.fov_mm, r.px_per_mm)
            for r in runs
        }
    )
    summary = {
        "n_runs": len(runs),
        "displacements_um": list(DISPLACEMENT_UM),
        "densify_spacing_px": DENSIFY_SPACING_PX,
        "inward": "colormask_pass1_intersect_user_roi",
        "outward": "method_e_nudge_of_inward_contours",
        "attraction": "pass1_colormask_first_hit",
        "pass2": False,
        "region_growing": False,
        "roi_enclosure_as_roi": False,
        "enable_color_snap": "documented_only",
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
        "unique_strata": sorted({d[3] for d in devices}),
        "unique_px_per_mm": sorted({d[5] for d in devices}),
        "cross_device_validation": False,
    }
    (out_dir / "device_check.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return sweep_rows


def _is_nondecreasing(values: List[float], eps: float = 1e-9) -> bool:
    return all(values[i] + eps >= values[i - 1] for i in range(1, len(values)))


def print_monotonicity(runs: List[DisplacementRun]) -> None:
    print("\n=== Monotonicity (mean/max move, add/remove vs inward) ===")
    by: Dict[Tuple[str, str], List[DisplacementRun]] = {}
    for run in runs:
        by.setdefault((run.grader, run.case_id), []).append(run)
    for key in sorted(by):
        seq = sorted(by[key], key=lambda r: r.displacement_um)
        mean_m = [r.mean_move_px for r in seq]
        max_m = [r.max_move_px for r in seq]
        added = [float(r.n_added) for r in seq]
        removed = [float(r.n_removed) for r in seq]
        n_moved = [float(r.n_moved) for r in seq]
        print(
            f"  {key[0]} {key[1]}: "
            f"mean_move {'mono↑' if _is_nondecreasing(mean_m) else 'NOT mono'} {mean_m} | "
            f"max_move {'mono↑' if _is_nondecreasing(max_m) else 'NOT mono'} {max_m} | "
            f"added {'mono↑' if _is_nondecreasing(added) else 'NOT mono'} "
            f"{[int(x) for x in added]} | "
            f"removed {'mono↑' if _is_nondecreasing(removed) else 'NOT mono'} "
            f"{[int(x) for x in removed]} | "
            f"n_moved {'mono↑' if _is_nondecreasing(n_moved) else 'NOT mono'} "
            f"{[int(x) for x in n_moved]}"
        )


def main() -> int:
    g1_rows = _index_by_stem(_read_csv(G1_CSV))
    g2_rows = _index_by_stem(_read_csv(G2_CSV))
    stems = sorted(set(g1_rows) & set(g2_rows))
    if len(stems) != 3:
        raise SystemExit(f"Expected 3 paired cases, got {stems}")

    method_a = _method_a_rpd(g1_rows, g2_rows)
    method_b = _method_b_rpd(
        PILOT_ROOT / "method_b" / "rpd_comparison.csv"
    )
    method_d = _method_d_rpd(METHOD_D_SWEEP)
    method_e = _method_e_rpd(METHOD_E_SWEEP)

    runs: List[DisplacementRun] = []
    for stem in stems:
        print(f"\n=== {stem} / g1 ===")
        runs.extend(
            run_grader_case(
                stem, "g1", G1_DIR / "export", g1_rows[stem], DISPLACEMENT_UM, QA_DIR
            )
        )
        print(f"=== {stem} / g2 ===")
        runs.extend(
            run_grader_case(
                stem, "g2", G2_DIR / "export", g2_rows[stem], DISPLACEMENT_UM, QA_DIR
            )
        )

    sweep_rows = write_outputs(
        runs, method_a, method_b, method_d, method_e, OUT_DIR
    )

    print("\n=== Device / scale (G1+G2 meta.json) ===")
    seen = set()
    for run in runs:
        key = (run.grader, run.case_id, run.device, run.stratum, run.px_per_mm, run.fov_mm)
        if key in seen:
            continue
        seen.add(key)
        print(
            f"  {run.grader} {run.case_id}: device={run.device} "
            f"stratum={run.stratum} fov={run.fov_mm} px_per_mm={run.px_per_mm}"
        )

    print("\n=== Method F displacement sweep (MNV / Vsl RPD) vs D / E ===")
    print(
        f"{'case':16} {'d_um':>5} {'d_px':>4} "
        f"{'F_MNV':>8} {'F_Vsl':>8} {'F_ad':>5} "
        f"{'D_MNV':>8} {'D_ad':>5} "
        f"{'E_MNV':>8} {'E_ad':>5} "
        f"{'g1_mv':>6} {'g2_mv':>6} "
        f"{'g1_add':>7} {'g2_add':>7} "
        f"{'jit':>5}"
    )
    for row in sweep_rows:
        jit = int(row["g1_n_jitter_mismatch"]) + int(row["g2_n_jitter_mismatch"])
        print(
            f"{row['case']:16} {row['displacement_um']:>5} {row['displacement_px']:>4} "
            f"{row['mnv_rpd_pct']:>8} {row['vsl_rpd_pct']:>8} {row['mnv_adopted']:>5} "
            f"{row['method_d_mnv_rpd']:>8} {row['method_d_mnv_adopted']:>5} "
            f"{row['method_e_mnv_rpd']:>8} {row['method_e_mnv_adopted']:>5} "
            f"{row['g1_mean_move_px']:>6} {row['g2_mean_move_px']:>6} "
            f"{row['g1_added_px']:>7} {row['g2_added_px']:>7} "
            f"{jit:>5}"
        )

    print_monotonicity(runs)

    print(f"\nWrote {OUT_DIR / 'displacement_sweep_results.csv'}")
    print(f"QA images: {QA_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
