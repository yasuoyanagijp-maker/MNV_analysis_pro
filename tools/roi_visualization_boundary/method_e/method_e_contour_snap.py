#!/usr/bin/env python3
"""
Method E (pilot verification only): contour-nudge a hand-drawn ROI onto ColorMask.

Pilot only. Parallel to Method D. Does not write into method_d/.
No production flag, no default ON, no intelligent_roi, no schemas,
no mnv_wizard, no MNVPipeline.analyze.

Phase 0 (see method_e/phase0_record.md)
-------------------------------------------
A. CHAIN_APPROX_SIMPLE max gaps are 5.7–14 px (>> 5 μm = 1 px; sometimes
   > 50 μm = 8 px). Densify to 1.0 px arc-length before nudging.
B. ROIModifier searches min-gray along the centroid ray. A sign flip
   (max instead of min) would pull into the bright lesion core or jump
   along the ray onto a distant arcade. Do not flip. Snap along the
   local normal, bounded by displacement_px, onto Pass-1 ColorMask.

Pipeline (per grader × case)
----------------------------
1. user_roi = hand-drawn mask
2. Full-field vessel binary via ``_detect_vessels`` (no ROI clip)
3. Pass-1 RGB with lesion_mask=user_roi, add_overlays=False
4. ColorMask = locked Method B extract (NO Pass-2 seed dilate)
5. Contours = ALL RETR_EXTERNAL (export masks are 150–326 CC, not one
   polygon). Each is CHAIN_APPROX_NONE, densified to 1.0 px.
   Largest-CC-only fill collapses the ROI (first-run bug; do not use).
6. If displacement_um > 0:
     displacement_px = round_half_up(displacement_um * px_per_mm / 1000)
     each point moves at most displacement_px along its local normal
     to the nearest ColorMask pixel (inward or outward)
     Hard cap: |move| <= displacement_px. No region growing.
7. refined = fillPoly(nudged contour)   (displacement 0 = user_roi)
8. MNV Area = refined px × (scale_mm / width)²
9. Vsl Area = (binary ∩ refined) px × scale

Production flag name ``enable_color_snap`` is documented only.
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
from tools.roi_visualization_boundary.lib.paths import PILOT_ROOT  # noqa: E402
from utils.dual_grader_merge import match_stem  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent
QA_DIR = OUT_DIR / "qa"
METHOD_D_DIR = PILOT_ROOT / "method_d"
METHOD_D_QA = METHOD_D_DIR / "qa"
METHOD_D_SWEEP = METHOD_D_DIR / "radius_sweep_results.csv"
DISPLACEMENT_UM = (0, 5, 10, 20, 30, 50)
PX_PER_MM_FALLBACK = 150.0
ADOPT_PCT = 20.0
DENSIFY_SPACING_PX = 1.0

# BGR (cv2.imwrite) — align with Method D where possible
COLOR_USER = (0, 200, 0)
COLOR_COLORMASK = (220, 220, 0)
COLOR_ADDED = (0, 140, 255)
COLOR_REMOVED = (0, 0, 220)
COLOR_REFINED = (255, 0, 255)


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
    n_external_cc: int
    n_contour_pts: int
    n_moved: int
    mean_move_px: float
    max_move_px: float
    n_added: int
    n_removed: int
    max_added_dist_px: float
    n_refined: int
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


def _round_half_up(x: float) -> int:
    """Nearest int, ties away from zero for x>=0. Min 0. Same as Method D."""
    if x <= 0:
        return 0
    return int(np.floor(float(x) + 0.5))


def displacement_px_from_um(displacement_um: float, px_per_mm: float) -> int:
    return _round_half_up(float(displacement_um) * float(px_per_mm) / 1000.0)


def _px_to_mm2(n_px: int, width: int, scale_mm: float) -> float:
    return float(n_px) * (float(scale_mm) / float(width)) ** 2


def _find_meta(export_root: Path, stem: str) -> Path:
    metas = list((export_root / "meta").rglob("*.json"))
    for p in metas:
        if match_stem(p.name) == stem:
            return p
    raise FileNotFoundError(f"meta.json not found for {stem} under {export_root}")


def _load_meta(path: Path) -> Dict[str, object]:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    px = data.get("px_per_mm")
    fov = data.get("fov_mm")
    return {
        "device": str(data.get("device") or "unknown"),
        "stratum": str(data.get("stratum") or "unknown"),
        "fov_mm": float(fov) if fov is not None else float(SCALE_MM),
        "px_per_mm": float(px) if px is not None else float(PX_PER_MM_FALLBACK),
        "path": str(path),
    }


def _contour_to_points(contour: np.ndarray) -> np.ndarray:
    pts = contour.reshape(-1, 2).astype(np.float64)
    if len(pts) >= 2 and np.allclose(pts[0], pts[-1]):
        pts = pts[:-1]
    return pts


def extract_all_external_contours(mask_bool: np.ndarray) -> List[np.ndarray]:
    """All RETR_EXTERNAL contours as (N, 2) float. Export masks are multi-CC."""
    u8 = (mask_bool.astype(np.uint8)) * 255
    contours, _ = cv2.findContours(u8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    return [_contour_to_points(c) for c in contours if len(c) > 0]


def densify_contour(points: np.ndarray, spacing: float = DENSIFY_SPACING_PX) -> np.ndarray:
    """Resample a closed polyline to ~spacing px arc-length (Phase 0 decision)."""
    pts = np.asarray(points, dtype=np.float64)
    if len(pts) < 3:
        return pts
    closed = np.vstack([pts, pts[0]])
    segs = np.diff(closed, axis=0)
    lengths = np.sqrt((segs**2).sum(axis=1))
    total = float(lengths.sum())
    if total < spacing:
        return pts
    cum = np.concatenate([[0.0], np.cumsum(lengths)])
    n_out = max(int(np.round(total / spacing)), 3)
    samples = np.linspace(0.0, total, n_out, endpoint=False)
    out = np.empty((n_out, 2), dtype=np.float64)
    j = 0
    for i, s in enumerate(samples):
        while j + 1 < len(cum) and cum[j + 1] < s:
            j += 1
        span = lengths[j] if lengths[j] > 1e-9 else 1.0
        t = (s - cum[j]) / span
        out[i] = closed[j] + t * (closed[j + 1] - closed[j])
    return out


def _sample_mask(mask: np.ndarray, xy: np.ndarray) -> np.ndarray:
    h, w = mask.shape[:2]
    ix = np.clip(np.round(xy[:, 0]).astype(int), 0, w - 1)
    iy = np.clip(np.round(xy[:, 1]).astype(int), 0, h - 1)
    return mask[iy, ix]


def outward_normals(points: np.ndarray, interior_mask: np.ndarray) -> np.ndarray:
    """Unit normals pointing out of this contour's interior (one CC)."""
    n = len(points)
    if n < 3:
        return np.zeros((n, 2), dtype=np.float64)
    prev = np.roll(points, 1, axis=0)
    nxt = np.roll(points, -1, axis=0)
    tangent = nxt - prev
    cand = np.stack([-tangent[:, 1], tangent[:, 0]], axis=1)
    norms = np.sqrt((cand**2).sum(axis=1, keepdims=True))
    norms = np.maximum(norms, 1e-9)
    cand = cand / norms
    inside_pos = _sample_mask(interior_mask, points + cand * 1.0)
    inside_neg = _sample_mask(interior_mask, points - cand * 1.0)
    flip = inside_pos & np.logical_not(inside_neg)
    both_out = np.logical_not(inside_pos) & np.logical_not(inside_neg)
    centroid = points.mean(axis=0)
    radial = points - centroid
    dots = (cand * radial).sum(axis=1)
    flip = flip | (both_out & (dots < 0))
    cand[flip] *= -1.0
    return cand


def snap_all_contours(
    contours: List[np.ndarray],
    color_mask: np.ndarray,
    displacement_px: int,
    shape: Tuple[int, int],
) -> Tuple[np.ndarray, np.ndarray, int]:
    """
    Densify and snap every external contour. Union of filled polygons.
    Tiny contours that cannot form a polygon keep their original fill.
    Returns (refined_bool, all_move_distances, n_densified_points).
    """
    refined = np.zeros(shape, dtype=bool)
    all_moves: List[np.ndarray] = []
    n_pts = 0
    for raw in contours:
        if len(raw) < 3:
            refined |= fill_contour(raw, shape)
            continue
        dens = densify_contour(raw, DENSIFY_SPACING_PX)
        if len(dens) < 3:
            refined |= fill_contour(raw, shape)
            continue
        own = fill_contour(raw, shape)
        if not np.any(own):
            own = fill_contour(dens, shape)
        normals = outward_normals(dens, own)
        if displacement_px <= 0:
            moved, moves = dens, np.zeros(len(dens), dtype=np.float64)
        else:
            moved, moves = snap_contour_to_colormask(
                dens, normals, color_mask, displacement_px
            )
        filled = fill_contour(moved, shape)
        if not np.any(filled):
            filled = own
        refined |= filled
        all_moves.append(moves)
        n_pts += int(len(dens))
    if all_moves:
        move_d = np.concatenate(all_moves)
    else:
        move_d = np.zeros(0, dtype=np.float64)
    return refined, move_d, n_pts


def snap_contour_to_colormask(
    points: np.ndarray,
    normals: np.ndarray,
    color_mask: np.ndarray,
    displacement_px: int,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Move each point at most displacement_px along ±normal to the nearest
    ColorMask pixel. Tie at the same |t|: prefer inward (conservative).
    Already-on-ColorMask points stay. Returns (moved_points, move_distances).
    """
    n = len(points)
    moved = points.copy()
    moves = np.zeros(n, dtype=np.float64)
    if displacement_px <= 0 or n == 0:
        return moved, moves
    h, w = color_mask.shape[:2]

    def on_cm(xy: np.ndarray) -> bool:
        ix = int(round(float(xy[0])))
        iy = int(round(float(xy[1])))
        if 0 <= iy < h and 0 <= ix < w:
            return bool(color_mask[iy, ix])
        return False

    for i in range(n):
        p = points[i]
        nrm = normals[i]
        if nrm[0] == 0.0 and nrm[1] == 0.0:
            continue
        if on_cm(p):
            continue
        hit_q = None
        hit_t = 0
        for t in range(1, int(displacement_px) + 1):
            # inward first on a tie (same t)
            for sign in (-1, 1):
                q = p + sign * t * nrm
                if on_cm(q):
                    hit_q = q
                    hit_t = t
                    break
            if hit_q is not None:
                break
        if hit_q is None:
            continue
        q_round = np.array(
            [round(float(hit_q[0])), round(float(hit_q[1]))], dtype=np.float64
        )
        actual = float(np.sqrt(((q_round - p) ** 2).sum()))
        if actual > float(displacement_px) + 1e-6:
            # hard cap after rounding
            scale = float(displacement_px) / actual
            q_round = np.round(p + (q_round - p) * scale)
            actual = float(np.sqrt(((q_round - p) ** 2).sum()))
        moved[i] = q_round
        moves[i] = actual
    return moved, moves


def fill_contour(points: np.ndarray, shape: Tuple[int, int]) -> np.ndarray:
    mask = np.zeros(shape, dtype=np.uint8)
    if len(points) < 3:
        return mask.astype(bool)
    cv2.fillPoly(mask, [np.round(points).astype(np.int32)], 255)
    return mask > 0


def _blend(
    bgr: np.ndarray, mask: np.ndarray, color_bgr: Tuple[int, int, int], alpha: float
) -> None:
    sel = mask.astype(bool)
    if not np.any(sel):
        return
    c = np.array(color_bgr, dtype=np.float64)
    bgr[sel] = (bgr[sel].astype(np.float64) * (1.0 - alpha) + c * alpha).astype(np.uint8)


def _outline(
    bgr: np.ndarray,
    mask: np.ndarray,
    color_bgr: Tuple[int, int, int],
    thickness: int = 1,
) -> None:
    contours, _ = cv2.findContours(
        mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    if contours:
        cv2.drawContours(bgr, contours, -1, color_bgr, thickness)


def _layer_overlay(
    image: np.ndarray,
    mask: np.ndarray,
    color_bgr: Tuple[int, int, int],
    alpha: float = 0.55,
) -> np.ndarray:
    out = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    _blend(out, mask, color_bgr, alpha)
    _outline(out, mask, color_bgr, 1)
    return out


def _delta_overlay(
    image: np.ndarray, added: np.ndarray, removed: np.ndarray
) -> np.ndarray:
    out = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    _blend(out, added, COLOR_ADDED, 0.75)
    _blend(out, removed, COLOR_REMOVED, 0.70)
    _outline(out, added, COLOR_ADDED, 1)
    _outline(out, removed, COLOR_REMOVED, 1)
    cv2.putText(
        out,
        "orange=added  red=removed",
        (8, 16),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.38,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    return out


def _composite_overlay(
    image: np.ndarray,
    user: np.ndarray,
    color1: np.ndarray,
    added: np.ndarray,
    removed: np.ndarray,
    refined: np.ndarray,
) -> np.ndarray:
    out = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    _blend(out, user, COLOR_USER, 0.18)
    _blend(out, color1, COLOR_COLORMASK, 0.45)
    _blend(out, added, COLOR_ADDED, 0.70)
    _blend(out, removed, COLOR_REMOVED, 0.65)
    _outline(out, user, COLOR_USER, 1)
    _outline(out, refined, COLOR_REFINED, 1)
    cv2.putText(
        out,
        "green=user  cyan=ColorMask  orange=add  red=remove  magenta=refined",
        (8, 16),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.36,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    return out


def _label(tile: np.ndarray, title: str) -> np.ndarray:
    vis = tile.copy()
    cv2.putText(
        vis,
        title,
        (8, 18),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    return vis


def _panel(
    image: np.ndarray,
    user: np.ndarray,
    color1: np.ndarray,
    added: np.ndarray,
    removed: np.ndarray,
    refined: np.ndarray,
) -> np.ndarray:
    tiles = [
        _label(_layer_overlay(image, user, COLOR_USER), "1 user_roi"),
        _label(_layer_overlay(image, color1, COLOR_COLORMASK), "2 ColorMask Pass-1"),
        _label(_delta_overlay(image, added, removed), "3 nudge add/remove"),
        _label(_layer_overlay(image, refined, COLOR_REFINED), "4 refined (metrics)"),
    ]
    top = np.hstack([tiles[0], tiles[1]])
    bot = np.hstack([tiles[2], tiles[3]])
    return np.vstack([top, bot])


def _vs_d_panel(
    image: np.ndarray,
    added_e: np.ndarray,
    refined_e: np.ndarray,
    d_outward_path: Path,
    d_refined_path: Path,
) -> Optional[np.ndarray]:
    if not d_outward_path.is_file() or not d_refined_path.is_file():
        return None
    d_out = cv2.imread(str(d_outward_path), cv2.IMREAD_COLOR)
    d_ref = cv2.imread(str(d_refined_path), cv2.IMREAD_COLOR)
    if d_out is None or d_ref is None:
        return None
    e_add = _label(_layer_overlay(image, added_e, COLOR_ADDED, 0.75), "E added (nudge)")
    e_ref = _label(_layer_overlay(image, refined_e, COLOR_REFINED), "E refined")
    d_out = _label(d_out, "D outward-added (same um)")
    d_ref = _label(d_ref, "D refined (same um)")
    top = np.hstack([e_add, d_out])
    bot = np.hstack([e_ref, d_ref])
    return np.vstack([top, bot])


def _save_qa(
    qa_dir: Path,
    prefix: str,
    image: np.ndarray,
    user: np.ndarray,
    color1: np.ndarray,
    added: np.ndarray,
    removed: np.ndarray,
    refined: np.ndarray,
    vs_d: Optional[np.ndarray],
) -> None:
    qa_dir.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(qa_dir / f"{prefix}_user_roi.png"), _layer_overlay(image, user, COLOR_USER))
    cv2.imwrite(
        str(qa_dir / f"{prefix}_colormask.png"),
        _layer_overlay(image, color1, COLOR_COLORMASK),
    )
    cv2.imwrite(
        str(qa_dir / f"{prefix}_nudge_added.png"),
        _layer_overlay(image, added, COLOR_ADDED, 0.75),
    )
    cv2.imwrite(
        str(qa_dir / f"{prefix}_nudge_removed.png"),
        _layer_overlay(image, removed, COLOR_REMOVED, 0.70),
    )
    cv2.imwrite(
        str(qa_dir / f"{prefix}_nudge_delta.png"),
        _delta_overlay(image, added, removed),
    )
    cv2.imwrite(
        str(qa_dir / f"{prefix}_refined.png"),
        _layer_overlay(image, refined, COLOR_REFINED),
    )
    cv2.imwrite(
        str(qa_dir / f"{prefix}_overlay.png"),
        _composite_overlay(image, user, color1, added, removed, refined),
    )
    cv2.imwrite(
        str(qa_dir / f"{prefix}_panel.png"),
        _panel(image, user, color1, added, removed, refined),
    )
    if vs_d is not None:
        cv2.imwrite(str(qa_dir / f"{prefix}_vs_d.png"), vs_d)


def _max_dist_from_mask(pixels: np.ndarray, source: np.ndarray) -> float:
    """Max distance (px) of True pixels from the nearest True in source."""
    if not np.any(pixels):
        return 0.0
    inv = np.logical_not(source).astype(np.uint8)
    dist_out = cv2.distanceTransform(inv * 255, cv2.DIST_L2, 3)
    return float(dist_out[pixels].max())


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

    raw_contours = extract_all_external_contours(user)
    n_raw = sum(len(c) for c in raw_contours)
    print(
        f"  contour {grader} {case_id}: n_cc={len(raw_contours)} "
        f"NONE_pts={n_raw} densify_spacing={DENSIFY_SPACING_PX} px"
    )

    runs: List[DisplacementRun] = []
    for displacement_um in displacements_um:
        dpx = displacement_px_from_um(displacement_um, px_per_mm)
        if displacement_um == 0:
            refined = user.copy()
            _, move_d, n_contour = snap_all_contours(
                raw_contours, color1, 0, (h, w)
            )
            move_d = np.zeros_like(move_d)
        else:
            print(
                f"  snap {grader} {case_id} d={displacement_um}um ({dpx}px) "
                f"n_cc={len(raw_contours)} ..."
            )
            refined, move_d, n_contour = snap_all_contours(
                raw_contours, color1, dpx, (h, w)
            )

        added = np.logical_and(refined, np.logical_not(user))
        removed = np.logical_and(user, np.logical_not(refined))
        n_refined = int(refined.sum())
        n_vsl = int(np.logical_and(bin_bool, refined).sum())
        mnv = _px_to_mm2(n_refined, w, scale_mm)
        vsl = _px_to_mm2(n_vsl, w, scale_mm)
        dens = (vsl / mnv) if mnv > 0 else 0.0
        max_added = _max_dist_from_mask(added, user)

        prefix = f"{grader}_{slug}_d{displacement_um:02d}um"
        d_out_path = METHOD_D_QA / f"{grader}_{slug}_r{displacement_um:02d}um_outward_added.png"
        d_ref_path = METHOD_D_QA / f"{grader}_{slug}_r{displacement_um:02d}um_refined.png"
        vs_d = _vs_d_panel(image, added, refined, d_out_path, d_ref_path)
        _save_qa(qa_dir, prefix, image, user, color1, added, removed, refined, vs_d)

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
                n_external_cc=len(raw_contours),
                n_contour_pts=n_contour,
                n_moved=int(np.count_nonzero(move_d > 0)),
                mean_move_px=float(move_d.mean()) if len(move_d) else 0.0,
                max_move_px=float(move_d.max()) if len(move_d) else 0.0,
                n_added=int(added.sum()),
                n_removed=int(removed.sum()),
                max_added_dist_px=max_added,
                n_refined=n_refined,
                n_vsl=n_vsl,
                mnv_mm2=mnv,
                vsl_mm2=vsl,
                dens=dens,
            )
        )
    return runs


def _fmt(x: Optional[float], nd: int = 4) -> str:
    if x is None:
        return ""
    return f"{x:.{nd}f}"


def _method_a_rpd(
    g1_rows: Dict[str, Dict[str, str]], g2_rows: Dict[str, Dict[str, str]]
) -> Dict[Tuple[str, str], float]:
    out: Dict[Tuple[str, str], float] = {}
    for stem, r1 in g1_rows.items():
        r2 = g2_rows.get(stem)
        if r2 is None:
            continue
        cid = _case_id(r1["File"])
        for metric in ("MNV Area (mm2)", "Vsl Area (mm2)"):
            val = rpd_pct(float(r1[metric]), float(r2[metric]))
            if val is not None:
                out[(cid, metric)] = val
    return out


def _method_b_rpd(path: Path) -> Dict[Tuple[str, str], float]:
    out: Dict[Tuple[str, str], float] = {}
    if not path.is_file():
        return out
    for row in _read_csv(path):
        if row.get("metric_group") != "area":
            continue
        metric = row["metric"]
        if metric not in ("MNV Area (mm2)", "Vsl Area (mm2)"):
            continue
        raw = row.get("rpd_method_b_pct") or ""
        if raw:
            out[(row["case"], metric)] = float(raw)
    return out


def _method_d_rpd(path: Path) -> Dict[Tuple[str, int], Dict[str, str]]:
    out: Dict[Tuple[str, int], Dict[str, str]] = {}
    if not path.is_file():
        return out
    for row in _read_csv(path):
        key = (row["case"], int(row["radius_um"]))
        out[key] = row
    return out


def write_outputs(
    runs: List[DisplacementRun],
    method_a: Dict[Tuple[str, str], float],
    method_b: Dict[Tuple[str, str], float],
    method_d: Dict[Tuple[str, int], Dict[str, str]],
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
                    "g1_refined_px": str(g1.n_refined),
                    "g2_refined_px": str(g2.n_refined),
                    "g1_user_px": str(g1.n_user),
                    "g2_user_px": str(g2.n_user),
                    "g1_color1_px": str(g1.n_color1),
                    "g2_color1_px": str(g2.n_color1),
                    "method_a_mnv_rpd": _fmt(a_mnv),
                    "method_a_vsl_rpd": _fmt(a_vsl),
                    "method_b_mnv_rpd": _fmt(b_mnv),
                    "method_b_vsl_rpd": _fmt(b_vsl),
                    "method_d_mnv_rpd": drow.get("mnv_rpd_pct", ""),
                    "method_d_vsl_rpd": drow.get("vsl_rpd_pct", ""),
                    "method_d_mnv_adopted": drow.get("mnv_adopted", ""),
                    "method_d_g1_mnv_mm2": drow.get("g1_mnv_mm2", ""),
                    "method_d_g2_mnv_mm2": drow.get("g2_mnv_mm2", ""),
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
        "densify": True,
        "move_rule": "bounded_normal_snap_to_pass1_colormask",
        "sign_flip_rejected": True,
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

    sweep_rows = write_outputs(runs, method_a, method_b, method_d, OUT_DIR)

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

    print("\n=== Method E displacement sweep (MNV / Vsl RPD) vs Method D ===")
    print(
        f"{'case':16} {'d_um':>5} {'d_px':>4} "
        f"{'E_MNV':>8} {'E_Vsl':>8} {'E_ad':>5} "
        f"{'D_MNV':>8} {'D_ad':>5} "
        f"{'g1_mv':>6} {'g2_mv':>6} "
        f"{'g1_add':>7} {'g2_add':>7}"
    )
    for row in sweep_rows:
        print(
            f"{row['case']:16} {row['displacement_um']:>5} {row['displacement_px']:>4} "
            f"{row['mnv_rpd_pct']:>8} {row['vsl_rpd_pct']:>8} {row['mnv_adopted']:>5} "
            f"{row['method_d_mnv_rpd']:>8} {row['method_d_mnv_adopted']:>5} "
            f"{row['g1_mean_move_px']:>6} {row['g2_mean_move_px']:>6} "
            f"{row['g1_added_px']:>7} {row['g2_added_px']:>7}"
        )

    print(f"\nWrote {OUT_DIR / 'displacement_sweep_results.csv'}")
    print(f"QA images: {QA_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
