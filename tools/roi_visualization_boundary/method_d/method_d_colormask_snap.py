#!/usr/bin/env python3
"""
Method D (pilot verification only): snap a hand-drawn ROI onto ColorMask.

Pilot only. No production flag, no default ON, no intelligent_roi,
no MNVPipeline.analyze, no Method C enclosure-as-ROI.

Pipeline (per grader × case)
----------------------------
1. user_roi = hand-drawn mask
2. Full-field vessel binary via ``_detect_vessels`` (preprocess_mnv, no ROI clip)
3. Pass-1 RGB with lesion_mask=user_roi, add_overlays=False
4. ColorMask₁ = locked Method B extract
     Li(GaussianBlur(unweighted_mean(|raw-rgb_viz|), σ=1.0))
5. Inward core = ColorMask₁ ∩ user_roi
     (verified Method B inward; not Method B' border-erase)
6. If radius_um > 0:
     radius_px = round_half_up(radius_um * px_per_mm / 1000)
     seed = disk-dilate(user_roi, radius_px)
     Pass-2 RGB with lesion_mask=seed
     ColorMask₂ = extract_color_mask(raw, rgb₂)
     outward_added = (ColorMask₂ ∩ seed) − user_roi
     Hard cap: everything stays inside seed.
7. refined = ((ColorMask₁ ∩ user_roi) ∪ (ColorMask₂ ∩ seed)) ∩ seed
8. MNV Area = refined px × (scale_mm / width)²
9. Vsl Area = (binary ∩ refined) px × scale
10. Density = Vsl / MNV  (reported; ColorMask is not the official area)

outward_added subtracts **user_roi**, not the inward core. Pixels inside the
hand ROI that appear only on Pass-2 can still enter ``refined`` via
ColorMask₂ ∩ seed, but they are not painted as outward-added (orange).

Radius 0 is inward-only (Method-B-like control): no Pass-2, outward empty,
refined = ColorMask₁ ∩ user_roi.
"""

from __future__ import annotations

import csv
import json
import sys
from dataclasses import dataclass, field
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
RADIUS_UM = (0, 5, 10, 20, 30, 50)
PX_PER_MM_FALLBACK = 150.0
ADOPT_PCT = 20.0

# BGR (cv2.imwrite)
COLOR_USER = (0, 200, 0)
COLOR_INWARD = (220, 220, 0)
COLOR_OUTWARD = (0, 140, 255)
COLOR_REFINED = (255, 0, 255)


@dataclass
class IsolatedCC:
    cc_id: int
    area_px: int
    area_mm2: float


@dataclass
class RadiusRun:
    case_id: str
    grader: str
    stem: str
    radius_um: int
    radius_px: int
    px_per_mm: float
    scale_mm: float
    device: str
    stratum: str
    fov_mm: float
    n_user: int
    n_color1: int
    n_inward: int
    n_color2: int
    n_outward: int
    n_refined: int
    n_vsl: int
    mnv_mm2: float
    vsl_mm2: float
    dens: float
    isolated: List[IsolatedCC] = field(default_factory=list)


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
    """Nearest int, ties away from zero for x>=0. Min 0."""
    if x <= 0:
        return 0
    return int(np.floor(float(x) + 0.5))


def radius_px_from_um(radius_um: float, px_per_mm: float) -> int:
    return _round_half_up(float(radius_um) * float(px_per_mm) / 1000.0)


def _disk_kernel(radius_px: int) -> np.ndarray:
    k = 2 * int(radius_px) + 1
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))


def dilate_roi(roi_bool: np.ndarray, radius_px: int) -> np.ndarray:
    if radius_px <= 0:
        return roi_bool.astype(bool)
    return cv2.dilate(roi_bool.astype(np.uint8), _disk_kernel(radius_px), iterations=1) > 0


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


def _as_u8(mask_bool: np.ndarray) -> np.ndarray:
    return (mask_bool.astype(np.uint8)) * 255


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


def _composite_overlay(
    image: np.ndarray,
    user: np.ndarray,
    inward: np.ndarray,
    outward: np.ndarray,
    refined: np.ndarray,
) -> np.ndarray:
    out = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    _blend(out, user, COLOR_USER, 0.22)
    _blend(out, inward, COLOR_INWARD, 0.50)
    _blend(out, outward, COLOR_OUTWARD, 0.70)
    _outline(out, user, COLOR_USER, 1)
    _outline(out, refined, COLOR_REFINED, 1)
    legend = "green=user  cyan=inward  orange=outward-added  magenta=refined"
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
    return out


def _panel(
    image: np.ndarray,
    user: np.ndarray,
    inward: np.ndarray,
    outward: np.ndarray,
    refined: np.ndarray,
) -> np.ndarray:
    tiles = [
        (_layer_overlay(image, user, COLOR_USER), "1 user_roi"),
        (_layer_overlay(image, inward, COLOR_INWARD), "2 inward ColorMask"),
        (_layer_overlay(image, outward, COLOR_OUTWARD), "3 outward-added"),
        (_layer_overlay(image, refined, COLOR_REFINED), "4 refined (metrics)"),
    ]
    labeled: List[np.ndarray] = []
    for tile, title in tiles:
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
        labeled.append(vis)
    top = np.hstack([labeled[0], labeled[1]])
    bot = np.hstack([labeled[2], labeled[3]])
    return np.vstack([top, bot])


def _save_qa(
    qa_dir: Path,
    prefix: str,
    image: np.ndarray,
    user: np.ndarray,
    inward: np.ndarray,
    outward: np.ndarray,
    refined: np.ndarray,
) -> None:
    qa_dir.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(qa_dir / f"{prefix}_user_roi.png"), _layer_overlay(image, user, COLOR_USER))
    cv2.imwrite(
        str(qa_dir / f"{prefix}_inward.png"), _layer_overlay(image, inward, COLOR_INWARD)
    )
    cv2.imwrite(
        str(qa_dir / f"{prefix}_outward_added.png"),
        _layer_overlay(image, outward, COLOR_OUTWARD, 0.75),
    )
    cv2.imwrite(
        str(qa_dir / f"{prefix}_refined.png"),
        _layer_overlay(image, refined, COLOR_REFINED),
    )
    cv2.imwrite(
        str(qa_dir / f"{prefix}_overlay.png"),
        _composite_overlay(image, user, inward, outward, refined),
    )
    cv2.imwrite(
        str(qa_dir / f"{prefix}_panel.png"),
        _panel(image, user, inward, outward, refined),
    )


def isolated_fragments(
    outward: np.ndarray, core: np.ndarray, width: int, scale_mm: float
) -> List[IsolatedCC]:
    """8-connected CCs of outward-added that do not touch dilate(core, 1 px)."""
    if not np.any(outward):
        return []
    n_labels, labels = cv2.connectedComponents(outward.astype(np.uint8), connectivity=8)
    core_touch = (
        cv2.dilate(core.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=1) > 0
    )
    out: List[IsolatedCC] = []
    for lab in range(1, n_labels):
        cc = labels == lab
        if np.any(np.logical_and(cc, core_touch)):
            continue
        area_px = int(cc.sum())
        out.append(
            IsolatedCC(
                cc_id=lab,
                area_px=area_px,
                area_mm2=_px_to_mm2(area_px, width, scale_mm),
            )
        )
    return out


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


def run_grader_case(
    stem: str,
    grader: str,
    export_root: Path,
    csv_row: Dict[str, str],
    radii_um: Tuple[int, ...],
    qa_dir: Path,
) -> List[RadiusRun]:
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

    runs: List[RadiusRun] = []
    for radius_um in radii_um:
        rpx = radius_px_from_um(radius_um, px_per_mm)
        seed = dilate_roi(user, rpx)
        if radius_um > 0:
            print(f"  pass-2 RGB {grader} {case_id} r={radius_um}um ({rpx}px) ...")
            rgb2 = _make_rgb(image, binary, _as_u8(seed))
            ref2 = np.logical_and(bin_bool, seed)
            color2 = extract_color_mask(image, rgb2, ref2).mask.astype(bool)
            color2_in_seed = np.logical_and(color2, seed)
            outward = np.logical_and(color2_in_seed, np.logical_not(user))
            refined = np.logical_and(np.logical_or(inward, color2_in_seed), seed)
            n_color2 = int(color2.sum())
        else:
            color2_in_seed = np.zeros_like(user)
            outward = np.zeros_like(user)
            refined = np.logical_and(inward, seed)
            n_color2 = 0

        n_refined = int(refined.sum())
        n_vsl = int(np.logical_and(bin_bool, refined).sum())
        mnv = _px_to_mm2(n_refined, w, scale_mm)
        vsl = _px_to_mm2(n_vsl, w, scale_mm)
        dens = (vsl / mnv) if mnv > 0 else 0.0
        isolated = isolated_fragments(outward, inward, w, scale_mm)

        prefix = f"{grader}_{slug}_r{radius_um:02d}um"
        _save_qa(qa_dir, prefix, image, user, inward, outward, refined)

        runs.append(
            RadiusRun(
                case_id=case_id,
                grader=grader,
                stem=stem,
                radius_um=int(radius_um),
                radius_px=rpx,
                px_per_mm=px_per_mm,
                scale_mm=scale_mm,
                device=str(meta["device"]),
                stratum=str(meta["stratum"]),
                fov_mm=float(meta["fov_mm"]),
                n_user=int(user.sum()),
                n_color1=int(color1.sum()),
                n_inward=int(inward.sum()),
                n_color2=n_color2,
                n_outward=int(outward.sum()),
                n_refined=n_refined,
                n_vsl=n_vsl,
                mnv_mm2=mnv,
                vsl_mm2=vsl,
                dens=dens,
                isolated=isolated,
            )
        )
    return runs


def _fmt(x: Optional[float], nd: int = 4) -> str:
    if x is None:
        return ""
    return f"{x:.{nd}f}"


def write_outputs(
    runs: List[RadiusRun],
    method_a: Dict[Tuple[str, str], float],
    method_b: Dict[Tuple[str, str], float],
    out_dir: Path,
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    by: Dict[Tuple[str, int], Dict[str, RadiusRun]] = {}
    for run in runs:
        by.setdefault((run.case_id, run.radius_um), {})[run.grader] = run

    sweep_rows: List[Dict[str, str]] = []
    frag_rows: List[Dict[str, str]] = []

    for case_id in CASE_ORDER:
        for radius_um in RADIUS_UM:
            pair = by.get((case_id, radius_um), {})
            g1, g2 = pair.get("g1"), pair.get("g2")
            if g1 is None or g2 is None:
                continue
            mnv_rpd = rpd_pct(g1.mnv_mm2, g2.mnv_mm2)
            vsl_rpd = rpd_pct(g1.vsl_mm2, g2.vsl_mm2)
            dens_rpd = rpd_pct(g1.dens, g2.dens)
            g1_iso_n = len(g1.isolated)
            g2_iso_n = len(g2.isolated)
            g1_iso_px = sum(c.area_px for c in g1.isolated)
            g2_iso_px = sum(c.area_px for c in g2.isolated)
            g1_iso_mm = sum(c.area_mm2 for c in g1.isolated)
            g2_iso_mm = sum(c.area_mm2 for c in g2.isolated)
            a_mnv = method_a.get((case_id, "MNV Area (mm2)"))
            a_vsl = method_a.get((case_id, "Vsl Area (mm2)"))
            b_mnv = method_b.get((case_id, "MNV Area (mm2)"))
            b_vsl = method_b.get((case_id, "Vsl Area (mm2)"))
            sweep_rows.append(
                {
                    "case": case_id,
                    "radius_um": str(radius_um),
                    "radius_px": str(g1.radius_px),
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
                    "g1_refined_px": str(g1.n_refined),
                    "g2_refined_px": str(g2.n_refined),
                    "g1_inward_px": str(g1.n_inward),
                    "g2_inward_px": str(g2.n_inward),
                    "g1_outward_px": str(g1.n_outward),
                    "g2_outward_px": str(g2.n_outward),
                    "g1_isolated_cc": str(g1_iso_n),
                    "g2_isolated_cc": str(g2_iso_n),
                    "isolated_cc_sum": str(g1_iso_n + g2_iso_n),
                    "g1_isolated_px": str(g1_iso_px),
                    "g2_isolated_px": str(g2_iso_px),
                    "isolated_px_sum": str(g1_iso_px + g2_iso_px),
                    "g1_isolated_mm2": f"{g1_iso_mm:.8g}",
                    "g2_isolated_mm2": f"{g2_iso_mm:.8g}",
                    "isolated_mm2_sum": f"{g1_iso_mm + g2_iso_mm:.8g}",
                    "method_a_mnv_rpd": _fmt(a_mnv),
                    "method_a_vsl_rpd": _fmt(a_vsl),
                    "method_b_mnv_rpd": _fmt(b_mnv),
                    "method_b_vsl_rpd": _fmt(b_vsl),
                    "g1_device": g1.device,
                    "g2_device": g2.device,
                    "g1_px_per_mm": f"{g1.px_per_mm:.6g}",
                    "g2_px_per_mm": f"{g2.px_per_mm:.6g}",
                }
            )
            for grader, run in (("g1", g1), ("g2", g2)):
                for cc in run.isolated:
                    frag_rows.append(
                        {
                            "case": case_id,
                            "grader": grader,
                            "radius_um": str(radius_um),
                            "cc_id": str(cc.cc_id),
                            "area_px": str(cc.area_px),
                            "area_mm2": f"{cc.area_mm2:.8g}",
                        }
                    )

    out_dir.mkdir(parents=True, exist_ok=True)
    sweep_path = out_dir / "radius_sweep_results.csv"
    with sweep_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(sweep_rows[0].keys()))
        writer.writeheader()
        writer.writerows(sweep_rows)

    frag_path = out_dir / "isolated_fragments.csv"
    frag_fields = ["case", "grader", "radius_um", "cc_id", "area_px", "area_mm2"]
    with frag_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=frag_fields)
        writer.writeheader()
        writer.writerows(frag_rows)

    devices = sorted(
        {
            (r.grader, r.case_id, r.device, r.stratum, r.fov_mm, r.px_per_mm)
            for r in runs
        }
    )
    summary = {
        "n_runs": len(runs),
        "radii_um": list(RADIUS_UM),
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
    return sweep_rows, frag_rows


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

    runs: List[RadiusRun] = []
    for stem in stems:
        print(f"\n=== {stem} / g1 ===")
        runs.extend(
            run_grader_case(
                stem, "g1", G1_DIR / "export", g1_rows[stem], RADIUS_UM, QA_DIR
            )
        )
        print(f"=== {stem} / g2 ===")
        runs.extend(
            run_grader_case(
                stem, "g2", G2_DIR / "export", g2_rows[stem], RADIUS_UM, QA_DIR
            )
        )

    sweep_rows, frag_rows = write_outputs(runs, method_a, method_b, OUT_DIR)

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

    print("\n=== Method D radius sweep (MNV / Vsl RPD) ===")
    print(
        f"{'case':16} {'r_um':>5} {'r_px':>4} "
        f"{'MNV_RPD':>8} {'Vsl_RPD':>8} "
        f"{'MNV_ad':>6} {'Vsl_ad':>6} "
        f"{'iso_n':>5} {'iso_mm2':>8}"
    )
    for row in sweep_rows:
        print(
            f"{row['case']:16} {row['radius_um']:>5} {row['radius_px']:>4} "
            f"{row['mnv_rpd_pct']:>8} {row['vsl_rpd_pct']:>8} "
            f"{row['mnv_adopted']:>6} {row['vsl_adopted']:>6} "
            f"{row['isolated_cc_sum']:>5} {row['isolated_mm2_sum']:>8}"
        )

    print(f"\nIsolated fragments (rows): {len(frag_rows)}")
    print(f"Wrote {OUT_DIR / 'radius_sweep_results.csv'}")
    print(f"Wrote {OUT_DIR / 'isolated_fragments.csv'}")
    print(f"QA images: {QA_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
