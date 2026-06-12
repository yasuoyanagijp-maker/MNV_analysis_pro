"""
MNV batch results table/chart helpers (summary screen).
"""

from __future__ import annotations

import io
import math
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from fpdf import FPDF

from src.utils.mnv_imagej_csv import (
    IMAGEJ_CSV_COLUMNS,
    _metrics_to_imagej_row,
    metrics_from_session_result_row,
    qc_status_for_row,
)
from src.utils.vd_batch_csv import is_vd_result_row

# Columns shown in the batch summary table (CSV-aligned).
SUMMARY_TABLE_COLUMNS = [
    "File",
    "Subtype",
    "Pathophysiology",
    "Maturity Index",
    "Network Complexity Score",
    "Caliber Uniformity Score",
    "MNV Area (mm2)",
    "Fractal Dim",
]

_NON_NUMERIC_CSV = frozenset(
    {
        "ID",
        "File",
        "Subtype",
        "Pathophysiology",
        "Quality of analysis",
        "FD quality reason",
        "FD box sizes",
        "Exclude from FD analysis",
        "FD scale insufficient (0=OK 1=insufficient)",
        "ROI coverage low quality (0=OK 1=low)",
        "FD quality flag (0=OK 1=abnormal)",
    }
)


def chartable_numeric_columns() -> List[str]:
    """Numeric CSV columns suitable for batch comparison charts."""
    preferred = [
        "Maturity Index",
        "Network Complexity Score",
        "Caliber Uniformity Score",
        "MNV Area (mm2)",
        "Vsl Density (Vessel Area/MNV (%))",
        "Vessel density index adjusted by signal intensity (aVDI)",
        "Fractal Dim",
        "Tortuosity",
        "Vsl Length (mm)",
        "Complexity Score",
    ]
    out: List[str] = []
    for col in preferred:
        if col in IMAGEJ_CSV_COLUMNS and col not in _NON_NUMERIC_CSV:
            out.append(col)
    for col in IMAGEJ_CSV_COLUMNS:
        if col in _NON_NUMERIC_CSV or col in out:
            continue
        if "%" in col or "flag" in col.lower() or "reason" in col.lower():
            continue
        out.append(col)
    return out


def imagej_rows_from_batch(batch_results: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build ImageJ CSV rows in batch_results order (MNV rows only)."""
    rows: List[Dict[str, Any]] = []
    seq = 0
    for r in batch_results:
        if is_vd_result_row(r):
            continue
        seq += 1
        fn = str(r.get("source_filename") or "N/A")
        success = "error" not in r
        metrics = metrics_from_session_result_row(r)
        rows.append(
            _metrics_to_imagej_row(
                fn,
                seq,
                qc_status_for_row(r),
                success,
                metrics,
            )
        )
    return rows


def _parse_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        f = float(val)
        return f if math.isfinite(f) else None
    s = str(val).strip()
    if not s or s in ("—", "-", "N/A", "nan", "None"):
        return None
    try:
        f = float(s)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def smart_y_bounds(values: Sequence[float]) -> Tuple[float, float]:
    """Trim axis limits for readability (light percentile clip + margin)."""
    nums = [float(v) for v in values if v is not None and math.isfinite(v)]
    if not nums:
        return 0.0, 1.0
    if len(nums) == 1:
        v = nums[0]
        pad = max(abs(v) * 0.15, 1.0)
        return v - pad, v + pad
    nums.sort()
    n = len(nums)
    lo = nums[max(0, int(n * 0.05))]
    hi = nums[min(n - 1, int(n * 0.95))]
    if lo > hi:
        lo, hi = nums[0], nums[-1]
    span = hi - lo
    if span <= 0:
        pad = max(abs(hi) * 0.15, 1.0)
        return hi - pad, hi + pad
    margin = span * 0.1
    return lo - margin, hi + margin


def _truncate_label(text: str, max_len: int = 22) -> str:
    s = str(text or "—").strip() or "—"
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."


def series_for_metric(
    imagej_rows: Sequence[Dict[str, Any]],
    metric_col: str,
) -> Tuple[List[Dict[str, str]], List[float]]:
    """Return chart point metadata and numeric values for one CSV column."""
    points: List[Dict[str, str]] = []
    values: List[float] = []
    for row in imagej_rows:
        val = _parse_float(row.get(metric_col))
        if val is None:
            continue
        points.append(
            {
                "file": _truncate_label(row.get("File")),
                "subtype": _truncate_label(row.get("Subtype"), 18),
                "pathophysiology": _truncate_label(row.get("Pathophysiology"), 18),
            }
        )
        values.append(val)
    return points, values


def build_batch_metric_chart_pdf(
    batch_results: Sequence[Dict[str, Any]],
    metric_col: str,
    *,
    title: str = "ARIAKE OCTA — MNV Batch Chart",
) -> bytes:
    """Render a bar chart for one CSV metric and return PDF bytes."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    imagej_rows = imagej_rows_from_batch(batch_results)
    points, values = series_for_metric(imagej_rows, metric_col)
    if not values:
        raise ValueError(f"No numeric data for column: {metric_col}")

    y_min, y_max = smart_y_bounds(values)
    fig_w = max(8.0, min(16.0, 0.55 * len(points) + 4.0))
    fig, ax = plt.subplots(figsize=(fig_w, 6.0))
    x = list(range(len(values)))
    ax.bar(x, values, color="#00E5FF", edgecolor="#00838F", linewidth=0.6)
    ax.set_xticks(x)
    tick_labels = [
        f"{p['file']}\n{p['subtype']}\n{p['pathophysiology']}" for p in points
    ]
    ax.set_xticklabels(tick_labels, rotation=0, ha="center", fontsize=7)
    ax.set_ylabel(metric_col, fontsize=10)
    ax.set_title(f"{title}\n{metric_col}", fontsize=12, pad=12)
    ax.set_ylim(y_min, y_max)
    ax.grid(axis="y", alpha=0.25, linestyle="--")
    fig.subplots_adjust(bottom=0.28)

    png_buf = io.BytesIO()
    fig.savefig(png_buf, format="png", dpi=150)
    plt.close(fig)
    png_buf.seek(0)

    pdf = FPDF(orientation="L" if len(points) > 8 else "P", unit="mm")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    safe_title = re.sub(r"[^\x00-\xFF]", "?", title)
    safe_metric = re.sub(r"[^\x00-\xFF]", "?", metric_col)
    pdf.cell(0, 10, safe_title, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=11)
    pdf.cell(0, 8, f"Metric: {safe_metric}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    page_w = pdf.w - pdf.l_margin - pdf.r_margin
    img_w = page_w
    img_h = img_w * 0.55
    pdf.image(png_buf, x=pdf.l_margin, w=img_w, h=img_h)

    out = pdf.output()
    if isinstance(out, bytes):
        return out
    if isinstance(out, bytearray):
        return bytes(out)
    return str(out).encode("latin-1")
