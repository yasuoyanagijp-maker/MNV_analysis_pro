"""
Batch folder file selection aligned with mainstreamer.py (Streamlit).

MNV folder batch: exclude superficial/deep/FD slot filenames so ROI queue matches Streamlit.
VD folder batch: no filename-based exclusion (pairing is done in VDAnalyzer by suffixes).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List


# OCTA slot suffixes (superficial=1, deep=2, CC/FD=4). Require a non-digit before the
# channel digit so multi-digit case IDs like Patient001.tif / Patient002.tif are kept.
_OCTA_SLOT_SUFFIX = re.compile(
    r"(?<![0-9])[124]\.(?:tif|tiff|png|jpg|jpeg)$",
    re.IGNORECASE,
)
# Legacy image1 / image2 / image4 tokens — do not match image10 / image20 / image40.
_IMAGE_SLOT_TOKEN = re.compile(r"image[124](?![0-9])", re.IGNORECASE)


def filter_mnv_files_for_roi_selection(
    image_files: List[Path],
    analysis_type: str = "MNV",
    *,
    fallback_all_if_empty: bool = True,
) -> List[Path]:
    """
    MNV folder batch: exclude OCTA slot filenames (*1/*2/*4, image1/2/4) so the ROI
    queue keeps en-face MNV frames (typically *3).

    Channel digits must not be part of a larger trailing number (Patient001 stays).
    ``image10`` is not treated as ``image1``.
    VD: return list unchanged (same as mainstreamer.filter_mnv_files_for_roi_selection).
    """
    if analysis_type != "MNV":
        return list(image_files)

    filtered_files: List[Path] = []

    for file_path in image_files:
        filename = file_path.name
        if _OCTA_SLOT_SUFFIX.search(filename) or _IMAGE_SLOT_TOKEN.search(filename):
            continue
        filtered_files.append(file_path)

    if not filtered_files and len(image_files) > 0:
        if fallback_all_if_empty:
            return list(image_files)
        return []

    return filtered_files


def select_mnv_images_for_batch(
    image_files: List[Path],
    *,
    mode: str = "auto",
    fallback_all_if_empty: bool = True,
) -> List[Path]:
    """
    Select MNV batch images.

    mode:
      - "auto": suffix/name filter (*1/*2/*4, image1/2/4 excluded)
      - "all": every image in the folder (sorted by filename)
    """
    if mode == "all":
        return sorted(image_files, key=lambda p: p.name.lower())
    return filter_mnv_files_for_roi_selection(
        image_files,
        "MNV",
        fallback_all_if_empty=fallback_all_if_empty,
    )
