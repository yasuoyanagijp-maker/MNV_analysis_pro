"""
VD batch CSV aligned with mainstreamer.build_vd_results_csv (same column order, UTF-8 BOM).
Supports a superficial-only column set for VD single (wizard / VD_SINGLE folder row).
"""

from __future__ import annotations

import csv
import io
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# Session/result flag: VD single UI (export + detail view without deep metrics)
VD_LAYOUT_VSL_DENSITY_ONLY = "vsl_density_only"

# (CSV column title, key in API / session VD payload) — full VD / folder batch / integrated
VD_CSV_COLUMNS: List[Tuple[str, str]] = [
    ("Patient ID", "patient_ids"),
    ("Superficial Image ID", "superficial_files"),
    ("Deep Image ID", "deep_files"),
    ("FAZ (mm^2)", "faz_areas"),
    ("Circularity", "faz_circularities"),
    ("Superficial", "superficial_whole"),
    ("Superior Area (Superficial)", "superficial_superior"),
    ("Temporal Area (Superficial)", "superficial_temporal"),
    ("Nasal Area (Superficial)", "superficial_nasal"),
    ("Inferior Area (Superficial)", "superficial_inferior"),
    ("Deep", "deep_whole"),
    ("Superior Area (Deep)", "deep_superior"),
    ("Temporal Area (Deep)", "deep_temporal"),
    ("Nasal Area (Deep)", "deep_nasal"),
    ("Inferior Area (Deep)", "deep_inferior"),
    ("Fractal Dimension (Superficial)", "fractal_dimension_superficial"),
    ("Fractal Dimension (Deep)", "fractal_dimension_deep"),
    ("Tortuosity (Superficial)", "tortuosity_superficial"),
    ("Tortuosity (Deep)", "tortuosity_deep"),
]

# VD single (wizard or dashboard VD_SINGLE): superficial metrics only, renamed for clinical label
VD_SINGLE_CSV_COLUMNS: List[Tuple[str, str]] = [
    ("Patient ID", "patient_ids"),
    ("Superficial Image ID", "superficial_files"),
    ("FAZ (mm^2)", "faz_areas"),
    ("Circularity", "faz_circularities"),
    ("Vsl Density", "superficial_whole"),
    ("Superior", "superficial_superior"),
    ("Temporal", "superficial_temporal"),
    ("Nasal", "superficial_nasal"),
    ("Inferior", "superficial_inferior"),
    ("Fractal Dimension", "fractal_dimension_superficial"),
    ("Tortuosity", "tortuosity_superficial"),
]

_META_KEYS = ("Analyst", "Started At", "Ended At", "Duration Sec", "Session ID")


def is_vd_result_row(res: Any) -> bool:
    if not isinstance(res, dict):
        return False
    if str(res.get("result_type") or "").upper() == "VD":
        return True
    pids = res.get("patient_ids")
    return isinstance(pids, list) and len(pids) > 0 and "superficial_files" in res


def merge_vd_batches_for_csv(
    vd_chunks: List[dict],
    columns_spec: Optional[List[Tuple[str, str]]] = None,
) -> Dict[str, List[Any]]:
    spec = columns_spec if columns_spec is not None else VD_CSV_COLUMNS
    keys = [k for _, k in spec]
    out: Dict[str, List[Any]] = {k: [] for k in keys}

    for res in vd_chunks:
        if not isinstance(res, dict):
            continue

        if res.get("error") and not (res.get("patient_ids")):
            for k in keys:
                out[k].append("")
            out["patient_ids"][-1] = "(engine error)"
            sf = str(res.get("source_filename") or "")
            err = str(res.get("error") or "")[:800]
            if "superficial_files" in out:
                out["superficial_files"][-1] = sf
            if "deep_files" in out:
                out["deep_files"][-1] = err
            elif sf and "superficial_files" in out:
                out["superficial_files"][-1] = f"{sf}: {err}"[:900]
            elif "superficial_files" in out:
                out["superficial_files"][-1] = err
            continue

        pids = res.get("patient_ids") or []
        if not pids:
            continue

        n = len(pids)
        for k in keys:
            src = res.get(k)
            if not isinstance(src, list):
                src = []
            for i in range(n):
                val = src[i] if i < len(src) else ""
                out[k].append(val)
    return out


def suggested_vd_csv_filename(
    merged: Dict[str, List[Any]],
    session_id: str,
    layout: str = "full",
) -> str:
    pids = [str(x) for x in (merged.get("patient_ids") or []) if x]
    unique = sorted({p for p in pids if p and not str(p).startswith("(engine error)")})
    timestamp_suffix = _timestamp_from_session(session_id)
    prefix = "VD_single" if layout == VD_LAYOUT_VSL_DENSITY_ONLY else "VD"
    if len(unique) == 1:
        safe = re.sub(r'[<>:"/\\\\|?*]', "_", unique[0])
        return f"{prefix}_{safe}_{timestamp_suffix}.csv"
    batch_name = "single_batch" if layout == VD_LAYOUT_VSL_DENSITY_ONLY else "batch"
    return f"VD_{batch_name}_{timestamp_suffix}.csv"


def _timestamp_from_session(session_id: str) -> str:
    s = str(session_id or "").strip()
    if not s:
        return datetime.now().strftime("%Y%m%d_%H%M%S")
    parts = s.split("_")
    if len(parts) >= 2:
        return f"{parts[0]}_{parts[1]}"
    return s.replace(" ", "")[:40]


def build_vd_batch_csv_bytes(
    merged: Dict[str, List[Any]],
    meta: Dict[str, Any],
    columns_spec: Optional[List[Tuple[str, str]]] = None,
) -> bytes:
    spec = columns_spec if columns_spec is not None else VD_CSV_COLUMNS
    rows_n = len(merged.get("patient_ids") or [])
    buf = io.StringIO()
    w = csv.writer(buf)
    header = [c for c, _ in spec] + list(_META_KEYS)
    w.writerow(header)
    for i in range(rows_n):
        line: List[Any] = []
        for _, key in spec:
            lst = merged.get(key) or []
            line.append(lst[i] if i < len(lst) else "")
        line.append(meta.get("Analyst", ""))
        line.append(meta.get("Started At", ""))
        line.append(meta.get("Ended At", ""))
        line.append(meta.get("Duration Sec", ""))
        line.append(meta.get("Session ID", ""))
        w.writerow(line)
    return buf.getvalue().encode("utf-8-sig")
