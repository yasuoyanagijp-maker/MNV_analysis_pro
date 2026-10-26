"""Image-quality and exclusion flags for 15 mm PDR NVE (not MNV 0.5–1.5 µm/px)."""

from __future__ import annotations

from typing import Dict, List

import numpy as np

from .register import RegistrationResult
from .scale import PixelScale


def _snr_db(image: np.ndarray) -> float:
    signal = float(image.mean())
    noise = float(image.std())
    if noise <= 0:
        return 0.0
    return float(20.0 * np.log10(signal / (noise + 1e-10)))


def _contrast(image: np.ndarray) -> float:
    mx, mn = float(image.max()), float(image.min())
    return (mx - mn) / (mx + mn + 1e-10)


def frame_quality(image: np.ndarray, label: str) -> Dict:
    snr = _snr_db(image)
    contrast = _contrast(image)
    n_unique = int(len(np.unique(image)))
    sat = float(np.mean(image >= 250))
    dark = float(np.mean(image <= 2))
    flags: List[str] = []
    if snr < 8.0:
        flags.append(f"{label}_low_snr")
    if contrast < 0.15:
        flags.append(f"{label}_low_contrast")
    if n_unique < 40:
        flags.append(f"{label}_low_dynamic_range")
    if sat > 0.02:
        flags.append(f"{label}_saturated")
    if dark > 0.85:
        flags.append(f"{label}_mostly_blank")
    h, w = image.shape[:2]
    if h < 256 or w < 256:
        flags.append(f"{label}_tiny_image")
    return {
        f"{label}_snr_db": snr,
        f"{label}_contrast": contrast,
        f"{label}_dynamic_range": n_unique,
        f"{label}_sat_frac": sat,
        f"{label}_blank_frac": dark,
        "flags": flags,
    }


def collect_flags(
    before: np.ndarray,
    after: np.ndarray,
    scale: PixelScale,
    registration: RegistrationResult,
    roi: np.ndarray,
    before_vessel_px: int,
    after_vessel_px: int,
    roi_mode: str,
) -> Dict:
    q_b = frame_quality(before, "before")
    q_a = frame_quality(after, "after")
    flags: List[str] = list(q_b.pop("flags")) + list(q_a.pop("flags"))
    record = {}
    record.update(q_b)
    record.update(q_a)

    if registration.failed:
        flags.append("registration_failed")
    elif registration.score < 0.80:
        flags.append("low_registration_cc")
    if registration.valid_overlap_frac < 0.70:
        flags.append("low_registration_overlap")

    roi_px = int((roi > 0).sum())
    roi_frac = roi_px / float(before.size)
    if roi_px < 200:
        flags.append("tiny_roi")
    if roi_mode in {"full", "full_fallback"}:
        flags.append("full_field_roi")
    if roi_mode == "full_fallback":
        flags.append("auto_roi_failed")
    if before_vessel_px < 20:
        flags.append("before_empty_vessels")
    if after_vessel_px < 20:
        flags.append("after_empty_vessels")
    if roi_frac > 0.98:
        flags.append("roi_nearly_full_field")

    # Expected ~14.65 µm/px at 15 mm / 1024; do not treat as an error.
    expected = (scale.scan_size_mm * 1000.0) / max(scale.pixel_width_px, 1)
    if abs(scale.um_per_px - expected) > 0.5:
        flags.append("um_per_px_inconsistent")

    exclude = any(
        f in flags
        for f in (
            "registration_failed",
            "before_empty_vessels",
            "tiny_roi",
            "before_tiny_image",
            "after_tiny_image",
        )
    )
    record.update(
        {
            "quality_flags": flags,
            "exclude_suggested": exclude,
            "roi_frac": roi_frac,
        }
    )
    return record
