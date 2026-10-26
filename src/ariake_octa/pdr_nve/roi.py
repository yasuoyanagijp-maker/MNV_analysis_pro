"""Freeform ROI: mask / polygon / auto lesion contour / full field."""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np
from skimage.morphology import (
    binary_closing,
    disk,
    remove_small_holes,
    remove_small_objects,
)

from .io import load_mask_u8, load_polygon, polygon_to_mask
from .scale import PixelScale
from .vessels import VesselMaps


def _as_u8(mask: np.ndarray) -> np.ndarray:
    return ((mask > 0).astype(np.uint8)) * 255


def auto_lesion_roi(
    maps: VesselMaps,
    scale: PixelScale,
    min_component_mm2: float = 0.15,
) -> Optional[np.ndarray]:
    """
    Estimate a freeform NVE contour from the *before* frame.

    After large-vessel removal, keep regions of locally high remaining-vessel
    density, close gaps, and retain the largest component(s). Returns None if
    nothing usable is found (caller should fall back to full field).
    """
    nve = maps.binary_no_large
    if int(nve.sum()) < 32:
        nve = maps.binary
    if int(nve.sum()) < 16:
        return None

    win_um = 250.0
    k = max(9, int(round(win_um / scale.um_per_px)))
    if k % 2 == 0:
        k += 1
    dens = cv2.blur(nve.astype(np.float32), (k, k))
    peak = float(dens.max())
    if peak <= 0:
        return None
    thr = max(0.04, 0.30 * peak)
    mask = dens >= thr
    close_r = max(2, k // 8)
    mask = binary_closing(mask, disk(close_r))
    min_px = max(64, int(round(min_component_mm2 / (scale.mm_per_px**2))))
    mask = remove_small_objects(mask, min_size=min_px, connectivity=2)
    mask = remove_small_holes(mask, area_threshold=min_px)
    if int(mask.sum()) == 0:
        return None

    n_lab, labels, stats, _ = cv2.connectedComponentsWithStats(
        mask.astype(np.uint8), connectivity=8
    )
    if n_lab <= 1:
        return None
    areas = stats[1:, cv2.CC_STAT_AREA]
    order = np.argsort(areas)[::-1]
    keep = np.zeros_like(mask, dtype=bool)
    kept_area = 0
    total = int(areas.sum())
    for idx in order:
        keep |= labels == (idx + 1)
        kept_area += int(areas[idx])
        if kept_area >= 0.85 * total:
            break
    if int(keep.sum()) < min_px:
        return None
    return _as_u8(keep)


def exclude_disc(
    roi: np.ndarray,
    image_u8: np.ndarray,
    scale: PixelScale,
    radius_mm: float = 0.85,
) -> Tuple[np.ndarray, dict]:
    """
    Conservative optic-disc punch-out: darkest compact circular region whose
    radius is near ``radius_mm``. No-op if nothing plausible is found.
    """
    h, w = image_u8.shape[:2]
    r_px = int(round(radius_mm / scale.mm_per_px))
    r_px = max(8, min(r_px, min(h, w) // 6))
    blur = cv2.GaussianBlur(image_u8, (0, 0), max(1.0, r_px / 6.0))
    circles = cv2.HoughCircles(
        blur,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=float(r_px),
        param1=80,
        param2=25,
        minRadius=int(r_px * 0.55),
        maxRadius=int(r_px * 1.45),
    )
    info = {"disc_excluded": False, "disc_cx": None, "disc_cy": None, "disc_r_px": None}
    if circles is None:
        return roi, info
    circ = np.round(circles[0]).astype(int)
    # Prefer a circle whose interior is relatively dark.
    best = None
    best_score = 1e9
    for x, y, r in circ:
        if not (0 <= x < w and 0 <= y < h):
            continue
        yy, xx = np.ogrid[:h, :w]
        disk_m = (xx - x) ** 2 + (yy - y) ** 2 <= r**2
        if int(disk_m.sum()) < 16:
            continue
        score = float(image_u8[disk_m].mean())
        if score < best_score:
            best_score = score
            best = (int(x), int(y), int(r))
    if best is None:
        return roi, info
    # Reject bright false positives (NVE tufts).
    if best_score > float(np.median(image_u8)) + 15:
        return roi, info
    cx, cy, r = best
    yy, xx = np.ogrid[:h, :w]
    disc = (xx - cx) ** 2 + (yy - cy) ** 2 <= r**2
    out = (roi > 0) & np.logical_not(disc)
    if int(out.sum()) < 32:
        return roi, info
    info.update(
        {"disc_excluded": True, "disc_cx": cx, "disc_cy": cy, "disc_r_px": r}
    )
    return _as_u8(out), info


def resolve_roi(
    shape: tuple,
    scale: PixelScale,
    maps_before: VesselMaps,
    image_before: np.ndarray,
    roi_mode: str = "auto",
    roi_mask_path: Optional[str] = None,
    roi_polygon_path: Optional[str] = None,
    roi_polygon: Optional[Sequence[tuple]] = None,
    exclude_disc_flag: bool = False,
) -> Tuple[np.ndarray, str, dict]:
    """
    Return ``(roi_u8, mode_used, extra)``.

    Modes: ``mask``, ``polygon``, ``auto``, ``full``.
    """
    extra: dict = {}
    mode = (roi_mode or "auto").strip().lower()
    if roi_mask_path:
        roi = load_mask_u8(roi_mask_path, shape=shape)
        used = "mask"
    elif roi_polygon is not None or roi_polygon_path:
        poly: List[tuple] = (
            list(roi_polygon) if roi_polygon is not None else load_polygon(roi_polygon_path)
        )
        roi = polygon_to_mask(poly, shape)
        used = "polygon"
        extra["n_polygon_vertices"] = len(poly)
    elif mode == "full":
        roi = np.ones(shape[:2], dtype=np.uint8) * 255
        used = "full"
    else:
        auto = auto_lesion_roi(maps_before, scale)
        if auto is None:
            roi = np.ones(shape[:2], dtype=np.uint8) * 255
            used = "full_fallback"
            extra["auto_roi_failed"] = True
        else:
            roi = auto
            used = "auto"

    if exclude_disc_flag:
        roi, disc_info = exclude_disc(roi, image_before, scale)
        extra.update(disc_info)

    if int((roi > 0).sum()) == 0:
        roi = np.ones(shape[:2], dtype=np.uint8) * 255
        used = "full_fallback"
        extra["empty_roi_fallback"] = True

    extra["roi_px"] = int((roi > 0).sum())
    return _as_u8(roi), used, extra
