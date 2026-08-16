"""
MNV batch results table/chart helpers (summary screen).
"""

from __future__ import annotations

import io
import math
import re
import textwrap
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
    "MNV present",
    "Pathophysiology",
    "Maturity Index",
    "Network Complexity Score",
    "Caliber Uniformity Score",
    "MNV Area (mm2)",
    "Fractal Dim",
]

# Short on-screen header labels so long CSV column names don't overlap.
# Keys are CSV column names; the full name stays available via tooltip.
SUMMARY_TABLE_HEADER_LABELS: Dict[str, str] = {
    "MNV present": "MNV",
    "Pathophysiology": "Pathophys.",
    "Maturity Index": "Maturity",
    "Network Complexity Score": "Complexity",
    "Caliber Uniformity Score": "Caliber",
    "MNV Area (mm2)": "Area (mm2)",
    "Fractal Dim": "FD",
}


def summary_table_header_label(col: str) -> str:
    """Short display label for a Results Table (CSV) column header."""
    return SUMMARY_TABLE_HEADER_LABELS.get(col, col)

# On-screen PNG canvas (must match ft.Image aspect in results_screen).
CHART_PNG_WIDTH_PX = 1180
CHART_PNG_HEIGHT_PX = 640

# Chart dropdown labels for standardized (U2) series → ImageJ CSV columns.
# Pipeline default Maturity/Caliber columns are already U2; (U2) is display-only.
CHART_METRIC_ALIASES: Dict[str, str] = {
    "Maturity Index (U2)": "Maturity Index",
    "Caliber Uniformity Score (U2)": "Caliber Uniformity Score",
}

# Prefer U2 only for legacy/bare session keys (no U2/PCA suffix).
# Do NOT remap explicit PCA selections — users must keep Maturity/Caliber (PCA).
CHART_METRIC_DEFAULT_REMAP: Dict[str, str] = {
    "Maturity Index": "Maturity Index (U2)",
    "Caliber Uniformity Score": "Caliber Uniformity Score (U2)",
}

_NON_NUMERIC_CSV = frozenset(
    {
        "ID",
        "File",
        "Subtype",
        "Pathophysiology",
        "Quality of analysis",
        "MNV present",
        "FD quality reason",
        "FD box sizes",
        "Exclude from FD analysis",
        "FD scale insufficient (0=OK 1=insufficient)",
        "ROI coverage low quality (0=OK 1=low)",
        "FD quality flag (0=OK 1=abnormal)",
    }
)


def resolve_chart_metric_col(metric_col: str) -> str:
    """Map chart dropdown labels (e.g. U2) to ImageJ CSV column names."""
    return CHART_METRIC_ALIASES.get(str(metric_col or "").strip(), str(metric_col or ""))


def chartable_numeric_columns() -> List[str]:
    """Numeric columns / chart labels suitable for batch comparison charts."""
    preferred = [
        "Maturity Index (U2)",
        "Caliber Uniformity Score (U2)",
        "Network Complexity Score",
        "Maturity Index (PCA)",
        "Caliber Uniformity Score (PCA)",
        "MNV Area (mm2)",
        "Vsl Density (Vessel Area/MNV (%))",
        "Vessel density index adjusted by signal intensity (aVDI)",
        "Fractal Dim",
        "Tortuosity",
        "Vsl Length (mm)",
        "Complexity Score",
    ]
    # Bare U2 columns are shown as "(U2)" labels — skip duplicate bare names.
    skip_bare_u2 = frozenset(CHART_METRIC_ALIASES.values())
    out: List[str] = []
    for col in preferred:
        csv_col = resolve_chart_metric_col(col)
        if csv_col in IMAGEJ_CSV_COLUMNS and col not in out:
            out.append(col)
    for col in IMAGEJ_CSV_COLUMNS:
        if col in _NON_NUMERIC_CSV or col in out or col in skip_bare_u2:
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


def format_summary_table_cell(col: str, val: Any) -> str:
    """Format a Results Table (CSV columns) cell; numerics to 1 decimal."""
    if col in _NON_NUMERIC_CSV:
        return "" if val is None else str(val)
    parsed = _parse_float(val)
    if parsed is None:
        return "" if val is None else str(val)
    return f"{round(parsed, 1):.1f}"


def _wrap_axis_label(text: str, width: int = 24) -> str:
    """Wrap long Y-axis labels so they stay inside the figure."""
    s = str(text or "").strip() or "Metric"
    return "\n".join(textwrap.wrap(s, width=width, break_long_words=False)) or s


def _truncate_label(text: str, max_len: int = 22) -> str:
    s = str(text or "—").strip() or "—"
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."


def _short_filename(text: str, max_len: int = 18) -> str:
    """Prefer stem before long IDs; truncate cleanly for axis ticks."""
    s = str(text or "—").strip() or "—"
    # Drop common image extensions for display
    for ext in (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"):
        if s.lower().endswith(ext):
            s = s[: -len(ext)]
            break
    if len(s) <= max_len:
        return s
    # Keep head + tail so patient/ID cues stay visible
    head = max(8, max_len // 2)
    tail = max(4, max_len - head - 1)
    return f"{s[:head]}…{s[-tail:]}"


def series_for_metric(
    imagej_rows: Sequence[Dict[str, Any]],
    metric_col: str,
) -> Tuple[List[Dict[str, str]], List[float]]:
    """Return chart point metadata and numeric values for one CSV column."""
    csv_col = resolve_chart_metric_col(metric_col)
    points: List[Dict[str, str]] = []
    values: List[float] = []
    for row in imagej_rows:
        val = _parse_float(row.get(csv_col))
        if val is None:
            continue
        points.append(
            {
                "file": _short_filename(row.get("File"), 20),
                "subtype": _truncate_label(row.get("Subtype"), 16),
                "pathophysiology": _truncate_label(row.get("Pathophysiology"), 16),
            }
        )
        values.append(val)
    return points, values


_THEME = {
    "dark": {
        "fig": "#050510",
        "axes": "#050510",
        "spine": "#1E2A44",
        "label": "#E8EEF8",
        "tick": "#C5D0E0",
        "muted": "#8B9BB4",
        "grid": "#2A3550",
        "bar": "#00E5FF",
        "bar_edge": "#00B8D4",
        "title": "#00E5FF",
        "subtitle": "#8B9BB4",
        "value": "#E8EEF8",
    },
    "light": {
        "fig": "#FFFFFF",
        "axes": "#FFFFFF",
        "spine": "#CFD8DC",
        "label": "#263238",
        "tick": "#37474F",
        "muted": "#607D8B",
        "grid": "#ECEFF1",
        "bar": "#00BCD4",
        "bar_edge": "#00838F",
        "title": "#006064",
        "subtitle": "#546E7A",
        "value": "#263238",
    },
}


def build_batch_metric_chart_png(
    batch_results: Sequence[Dict[str, Any]],
    metric_col: str,
    *,
    title: str = "ARIAKE OCTA Pro — MNV Batch Chart",
    theme: str = "dark",
    dpi: int = 144,
    width_px: int = CHART_PNG_WIDTH_PX,
    height_px: int = CHART_PNG_HEIGHT_PX,
) -> bytes:
    """Render a bar chart for one CSV metric and return PNG bytes (Agg backend).

    Sized for on-screen display: figure pixel size ≈ Image widget so tick
    labels stay readable after CONTAIN fit (avoid huge canvases that shrink).
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colors = _THEME.get(theme, _THEME["dark"])
    display_metric = str(metric_col or "").strip() or "Metric"
    imagej_rows = imagej_rows_from_batch(batch_results)
    points, values = series_for_metric(imagej_rows, display_metric)
    if not values:
        raise ValueError(f"No numeric data for column: {display_metric}")

    n = len(values)
    y_min, y_max = smart_y_bounds(values)

    # Extra width for many bars; keep height fixed for label scale
    w_px = max(width_px, int(140 * n + 420))
    h_px = height_px
    fig_w = w_px / float(dpi)
    fig_h = h_px / float(dpi)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h), facecolor=colors["fig"], dpi=dpi)
    ax.set_facecolor(colors["axes"])

    x = list(range(n))
    # Thin rods — leave clear gaps between categories
    bar_w = 0.22 if n <= 10 else max(0.14, 0.32 - 0.012 * n)
    bars = ax.bar(
        x,
        values,
        width=bar_w,
        color=colors["bar"],
        edgecolor=colors["bar_edge"],
        linewidth=1.15,
        zorder=3,
        alpha=0.95,
    )
    for rect, v in zip(bars, values):
        ax.text(
            rect.get_x() + rect.get_width() / 2,
            float(v),
            f"{round(float(v), 1):.1f}",
            ha="center",
            va="bottom",
            fontsize=15,
            color=colors["value"],
            zorder=4,
            clip_on=False,
        )

    ax.set_xticks(x)
    tick_labels = []
    for p in points:
        lines = [p["file"]]
        if p.get("subtype") and p["subtype"] != "—":
            lines.append(p["subtype"])
        if p.get("pathophysiology") and p["pathophysiology"] != "—":
            lines.append(p["pathophysiology"])
        tick_labels.append("\n".join(lines))
    ax.set_xticklabels(
        tick_labels, rotation=0, ha="center", fontsize=14, color=colors["tick"]
    )
    ax.tick_params(axis="y", labelsize=15, colors=colors["tick"], length=5, width=1)
    ax.tick_params(axis="x", length=0, pad=14)

    # Metric name only on Y-axis (no product banner title on the PNG).
    # Wrap + wider left margin so the label is not clipped by the figure edge.
    ylabel = _wrap_axis_label(display_metric, width=22)
    ax.set_ylabel(ylabel, fontsize=14, color=colors["label"], labelpad=10)
    # `title` kept for API/PDF callers; on-screen chart omits it.
    _ = title

    # Headroom for value labels above bars
    span = y_max - y_min
    ax.set_ylim(y_min, y_max + span * 0.08)
    ax.set_xlim(-0.55, n - 0.45)
    ax.yaxis.grid(
        True, linestyle="--", linewidth=0.8, color=colors["grid"], alpha=0.9, zorder=0
    )
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(colors["spine"])
        ax.spines[spine].set_linewidth(1.15)

    # Left room for wrapped ylabel; bottom for 3-line x ticks
    left_m = 0.20 if len(display_metric) > 28 else 0.14
    fig.subplots_adjust(left=left_m, right=0.985, top=0.94, bottom=0.34)

    png_buf = io.BytesIO()
    # Fixed canvas size — no bbox_inches='tight' (that shrinks text on screen)
    fig.savefig(
        png_buf,
        format="png",
        dpi=dpi,
        facecolor=fig.get_facecolor(),
        edgecolor="none",
    )
    plt.close(fig)
    return png_buf.getvalue()


def build_batch_metric_chart_png_base64(
    batch_results: Sequence[Dict[str, Any]],
    metric_col: str,
    *,
    title: str = "ARIAKE OCTA Pro — MNV Batch Chart",
    theme: str = "dark",
) -> str:
    """PNG chart as ASCII base64 for ft.Image(src_base64=...)."""
    import base64

    return base64.b64encode(
        build_batch_metric_chart_png(
            batch_results,
            metric_col,
            title=title,
            theme=theme,
            dpi=144,
            width_px=CHART_PNG_WIDTH_PX,
            height_px=CHART_PNG_HEIGHT_PX,
        )
    ).decode("ascii")


def build_batch_metric_chart_pdf(
    batch_results: Sequence[Dict[str, Any]],
    metric_col: str,
    *,
    title: str = "ARIAKE OCTA Pro — MNV Batch Chart",
) -> bytes:
    """Render a bar chart for one CSV metric and return PDF bytes (light print theme)."""
    imagej_rows = imagej_rows_from_batch(batch_results)
    points, values = series_for_metric(imagej_rows, metric_col)
    if not values:
        raise ValueError(f"No numeric data for column: {metric_col}")

    png_buf = io.BytesIO(
        build_batch_metric_chart_png(
            batch_results,
            metric_col,
            title=title,
            theme="light",
            dpi=160,
            width_px=1400,
            height_px=760,
        )
    )

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
