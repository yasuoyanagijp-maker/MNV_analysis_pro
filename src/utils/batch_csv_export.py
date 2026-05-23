"""
Build and write MNV / VD batch CSV exports (Flet results screen, auto-save on completion).
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.utils.mnv_imagej_csv import (
    _metrics_to_imagej_row,
    build_csv_bytes_from_imagej_rows,
    metrics_from_session_result_row,
    qc_status_for_row,
)
from src.utils.vd_batch_csv import (
    VD_LAYOUT_VSL_DENSITY_ONLY,
    VD_SINGLE_CSV_COLUMNS,
    build_vd_batch_csv_bytes,
    is_vd_result_row,
    merge_vd_batches_for_csv,
    suggested_vd_csv_filename,
)


def analysis_now_iso() -> str:
    """Timezone-aware ISO timestamp (matches mainstreamer now_iso)."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def mark_analysis_started(session) -> str:
    """Record analysis start time for CSV metadata."""
    started = analysis_now_iso()
    session.set("analysis_started_at", started)
    session.set("analysis_ended_at", "")
    session.set("analysis_duration_sec", 0.0)
    if not session.get("session_id"):
        session.set(
            "session_id",
            f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}",
        )
    return started


def _duration_seconds(started_iso: str, ended_iso: str) -> float:
    try:
        t0 = datetime.fromisoformat(str(started_iso))
        t1 = datetime.fromisoformat(str(ended_iso))
        return max((t1 - t0).total_seconds(), 0.0)
    except (TypeError, ValueError):
        return 0.0


def mark_analysis_ended(session) -> str:
    """Record end time and duration from session start."""
    ended = analysis_now_iso()
    session.set("analysis_ended_at", ended)
    started = str(session.get("analysis_started_at") or "")
    if started:
        session.set("analysis_duration_sec", _duration_seconds(started, ended))
    return ended


def batch_export_meta_from_session(session) -> Dict[str, Any]:
    uname = (session.get("username") or "").strip()
    started = str(session.get("analysis_started_at") or "")
    ended = str(session.get("analysis_ended_at") or "")
    if not ended:
        ended = mark_analysis_ended(session)
    duration = float(session.get("analysis_duration_sec") or 0.0)
    if started and duration <= 0:
        duration = _duration_seconds(started, ended)
        session.set("analysis_duration_sec", duration)
    return {
        "Analyst": uname if uname else "Unknown",
        "Started At": started,
        "Ended At": ended,
        "Duration Sec": duration,
        "Session ID": str(session.get("session_id") or ""),
    }


def collect_batch_csv_exports(
    batch_results: List[Dict[str, Any]],
    meta: Dict[str, Any],
) -> List[Tuple[str, str, bytes]]:
    """
    Build CSV payloads for a batch.

    Returns:
        List of (kind_label, filename, utf-8-sig bytes).
    """
    if not batch_results:
        return []

    vd_chunks = [r for r in batch_results if is_vd_result_row(r)]
    vd_vsl = [r for r in vd_chunks if r.get("vd_layout") == VD_LAYOUT_VSL_DENSITY_ONLY]
    vd_full = [r for r in vd_chunks if r not in vd_vsl]
    mnv_rows = [
        r for r in batch_results if str(r.get("result_type") or "MNV") == "MNV"
    ]

    out: List[Tuple[str, str, bytes]] = []

    if vd_vsl:
        merged_vsl = merge_vd_batches_for_csv(vd_vsl, VD_SINGLE_CSV_COLUMNS)
        if len(merged_vsl.get("patient_ids") or []) > 0:
            fname = suggested_vd_csv_filename(
                merged_vsl, meta["Session ID"], VD_LAYOUT_VSL_DENSITY_ONLY
            )
            out.append(
                (
                    "VD (single)",
                    fname,
                    build_vd_batch_csv_bytes(merged_vsl, meta, VD_SINGLE_CSV_COLUMNS),
                )
            )

    if vd_full:
        merged_full = merge_vd_batches_for_csv(vd_full)
        if len(merged_full.get("patient_ids") or []) > 0:
            fname = suggested_vd_csv_filename(merged_full, meta["Session ID"], "full")
            out.append(
                (
                    "VD (full)",
                    fname,
                    build_vd_batch_csv_bytes(merged_full, meta),
                )
            )

    if mnv_rows:
        ordered = sorted(mnv_rows, key=lambda x: str(x.get("source_filename") or ""))
        rows = []
        for idx, r in enumerate(ordered):
            fn = str(r.get("source_filename") or "N/A")
            success = "error" not in r
            metrics = metrics_from_session_result_row(r)
            rows.append(
                _metrics_to_imagej_row(
                    fn,
                    idx,
                    qc_status_for_row(r),
                    success,
                    metrics,
                )
            )
        mnv_fname = f"mnv_batch_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.csv"
        out.append(
            ("MNV", mnv_fname, build_csv_bytes_from_imagej_rows(rows, meta)),
        )

    return out


def write_batch_csv_exports(
    batch_results: List[Dict[str, Any]],
    meta: Dict[str, Any],
    target_dir: Path,
) -> List[Tuple[str, Path]]:
    """Write CSV files to target_dir. Returns (kind, path) for each file written."""
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    written: List[Tuple[str, Path]] = []
    for kind, fname, data in collect_batch_csv_exports(batch_results, meta):
        path = (target_dir / fname).resolve()
        path.write_bytes(data)
        written.append((kind, path))
    return written
