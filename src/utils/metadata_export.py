"""
Export analysis logs as LoRA / dataset-ready bundles.

Layout (under the CSV target output dir, or app data root):
  export/{institution_id}/{lesion_id}/
    image_raw.png   — en-face without ROI overlay
    mask_roi.png    — binary ROI mask (0/255)
    meta.json       — annotation + acquisition metadata

Designed for SAM-OCTA2 fine-tuning (Colab) and multi-site Hold-out splits.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

from src.utils.app_paths import get_base_data_dir, sanitize_path_component
from src.utils.cv2_path import imread_grayscale
from src.utils.image_utils import ScaleManager
from src.utils.institution_config import normalize_institution_id
from src.utils.vd_batch_csv import is_vd_result_row

SOP_VERSION = "1.0"
SESSION_LABEL = "initial"
CONSENT_FLAG = True

# Heuristic device labels aligned with size_class / FOV used in the pipeline
_DEVICE_BY_STRATUM = {
    "small_3mm": "CIRRUS",
    "large": "PlexElite",
    "small": "Solix",
}


def _imwrite_png(path: Path, image: np.ndarray) -> None:
    """Unicode-safe PNG write via imencode (cv2.imwrite fails on non-ASCII paths)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, buf = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError(f"Failed to encode PNG: {path}")
    path.write_bytes(buf.tobytes())


def _decode_mask_bytes(data: bytes) -> Optional[np.ndarray]:
    arr = np.frombuffer(data, dtype=np.uint8)
    mask = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if mask is None or mask.size == 0:
        return None
    return mask


def _load_roi_mask(
    result: Dict[str, Any],
    *,
    session_mask_b64: Optional[str] = None,
    target_shape: Optional[Tuple[int, int]] = None,
) -> Optional[np.ndarray]:
    """
    Resolve ROI mask from result / disk / session (same sources as ROI confirm flow).

    Priority: mask_path → mask_base64 → session roi_mask_b64
    """
    mask: Optional[np.ndarray] = None

    mask_path = result.get("mask_path")
    if mask_path and Path(str(mask_path)).is_file():
        mask = imread_grayscale(str(mask_path))

    if mask is None:
        b64 = result.get("mask_base64") or session_mask_b64
        if b64:
            try:
                raw = base64.b64decode(b64)
                mask = _decode_mask_bytes(raw)
            except Exception:
                mask = None

    if mask is None:
        return None

    if target_shape is not None and mask.shape[:2] != target_shape:
        h, w = target_shape
        mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)

    # Force 0/255 binary
    return ((mask > 0).astype(np.uint8)) * 255


def _resolve_source_path(
    result: Dict[str, Any],
    *,
    source_path_hint: Optional[str] = None,
) -> Optional[Path]:
    for key in ("_absolute_source_path", "image_path", "target_path"):
        raw = result.get(key)
        if raw and Path(str(raw)).is_file():
            return Path(str(raw))
    if source_path_hint and Path(str(source_path_hint)).is_file():
        return Path(str(source_path_hint))
    return None


def _lesion_id_from_result(result: Dict[str, Any], source_path: Optional[Path]) -> str:
    name = result.get("source_filename") or (source_path.name if source_path else "lesion")
    stem = Path(str(name)).stem
    safe = sanitize_path_component(stem) or "lesion"
    return safe


def _fov_mm(result: Dict[str, Any], *, scale_mm_hint: Optional[float] = None) -> float:
    cm = result.get("csv_metrics") if isinstance(result.get("csv_metrics"), dict) else {}
    for candidate in (
        result.get("scale_mm"),
        result.get("fov_mm"),
        cm.get("scale_mm"),
        scale_mm_hint,
    ):
        try:
            if candidate is not None and float(candidate) > 0:
                return float(candidate)
        except (TypeError, ValueError):
            pass
    return 6.0


def _stratum(result: Dict[str, Any], fov_mm: float, image_width: int) -> str:
    cm = result.get("csv_metrics") if isinstance(result.get("csv_metrics"), dict) else {}
    sc = cm.get("size_class") or result.get("size_class")
    if sc in ("small_3mm", "small", "large"):
        return str(sc)
    # Mirror MNVPipeline._perform_spatial_analysis
    if abs(float(fov_mm) - 3.0) < 0.01:
        return "small_3mm"
    if image_width > 800 or float(fov_mm) >= 6.0:
        return "large"
    return "small"


def _px_per_mm(result: Dict[str, Any], image_width: int, fov_mm: float) -> float:
    cm = result.get("csv_metrics") if isinstance(result.get("csv_metrics"), dict) else {}
    mpp = cm.get("mm_per_pixel") or result.get("mm_per_pixel")
    try:
        if mpp is not None and float(mpp) > 0:
            return 1.0 / float(mpp)
    except (TypeError, ValueError):
        pass
    if image_width > 0 and fov_mm > 0:
        mpp = ScaleManager(image_width, fov_mm).mm_per_pixel
        return (1.0 / mpp) if mpp > 0 else 0.0
    return 0.0


def _infer_device(
    stratum: str,
    result: Dict[str, Any],
    *,
    device_hint: Optional[str] = None,
) -> str:
    explicit = result.get("device") or device_hint
    if explicit:
        return str(explicit)
    return _DEVICE_BY_STRATUM.get(stratum, "unknown")


def _acquisition_date(source_path: Optional[Path], result: Dict[str, Any]) -> str:
    """Prefer file mtime (UTC date); fall back to analysis_timestamp date."""
    if source_path is not None:
        try:
            ts = source_path.stat().st_mtime
            return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
        except OSError:
            pass
    stamp = str(result.get("analysis_timestamp") or "").strip()
    if stamp:
        return stamp[:10]
    return datetime.now(timezone.utc).date().isoformat()


def build_meta_dict(
    *,
    lesion_id: str,
    institution_id: str,
    device: str,
    stratum: str,
    fov_mm: float,
    px_per_mm: float,
    rater_id: str,
    acquisition_date: str,
) -> Dict[str, Any]:
    return {
        "lesion_id": lesion_id,
        "institution_id": institution_id,
        "device": device,
        "stratum": stratum,
        "fov_mm": float(fov_mm),
        "px_per_mm": float(px_per_mm),
        "rater_id": rater_id,
        "session": SESSION_LABEL,
        "acquisition_date": acquisition_date,
        "sop_version": SOP_VERSION,
        "consent_flag": CONSENT_FLAG,
    }


def resolve_export_root(output_dir: Optional[Path] = None) -> Path:
    """
    Root that contains ``export/{institution_id}/{lesion_id}/``.

    Prefer the same folder used for CSV exports when provided; else app data dir.
    """
    if output_dir is not None:
        return Path(output_dir)
    return get_base_data_dir()


def _rater_id_from_value(username: Optional[str] = None, result: Optional[Dict[str, Any]] = None) -> str:
    if result and result.get("rater_id"):
        return str(result["rater_id"]).strip()
    if username and str(username).strip():
        return str(username).strip()
    return "Unknown"


def export_result_metadata_bundle(
    result: Dict[str, Any],
    *,
    institution_id: str,
    rater_id: str,
    output_dir: Optional[Path] = None,
    source_path_hint: Optional[str] = None,
    session_mask_b64: Optional[str] = None,
    scale_mm_hint: Optional[float] = None,
    device_hint: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Write image_raw.png, mask_roi.png, meta.json for one MNV result.

    Returns a summary dict with ``export_dir``, paths, and status.
    Raises ValueError when the row cannot be exported (VD / missing files).
    """
    if is_vd_result_row(result) or str(result.get("result_type") or "").upper() == "VD":
        raise ValueError("VD results have no ROI mask; skip metadata export")

    if result.get("error") or result.get("status") == "failed":
        raise ValueError("Failed analysis result; cannot export")

    inst = normalize_institution_id(institution_id)
    source = _resolve_source_path(result, source_path_hint=source_path_hint)
    if source is None:
        raise ValueError(
            f"Raw en-face path not found for {result.get('source_filename', '?')}"
        )

    raw = imread_grayscale(str(source))
    if raw is None:
        raise ValueError(f"Failed to load en-face image: {source}")

    mask = _load_roi_mask(
        result,
        session_mask_b64=session_mask_b64,
        target_shape=raw.shape[:2],
    )
    if mask is None:
        raise ValueError(
            f"ROI mask not available for {result.get('source_filename', '?')} "
            "(mask_path / mask_base64 missing)"
        )

    lesion_id = _lesion_id_from_result(result, source)
    fov = _fov_mm(result, scale_mm_hint=scale_mm_hint)
    stratum = _stratum(result, fov, raw.shape[1])
    pxpm = _px_per_mm(result, raw.shape[1], fov)
    device = _infer_device(stratum, result, device_hint=device_hint)
    acq = _acquisition_date(source, result)

    root = resolve_export_root(output_dir)
    export_dir = root / "export" / inst / lesion_id
    export_dir.mkdir(parents=True, exist_ok=True)

    image_path = export_dir / "image_raw.png"
    mask_path_out = export_dir / "mask_roi.png"
    meta_path = export_dir / "meta.json"

    _imwrite_png(image_path, raw)
    _imwrite_png(mask_path_out, mask)

    meta = build_meta_dict(
        lesion_id=lesion_id,
        institution_id=inst,
        device=device,
        stratum=stratum,
        fov_mm=fov,
        px_per_mm=pxpm,
        rater_id=rater_id or "Unknown",
        acquisition_date=acq,
    )
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    return {
        "status": "ok",
        "lesion_id": lesion_id,
        "institution_id": inst,
        "export_dir": str(export_dir),
        "image_raw": str(image_path),
        "mask_roi": str(mask_path_out),
        "meta_json": str(meta_path),
        "meta": meta,
    }


def export_batch_metadata_bundles(
    batch_results: List[Dict[str, Any]],
    *,
    institution_id: str,
    rater_id: str,
    output_dir: Optional[Path] = None,
    source_path_hint: Optional[str] = None,
    session_mask_b64: Optional[str] = None,
    scale_mm_hint: Optional[float] = None,
    device_hint: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Export all eligible MNV rows in a batch (sync; call from a worker thread).

    Pass plain strings/floats extracted on the UI thread — do not pass Flet session.
    """
    inst = normalize_institution_id(institution_id)
    rater = (rater_id or "").strip() or "Unknown"

    exported: List[Dict[str, Any]] = []
    skipped: List[Dict[str, str]] = []
    errors: List[Dict[str, str]] = []

    for result in batch_results or []:
        if not isinstance(result, dict):
            continue
        name = str(result.get("source_filename") or "?")
        try:
            summary = export_result_metadata_bundle(
                result,
                institution_id=inst,
                rater_id=rater,
                output_dir=output_dir,
                source_path_hint=source_path_hint,
                session_mask_b64=session_mask_b64,
                scale_mm_hint=scale_mm_hint,
                device_hint=device_hint,
            )
            exported.append(summary)
        except ValueError as ex:
            skipped.append({"source": name, "reason": str(ex)})
        except Exception as ex:
            errors.append({"source": name, "reason": str(ex)})

    root = resolve_export_root(output_dir)
    return {
        "institution_id": inst,
        "rater_id": rater,
        "export_root": str(root / "export" / inst),
        "exported": exported,
        "skipped": skipped,
        "errors": errors,
    }
