"""Recordable pixel size for wide-field PDR OCTA (not the MNV 3/6 mm defaults)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class PixelScale:
    """Physical scale derived from scan size and pixel width (or an explicit um/px)."""

    scan_size_mm: float
    pixel_width_px: int
    pixel_height_px: int
    um_per_px: float

    @property
    def mm_per_px(self) -> float:
        return self.um_per_px / 1000.0

    def area_mm2(self, n_pixels: int) -> float:
        return float(n_pixels) * (self.mm_per_px**2)

    def length_mm(self, n_pixels: float) -> float:
        return float(n_pixels) * self.mm_per_px

    def to_record(self) -> dict:
        return {
            "scan_size_mm": self.scan_size_mm,
            "pixel_width_px": int(self.pixel_width_px),
            "pixel_height_px": int(self.pixel_height_px),
            "um_per_px": self.um_per_px,
            "mm_per_px": self.mm_per_px,
        }


def resolve_pixel_scale(
    image_shape: tuple,
    scan_size_mm: float = 15.0,
    pixel_width_px: Optional[int] = None,
    um_per_px: Optional[float] = None,
) -> PixelScale:
    """
    Resolve µm/px from either an explicit value or ``scan_size_mm / pixel_width``.

    Default intended use: 15 mm over 1024 px → ≈ 14.648 µm/px.
    """
    h, w = int(image_shape[0]), int(image_shape[1])
    width = int(pixel_width_px) if pixel_width_px else w
    if width <= 0:
        raise ValueError(f"pixel_width_px must be positive, got {width}")
    if um_per_px is not None:
        if um_per_px <= 0:
            raise ValueError(f"um_per_px must be positive, got {um_per_px}")
        resolved = float(um_per_px)
        scan = float(scan_size_mm) if scan_size_mm > 0 else resolved * width / 1000.0
    else:
        if scan_size_mm <= 0:
            raise ValueError(f"scan_size_mm must be positive, got {scan_size_mm}")
        resolved = (float(scan_size_mm) * 1000.0) / float(width)
        scan = float(scan_size_mm)
    return PixelScale(
        scan_size_mm=scan,
        pixel_width_px=width,
        pixel_height_px=h,
        um_per_px=resolved,
    )
