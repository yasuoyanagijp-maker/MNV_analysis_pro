#!/usr/bin/env python3
"""
Method B: Fiji-style difference extraction on ARIAKE RGB visualization.

ColorMask = Li(GaussianBlur(grayscale(|raw - rgb_viz|), sigma=1.0))

Then, replacing the hand-drawn ROI:
  MNV Area    = ColorMask px * (scale_mm / width)^2
  Vsl Area    = (ColorMask ∩ vessel_binary) px * scale
  Vsl Density = Vsl Area / MNV Area

Method A RPD is read from the existing integrated CSV (not recomputed).
"""

from __future__ import annotations

import csv
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from ariake_octa.mnv.color_mask import (  # noqa: E402
    ColorMaskChoice,
    extract_color_mask,
)
from core.mnv_pipeline import FILTER_PARAMS_SMALL, MNVPipeline  # noqa: E402
from core.roi_manager import ROIEnclosure  # noqa: E402
from tools.reading_center_rpd.compute_adopted_from_dual_csv import (  # noqa: E402
    rpd_pct,
)
from tools.roi_visualization_boundary.lib.cases import (  # noqa: E402
    G1_CSV,
    G1_DIR,
    G2_CSV,
    G2_DIR,
    INTEGRATED_RECHECK,
    SCALE_MM,
)
from tools.roi_visualization_boundary.lib.io import (  # noqa: E402
    case_id as _case_id,
    detect_vessels as _detect_vessels,
    find_image as _find_image,
    find_mask as _find_mask,
    index_by_stem as _index_by_stem,
    load_gray as _load_gray,
    load_roi as _load_roi,
    make_rgb as _make_rgb,
    read_csv as _read_csv,
)
from utils.mnv_imagej_csv import _PIPELINE_TO_IMAGEJ  # noqa: E402

AREA_METRICS = (
    "MNV Area (mm2)",
    "Vsl Area (mm2)",
    "Vsl Density (Vessel Area/MNV (%))",
)
TOPOLOGY_METRICS = (
    "Junction Density (n/mm)",
    "End Pts Density (n/mm)",
    "Multi-Branch Pts Density (n/mm)",
    "Branch Density (n/mm)",
)
CENTER_PERIPHERY_METRICS = (
    "Center Branches",
    "Center Total Length (mm)",
    "Center Tortuosity",
    "Center FD (Box-Counting)",
    "Center Euler Number",
    "Center Loop Number",
    "Periphery Branches",
    "Periphery Total Length (mm)",
    "Periphery Tortuosity",
    "Periphery FD (Box-Counting)",
    "Periphery Euler Number",
    "Periphery Loop Number",
)
METRICS = AREA_METRICS + TOPOLOGY_METRICS + CENTER_PERIPHERY_METRICS
METRIC_GROUP = {
    **{m: "area" for m in AREA_METRICS},
    **{m: "topology" for m in TOPOLOGY_METRICS},
    **{m: "center_periphery" for m in CENTER_PERIPHERY_METRICS},
}


@dataclass
class CaseRun:
    case_id: str
    grader: str
    n_roi: int
    n_binary_in_roi: int
    n_binary_outside_roi: int
    n_color: int
    n_enclose: int
    n_vsl_b: int
    n_vsl_c: int
    mnv_a_csv: float
    vsl_a_csv: float
    dens_a_csv: float
    mnv_a_repro: float
    vsl_a_repro: float
    dens_a_repro: float
    mnv_b: float
    vsl_b: float
    dens_b: float
    mnv_c: float
    vsl_c: float
    dens_c: float
    color_dice_vs_vsl: float
    color_outside_roi: int
    choice: ColorMaskChoice
    metrics_a: Dict[str, float] = field(default_factory=dict)
    metrics_b: Dict[str, float] = field(default_factory=dict)
    metrics_c: Dict[str, float] = field(default_factory=dict)


def _f(row: Dict[str, str], key: str) -> float:
    return float(row[key])


def _px_to_mm2(n_px: int, width: int) -> float:
    return float(n_px) * (SCALE_MM / width) ** 2


def _csv_metrics(row: Dict[str, str]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for metric in METRICS:
        try:
            out[metric] = _f(row, metric)
        except (KeyError, ValueError, TypeError):
            continue
    return out


def _pipeline_metrics(image_path: Path, roi_u8: np.ndarray) -> Dict[str, float]:
    pipeline = MNVPipeline(
        scale_mm=SCALE_MM,
        save_stages=False,
        verbose=False,
        enable_roi_refinement=False,
        filter_params=dict(FILTER_PARAMS_SMALL),
    )
    result = pipeline.analyze(
        str(image_path),
        roi_mask=roi_u8,
    )
    out: Dict[str, float] = {}
    for key, col in _PIPELINE_TO_IMAGEJ.items():
        if col not in METRICS:
            continue
        val = result.get(key)
        if val is None:
            continue
        try:
            out[col] = float(val)
        except (TypeError, ValueError):
            continue
    return out


def _save_qa(
    out_dir: Path,
    stem: str,
    grader: str,
    image: np.ndarray,
    roi: np.ndarray,
    binary: np.ndarray,
    rgb: np.ndarray,
    color_mask: np.ndarray,
    enclosed: np.ndarray | None = None,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"{grader}_{stem}"
    cv2.imwrite(str(out_dir / f"{prefix}_rgb.png"), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    cv2.imwrite(str(out_dir / f"{prefix}_binary.png"), binary)
    cv2.imwrite(
        str(out_dir / f"{prefix}_colormask.png"),
        (color_mask.astype(np.uint8) * 255),
    )
    overlay = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    overlay[roi > 0] = (overlay[roi > 0] * 0.6 + np.array([0, 180, 0]) * 0.4).astype(
        np.uint8
    )
    overlay[color_mask] = (overlay[color_mask] * 0.4 + np.array([0, 0, 255]) * 0.6).astype(
        np.uint8
    )
    cv2.imwrite(str(out_dir / f"{prefix}_overlay_roi_green_color_red.png"), overlay)
    if enclosed is not None:
        cv2.imwrite(str(out_dir / f"{prefix}_enclosure.png"), enclosed)
        enc_ov = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        enc_bool = enclosed > 0
        enc_ov[enc_bool] = (
            enc_ov[enc_bool] * 0.55 + np.array([180, 80, 0]) * 0.45
        ).astype(np.uint8)
        enc_ov[color_mask] = (
            enc_ov[color_mask] * 0.35 + np.array([0, 0, 255]) * 0.65
        ).astype(np.uint8)
        cv2.imwrite(str(out_dir / f"{prefix}_overlay_enclosure_cyan_color_red.png"), enc_ov)


def run_one(
    stem: str,
    grader: str,
    export_root: Path,
    csv_row: Dict[str, str],
    qa_dir: Path,
) -> CaseRun:
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

    h, w = image.shape
    n_roi = int(roi_bool.sum())
    n_bin_in = int(np.logical_and(bin_bool, roi_bool).sum())
    n_bin_out = int(np.logical_and(bin_bool, ~roi_bool).sum())
    n_color = int(color.sum())
    n_vsl_b = int(np.logical_and(color, bin_bool).sum())
    n_color_out = int(np.logical_and(color, ~roi_bool).sum())

    mnv_a_repro = _px_to_mm2(n_roi, w)
    vsl_a_repro = _px_to_mm2(n_bin_in, w)
    dens_a_repro = (vsl_a_repro / mnv_a_repro) if mnv_a_repro > 0 else 0.0
    mnv_b = _px_to_mm2(n_color, w)
    vsl_b = _px_to_mm2(n_vsl_b, w)
    dens_b = (vsl_b / mnv_b) if mnv_b > 0 else 0.0

    color_u8 = (color.astype(np.uint8)) * 255
    enclosed = ROIEnclosure.generate_enclosed_mask(color_u8, smoothing_factor=1.0)
    enc_bool = enclosed > 0
    n_enclose = int(enc_bool.sum())
    n_vsl_c = int(np.logical_and(enc_bool, bin_bool).sum())
    mnv_c = _px_to_mm2(n_enclose, w)
    vsl_c = _px_to_mm2(n_vsl_c, w)
    dens_c = (vsl_c / mnv_c) if mnv_c > 0 else 0.0

    _save_qa(qa_dir, stem, grader, image, roi, binary, rgb, color, enclosed)

    print(f"  Running pipeline on ColorMask ({int(color.sum())} px)...")
    metrics_b = _pipeline_metrics(image_path, color_u8)
    metrics_b["MNV Area (mm2)"] = mnv_b
    metrics_b["Vsl Area (mm2)"] = vsl_b
    metrics_b["Vsl Density (Vessel Area/MNV (%))"] = dens_b
    print(f"  Running pipeline on ROIEnclosure ({n_enclose} px)...")
    metrics_c = _pipeline_metrics(image_path, enclosed)
    metrics_c["MNV Area (mm2)"] = mnv_c
    metrics_c["Vsl Area (mm2)"] = vsl_c
    metrics_c["Vsl Density (Vessel Area/MNV (%))"] = dens_c
    metrics_a = _csv_metrics(csv_row)

    return CaseRun(
        case_id=_case_id(csv_row["File"]),
        grader=grader,
        n_roi=n_roi,
        n_binary_in_roi=n_bin_in,
        n_binary_outside_roi=n_bin_out,
        n_color=n_color,
        n_enclose=n_enclose,
        n_vsl_b=n_vsl_b,
        n_vsl_c=n_vsl_c,
        mnv_a_csv=_f(csv_row, "MNV Area (mm2)"),
        vsl_a_csv=_f(csv_row, "Vsl Area (mm2)"),
        dens_a_csv=_f(csv_row, "Vsl Density (Vessel Area/MNV (%))"),
        mnv_a_repro=mnv_a_repro,
        vsl_a_repro=vsl_a_repro,
        dens_a_repro=dens_a_repro,
        mnv_b=mnv_b,
        vsl_b=vsl_b,
        dens_b=dens_b,
        mnv_c=mnv_c,
        vsl_c=vsl_c,
        dens_c=dens_c,
        color_dice_vs_vsl=choice.dice,
        color_outside_roi=n_color_out,
        choice=choice,
        metrics_a=metrics_a,
        metrics_b=metrics_b,
        metrics_c=metrics_c,
    )


def _method_a_rpd_from_integrated(
    g1_rows: Dict[str, Dict[str, str]],
    g2_rows: Dict[str, Dict[str, str]],
) -> Dict[Tuple[str, str], float]:
    """Prefer integrated recheck RPD; fill Vsl Density from the two batch CSVs."""
    out: Dict[Tuple[str, str], float] = {}
    if INTEGRATED_RECHECK.is_file():
        for row in _read_csv(INTEGRATED_RECHECK):
            cid = _case_id(row["File"])
            metric = row["Metric"]
            if metric in METRICS:
                out[(cid, metric)] = float(row["RPD_pct"])
    for stem, r1 in g1_rows.items():
        r2 = g2_rows.get(stem)
        if r2 is None:
            continue
        cid = _case_id(r1["File"])
        for metric in METRICS:
            if (cid, metric) in out:
                continue
            a = _f(r1, metric)
            b = _f(r2, metric)
            val = rpd_pct(a, b)
            if val is not None:
                out[(cid, metric)] = val
    return out


def write_comparison(
    runs: List[CaseRun],
    method_a_rpd: Dict[Tuple[str, str], float],
    out_csv: Path,
) -> List[Dict[str, str]]:
    by_case: Dict[str, Dict[str, CaseRun]] = {}
    for run in runs:
        by_case.setdefault(run.case_id, {})[run.grader] = run

    rows: List[Dict[str, str]] = []
    for case_id in ("abe 20250409", "abe 20260225", "asai 20230314"):
        pair = by_case.get(case_id, {})
        g1, g2 = pair.get("g1"), pair.get("g2")
        if g1 is None or g2 is None:
            continue
        for metric in METRICS:
            a1 = g1.metrics_a.get(metric)
            a2 = g2.metrics_a.get(metric)
            b1 = g1.metrics_b.get(metric)
            b2 = g2.metrics_b.get(metric)
            c1 = g1.metrics_c.get(metric)
            c2 = g2.metrics_c.get(metric)
            if None in (a1, a2, b1, b2, c1, c2):
                continue
            rpd_a = method_a_rpd.get((case_id, metric))
            if rpd_a is None:
                rpd_a = rpd_pct(a1, a2)
            rpd_b = rpd_pct(b1, b2)
            rpd_c = rpd_pct(c1, c2)
            delta_ba = None if rpd_a is None or rpd_b is None else rpd_b - rpd_a
            delta_ca = None if rpd_a is None or rpd_c is None else rpd_c - rpd_a
            rows.append(
                {
                    "case": case_id,
                    "metric_group": METRIC_GROUP.get(metric, ""),
                    "metric": metric,
                    "grader1_method_a": f"{a1:.6g}",
                    "grader2_method_a": f"{a2:.6g}",
                    "rpd_method_a_pct": "" if rpd_a is None else f"{rpd_a:.4f}",
                    "grader1_method_b": f"{b1:.6g}",
                    "grader2_method_b": f"{b2:.6g}",
                    "rpd_method_b_pct": "" if rpd_b is None else f"{rpd_b:.4f}",
                    "rpd_delta_b_minus_a": "" if delta_ba is None else f"{delta_ba:.4f}",
                    "method_b_improved": (
                        ""
                        if delta_ba is None
                        else ("yes" if delta_ba < 0 else ("no" if delta_ba > 0 else "tie"))
                    ),
                    "grader1_method_c": f"{c1:.6g}",
                    "grader2_method_c": f"{c2:.6g}",
                    "rpd_method_c_pct": "" if rpd_c is None else f"{rpd_c:.4f}",
                    "rpd_delta_c_minus_a": "" if delta_ca is None else f"{delta_ca:.4f}",
                    "method_c_improved": (
                        ""
                        if delta_ca is None
                        else ("yes" if delta_ca < 0 else ("no" if delta_ca > 0 else "tie"))
                    ),
                }
            )

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return rows


def main() -> int:
    out_dir = Path(__file__).resolve().parent
    qa_dir = out_dir / "qa_masks"
    g1_rows = _index_by_stem(_read_csv(G1_CSV))
    g2_rows = _index_by_stem(_read_csv(G2_CSV))
    stems = sorted(set(g1_rows) & set(g2_rows))
    if len(stems) != 3:
        raise SystemExit(f"Expected 3 paired cases, got {stems}")

    runs: List[CaseRun] = []
    for stem in stems:
        print(f"\n=== {stem} / grader1 ===")
        runs.append(run_one(stem, "g1", G1_DIR / "export", g1_rows[stem], qa_dir))
        print(f"=== {stem} / grader2 ===")
        runs.append(run_one(stem, "g2", G2_DIR / "export", g2_rows[stem], qa_dir))

    method_a_rpd = _method_a_rpd_from_integrated(g1_rows, g2_rows)
    rows = write_comparison(runs, method_a_rpd, out_dir / "rpd_comparison.csv")

    print("\n=== Enclosure vs ColorMask vs hand ROI (px) ===")
    for run in runs:
        print(
            f"{run.case_id} {run.grader}: ROI={run.n_roi}  "
            f"ColorMask={run.n_color}  Enclosure={run.n_enclose}  "
            f"Vsl_B={run.n_vsl_b}  Vsl_C={run.n_vsl_c}"
        )

    print("\n=== ColorMask variant (locked per run by Dice vs binary∩ROI) ===")
    for run in runs:
        print(
            f"{run.case_id} {run.grader}: weighted={run.choice.weighted} "
            f"invert={run.choice.invert} dice={run.choice.dice:.3f} "
            f"color_outside_roi={run.color_outside_roi} "
            f"binary_outside_roi={run.n_binary_outside_roi}"
        )

    print("\n=== Method A reproducibility (CSV vs re-run ROI/binary) ===")
    for run in runs:
        print(
            f"{run.case_id} {run.grader}: "
            f"MNV Δ={run.mnv_a_repro - run.mnv_a_csv:.6g} "
            f"Vsl Δ={run.vsl_a_repro - run.vsl_a_csv:.6g} "
            f"Dens Δ={run.dens_a_repro - run.dens_a_csv:.6g}"
        )

    print("\n=== RPD comparison ===")
    for row in rows:
        print(
            f"{row['case']:16} {row['metric_group']:16} {row['metric'][:28]:28} "
            f"A={row['rpd_method_a_pct']:>8}  B={row['rpd_method_b_pct']:>8}  "
            f"C={row['rpd_method_c_pct']:>8}  "
            f"ΔC-A={row['rpd_delta_c_minus_a']:>8}  {row['method_c_improved']}"
        )
    print(f"\nWrote {out_dir / 'rpd_comparison.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
