import os
import base64
import tempfile
from io import BytesIO
from datetime import datetime
from typing import Any, Optional

from fpdf import FPDF
from fpdf.enums import Align, XPos, YPos
from PIL import Image

from utils.mnv_imagej_csv import metrics_from_session_result_row


def _dash() -> str:
    # Core Helvetica fonts are Latin-1 only in fpdf2; avoid unicode em-dash in cells.
    return "-"


def _round_fmt(val: Any, digits: int = 2) -> str:
    try:
        return f"{round(float(val), digits):.{digits}f}"
    except (TypeError, ValueError):
        return _dash()


def _subtype_display(data: dict, pm: dict) -> str:
    return str(data.get("mnv_subtype") or pm.get("mnv_subtype") or _dash())


def _avdi_display(data: dict) -> str:
    pm = metrics_from_session_result_row(data)
    vd, mi = pm.get("vessel_density"), pm.get("mean_intensity")
    if vd is not None and mi is not None:
        try:
            return f"{round(float(vd) * float(mi) * 100, 2):.2f}"
        except (TypeError, ValueError):
            pass
    return _dash()


def _float_metric(pm: dict, key: str, digits: int = 2) -> str:
    v = pm.get(key)
    if v is None:
        return _dash()
    try:
        return f"{round(float(v), digits):.{digits}f}"
    except (TypeError, ValueError):
        return str(v)


def _raw_from_data_url_or_b64(s: str) -> bytes:
    t = (s or "").strip()
    if "," in t and t.lower().startswith("data:"):
        t = t.split(",", 1)[1]
    return base64.b64decode(t, validate=False)


def _persist_image_for_pdf(b64: Optional[str]) -> Optional[str]:
    """
    Decode base64, normalize with Pillow, write a closed PNG temp file path.
    Returns None if decoding or image recognition fails (avoids fpdf/PIL BytesIO errors).
    """
    if not b64 or not isinstance(b64, str):
        return None
    try:
        raw = _raw_from_data_url_or_b64(b64)
    except Exception:
        return None
    if not raw:
        return None
    try:
        im = Image.open(BytesIO(raw))
        im.load()
    except Exception:
        # Invalid / truncated payload from API/session — UI may still decode in browser differently
        return None

    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        if im.mode in ("RGBA", "P", "LA"):
            im.convert("RGBA").save(path, format="PNG")
        else:
            im.convert("RGB").save(path, format="PNG")
        return path
    except Exception:
        try:
            os.unlink(path)
        except OSError:
            pass
        return None


class AnalysisReport(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 15)
        self.cell(80)
        self.cell(
            30,
            10,
            "ARIAKE OCTA - Quantitative Analysis Report",
            border=0,
            align=Align.C,
            new_x=XPos.RIGHT,
            new_y=YPos.TOP,
        )
        self.ln(20)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.cell(
            0,
            10,
            f"Page {self.page_no()} / {{nb}}",
            border=0,
            align=Align.C,
            new_x=XPos.RIGHT,
            new_y=YPos.TOP,
        )


def _metrics_table_row(pdf: FPDF, label: str, value: str):
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(95, 8, label, border=1, new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.cell(85, 8, value, border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def generate_pdf_report(data: dict, output_path: str):
    pdf = AnalysisReport()
    pdf.alias_nb_pages()
    pdf.add_page()
    pm = metrics_from_session_result_row(data)

    pdf.set_font("Helvetica", "", 12)

    # --- General ---
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "General Information", border=0, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 11)
    is_mnv = data.get("result_type") == "MNV" or "mnv_area_mm2" in data
    pdf.cell(
        0,
        8,
        f"Source File: {data.get('source_filename', 'N/A')}",
        border=0,
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.cell(
        0,
        8,
        f"Analysis Timestamp: {data.get('analysis_timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}",
        border=0,
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.cell(
        0,
        8,
        f"Analysis Type: {'MNV' if is_mnv else 'VD'}",
        border=0,
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.ln(6)

    # --- Basic Metrics & Topology ---
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "Basic Metrics & Topology", border=0, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    _metrics_table_row(pdf, "Area (mm2)", _round_fmt(data.get("mnv_area_mm2", 0)))
    _metrics_table_row(pdf, "Subtype", _subtype_display(data, pm))
    _metrics_table_row(pdf, "Complexity", _round_fmt(data.get("complexity_score", 0)))
    _metrics_table_row(pdf, "Vsl Density", _avdi_display(data))
    pdf.ln(8)

    # --- Advanced Morphometry ---
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(
        0,
        10,
        "Advanced Morphometry (Spatial Distribution)",
        border=0,
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    _metrics_table_row(pdf, "End Density", _float_metric(pm, "endpoint_density"))
    _metrics_table_row(pdf, "Branch Density", _float_metric(pm, "branch_density"))
    _metrics_table_row(pdf, "Uniformity", _round_fmt(data.get("stability_score", 0)))
    _metrics_table_row(pdf, "Maturity Index", _round_fmt(data.get("maturity_index", 0)))
    pdf.ln(8)

    # --- Flow Deficit ---
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(
        0,
        10,
        "Flow Deficit Analysis (Regional)",
        border=0,
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    _metrics_table_row(pdf, "FD R1 (Central)", f"{_round_fmt(data.get('fd_percent_r1', 0))} %")
    _metrics_table_row(pdf, "FD R2 (Inner)", f"{_round_fmt(data.get('fd_percent_r2', 0))} %")
    _metrics_table_row(pdf, "FD R3 (Outer)", f"{_round_fmt(data.get('fd_percent_r3', 0))} %")
    pdf.ln(10)

    # --- Visualizations ---
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(
        0,
        10,
        "Vessel Analysis (Clinical Mode)",
        border=0,
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )

    viz_b64 = data.get("visualization_base64")
    mask_b64 = data.get("mask_base64")

    temp_files = []
    viz_path = _persist_image_for_pdf(viz_b64)
    mask_path = _persist_image_for_pdf(mask_b64)
    if viz_path:
        temp_files.append(viz_path)
    if mask_path:
        temp_files.append(mask_path)

    try:
        if viz_path:
            pdf.image(viz_path, x=10, y=None, w=90)
        if mask_path:
            pdf.image(mask_path, x=110, y=pdf.get_y() - 90 if viz_path else None, w=90)
        if not viz_path and not mask_path and (viz_b64 or mask_b64):
            pdf.set_font("Helvetica", "I", 10)
            pdf.cell(
                0,
                8,
                "Visualization could not be embedded (invalid image data); metrics above are unaffected.",
                border=0,
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )
    except Exception:
        pdf.set_font("Helvetica", "I", 10)
        pdf.cell(
            0,
            10,
            "Error embedding images; metrics above are unaffected.",
            border=0,
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )

    pdf.output(output_path)

    for p in temp_files:
        try:
            os.unlink(p)
        except OSError:
            pass
