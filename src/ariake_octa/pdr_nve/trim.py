"""
Blank-margin helpers.

1. Common near-black image borders (export letterboxing).
2. ROI 余白trim — same rule as the MNV ColorMask / method-B-prime refine:
   drop uncolored padding that touches the ROI exterior; keep enclosed holes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import cv2
import numpy as np


@dataclass(frozen=True)
class BorderCrop:
    top: int
    bottom: int
    left: int
    right: int

    def apply(self, image: np.ndarray) -> np.ndarray:
        h, w = image.shape[:2]
        y0, y1 = self.top, h - self.bottom
        x0, x1 = self.left, w - self.right
        if y1 <= y0 or x1 <= x0:
            return image
        return image[y0:y1, x0:x1]

    @property
    def cropped(self) -> bool:
        return any((self.top, self.bottom, self.left, self.right))


def _blank_rows(image: np.ndarray, max_value: int, max_frac: float) -> Tuple[int, int]:
    h = image.shape[0]
    bright = image > max_value
    row_frac = bright.mean(axis=1) if bright.ndim == 2 else bright.mean(axis=(1, 2))
    keep = row_frac > max_frac
    if not np.any(keep):
        return 0, 0
    ys = np.where(keep)[0]
    return int(ys[0]), int(h - 1 - ys[-1])


def _blank_cols(image: np.ndarray, max_value: int, max_frac: float) -> Tuple[int, int]:
    w = image.shape[1]
    bright = image > max_value
    col_frac = bright.mean(axis=0) if bright.ndim == 2 else bright.mean(axis=(0, 2))
    keep = col_frac > max_frac
    if not np.any(keep):
        return 0, 0
    xs = np.where(keep)[0]
    return int(xs[0]), int(w - 1 - xs[-1])


def detect_blank_border(
    image: np.ndarray,
    max_value: int = 3,
    max_bright_frac: float = 0.002,
) -> BorderCrop:
    """Rows/cols whose bright-pixel fraction is below ``max_bright_frac``."""
    top, bottom = _blank_rows(image, max_value, max_bright_frac)
    left, right = _blank_cols(image, max_value, max_bright_frac)
    return BorderCrop(top=top, bottom=bottom, left=left, right=right)


def common_blank_border(before: np.ndarray, after: np.ndarray) -> BorderCrop:
    """Crop only margins that are blank on *both* frames (keeps them aligned)."""
    a = detect_blank_border(before)
    b = detect_blank_border(after)
    return BorderCrop(
        top=min(a.top, b.top),
        bottom=min(a.bottom, b.bottom),
        left=min(a.left, b.left),
        right=min(a.right, b.right),
    )


def trim_roi_blank_margin(
    roi: np.ndarray,
    color_or_vessel: np.ndarray,
) -> Tuple[np.ndarray, dict]:
    """
    Existing MNV 余白trim (method-B prime): ROI minus border-touching uncolored
    padding. Enclosed uncolored pockets stay inside the lesion contour.
    """
    roi_b = roi.astype(bool)
    color = color_or_vessel.astype(bool)
    if roi_b.shape != color.shape:
        color_u8 = (color.astype(np.uint8)) * 255
        color_u8 = cv2.resize(
            color_u8, (roi_b.shape[1], roi_b.shape[0]), interpolation=cv2.INTER_NEAREST
        )
        color = color_u8 > 0

    padding = np.logical_and(roi_b, np.logical_not(color))
    exterior = np.logical_not(roi_b)
    kernel = np.ones((3, 3), np.uint8)
    touches_exterior = cv2.dilate(exterior.astype(np.uint8), kernel, iterations=1) > 0

    n_labels, labels = cv2.connectedComponents(padding.astype(np.uint8), connectivity=8)
    border = np.zeros_like(padding, dtype=bool)
    n_cc_border = 0
    n_cc_enclosed = 0
    for lab in range(1, n_labels):
        cc = labels == lab
        if np.any(np.logical_and(cc, touches_exterior)):
            border[cc] = True
            n_cc_border += 1
        else:
            n_cc_enclosed += 1

    refined = np.logical_and(roi_b, np.logical_not(border))
    if int(refined.sum()) == 0:
        refined = roi_b

    info = {
        "n_padding_px": int(padding.sum()),
        "n_border_padding_px": int(border.sum()),
        "n_cc_border": n_cc_border,
        "n_cc_enclosed": n_cc_enclosed,
        "n_roi_before_px": int(roi_b.sum()),
        "n_roi_after_px": int(refined.sum()),
    }
    return (refined.astype(np.uint8) * 255), info


def maybe_compute_color_mask(
    image_u8: np.ndarray,
    roi: np.ndarray,
    vessel_binary: Optional[np.ndarray] = None,
) -> Optional[np.ndarray]:
    """
    Best-effort reuse of ``ariake_octa.mnv.color_mask``. Returns None if the
    MNV visualization stack cannot be imported (PDR CLI must still run).
    """
    try:
        from ariake_octa.mnv.color_mask import compute_rgb_and_color_mask
    except Exception:
        return None
    try:
        _binary, _rgb, mask = compute_rgb_and_color_mask(
            image_u8, roi, vessel_binary=vessel_binary
        )
        return mask.astype(bool)
    except Exception:
        return None
