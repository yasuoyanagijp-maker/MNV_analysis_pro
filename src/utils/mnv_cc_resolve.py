"""
Resolve choroidal / CC (Flow Deficit source) sibling next to an MNV image.
Aligned with core.mnv_pipeline.MNVBatchAnalyzer._find_cc_file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

_SUPPORTED_SUFFIXES = (
    ".tif",
    ".tiff",
    ".jpg",
    ".jpeg",
    ".png",
    ".TIF",
    ".TIFF",
    ".JPG",
    ".JPEG",
    ".PNG",
)


def resolve_flow_deficit_cc_path(
    mnv_image_path: str | Path,
    *,
    mnv_suffix: str = "3.tif",
    cc_suffix: str = "4.tif",
) -> Optional[Path]:
    """
    Return path to sibling CC (*4.tif style) image if present, else None.
    """
    mnv_file = Path(mnv_image_path).resolve()
    if not mnv_file.is_file():
        return None

    mnv_pattern = mnv_suffix.rsplit(".", 1)[0] if "." in mnv_suffix else mnv_suffix
    cc_pattern = cc_suffix.rsplit(".", 1)[0] if "." in cc_suffix else cc_suffix

    if mnv_file.stem.endswith(mnv_pattern):
        base_name = mnv_file.stem[: -len(mnv_pattern)]
    else:
        base_name = mnv_file.stem

    for ext in _SUPPORTED_SUFFIXES:
        cc_file = mnv_file.parent / f"{base_name}{cc_pattern}{ext}"
        if cc_file.is_file():
            return cc_file

    return None
