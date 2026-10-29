"""Raw PDR NVE metrics. No 0–100 scores, no MNV maturity index."""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

import numpy as np
from skimage.measure import label

from ._paths import ensure_import_paths
from .scale import PixelScale
from .vessels import VesselMaps

ensure_import_paths()

# Keys that appear as before_*, after_*, pct_* in the case CSV.
PAIR_METRIC_KEYS: List[str] = [
    "roi_area_mm2",
    "vessel_area_px",
    "vessel_area_mm2",
    "vessel_area_density",
    "vessel_area_density_no_large",
    "skeleton_length_mm",
    "skeleton_length_density_mm_per_mm2",
    "skeleton_length_mm_no_large",
    "n_junctions",
    "junction_density_per_mm2",
    "n_endpoints",
    "n_branches",
    "n_loops",
    "euler_number",
    "n_components",
    "fractal_dimension",
    "fractal_r_squared",
    "lacunarity_mean",
    "lacunarity_r8",
    "caliber_mean_um",
    "caliber_cv_pct",
    "caliber_mean_um_no_large",
    "caliber_cv_pct_no_large",
    "ij_mean_diameter_um",
    "ij_cv_diameter",
]


def _neighbor_counts(skeleton: np.ndarray) -> np.ndarray:
    from scipy import ndimage

    kernel = np.array([[1, 1, 1], [1, 0, 1], [1, 1, 1]], dtype=np.uint8)
    counts = ndimage.convolve(skeleton.astype(np.uint8), kernel, mode="constant", cval=0)
    return counts * skeleton.astype(np.uint8)


def _junction_endpoint_counts(skeleton: np.ndarray) -> tuple:
    import cv2

    neigh = _neighbor_counts(skeleton)
    n_endpoints = int(np.sum(neigh == 1))
    junc = (neigh >= 3) & skeleton
    n_junctions = int(
        cv2.connectedComponents(junc.astype(np.uint8), connectivity=8)[0] - 1
    )
    return n_junctions, n_endpoints


def gliding_box_lacunarity(
    binary: np.ndarray,
    box_sizes: Optional[Iterable[int]] = None,
) -> Dict[int, float]:
    """Allain–Cloitre gliding-box lacunarity Λ(r) = ⟨s²⟩ / ⟨s⟩²."""
    img = (binary > 0).astype(np.float64)
    h, w = img.shape
    if box_sizes is None:
        box_sizes = (2, 4, 8, 16, 32)
    integral = np.pad(img, ((1, 0), (1, 0)), mode="constant").cumsum(0).cumsum(1)
    out: Dict[int, float] = {}
    for r in box_sizes:
        r = int(r)
        if r < 2 or r >= min(h, w):
            continue
        s = (
            integral[r : h + 1, r : w + 1]
            - integral[0 : h - r + 1, r : w + 1]
            - integral[r : h + 1, 0 : w - r + 1]
            + integral[0 : h - r + 1, 0 : w - r + 1]
        )
        mean = float(s.mean())
        if mean <= 0:
            out[r] = float("nan")
            continue
        out[r] = float((s**2).mean() / (mean**2))
    return out


def _caliber_stats(distance_px: np.ndarray, skeleton: np.ndarray, scale: PixelScale) -> tuple:
    pts = skeleton.astype(bool)
    if int(pts.sum()) == 0:
        return 0.0, 0.0
    diameters = distance_px[pts] * 2.0 * scale.um_per_px
    mean = float(diameters.mean())
    std = float(diameters.std())
    cv = (100.0 * std / mean) if mean > 0 else 0.0
    return mean, cv


def _crop_to_roi(binary: np.ndarray, roi: np.ndarray) -> np.ndarray:
    ys, xs = np.where(roi > 0)
    if len(ys) == 0:
        return np.zeros((1, 1), dtype=bool)
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    cropped = np.zeros((y1 - y0, x1 - x0), dtype=bool)
    local = (binary > 0) & (roi > 0)
    cropped[:, :] = local[y0:y1, x0:x1]
    return cropped


def compute_raw_metrics(
    maps: VesselMaps,
    roi: np.ndarray,
    scale: PixelScale,
) -> Dict[str, float]:
    """Compute raw structural metrics inside ``roi``. Never standardizes."""
    from core.skeleton_analysis import DiameterAnalyzer, EulerAnalyzer, FractalAnalyzer

    roi_b = roi > 0
    roi_px = int(roi_b.sum())
    roi_mm2 = scale.area_mm2(roi_px) if roi_px else 0.0

    vessels = maps.in_roi(roi)
    vox = int(vessels.binary.sum())
    vox_nl = int(vessels.binary_no_large.sum())
    skel_px = int(vessels.skeleton.sum())
    skel_nl_px = int(vessels.skeleton_no_large.sum())

    n_junc, n_end = _junction_endpoint_counts(vessels.skeleton)
    n_comp = int(label(vessels.skeleton, connectivity=2).max()) if skel_px else 0

    skel_u8 = (vessels.skeleton.astype(np.uint8)) * 255
    if skel_px:
        euler, n_loops = EulerAnalyzer.calculate_euler_number(skel_u8)
        n_branches = max(int(n_junc + n_end // 2), n_comp)
        box_sizes, box_counts = FractalAnalyzer.box_counting(
            skel_u8, use_fixed_scale=True
        )
        fd, r2 = FractalAnalyzer.calculate_fractal_dimension(box_sizes, box_counts)
        diam = DiameterAnalyzer(scale.mm_per_px)
        dist = diam.create_distance_map((vessels.binary.astype(np.uint8)) * 255)
        ij = diam.analyze_diameter_statistics(dist, skel_u8)
    else:
        euler, n_loops, n_branches = 0, 0, 0
        fd, r2 = 0.0, 0.0
        ij = {"mean_diameter_um": 0.0, "cv_diameter": 0.0}

    lac_src = _crop_to_roi(vessels.binary, roi)
    lac = gliding_box_lacunarity(lac_src)
    lac_vals = [v for v in lac.values() if np.isfinite(v)]
    lac_mean = float(np.mean(lac_vals)) if lac_vals else float("nan")
    lac_r8 = float(lac[8]) if 8 in lac else float("nan")

    cal_mean, cal_cv = _caliber_stats(vessels.distance_px, vessels.skeleton, scale)
    cal_mean_nl, cal_cv_nl = _caliber_stats(
        vessels.distance_px, vessels.skeleton_no_large, scale
    )

    length_mm = scale.length_mm(skel_px)
    length_nl_mm = scale.length_mm(skel_nl_px)
    dens = (vox / roi_px) if roi_px else 0.0
    dens_nl = (vox_nl / roi_px) if roi_px else 0.0
    length_dens = (length_mm / roi_mm2) if roi_mm2 > 0 else 0.0
    junc_dens = (n_junc / roi_mm2) if roi_mm2 > 0 else 0.0

    return {
        "roi_area_mm2": roi_mm2,
        "vessel_area_px": vox,
        "vessel_area_mm2": scale.area_mm2(vox),
        "vessel_area_density": dens,
        "vessel_area_density_no_large": dens_nl,
        "skeleton_length_mm": length_mm,
        "skeleton_length_density_mm_per_mm2": length_dens,
        "skeleton_length_mm_no_large": length_nl_mm,
        "n_junctions": n_junc,
        "junction_density_per_mm2": junc_dens,
        "n_endpoints": n_end,
        "n_branches": n_branches,
        "n_loops": int(n_loops),
        "euler_number": int(euler),
        "n_components": n_comp,
        "fractal_dimension": float(fd),
        "fractal_r_squared": float(r2),
        "lacunarity_mean": lac_mean,
        "lacunarity_r8": lac_r8,
        "caliber_mean_um": cal_mean,
        "caliber_cv_pct": cal_cv,
        "caliber_mean_um_no_large": cal_mean_nl,
        "caliber_cv_pct_no_large": cal_cv_nl,
        "ij_mean_diameter_um": float(ij.get("mean_diameter_um", 0.0)),
        "ij_cv_diameter": float(ij.get("cv_diameter", 0.0)),
    }


def percent_change(before: float, after: float) -> float:
    if before is None or after is None:
        return float("nan")
    before = float(before)
    after = float(after)
    if not np.isfinite(before) or not np.isfinite(after) or abs(before) < 1e-12:
        return float("nan")
    return 100.0 * (after - before) / before


def pair_record(before: Dict[str, float], after: Dict[str, float]) -> Dict[str, float]:
    row: Dict[str, float] = {}
    for key in PAIR_METRIC_KEYS:
        b = before.get(key, float("nan"))
        a = after.get(key, float("nan"))
        row[f"before_{key}"] = b
        row[f"after_{key}"] = a
        row[f"pct_{key}"] = percent_change(b, a)
    return row


FORBIDDEN_SCORE_KEYS = (
    "maturity_index",
    "maturity_index_pca",
    "complexity_score",
    "stability_score",
    "caliber_u2",
    "standardized_score",
)


def assert_raw_only(record: dict) -> None:
    lowered = {str(k).lower() for k in record}
    for banned in FORBIDDEN_SCORE_KEYS:
        if banned in lowered:
            raise AssertionError(
                f"PDR NVE output must not include MNV standardized key {banned!r}"
            )
