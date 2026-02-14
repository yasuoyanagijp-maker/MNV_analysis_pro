import json
from pathlib import Path

import numpy as np
import tifffile as tiff

from .arteriolarization import analyze_arteriolarization
from .binarize import adaptive_binarize_phansalkar
from .classify import classify_mnv
from .faz_segmentation import segment_faz
from .filters import fuse_filters, gabor_filter_max, multi_scale_frangi
from .flow_deficit import flow_deficit_analysis
from .fractal import box_counting_fd
from .preprocess import preprocess_image
from .roi import polygon_to_mask_coords, refine_roi_by_intensity
from .skeleton import compute_graph_metrics, compute_skeleton_metrics
from .spatial import analyze_spatial_distribution
from .utils import mm_per_pixel_from_scale
from .vd.vd_pipeline import VDPipeline



def default_roi_center_circle(shape):
    h, w = shape
    cx, cy = w // 2, h // 2
    r = min(w, h) // 4
    t = np.linspace(0, 2 * np.pi, 128)
    xs = (cx + r * np.cos(t)).tolist()
    ys = (cy + r * np.sin(t)).tolist()
    return list(zip(xs, ys))


def process_file(path, output_dir, params):
    out = {}
    img = tiff.imread(str(path))
    if img.ndim == 3 and img.shape[2] == 3:
        img_gray = img[:, :, 1]
    else:
        img_gray = img
    pre = preprocess_image(
        img_gray, clahe_clip=3.0, background_sigma=params.get("background_sigma", 5.0)
    )
    out["preprocessed_shape"] = pre.shape
    fr = multi_scale_frangi(pre)
    gb = gabor_filter_max(pre)
    fused = fuse_filters([fr, gb], weights=[0.4, 0.4])
    out["fused_mean"] = float(np.mean(fused))
    bin_mask = adaptive_binarize_phansalkar(
        fused,
        radius=params.get("phansalkar_radius_px", 15),
        k=params.get("phansalkar_k", 0.1),
        R=128,
    )
    image_width_px = params.get("image_width_px", pre.shape[1])
    scale_mm = params.get("scale_mm", params.get("scale_mm", 1.0))
    mm_per_pixel = mm_per_pixel_from_scale(image_width_px, scale_mm)
    pixel_size_um = (
        mm_per_pixel * 1000.0 if mm_per_pixel > 0 else params.get("pixel_size_um", 1.0)
    )
    sk_metrics = compute_skeleton_metrics(bin_mask, pixel_size_um=pixel_size_um)
    out.update(sk_metrics)
    graph_metrics = compute_graph_metrics(bin_mask, pixel_size_um=pixel_size_um)
    # normalize graph keys to macro-like names if available
    out["n_branches"] = graph_metrics.get("n_branches", 0)
    out["n_junctions"] = graph_metrics.get("n_junctions", 0)
    out["n_endpoints"] = graph_metrics.get("n_endpoints", 0)
    out["total_branch_length_mm"] = graph_metrics.get("total_branch_length_mm", 0.0)
    out["tortuosity"] = graph_metrics.get("tortuosity", 0.0)
    fd_val = box_counting_fd((bin_mask > 0).astype("uint8"))
    out["fractal_fd"] = float(fd_val)
    # compute distance map
    from scipy.ndimage import distance_transform_edt

    distance_map = distance_transform_edt((bin_mask > 0).astype("uint8"))
    # ROI handling
    roi = params.get("roi_coords", None)
    if roi is None:
        roi = default_roi_center_circle(pre.shape)
    # optional refinement using intensity
    try:
        refined_roi = refine_roi_by_intensity(pre, roi, iterations=3)
    except Exception:
        refined_roi = roi
    roi_mask = polygon_to_mask_coords(refined_roi, pre.shape)
    # vessel density (VD) — fraction of vessel pixels inside ROI
    vessel_pixels = (bin_mask > 0) & roi_mask
    roi_pixels = (
        int(roi_mask.sum())
        if hasattr(roi_mask, "sum")
        else int(sum(1 for _ in roi_mask))
    )
    vessel_density = float(vessel_pixels.sum() / roi_pixels) if roi_pixels > 0 else 0.0
    out["vessel_density"] = vessel_density
    out["vessel_density_percent"] = vessel_density * 100.0

    # spatial analysis
    spatial = analyze_spatial_distribution(
        distance_map=distance_map, roi_coords=refined_roi, mm_per_pixel=mm_per_pixel
    )
    out.update(spatial)
    # flow deficit
    fd = flow_deficit_analysis(
        (bin_mask > 0).astype("uint8"),
        refined_roi,
        pixel_size_um=pixel_size_um,
        num_rings=params.get("fd_num_rings", 3),
        enlarge_step_mm=params.get("fd_enlarge_step_mm", 0.2),
    )
    out.update(fd)
    # arteriolarization analysis
    arteriol = analyze_arteriolarization(
        distance_map,
        skeleton_mask=(bin_mask > 0).astype("uint8"),
        roi_mask=roi_mask,
        mm_per_pixel=mm_per_pixel,
    )
    out.update(arteriol)
    # Create output directory
    p = Path(output_dir)
    p.mkdir(parents=True, exist_ok=True)
    # FAZ segmentation
    if params.get("enable_faz", True):
        faz_method = params.get("faz_method", "original")
        if faz_method == "enhanced":
            from .enhanced_faz_detection import ImprovedFAZDetector

            detector = ImprovedFAZDetector()
            faz_mask, faz_metrics = detector.detect(
                pre, (bin_mask > 0).astype(bool), mm_per_pixel=mm_per_pixel
            )
        elif faz_method == "auto":
            from .auto_faz_optimizer import get_auto_optimized_detector

            detector, opt_params = get_auto_optimized_detector(
                pre,
                pixel_size_mm=mm_per_pixel,
                use_test_detection=params.get("faz_auto_use_test_detection", False),
                cache_dir=params.get("faz_cache_dir", None),
            )
            faz_mask, faz_metrics = detector.detect(
                pre, (bin_mask > 0).astype(bool), mm_per_pixel=mm_per_pixel
            )
            # 最適化パラメータをメトリクスに追加
            faz_metrics["auto_optimization_params"] = {
                "min_area_mm2": opt_params.min_area_mm2,
                "max_area_mm2": opt_params.max_area_mm2,
                "min_circularity": opt_params.min_circularity,
                "max_circularity": opt_params.max_circularity,
                "search_radius_ratio": opt_params.search_radius_ratio,
                "optimization_score": opt_params.optimization_score,
            }
        else:
            faz_mask, faz_metrics = segment_faz(
                pre,
                (bin_mask > 0).astype(bool),
                mm_per_pixel=mm_per_pixel,
                refine=params.get("faz_refine", False),
                min_area_px=params.get("faz_min_area_px", 100),
            )
        out.update(faz_metrics)
        # --- Sector-based VD metrics (4 sectors: Temporal/Nasal/Superior/Inferior) ---
        try:
            from .vd import SectorSplitter

            splitter = SectorSplitter(n_sectors=4)

            side = params.get("eye_side", "right")
            center_radius_mm = params.get("sector_center_radius_mm", 1.0)

            sectors = splitter.split_into_sectors(
                faz_mask.astype(bool), pixel_size_mm=mm_per_pixel, side=side
            )
            center_roi, periphery_roi = splitter.split_center_periphery(
                faz_mask.astype(bool),
                center_radius_mm=center_radius_mm,
                pixel_size_mm=mm_per_pixel,
            )

            # Per-sector vessel area (percent and mm^2)
            for name in ["superior", "temporal", "nasal", "inferior"]:
                s_mask = sectors.get(name)
                if s_mask is None:
                    out[f"{name}_area_superficial_percent"] = 0.0
                    out[f"{name}_area_superficial_mm2"] = 0.0
                    continue

                vessel_px = int(((bin_mask > 0) & s_mask).sum())
                sector_px = int(s_mask.sum())
                percent = (
                    float((vessel_px / sector_px) * 100.0) if sector_px > 0 else 0.0
                )
                area_mm2 = float(vessel_px * (mm_per_pixel**2))

                out[f"{name}_area_superficial_percent"] = percent
                out[f"{name}_area_superficial_mm2"] = area_mm2

            # Center / Periphery vessel density (percent)
            center_vessel_px = int(((bin_mask > 0) & center_roi).sum())
            periph_vessel_px = int(((bin_mask > 0) & periphery_roi).sum())
            center_px = int(center_roi.sum())
            periph_px = int(periphery_roi.sum())

            center_pct = (
                float((center_vessel_px / center_px) * 100.0) if center_px > 0 else 0.0
            )
            periph_pct = (
                float((periph_vessel_px / periph_px) * 100.0) if periph_px > 0 else 0.0
            )
            ratio = float(center_pct / periph_pct) if periph_pct > 0 else 1.0

            out["vessel_density_center_percent"] = center_pct
            out["vessel_density_periphery_percent"] = periph_pct
            out["vessel_density_center_periphery_ratio"] = ratio
            # mark success
            out["sector_splitter_executed"] = True
        except Exception:
            # If any error happens, ensure keys exist as fallbacks
            out["superior_area_superficial_percent"] = out.get(
                "superior_area_superficial_percent", 0.0
            )
            out["temporal_area_superficial_percent"] = out.get(
                "temporal_area_superficial_percent", 0.0
            )
            out["nasal_area_superficial_percent"] = out.get(
                "nasal_area_superficial_percent", 0.0
            )
            out["inferior_area_superficial_percent"] = out.get(
                "inferior_area_superficial_percent", 0.0
            )
            out["superior_area_superficial_mm2"] = out.get(
                "superior_area_superficial_mm2", 0.0
            )
            out["temporal_area_superficial_mm2"] = out.get(
                "temporal_area_superficial_mm2", 0.0
            )
            out["nasal_area_superficial_mm2"] = out.get(
                "nasal_area_superficial_mm2", 0.0
            )
            out["inferior_area_superficial_mm2"] = out.get(
                "inferior_area_superficial_mm2", 0.0
            )
            out["vessel_density_center_percent"] = out.get(
                "vessel_density_center_percent", 0.0
            )
            out["vessel_density_periphery_percent"] = out.get(
                "vessel_density_periphery_percent", 0.0
            )
            out["vessel_density_center_periphery_ratio"] = out.get(
                "vessel_density_center_periphery_ratio", 1.0
            )
            out["sector_splitter_executed"] = False

        # Save FAZ mask
        tiff.imwrite(
            str(p / (Path(path).stem + "_faz_mask.tif")), faz_mask.astype("uint8") * 255
        )
    # Final safety: ensure sector VD keys exist — attempt safe fallback computation if missing
    if "superior_area_superficial_percent" not in out:
        try:
            from .vd import SectorSplitter

            splitter = SectorSplitter(n_sectors=4)

            # try to reconstruct a FAZ mask from centroid + area if original mask not present
            if (
                "faz_centroid_x_px" in out
                and "faz_centroid_y_px" in out
                and out.get("faz_area_mm2", 0.0) > 0
            ):
                cx = int(round(out.get("faz_centroid_x_px")))
                cy = int(round(out.get("faz_centroid_y_px")))
                area_mm2 = out.get("faz_area_mm2", 0.0)
                est_r_px = max(
                    1, int(round((area_mm2 / (mm_per_pixel**2) / np.pi) ** 0.5))
                )
                yv, xv = np.indices(pre.shape)
                faz_mask = ((xv - cx) ** 2 + (yv - cy) ** 2) <= (est_r_px**2)
            else:
                # fallback to centered circle
                h, w = pre.shape
                cy, cx = h // 2, w // 2
                r = min(h, w) // 8
                yv, xv = np.indices(pre.shape)
                faz_mask = ((xv - cx) ** 2 + (yv - cy) ** 2) <= (r**2)

            sectors = splitter.split_into_sectors(
                faz_mask.astype(bool),
                pixel_size_mm=mm_per_pixel,
                side=params.get("eye_side", "right"),
            )
            center_roi, periphery_roi = splitter.split_center_periphery(
                faz_mask.astype(bool),
                center_radius_mm=params.get("sector_center_radius_mm", 1.0),
                pixel_size_mm=mm_per_pixel,
            )

            for name in ["superior", "temporal", "nasal", "inferior"]:
                s_mask = sectors.get(name, np.zeros_like(faz_mask, dtype=bool))
                vessel_px = int(((bin_mask > 0) & s_mask).sum())
                sector_px = int(s_mask.sum())
                percent = (
                    float((vessel_px / sector_px) * 100.0) if sector_px > 0 else 0.0
                )
                area_mm2 = float(vessel_px * (mm_per_pixel**2))
                out[f"{name}_area_superficial_percent"] = percent
                out[f"{name}_area_superficial_mm2"] = area_mm2

            center_vessel_px = int(((bin_mask > 0) & center_roi).sum())
            periph_vessel_px = int(((bin_mask > 0) & periphery_roi).sum())
            center_px = int(center_roi.sum())
            periph_px = int(periphery_roi.sum())
            center_pct = (
                float((center_vessel_px / center_px) * 100.0) if center_px > 0 else 0.0
            )
            periph_pct = (
                float((periph_vessel_px / periph_px) * 100.0) if periph_px > 0 else 0.0
            )
            ratio = float(center_pct / periph_pct) if periph_pct > 0 else 1.0
            out["vessel_density_center_percent"] = center_pct
            out["vessel_density_periphery_percent"] = periph_pct
            out["vessel_density_center_periphery_ratio"] = ratio
        except Exception:
            out.setdefault("superior_area_superficial_percent", 0.0)
            out.setdefault("temporal_area_superficial_percent", 0.0)
            out.setdefault("nasal_area_superficial_percent", 0.0)
            out.setdefault("inferior_area_superficial_percent", 0.0)
            out.setdefault("superior_area_superficial_mm2", 0.0)
            out.setdefault("temporal_area_superficial_mm2", 0.0)
            out.setdefault("nasal_area_superficial_mm2", 0.0)
            out.setdefault("inferior_area_superficial_mm2", 0.0)
            out.setdefault("vessel_density_center_percent", 0.0)
            out.setdefault("vessel_density_periphery_percent", 0.0)
            out.setdefault("vessel_density_center_periphery_ratio", 1.0)

    # classification
    metrics_for_class = {
        "center_branch": out.get("n_branches", 0),
        "periphery_branch": 0,
        "loop_center": out.get("n_endpoints", 0),
        "loop_periphery": 0,
        "euler_center": out.get("n_junctions", 0) * -1,
        "euler_periphery": 0,
        "vessel_length_center": out.get("total_branch_length_mm", 0.0),
        "vessel_length_periphery": 0.0,
        "trunk_eccentricity": out.get("trunk_eccentricity", 0.5),
        "angular_distribution_cv": out.get("angular_distribution_cv", 0.5),
        "thick_vessel_center_ratio": out.get("thick_vessel_center_ratio", 0.0),
        "diameter_center_periphery_ratio": out.get(
            "diameter_center_periphery_ratio", 1.0
        ),
        "patternClassification": out.get("patternClassification", ""),
        "stability_score": params.get("stability_score", 50),
    }
    classification = classify_mnv(metrics_for_class)
    out.update(classification)
    tiff.imwrite(str(p / (Path(path).stem + "_preprocessed.tif")), pre.astype("uint8"))
    tiff.imwrite(str(p / (Path(path).stem + "_fused.tif")), fused.astype("uint8"))
    tiff.imwrite(
        str(p / (Path(path).stem + "_binary.tif")), (bin_mask > 0).astype("uint8") * 255
    )
    # ensure VD keys present (fallback)
    out.setdefault("vessel_density", None)
    out.setdefault("vessel_density_percent", None)

    # Ensure sector keys always present (even if splitting failed earlier)
    for name in ["superior", "temporal", "nasal", "inferior"]:
        out.setdefault(f"{name}_area_superficial_percent", 0.0)
        out.setdefault(f"{name}_area_superficial_mm2", 0.0)

    out.setdefault("vessel_density_center_percent", 0.0)
    out.setdefault("vessel_density_periphery_percent", 0.0)
    out.setdefault("vessel_density_center_periphery_ratio", 1.0)
    out.setdefault(
        "sector_splitter_executed", out.get("sector_splitter_executed", False)
    )

    return out


# ---------- Paired VD pipeline wrapper ----------



def process_vd_pair(superficial_path, deep_path, output_dir, params):
    """Process a superficial+deep pair using the VDPipeline and save metrics as JSON.

    Parameters
    ----------
    superficial_path : str or Path
    deep_path : str or Path
    output_dir : str or Path
    params : dict
    """
    sup = tiff.imread(str(superficial_path))
    deep = tiff.imread(str(deep_path))

    # normalize to single-channel grayscale if needed
    if sup.ndim == 3 and sup.shape[2] == 3:
        sup_gray = sup[:, :, 1]
    else:
        sup_gray = sup
    if deep.ndim == 3 and deep.shape[2] == 3:
        deep_gray = deep[:, :, 1]
    else:
        deep_gray = deep

    image_width_px = params.get("image_width_px", sup_gray.shape[1])
    scale_mm = params.get("scale_mm", params.get("scale_mm", 1.0))
    mm_per_pixel = mm_per_pixel_from_scale(image_width_px, scale_mm)

    vdp = VDPipeline(pixel_size_mm=mm_per_pixel)
    metrics = vdp.process(
        sup_gray.astype("float32"),
        deep_gray.astype("float32"),
        eye_side=params.get("eye_side", "right"),
        center_radius_mm=params.get("sector_center_radius_mm", 1.0),
    )

    p = Path(output_dir)
    p.mkdir(parents=True, exist_ok=True)
    outpath = p / (Path(superficial_path).stem + "_vd_pair_metrics.json")
    with open(outpath, "w") as fh:
        json.dump(metrics, fh, indent=2)

    return metrics
