"""
Export analysis logs as MedSAM-style dataset bundles for OCTA MNV ROI segmentation.

Why MedSAM-style (not SAM-OCTA / OCTA-500):
  - Our labels are binary **MNV lesion ROI** masks on en-face OCTA, not OCTA-500
    vessel/FAZ/artery/vein task folders (GT_Artery, ProjectionMaps, …).
  - MedSAM / finetune-SAM / SAM2 image fine-tunes expect paired ``images/`` + ``masks/``
    with matching IDs (and often a CSV path list). That maps 1:1 to our task.
  - SAM-OCTA layouts are FOV×task taxonomies for public OCTA-500; converting later
    is possible from this archive, but is the wrong primary store for MNV ROI.

Layout under the CSV target output dir (or app data root)::

  export/
    images/{institution_id}/{lesion_id}.png   — en-face without ROI overlay
    masks/{institution_id}/{lesion_id}.png    — binary ROI mask (0/255);
                                                all-zero when ``mnv_present=false``
    meta/{institution_id}/{lesion_id}.json    — acquisition / rater / presence metadata
    pdfs/{institution_id}/{lesion_id}.pdf     — per-case analysis PDF (clinical archive)
    manifest.csv                              — MedSAM-ready path list (append/upsert)

Negative / MNV-absent cases (user Skip): keep the paired mask file as an empty
(all-zero) mask and set ``mnv_present=false`` in meta + manifest. Do **not** encode
absence only in QC — QC remains Pass/Fail/N/A for analysis quality.

Designed for multi-site Hold-out splits via ``institution_id``.
"""

from __future__ import annotations

import base64
import csv
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
from src.utils.mnv_absent import (
    ANNOTATION_STATUS_ABSENT,
    SKIP_REASON_NO_CLEAR_MNV,
    is_mnv_absent_result,
    zero_mask_array,
)
from src.utils.vd_batch_csv import is_vd_result_row

SOP_VERSION = "1.2"
LAYOUT_ID = "medsam_v1"
TASK_ID = "octa_mnv_roi"
SESSION_LABEL = "initial"
CONSENT_FLAG = True

MANIFEST_NAME = "manifest.csv"
MANIFEST_FIELDS = [
    "img_path",
    "mask_path",
    "meta_path",
    "lesion_id",
    "institution_id",
    "device",
    "stratum",
    "fov_mm",
    "px_per_mm",
    "rater_id",
    "acquisition_date",
    "mnv_present",
    "annotation_status",
    "task",
    "layout",
]

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
        cm.get("scale_mm"),
        scale_mm_hint,
    ):
        try:
            if candidate is not None and float(candidate) > 0:
                return float(candidate)
        except (TypeError, ValueError):
            pass
    return 6.0


def _stratum(result: Dict[str, Any], fov_mm: float, width_px: int) -> str:
    sc = str(result.get("size_class") or "").strip().lower()
    if sc in _DEVICE_BY_STRATUM:
        return sc
    cm = result.get("csv_metrics") if isinstance(result.get("csv_metrics"), dict) else {}
    sc2 = str(cm.get("size_class") or "").strip().lower()
    if sc2 in _DEVICE_BY_STRATUM:
        return sc2
    if abs(float(fov_mm) - 3.0) < 0.6:
        return "small_3mm"
    if width_px >= 900:
        return "large"
    return "small"


def _px_per_mm(result: Dict[str, Any], width_px: int, fov_mm: float) -> float:
    cm = result.get("csv_metrics") if isinstance(result.get("csv_metrics"), dict) else {}
    for candidate in (result.get("px_per_mm"), cm.get("px_per_mm")):
        try:
            if candidate is not None and float(candidate) > 0:
                return float(candidate)
        except (TypeError, ValueError):
            pass
    try:
        return float(ScaleManager.compute_px_per_mm(width_px, float(fov_mm)))
    except Exception:
        return float(width_px) / max(float(fov_mm), 1e-6)


def _infer_device(
    stratum: str,
    result: Dict[str, Any],
    *,
    device_hint: Optional[str] = None,
) -> str:
    for candidate in (
        device_hint,
        result.get("device"),
        result.get("device_name"),
    ):
        if candidate and str(candidate).strip():
            return str(candidate).strip()
    return _DEVICE_BY_STRATUM.get(stratum, "Unknown")


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
    mnv_present: bool = True,
    annotation_status: str = "labeled",
    skip_reason: Optional[str] = None,
) -> Dict[str, Any]:
    meta: Dict[str, Any] = {
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
        "task": TASK_ID,
        "layout": LAYOUT_ID,
        "modality": "OCTA",
        "label_type": "mnv_roi",
        # Presence is a diagnosis/annotation label — not image QC (Pass/Fail).
        "mnv_present": bool(mnv_present),
        "annotation_status": annotation_status,
    }
    if skip_reason:
        meta["skip_reason"] = str(skip_reason)
    if not mnv_present:
        meta["negative_sample"] = True
    return meta


def resolve_export_root(output_dir: Optional[Path] = None) -> Path:
    """
    Root that contains ``export/images|masks|meta/…``.

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


def _rel_posix(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _upsert_manifest_row(root: Path, row: Dict[str, str]) -> Path:
    """Append or replace a manifest row keyed by institution_id + lesion_id."""
    export_root = root / "export"
    export_root.mkdir(parents=True, exist_ok=True)
    manifest_path = export_root / MANIFEST_NAME
    key = (row.get("institution_id", ""), row.get("lesion_id", ""))
    rows: List[Dict[str, str]] = []
    if manifest_path.is_file():
        with manifest_path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for existing in reader:
                ek = (existing.get("institution_id", ""), existing.get("lesion_id", ""))
                if ek != key:
                    rows.append({f: existing.get(f, "") for f in MANIFEST_FIELDS})
    rows.append({f: row.get(f, "") for f in MANIFEST_FIELDS})
    with manifest_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return manifest_path


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
    Write MedSAM-style image / mask / meta for one MNV result and upsert manifest.csv.

    Returns a summary dict with paths and status.
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

    absent = is_mnv_absent_result(result)
    mask = _load_roi_mask(
        result,
        session_mask_b64=session_mask_b64,
        target_shape=raw.shape[:2],
    )
    if mask is None and absent:
        # Negative samples: all-zero mask keeps MedSAM image/mask pairing.
        mask = zero_mask_array(raw.shape[0], raw.shape[1])
    if mask is None:
        raise ValueError(
            f"ROI mask not available for {result.get('source_filename', '?')} "
            "(mask_path / mask_base64 missing)"
        )
    if absent:
        mask = np.zeros_like(mask)

    lesion_id = _lesion_id_from_result(result, source)
    fov = _fov_mm(result, scale_mm_hint=scale_mm_hint)
    stratum = _stratum(result, fov, raw.shape[1])
    pxpm = _px_per_mm(result, raw.shape[1], fov)
    device = _infer_device(stratum, result, device_hint=device_hint)
    acq = _acquisition_date(source, result)

    mnv_present = False if absent else bool(result.get("mnv_present", True))
    annotation_status = (
        ANNOTATION_STATUS_ABSENT
        if absent
        else str(result.get("annotation_status") or "labeled")
    )
    skip_reason = None
    if absent:
        skip_reason = str(
            result.get("skip_reason")
            or (result.get("csv_metrics") or {}).get("skip_reason")
            or SKIP_REASON_NO_CLEAR_MNV
        )

    root = resolve_export_root(output_dir)
    export_root = root / "export"
    image_path = export_root / "images" / inst / f"{lesion_id}.png"
    mask_path_out = export_root / "masks" / inst / f"{lesion_id}.png"
    meta_path = export_root / "meta" / inst / f"{lesion_id}.json"

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
        mnv_present=mnv_present,
        annotation_status=annotation_status,
        skip_reason=skip_reason,
    )
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    manifest_row = {
        "img_path": _rel_posix(image_path, export_root),
        "mask_path": _rel_posix(mask_path_out, export_root),
        "meta_path": _rel_posix(meta_path, export_root),
        "lesion_id": lesion_id,
        "institution_id": inst,
        "device": device,
        "stratum": stratum,
        "fov_mm": f"{float(fov):.6g}",
        "px_per_mm": f"{float(pxpm):.6g}",
        "rater_id": rater_id or "Unknown",
        "acquisition_date": acq,
        "mnv_present": "1" if mnv_present else "0",
        "annotation_status": annotation_status,
        "task": TASK_ID,
        "layout": LAYOUT_ID,
    }
    manifest_path = _upsert_manifest_row(root, manifest_row)

    return {
        "status": "ok",
        "lesion_id": lesion_id,
        "institution_id": inst,
        "export_dir": str(export_root / "images" / inst),
        "layout": LAYOUT_ID,
        "task": TASK_ID,
        "image_raw": str(image_path),
        "mask_roi": str(mask_path_out),
        "meta_json": str(meta_path),
        "manifest_csv": str(manifest_path),
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
            msg = str(ex)
            if "VD results" in msg or "Failed analysis" in msg:
                skipped.append({"source_filename": name, "reason": msg})
            else:
                errors.append({"source_filename": name, "reason": msg})
        except Exception as ex:
            errors.append({"source_filename": name, "reason": str(ex)})

    root = resolve_export_root(output_dir)
    return {
        "status": "ok",
        "layout": LAYOUT_ID,
        "task": TASK_ID,
        "institution_id": inst,
        "rater_id": rater,
        "export_root": str(root / "export"),
        "manifest_csv": str(root / "export" / MANIFEST_NAME),
        "exported_count": len(exported),
        "skipped_count": len(skipped),
        "error_count": len(errors),
        "exported": exported,
        "skipped": skipped,
        "errors": errors,
    }


def export_batch_pdf_reports(
    batch_results: List[Dict[str, Any]],
    *,
    institution_id: str,
    output_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Write one PDF report per result under ``export/pdfs/{institution_id}/{lesion_id}.pdf``.

    Separate from MedSAM image/mask folders so clinicians can archive reports without
    mixing binary training assets.
    """
    from src.utils.report_generator import generate_pdf_report

    inst = normalize_institution_id(institution_id)
    root = resolve_export_root(output_dir)
    pdf_root = root / "export" / "pdfs" / inst
    pdf_root.mkdir(parents=True, exist_ok=True)

    exported: List[Dict[str, Any]] = []
    skipped: List[Dict[str, str]] = []
    errors: List[Dict[str, str]] = []

    for result in batch_results or []:
        if not isinstance(result, dict):
            continue
        name = str(result.get("source_filename") or "?")
        if result.get("error") or result.get("status") == "failed":
            errors.append({"source_filename": name, "reason": "Failed analysis result"})
            continue
        if is_mnv_absent_result(result):
            # Clinical PDF is optional for negatives; MedSAM image/mask/meta is the ML record.
            skipped.append(
                {
                    "source_filename": name,
                    "reason": "MNV absent — PDF skipped (meta/mask export still applies)",
                }
            )
            continue
        try:
            source = _resolve_source_path(result)
            lesion_id = _lesion_id_from_result(result, source)
            out_path = pdf_root / f"{lesion_id}.pdf"
            generate_pdf_report(result, str(out_path))
            exported.append(
                {
                    "source_filename": name,
                    "lesion_id": lesion_id,
                    "pdf_path": str(out_path),
                }
            )
        except Exception as ex:
            errors.append({"source_filename": name, "reason": str(ex)})

    return {
        "status": "ok",
        "institution_id": inst,
        "pdf_root": str(pdf_root),
        "exported_count": len(exported),
        "skipped_count": len(skipped),
        "error_count": len(errors),
        "exported": exported,
        "skipped": skipped,
        "errors": errors,
    }
