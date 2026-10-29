"""End-to-end PDR NVE before/after analysis (raw metrics only)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

import numpy as np

from .io import load_gray_u8, write_csv, write_json
from .metrics import PAIR_METRIC_KEYS, assert_raw_only, compute_raw_metrics, pair_record
from .overlay import create_register_qa, save_analysis_images, save_gray_png, save_rgb_png
from .quality import collect_flags
from .register import (
    combine_slabs,
    compute_alignment_cc,
    register_after_to_before,
    register_using_reference_slabs,
    warp_gray,
)
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
    register_before_paths: Optional[Sequence[str]] = None
    register_after_paths: Optional[Sequence[str]] = None
    register_combine: str = "mean"
    roi_boxes: Optional[Sequence[tuple]] = None
    min_cc_mm2: float = 0.012
    max_auto_roi_frac: float = 0.40
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

    ref_before_imgs = _load_optional_slabs(cfg.register_before_paths)
    ref_after_imgs = _load_optional_slabs(cfg.register_after_paths)
    if bool(ref_before_imgs) != bool(ref_after_imgs):
        raise ValueError(
            "Provide both register-before and register-after slabs, or neither."
        )
    used_ref_slabs = bool(ref_before_imgs) and bool(ref_after_imgs)
    if used_ref_slabs:
        if len(ref_before_imgs) != len(ref_after_imgs):
            raise ValueError(
                "register-before and register-after must have the same number of slabs "
                f"({len(ref_before_imgs)} vs {len(ref_after_imgs)})"
            )
        ref_before = combine_slabs(
            ref_before_imgs, mode=cfg.register_combine, target_shape=before.shape[:2]
        )
        ref_after = combine_slabs(
            ref_after_imgs, mode=cfg.register_combine, target_shape=after.shape[:2]
        )
        kind = (
            "single_other_slab"
            if len(ref_before_imgs) == 1
            else f"combined_{cfg.register_combine}"
        )
        registration = register_using_reference_slabs(
            before,
            after,
            ref_before,
            ref_after,
            enabled=cfg.register,
            reference_kind=kind,
            n_register_slabs=len(ref_before_imgs),
            combine_mode=cfg.register_combine,
        )
    else:
        registration = register_after_to_before(before, after, enabled=cfg.register)
        ref_before = before
        ref_after = after
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
        min_cc_mm2=cfg.min_cc_mm2,
    )
    maps_a_full = build_vessel_maps(
        after_reg,
        scale,
        roi=None,
        segment_mode=cfg.segment_mode,
        large_vessel_um=cfg.large_vessel_um,
        exclude_large_vessels=cfg.exclude_large_vessels,
        precomputed_binary=pre_after,
        min_cc_mm2=cfg.min_cc_mm2,
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
        roi_boxes=cfg.roi_boxes,
        exclude_disc_flag=cfg.exclude_disc,
        max_auto_roi_frac=cfg.max_auto_roi_frac,
    )

    if cfg.trim_roi_margin and roi_used in {"mask", "polygon"}:
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
    if used_ref_slabs:
        image_paths["register_ref_before"] = str(
            save_gray_png(out_dir / f"{cfg.case_id}_register_ref_before.png", ref_before)
        )
        image_paths["register_ref_after"] = str(
            save_gray_png(out_dir / f"{cfg.case_id}_register_ref_after.png", ref_after)
        )
        ref_after_warped = warp_gray(ref_after, registration.matrix, before.shape)
        image_paths["register_ref_after_warped"] = str(
            save_gray_png(
                out_dir / f"{cfg.case_id}_register_ref_after_warped.png",
                ref_after_warped,
            )
        )
        cc_analysis = compute_alignment_cc(before, after, registration.matrix)
        image_paths["register_qa"] = str(
            save_rgb_png(
                out_dir / f"{cfg.case_id}_register_qa.png",
                create_register_qa(
                    ref_before,
                    ref_after_warped,
                    before,
                    after_reg,
                    cc_ref=float(registration.score),
                    cc_ref_persistent=float(registration.persistent_score),
                    cc_analysis=float(cc_analysis),
                    tx=float(registration.translation_xy[0]),
                    ty=float(registration.translation_xy[1]),
                    method=registration.method,
                    reference_kind=registration.reference_kind,
                ),
            )
        )
        registration.analysis_score = float(cc_analysis)
    else:
        cc_analysis = compute_alignment_cc(before, after, registration.matrix)
        registration.analysis_score = float(cc_analysis)
        image_paths["register_qa"] = str(
            save_rgb_png(
                out_dir / f"{cfg.case_id}_register_qa.png",
                create_register_qa(
                    before,
                    after_reg,
                    before,
                    after_reg,
                    cc_ref=float(registration.score),
                    cc_ref_persistent=float(registration.persistent_score),
                    cc_analysis=float(cc_analysis),
                    tx=float(registration.translation_xy[0]),
                    ty=float(registration.translation_xy[1]),
                    method=registration.method,
                    reference_kind=registration.reference_kind,
                ),
            )
        )

    record: Dict[str, Any] = {
        "case_id": cfg.case_id,
        "before_path": str(before_path),
        "after_path": str(after_path),
        "roi_mode": roi_used,
        "exclude_large_vessels": bool(cfg.exclude_large_vessels),
        "large_vessel_threshold_um": float(cfg.large_vessel_um),
        "min_cc_mm2": float(cfg.min_cc_mm2),
        "max_auto_roi_frac": float(cfg.max_auto_roi_frac),
        "segment_mode": maps_b_full.segment_mode,
        "blank_border_top": 0 if crop is None else crop.top,
        "blank_border_bottom": 0 if crop is None else crop.bottom,
        "blank_border_left": 0 if crop is None else crop.left,
        "blank_border_right": 0 if crop is None else crop.right,
        "notes": (
            "raw metrics only; no MNV standardized score or maturity index; "
            "after_* images are in the registered before frame; "
            "prefer Retina / VRI+Retina Global / mean-of-all-slabs for registration"
        ),
        "registration_used_analysis_slab": not used_ref_slabs,
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
    if not used_ref_slabs and cfg.register:
        flags = record.get("quality_flags") or ""
        extra = "registration_on_analysis_slab"
        record["quality_flags"] = f"{flags};{extra}" if flags else extra
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


def _load_optional_slabs(paths: Optional[Sequence[str]]):
    if not paths:
        return []
    return [load_gray_u8(p) for p in paths]
