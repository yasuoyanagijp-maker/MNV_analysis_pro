"""Locked Method B ColorMask extract (Fiji-style difference on RGB viz).

ColorMask = Li(GaussianBlur(unweighted_mean(|raw − rgb_viz|), σ=1.0))

Moved out of tools/ so the Flet app can reuse the same extract without
importing the pilot scripts. Does not include Method C enclosure, Pass-2,
fill-holes, or morphological close.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import cv2
import numpy as np
from skimage.color import rgb2gray
from skimage.filters import gaussian

from core.mnv_pipeline import (
    FILTER_PARAMS_LARGE,
    FILTER_PARAMS_SMALL,
    SMALL_IMAGE_THRESHOLD,
)
from core.vessel_detection import MNVPreprocessor, VDProcessor
from utils.runtime_threads import use_filter_parallel

from .visualization_rgb import VisualizationRGB

GAUSSIAN_SIGMA = 1.0

# Empirically locked on all 6 grader×case runs (2026-08-15):
# unweighted (R+G+B)/3 + no Invert maximized Dice vs binary∩ROI (0.80–0.87).
# Invert would select the uncolored background and is rejected.
LOCKED_WEIGHTED = False
LOCKED_INVERT = False


@dataclass
class ColorMaskChoice:
    weighted: bool
    invert: bool
    dice: float
    mask: np.ndarray


def _dice(a: np.ndarray, b: np.ndarray) -> float:
    inter = np.logical_and(a, b).sum()
    denom = a.sum() + b.sum()
    if denom == 0:
        return 1.0
    return 2.0 * inter / denom


def _diff_gray(raw_u8: np.ndarray, rgb: np.ndarray, weighted: bool) -> np.ndarray:
    raw_rgb = np.stack([raw_u8] * 3, axis=-1).astype(np.int16)
    diff = np.abs(rgb.astype(np.int16) - raw_rgb).astype(np.uint8)
    if weighted:
        gray = rgb2gray(diff)
        if gray.max() <= 1.0:
            gray = gray * 255.0
        return gray.astype(np.float64)
    return diff.mean(axis=-1).astype(np.float64)


def _li_mask(diff_gray: np.ndarray, invert: bool) -> np.ndarray:
    blurred = gaussian(diff_gray, sigma=GAUSSIAN_SIGMA, preserve_range=True)
    thresh = VDProcessor.li_threshold_imagej_style(
        np.clip(blurred, 0, 255).astype(np.uint8)
    )
    mask = blurred > thresh
    if invert:
        mask = ~mask
    return mask


def extract_color_mask(
    raw_u8: np.ndarray,
    rgb: np.ndarray,
    reference: Optional[np.ndarray] = None,
) -> ColorMaskChoice:
    """Locked Method B extract. ``reference`` is only used for the Dice field."""
    gray = _diff_gray(raw_u8, rgb, weighted=LOCKED_WEIGHTED)
    mask = _li_mask(gray, invert=LOCKED_INVERT)
    dice = _dice(mask, reference) if reference is not None else 0.0
    return ColorMaskChoice(
        LOCKED_WEIGHTED, LOCKED_INVERT, dice, mask
    )


def detect_fullfield_vessels(image_u8: np.ndarray) -> np.ndarray:
    """Full-field vessel binary (same recipe as method_b ``_detect_vessels``).

    Filter params follow the same width gate as the analysis pipeline
    (``MNVPipeline.analyze``: width < ``SMALL_IMAGE_THRESHOLD`` → SMALL,
    else LARGE) so the trim preview matches the vessels the analysis sees.
    """
    width = int(image_u8.shape[1])
    params = (
        FILTER_PARAMS_SMALL if width < SMALL_IMAGE_THRESHOLD else FILTER_PARAMS_LARGE
    )
    preprocessor = MNVPreprocessor(
        mexican_hat_sigma=1.0,
        tubeness_sigma=2.5,
        filter_params=dict(params),
        use_parallel=use_filter_parallel(),
    )
    out = preprocessor.preprocess_mnv(image_u8, roi_mask=np.ones_like(image_u8) * 255)
    binary = out["binary"]
    return ((binary > 0).astype(np.uint8)) * 255


def create_preview_rgb(
    image_u8: np.ndarray,
    binary: np.ndarray,
    lesion_mask: np.ndarray,
    pixel_size_mm: float = 0.003,
) -> np.ndarray:
    """RGB viz for ColorMask / on-screen preview. Overlays off."""
    vis = VisualizationRGB(pixel_size_mm=pixel_size_mm)
    return vis.create_rgb_visualization(
        original_image=image_u8,
        binary_vessel=binary,
        lesion_mask=lesion_mask,
        metrics=None,
        highskew_mask=None,
        add_overlays=False,
    )


def compute_rgb_and_color_mask(
    raw_u8: np.ndarray,
    lesion_mask: np.ndarray,
    vessel_binary: Optional[np.ndarray] = None,
    pixel_size_mm: float = 0.003,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Detect (or reuse) vessels, build preview RGB, extract ColorMask.

    Does not modify ``lesion_mask``. Returns
    ``(vessel_binary uint8, rgb_viz RGB uint8, color_mask bool)``.
    """
    h, w = raw_u8.shape[:2]
    if lesion_mask.shape[:2] != (h, w):
        lesion_mask = cv2.resize(
            lesion_mask, (w, h), interpolation=cv2.INTER_NEAREST
        )
    if vessel_binary is None:
        vessel_binary = detect_fullfield_vessels(raw_u8)
    elif vessel_binary.shape[:2] != (h, w):
        vessel_binary = cv2.resize(
            vessel_binary, (w, h), interpolation=cv2.INTER_NEAREST
        )
    rgb = create_preview_rgb(raw_u8, vessel_binary, lesion_mask, pixel_size_mm)
    reference = (vessel_binary > 0) & (lesion_mask > 0)
    choice = extract_color_mask(raw_u8, rgb, reference)
    return vessel_binary, rgb, choice.mask
