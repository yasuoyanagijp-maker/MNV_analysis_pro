"""
MNV batch CSV export (ImageJ createMeasurementsTable–compatible columns).

Shared by Streamlit (mainstreamer) and Flet/API so output matches exactly.
"""

from __future__ import annotations

import csv
import io
from typing import Any, Dict, List, Optional

# MNV結果CSV・結果テーブルの列順（指定順）
IMAGEJ_CSV_COLUMNS = [
    "ID",
    "File",
    "Subtype",
    "Pathophysiology",
    "Maturity Index",
    "Caliber Uniformity Score",
    "Network Complexity Score",
    "MNV Area (mm2)",
    "Vsl Area (mm2)",
    "Vsl Density (Vessel Area/MNV (%))",
    "Vessel density index adjusted by signal intensity (aVDI)",
    "MNV Area adjusted by signal intensity (aMNV)",
    "Vsl Length (mm)",
    "Junction Density (n/mm)",
    "End Pts Density (n/mm)",
    "Multi-Branch Pts Density (n/mm)",
    "Branch Density (n/mm)",
    "Dilated vessel (%)",
    "Arteriolarization Segment Count",
    "Arteriolarization Total Length (mm)",
    "Arteriolarization Max Segment Length (mm)",
    "Arteriolarization Density (/mm²)",
    "Arteriolarization Connectivity Index (mm/segment)",
    "Local Diameter Variation (max CV%)",
    "Center Branches",
    "Center Total Length (mm)",
    "Center Tortuosity",
    "Center FD (Box-Counting)",
    "Center Euler Number",
    "Center Loop Number",
    "Periphery Branches",
    "Periphery Total Length (mm)",
    "Periphery Tortuosity",
    "Periphery FD (Box-Counting)",
    "Periphery Euler Number",
    "Periphery Loop Number",
    "MNV mean gray intensity (AU)",
    "Fractal Dim",
    "Tortuosity",
    "MNV intensity Variation (CV)",
    "NV Diameter (CV)",
    "(Skel) Vsl Diameter",
    "End Pts",
    "Vsl Branches",
    "Vsl Junctions",
    "Triple Pts",
    "Quadruple Pts",
    "Raw Vsl Length",
    "Raw Vsl Diameter",
    "Quality of analysis",
    "FD% (R1)",
    "FD Avg Area µm² (R1)",
    "FD number (R1)",
    "FD density /mm² (R1)",
    "FD% (R2)",
    "FD Avg Area µm² (R2)",
    "FD number (R2)",
    "FD density /mm² (R2)",
    "FD% (R3)",
    "FD Avg Area µm² (R3)",
    "FD number (R3)",
    "FD density /mm² (R3)",
    "FD quality flag (0=OK 1=abnormal)",
    "Exclude from FD analysis",
    "FD quality reason",
    "ROI coverage (%)",
    "ROI coverage low quality (0=OK 1=low)",
    "FD box sizes",
    "N FD box sizes",
    "FD scale insufficient (0=OK 1=insufficient)",
]

# FD関連13列（行除外は現在行わず全行出力するため未使用・参照用）
FD_ZERO_EXCLUDE_COLUMNS = [
    "FD% (R1)",
    "FD Avg Area µm² (R1)",
    "FD number (R1)",
    "FD density /mm² (R1)",
    "FD% (R2)",
    "FD Avg Area µm² (R2)",
    "FD number (R2)",
    "FD density /mm² (R2)",
    "FD% (R3)",
    "FD Avg Area µm² (R3)",
    "FD number (R3)",
    "FD density /mm² (R3)",
    "FD quality flag (0=OK 1=abnormal)",
]

MNV_EXPORT_META_COLUMNS = [
    "Analyst",
    "Started At",
    "Ended At",
    "Duration Sec",
    "Session ID",
]

# Pipeline metrics key -> ImageJ column マッピング
# Note: total_length_mm = arteriolarization (high skew) total length only.
#       vessel_length_mm = full skeleton length (Vsl Length / Raw Vsl Length).
_PIPELINE_TO_IMAGEJ = {
    "mnv_subtype": "Subtype",
    "pathophysiology": "Pathophysiology",
    "mnv_area_mm2": "MNV Area (mm2)",
    "vessel_area_mm2": "Vsl Area (mm2)",
    "vessel_density": "Vsl Density (Vessel Area/MNV (%))",
    "vessel_length_mm": "Vsl Length (mm)",
    "high_skew_percentage": "Dilated vessel (%)",
    "maturity_index": "Maturity Index",
    "stability_score": "Caliber Uniformity Score",
    "complexity_score": "Network Complexity Score",
    "junction_density": "Junction Density (n/mm)",
    "endpoint_density": "End Pts Density (n/mm)",
    "multiple_density": "Multi-Branch Pts Density (n/mm)",
    "branch_density": "Branch Density (n/mm)",
    "segment_count": "Arteriolarization Segment Count",
    "total_length_mm": "Arteriolarization Total Length (mm)",
    "max_segment_length_mm": "Arteriolarization Max Segment Length (mm)",
    "density": "Arteriolarization Density (/mm²)",
    "connectivity_index": "Arteriolarization Connectivity Index (mm/segment)",
    "localized_diameter_variation": "Local Diameter Variation (max CV%)",
    "center_branch_count": "Center Branches",
    "vessel_length_center": "Center Total Length (mm)",
    "tortuosity_center": "Center Tortuosity",
    "fractal_dimension_center": "Center FD (Box-Counting)",
    "euler_center": "Center Euler Number",
    "loop_center": "Center Loop Number",
    "periphery_branch_count": "Periphery Branches",
    "vessel_length_periphery": "Periphery Total Length (mm)",
    "tortuosity_periphery": "Periphery Tortuosity",
    "fractal_dimension_periphery": "Periphery FD (Box-Counting)",
    "euler_periphery": "Periphery Euler Number",
    "loop_periphery": "Periphery Loop Number",
    "mean_intensity": "MNV mean gray intensity (AU)",
    "fractal_dimension": "Fractal Dim",
    "tortuosity": "Tortuosity",
    "standard_deviation": "MNV intensity Variation (CV)",
    "cv_diameter": "NV Diameter (CV)",
    "mean_diameter_um": "(Skel) Vsl Diameter",
    "num_endpoints": "End Pts",
    "num_branches": "Vsl Branches",
    "num_junctions": "Vsl Junctions",
    "num_triple_points": "Triple Pts",
    "num_quadruple_points": "Quadruple Pts",
    "FD_percent_R1": "FD% (R1)",
    "FD_average_area_R1": "FD Avg Area µm² (R1)",
    "FD_number_R1": "FD number (R1)",
    "FD_density_R1": "FD density /mm² (R1)",
    "FD_percent_R2": "FD% (R2)",
    "FD_average_area_R2": "FD Avg Area µm² (R2)",
    "FD_number_R2": "FD number (R2)",
    "FD_density_R2": "FD density /mm² (R2)",
    "FD_percent_R3": "FD% (R3)",
    "FD_average_area_R3": "FD Avg Area µm² (R3)",
    "FD_number_R3": "FD number (R3)",
    "FD_density_R3": "FD density /mm² (R3)",
}


def _metrics_to_imagej_row(
    filename: str, idx: int, qc_status: str, success: bool, metrics: dict
) -> dict:
    """
    Core Pipeline metricsをImageJ形式の行に変換

    ImageJ互換（ARIAKE_OCTA_color_code_J.ijm.original）:
    - vessel_density: ratio (vessel_Areas/MNV_Areas)、CSVにはそのまま出力
    - mean_intensity: MNVmean/MNVmax（ROI内の正規化平均）
    - aVDI = vessel_density * mean_intensity * 100
    - aMNV = (1 - aVDI/100) * vessel_area_mm2
    """
    row = {col: "" for col in IMAGEJ_CSV_COLUMNS}
    row["ID"] = str(idx + 1)
    row["File"] = filename
    row["Subtype"] = metrics.get("mnv_subtype", "")
    row["Quality of analysis"] = qc_status if success else "Error"

    def _to_csv_value(val):
        if val is None:
            return None
        if isinstance(val, str):
            return val
        try:
            import numpy as np

            if isinstance(val, np.integer):
                return int(val)
            if isinstance(val, np.floating):
                return float(val)
        except ImportError:
            pass
        if isinstance(val, (int, float)):
            return val
        return None

    for pk, ij_col in _PIPELINE_TO_IMAGEJ.items():
        if pk in metrics and ij_col in row:
            csv_val = _to_csv_value(metrics[pk])
            if csv_val is not None:
                row[ij_col] = csv_val

    # Vsl Length (mm): Corrected優先 / Raw Vsl Length: 常にRaw（ImageJ互換）
    corrected_len = metrics.get("corrected_vessel_length_mm")
    vlen = metrics.get("vessel_length_mm")
    if corrected_len is not None and isinstance(corrected_len, (int, float)):
        row["Vsl Length (mm)"] = corrected_len
    elif vlen is not None and isinstance(vlen, (int, float)):
        row["Vsl Length (mm)"] = vlen
    if vlen is not None and isinstance(vlen, (int, float)):
        row["Raw Vsl Length"] = vlen

    vd = metrics.get("vessel_density")
    mi = metrics.get("mean_intensity")
    va = metrics.get("vessel_area_mm2")
    if vd is not None and mi is not None:
        try:
            vd_val = float(vd)
            mi_val = float(mi)
            vdi = vd_val * mi_val * 100
            row["Vessel density index adjusted by signal intensity (aVDI)"] = vdi
            if va is not None:
                try:
                    va_val = float(va)
                    imv = (1 - vdi / 100) * va_val
                    row["MNV Area adjusted by signal intensity (aMNV)"] = imv
                except (TypeError, ValueError):
                    pass
        except (TypeError, ValueError):
            pass

    if va is not None and vlen is not None and vlen > 0:
        try:
            raw_dia = 1000 * float(va) / float(vlen)
            row["Raw Vsl Diameter"] = raw_dia
        except (TypeError, ValueError):
            pass

    if "fractal_dimension_center" in metrics:
        row["Center FD (Box-Counting)"] = metrics.get("fractal_dimension_center")
    if "fractal_dimension_periphery" in metrics:
        row["Periphery FD (Box-Counting)"] = metrics.get("fractal_dimension_periphery")

    num_loops = metrics.get("num_loops")
    euler_number = metrics.get("euler_number")
    if num_loops is not None and row["Center Loop Number"] == "":
        row["Center Loop Number"] = num_loops // 2
        row["Periphery Loop Number"] = num_loops - (num_loops // 2)
    if euler_number is not None and row["Center Euler Number"] == "":
        row["Center Euler Number"] = euler_number // 2
        row["Periphery Euler Number"] = euler_number - (euler_number // 2)

    def _csv_val(val):
        v = _to_csv_value(val)
        return v if v is not None else ""

    if "fd_quality_flag" in metrics:
        row["FD quality flag (0=OK 1=abnormal)"] = _csv_val(metrics["fd_quality_flag"])
    if "exclude_from_fd_analysis" in metrics:
        row["Exclude from FD analysis"] = _csv_val(metrics["exclude_from_fd_analysis"])
    if "fd_quality_reason" in metrics:
        row["FD quality reason"] = str(metrics["fd_quality_reason"])
    if "roi_coverage" in metrics:
        row["ROI coverage (%)"] = _csv_val(metrics["roi_coverage"])
    if "roi_coverage_low_quality" in metrics:
        row["ROI coverage low quality (0=OK 1=low)"] = _csv_val(
            metrics["roi_coverage_low_quality"]
        )
    if "fd_box_sizes" in metrics:
        row["FD box sizes"] = str(metrics["fd_box_sizes"])
    if "n_fd_box_sizes" in metrics:
        row["N FD box sizes"] = _csv_val(metrics["n_fd_box_sizes"])
    if "fd_scale_insufficient" in metrics:
        row["FD scale insufficient (0=OK 1=insufficient)"] = _csv_val(
            metrics["fd_scale_insufficient"]
        )

    return row


def build_csv_bytes_from_imagej_rows(rows: List[dict], meta: Dict[str, Any]) -> bytes:
    """Same bytes as mainstreamer export_mnv_results_to_csv (UTF-8 BOM)."""
    export_columns = IMAGEJ_CSV_COLUMNS + MNV_EXPORT_META_COLUMNS
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=export_columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        row_out = {k: row.get(k, "") for k in IMAGEJ_CSV_COLUMNS}
        row_out.update(meta)
        writer.writerow({k: row_out.get(k, "") for k in export_columns})
    return buf.getvalue().encode("utf-8-sig")


_SKIP_METRICS_KEYS = frozenset(
    {
        "binary",
        "roi_mask",
        "mex_hat",
        "tubeness",
        "rgb",
        "fd_visualization",
        "skeleton",
        "refined_skeleton",
        "refined_skeleton_structure",
        "distance_map",
        "thick_vessel_map",
        "high_skew_skeleton",
        "dilated_highSkew_for_visualization",
    }
)


def metrics_for_csv_export(res: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract JSON-safe pipeline scalars from MNVPipeline.analyze() result dict
    for API / session storage (fed into _metrics_to_imagej_row).
    """
    try:
        import numpy as np
    except ImportError:
        np = None  # type: ignore

    out: Dict[str, Any] = {}
    for k, v in res.items():
        if k in _SKIP_METRICS_KEYS:
            continue
        if np is not None and isinstance(v, np.ndarray):
            continue
        if isinstance(v, dict):
            continue
        if isinstance(v, (list, tuple)) and k != "fd_box_sizes":
            continue
        if v is None:
            continue
        if np is not None:
            if isinstance(v, np.integer):
                out[k] = int(v)
                continue
            if isinstance(v, np.floating):
                out[k] = float(v)
                continue
        if isinstance(v, bool):
            out[k] = bool(v)
            continue
        if isinstance(v, (int, float, str)):
            out[k] = v
        elif isinstance(v, (list, tuple)) and k == "fd_box_sizes":
            out[k] = v
        elif np is not None and isinstance(v, np.bool_):
            out[k] = bool(v)
    return out


# API / session row (snake_case + lower fd fields) -> pipeline-style metrics for CSV fallback
_FLAT_TO_PIPELINE_FD = (
    ("fd_percent_r1", "FD_percent_R1"),
    ("fd_number_r1", "FD_number_R1"),
    ("fd_percent_r2", "FD_percent_R2"),
    ("fd_number_r2", "FD_number_R2"),
    ("fd_percent_r3", "FD_percent_R3"),
    ("fd_number_r3", "FD_number_R3"),
)


def metrics_from_session_result_row(r: Dict[str, Any]) -> Dict[str, Any]:
    """
    Prefer csv_metrics from API; else map flat MNVResult keys into pipeline keys
    (partial row — full parity requires csv_metrics from analyze).
    """
    cm = r.get("csv_metrics")
    if isinstance(cm, dict) and cm:
        return dict(cm)
    m: Dict[str, Any] = {}
    skip = frozenset(
        {
            "result_type",
            "source_filename",
            "analysis_timestamp",
            "binary_path",
            "mask_path",
            "visualization_path",
            "visualization_base64",
            "mask_base64",
            "error",
            "csv_metrics",
        }
    )
    for k, v in r.items():
        if k in skip or v is None:
            continue
        if isinstance(v, str) and k.endswith("base64"):
            continue
        m[k] = v
    for flat_k, pipe_k in _FLAT_TO_PIPELINE_FD:
        if flat_k in r and r[flat_k] is not None:
            m[pipe_k] = r[flat_k]
    if "diameter_ratio" in r and r["diameter_ratio"] is not None:
        m["diameter_center_periphery_ratio"] = r["diameter_ratio"]
    return m


def qc_status_for_row(r: Dict[str, Any]) -> str:
    if r.get("error"):
        return "unknown"
    return str(r.get("qc_status") or r.get("quality_of_analysis") or "unknown")
