"""
MNV-absent / negative-sample encoding for MedSAM-style training + CSV audit.

Conventions (see research notes in metadata_export / USER_MANUAL):
  - Keep paired ``images/`` + ``masks/``: write an **all-zero** binary mask (0/255).
  - Presence is a **dedicated label** (``mnv_present``), not image QC.
  - Numeric morphometrics are left empty (NA); analysis was not run.
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import cv2
import numpy as np

ANNOTATION_STATUS_ABSENT = "mnv_absent"
SKIP_REASON_NO_CLEAR_MNV = "no_clear_mnv"
QC_STATUS_ABSENT = "N/A"  # no analysis to Pass/Fail; not "Fail"


def is_mnv_absent_result(result: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(result, dict):
        return False
    if result.get("mnv_present") is False or result.get("mnv_absent") is True:
        return True
    return str(result.get("annotation_status") or "") == ANNOTATION_STATUS_ABSENT


def encode_zero_mask_png_b64(height: int, width: int) -> str:
    """All-black / empty binary mask as PNG base64 (MedSAM negative target)."""
    h = max(int(height), 1)
    w = max(int(width), 1)
    mask = np.zeros((h, w), dtype=np.uint8)
    ok, buf = cv2.imencode(".png", mask)
    if not ok:
        raise RuntimeError("Failed to encode empty MNV mask")
    return base64.b64encode(buf.tobytes()).decode("utf-8")


def zero_mask_array(height: int, width: int) -> np.ndarray:
    return np.zeros((max(int(height), 1), max(int(width), 1)), dtype=np.uint8)


def build_mnv_absent_result(
    source_path: str,
    *,
    scale_mm: float = 6.0,
    height: Optional[int] = None,
    width: Optional[int] = None,
    mask_b64: Optional[str] = None,
    skip_reason: str = SKIP_REASON_NO_CLEAR_MNV,
) -> Dict[str, Any]:
    """
    Durable session/API row for a user Skip (no clear MNV).

    Does not run the MNV pipeline; metrics stay empty for CSV NA.
    """
    clean = str(source_path).strip().strip("'").strip('"')
    path = Path(clean)
    if height is None or width is None:
        from src.utils.cv2_path import imread_grayscale

        img = imread_grayscale(clean)
        if img is None:
            raise ValueError(f"Cannot load image for MNV-absent record: {clean}")
        height, width = int(img.shape[0]), int(img.shape[1])

    if not mask_b64:
        mask_b64 = encode_zero_mask_png_b64(int(height), int(width))

    try:
        scale = float(scale_mm) if scale_mm is not None else 6.0
    except (TypeError, ValueError):
        scale = 6.0
    if scale <= 0:
        scale = 6.0

    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    csv_metrics: Dict[str, Any] = {
        "mnv_present": False,
        "mnv_absent": True,
        "annotation_status": ANNOTATION_STATUS_ABSENT,
        "skip_reason": skip_reason,
    }

    return {
        "result_type": "MNV",
        "source_filename": path.name,
        "_absolute_source_path": clean,
        "image_path": clean,
        "analysis_timestamp": stamp,
        "mnv_present": False,
        "mnv_absent": True,
        "annotation_status": ANNOTATION_STATUS_ABSENT,
        "skip_reason": skip_reason,
        "qc_status": QC_STATUS_ABSENT,
        "quality_of_analysis": QC_STATUS_ABSENT,
        "mask_base64": mask_b64,
        "csv_metrics": csv_metrics,
        "scale_mm": scale,
        "fov_mm": scale,
        "status": "mnv_absent",
    }
