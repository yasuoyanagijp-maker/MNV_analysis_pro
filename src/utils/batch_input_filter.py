"""
Batch folder file selection aligned with mainstreamer.py (Streamlit).

MNV folder batch: exclude superficial/deep/FD slot filenames so ROI queue matches Streamlit.
VD folder batch: no filename-based exclusion (pairing is done in VDAnalyzer by suffixes).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List


def filter_mnv_files_for_roi_selection(
    image_files: List[Path],
    analysis_type: str = "MNV",
    *,
    fallback_all_if_empty: bool = True,
) -> List[Path]:
    """
    MNV folder batch: exclude *1 / *2 / *4 extensions and image1/2/4 name patterns.
    VD: return list unchanged (same as mainstreamer.filter_mnv_files_for_roi_selection).
    """
    if analysis_type != "MNV":
        return list(image_files)

    filtered_files: List[Path] = []
    exclude_patterns = [
        (r"1\.(tif|tiff|png|jpg|jpeg)$", re.IGNORECASE),
        (r"2\.(tif|tiff|png|jpg|jpeg)$", re.IGNORECASE),
        (r"4\.(tif|tiff|png|jpg|jpeg)$", re.IGNORECASE),
        (r"image[124]", re.IGNORECASE),
    ]

    for file_path in image_files:
        filename = file_path.name
        should_exclude = False
        for pattern, flags in exclude_patterns:
            if re.search(pattern, filename, flags):
                should_exclude = True
                break
        if should_exclude:
            continue
        filtered_files.append(file_path)

    if not filtered_files and len(image_files) > 0:
        if fallback_all_if_empty:
            return list(image_files)
        return []

    return filtered_files
