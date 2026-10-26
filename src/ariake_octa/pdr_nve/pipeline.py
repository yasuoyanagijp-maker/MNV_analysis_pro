"""End-to-end PDR NVE before/after analysis (raw metrics only)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

import numpy as np

from .io import load_gray_u8, write_csv, write_json
from .metrics import PAIR_METRIC_KEYS, assert_raw_only, compute_raw_metrics, pair_record
from .overlay import save_analysis_images
from .quality import collect_flags
from .register import register_after_to_before
from .roi import resolve_roi
from .scale import PixelScale, resolve_pixel_scale
from .trim import common_blank_border, maybe_compute_color_mask, trim_roi_blank_margin
from .vessels import build_vessel_maps


@dataclass
class PdrNveConfig:
    case_id: str = "case"
    scan_size_mm: float = 15.0
    pixel_width_px: Optional[int] = None
    um_per_px: Optional[float] = None
    roi_mode: str = "auto"
    roi_mask_path: Optional[str] = None
    roi_polygon_path: Optional[str] = None
    roi_polygon: Optional[Sequence[tuple]] = None
    register: bool = True
    trim_blank_border: bool = True
    trim_roi_margin: bool = True
    exclude_disc: bool = False
    exclude_large_vessels: bool = True
    large_vessel_um: float = 100.0
    segment_mode: str = "mnv"
    output_dir: str = "pdr_nve_output"
    precomputed_before_binary: Optional[Any] = None
    precomputed_after_binary: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d.pop("roi_polygon", None)
        d.pop("precomputed_before_binary", None)
        d.pop("precomputed_after_binary", None)
        return d


@dataclass
class PdrNveResult:
    record: Dict[str, Any]
    paths: Dict[str, str] = field(default_factory=dict)
    scale: Optional[PixelScale] = None


def analyze_pair(
    before_path: str,
    after_path: str,
    config: Optional[PdrNveConfig] = None,
) -> PdrNveResult:
    """
    Register after→before, apply one shared ROI, compute raw metrics, write
    CSV / QA overlay / ARIAKE RGB / binary masks.
    """
    cfg = config or PdrNveConfig()
    before = load_gray_u8(before_path)
    after = load_gray_u8(after_path)

    crop = None
    if cfg.trim_blank_border:
        crop = common_blank_border(before, after)
        if crop.cropped:
            before = crop.apply(before)
            after = crop.apply(after)

    scale = resolve_pixel_scale(
        before.shape,
        scan_size_mm=cfg.scan_size_mm,
        pixel_width_px=cfg.pixel_width_px,
        um_per_px=cfg.um_per_px,
    )

    registration = register_after_to_before(before, after, enabled=cfg.register)
    after_reg = registration.warped_after

    pre_after = cfg.precomputed_after_binary
    if pre_after is not None and cfg.register:
        from .register import warp_mask

        pre_after = warp_mask(pre_after, registration.matrix, before.shape) > 0

    # Segment on the full field first so auto-ROI can see the lesion network.
    maps_b_full = build_vessel_maps(
        before,
        scale,
        roi=None,
        segment_mode=cfg.segment_mode,
        large_vessel_um=cfg.large_vessel_um,
        exclude_large_vessels=cfg.exclude_large_vessels,
        precomputed_binary=cfg.precomputed_before_binary,
    )
    maps_a_full = build_vessel_maps(
        after_reg,
        scale,
        roi=None,
        segment_mode=cfg.segment_mode,
        large_vessel_um=cfg.large_vessel_um,
        exclude_large_vessels=cfg.exclude_large_vessels,
        precomputed_binary=pre_after,
    )

    roi, roi_used, roi_extra = resolve_roi(
        before.shape,
        scale,
        maps_b_full,
        before,
        roi_mode=cfg.roi_mode,
        roi_mask_path=cfg.roi_mask_path,
        roi_polygon_path=cfg.roi_polygon_path,
        roi_polygon=cfg.roi_polygon,
        exclude_disc_flag=cfg.exclude_disc,
    )

    if cfg.trim_roi_margin:
        color = maybe_compute_color_mask(
            before, roi, vessel_binary=(maps_b_full.binary.astype(np.uint8) * 255)
        )
        trim_src = color if color is not None else maps_b_full.binary
        roi, trim_info = trim_roi_blank_margin(roi, trim_src)
        roi_extra["trim"] = trim_info

    maps_b = maps_b_full.in_roi(roi)
    maps_a = maps_a_full.in_roi(roi)

    before_m = compute_raw_metrics(maps_b, roi, scale)
    after_m = compute_raw_metrics(maps_a, roi, scale)
    paired = pair_record(before_m, after_m)

    quality = collect_flags(
        before,
        after_reg,
        scale,
        registration,
        roi,
        int(before_m["vessel_area_px"]),
        int(after_m["vessel_area_px"]),
        roi_used,
    )

    out_dir = Path(cfg.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    image_paths = save_analysis_images(
        out_dir,
        cfg.case_id,
        before,
        after_reg,
        maps_b_full,
        maps_a_full,
        roi,
        scale,
        before_m,
        after_m,
    )

    record: Dict[str, Any] = {
        "case_id": cfg.case_id,
        "before_path": str(before_path),
        "after_path": str(after_path),
        "roi_mode": roi_used,
        "exclude_large_vessels": bool(cfg.exclude_large_vessels),
        "large_vessel_threshold_um": float(cfg.large_vessel_um),
        "segment_mode": maps_b_full.segment_mode,
        "blank_border_top": 0 if crop is None else crop.top,
        "blank_border_bottom": 0 if crop is None else crop.bottom,
        "blank_border_left": 0 if crop is None else crop.left,
        "blank_border_right": 0 if crop is None else crop.right,
        "notes": (
            "raw metrics only; no MNV standardized score or maturity index; "
            "after_* images are in the registered before frame"
        ),
    }
    record.update(scale.to_record())
    record.update(registration.to_record())
    record.update(paired)
    record.update(
        {
            "quality_flags": ";".join(quality["quality_flags"]),
            "exclude_suggested": quality["exclude_suggested"],
            "before_snr_db": quality["before_snr_db"],
            "after_snr_db": quality["after_snr_db"],
            "before_contrast": quality["before_contrast"],
            "after_contrast": quality["after_contrast"],
            "roi_frac": quality["roi_frac"],
            "auto_roi_failed": bool(roi_extra.get("auto_roi_failed", False)),
            "disc_excluded": bool(roi_extra.get("disc_excluded", False)),
        }
    )
    for key, path in image_paths.items():
        record[f"file_{key}"] = path

    assert_raw_only(record)

    csv_path = write_csv(out_dir / f"{cfg.case_id}_metrics.csv", [record])
    json_path = write_json(
        out_dir / f"{cfg.case_id}_params.json",
        {
            "config": cfg.to_dict(),
            "scale": scale.to_record(),
            "registration": registration.to_record(),
            "roi": roi_extra,
            "pair_metric_keys": PAIR_METRIC_KEYS,
            "output_files": image_paths,
            "csv": str(csv_path),
        },
    )
    image_paths["metrics_csv"] = str(csv_path)
    image_paths["params_json"] = str(json_path)
    return PdrNveResult(record=record, paths=image_paths, scale=scale)
