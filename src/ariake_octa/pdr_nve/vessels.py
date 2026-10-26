"""Vessel segmentation and large-caliber exclusion for 15 mm PDR NVE."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np
from scipy.ndimage import distance_transform_edt
from skimage.morphology import remove_small_objects, skeletonize

from ._paths import ensure_import_paths
from .scale import PixelScale

ensure_import_paths()


@dataclass
class VesselMaps:
    binary: np.ndarray
    binary_no_large: np.ndarray
    large_mask: np.ndarray
    skeleton: np.ndarray
    skeleton_no_large: np.ndarray
    distance_px: np.ndarray
    segment_mode: str

    def in_roi(self, roi: np.ndarray) -> "VesselMaps":
        r = roi > 0
        return VesselMaps(
            binary=self.binary & r,
            binary_no_large=self.binary_no_large & r,
            large_mask=self.large_mask & r,
            skeleton=self.skeleton & r,
            skeleton_no_large=self.skeleton_no_large & r,
            distance_px=np.where(r, self.distance_px, 0.0),
            segment_mode=self.segment_mode,
        )


def _as_bool(mask: np.ndarray) -> np.ndarray:
    return mask.astype(bool) if mask.dtype != bool else mask


def segment_vessels_adaptive(image_u8: np.ndarray, roi: Optional[np.ndarray] = None) -> np.ndarray:
    """CLAHE + Li threshold fallback (no MNV preprocessor)."""
    from skimage.filters import threshold_li

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(image_u8)
    blurred = cv2.GaussianBlur(enhanced, (0, 0), 1.0)
    thr = float(threshold_li(blurred))
    binary = blurred > max(thr, 8.0)
    if roi is not None:
        binary = binary & (roi > 0)
    binary = remove_small_objects(binary, min_size=16, connectivity=2)
    return binary


def segment_vessels_mnv(image_u8: np.ndarray, roi: Optional[np.ndarray] = None) -> np.ndarray:
    """Reuse the MNV preprocessor (Mexican Hat + Tubeness). Does not score MNV."""
    from core.mnv_pipeline import (
        FILTER_PARAMS_LARGE,
        FILTER_PARAMS_SMALL,
        SMALL_IMAGE_THRESHOLD,
    )
    from core.vessel_detection import MNVPreprocessor
    from utils.runtime_threads import use_filter_parallel

    width = int(image_u8.shape[1])
    params = dict(
        FILTER_PARAMS_SMALL if width < SMALL_IMAGE_THRESHOLD else FILTER_PARAMS_LARGE
    )
    # 15 mm / 1024 px vessels are thinner in pixels than 6 mm MNV; keep a
    # slightly smaller tubeness sigma unless the caller overwrote filter_params.
    params.setdefault("sigma", 1.5)
    roi_u8 = (
        np.ones(image_u8.shape[:2], dtype=np.uint8) * 255
        if roi is None
        else ((roi > 0).astype(np.uint8) * 255)
    )
    preprocessor = MNVPreprocessor(
        mexican_hat_sigma=1.0,
        tubeness_sigma=float(params.get("sigma", 1.5)),
        filter_params=params,
        use_parallel=use_filter_parallel(),
    )
    out = preprocessor.preprocess_mnv(image_u8, roi_mask=roi_u8)
    binary = out["binary"] > 0
    if roi is not None:
        binary = binary & (roi > 0)
    return binary


def segment_vessels(
    image_u8: np.ndarray,
    roi: Optional[np.ndarray] = None,
    mode: str = "mnv",
) -> np.ndarray:
    mode = (mode or "mnv").strip().lower()
    if mode == "adaptive":
        return segment_vessels_adaptive(image_u8, roi)
    if mode != "mnv":
        raise ValueError(f"Unknown segment mode: {mode}")
    try:
        return segment_vessels_mnv(image_u8, roi)
    except Exception:
        # Keep the CLI usable if the heavy preprocessor fails in a slim env.
        return segment_vessels_adaptive(image_u8, roi)


def large_vessel_mask(
    binary: np.ndarray,
    scale: PixelScale,
    threshold_um: float,
    distance_px: Optional[np.ndarray] = None,
) -> np.ndarray:
    """
    Pixels whose local diameter (2 × EDT × µm/px) exceeds ``threshold_um``.

    The mask is dilated by the corresponding radius so the full trunk width is
    removed, not only the centerline.
    """
    bw = _as_bool(binary)
    if distance_px is None:
        distance_px = distance_transform_edt(bw)
    diameter_um = distance_px * 2.0 * scale.um_per_px
    core = bw & (diameter_um >= float(threshold_um))
    radius_px = max(1, int(round((float(threshold_um) / 2.0) / scale.um_per_px)))
    kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (2 * radius_px + 1, 2 * radius_px + 1)
    )
    dilated = cv2.dilate(core.astype(np.uint8), kernel, iterations=1) > 0
    return dilated & bw


def build_vessel_maps(
    image_u8: np.ndarray,
    scale: PixelScale,
    roi: Optional[np.ndarray] = None,
    segment_mode: str = "mnv",
    large_vessel_um: float = 100.0,
    exclude_large_vessels: bool = True,
    precomputed_binary: Optional[np.ndarray] = None,
) -> VesselMaps:
    binary = (
        _as_bool(precomputed_binary)
        if precomputed_binary is not None
        else segment_vessels(image_u8, roi=roi, mode=segment_mode)
    )
    if roi is not None:
        binary = binary & (roi > 0)
    distance_px = distance_transform_edt(binary)
    if exclude_large_vessels:
        large = large_vessel_mask(
            binary, scale, threshold_um=large_vessel_um, distance_px=distance_px
        )
        no_large = binary & np.logical_not(large)
    else:
        large = np.zeros(binary.shape, dtype=bool)
        no_large = binary
    skel = skeletonize(binary)
    skel_nl = skeletonize(no_large)
    return VesselMaps(
        binary=binary,
        binary_no_large=no_large,
        large_mask=large,
        skeleton=skel,
        skeleton_no_large=skel_nl,
        distance_px=distance_px,
        segment_mode=segment_mode if precomputed_binary is None else "precomputed",
    )
