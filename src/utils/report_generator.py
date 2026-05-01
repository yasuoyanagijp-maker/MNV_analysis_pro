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
from utils.vd_batch_csv import VD_LAYOUT_VSL_DENSITY_ONLY
from utils.vd_display_helpers import get_vd_metrics_for_file


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


def _merge_vd_overlays_horizontal(
    left_path: Optional[str], right_path: Optional[str]
) -> tuple[Optional[str], list[str]]:
    """
    Return a single PNG path with superficial (left) and deep (right) side-by-side
    at equal height — avoids fpdf multi-image/page-break layout glitches.
    """
    extras: list[str] = []
    if left_path and right_path:
        a = Image.open(left_path).convert("RGBA")
        b = Image.open(right_path).convert("RGBA")
        h_target = max(a.height, b.height)

        def scale_to_height(im: Image.Image, th: int) -> Image.Image:
            if im.height <= 0:
                return im
            nw = max(1, int(round(im.width * th / float(im.height))))
            return im.resize((nw, th), Image.Resampling.LANCZOS)

        a2 = scale_to_height(a, h_target)
        b2 = scale_to_height(b, h_target)
        gap_px = max(8, h_target // 120)
        total_w = a2.width + gap_px + b2.width
        canvas = Image.new("RGBA", (total_w, h_target), (255, 255, 255, 255))
        canvas.paste(a2, (0, 0))
        canvas.paste(b2, (a2.width + gap_px, 0))
        fd, merged = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        canvas.convert("RGB").save(merged, format="PNG")
        extras.append(merged)
        return merged, extras

    return left_path or right_path, extras


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


def _latin1_cell(s: str) -> str:
    return str(s).encode("latin-1", "replace").decode("latin-1")


def generate_vd_pdf_report(data: dict, output_path: str) -> None:
    """PDF for VD analyzer API payload (aligned with vd_display_helpers + result screen)."""
    pdf = AnalysisReport()
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.set_font("Helvetica", "", 11)

    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(
        0,
        10,
        "General Information",
        border=0,
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(
        0,
        8,
        _latin1_cell(f"Source: {data.get('source_filename', 'N/A')}"),
        border=0,
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.cell(
        0,
        8,
        _latin1_cell(
            f"Timestamp: {data.get('analysis_timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}"
        ),
        border=0,
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.cell(
        0,
        8,
        "Analysis Type: VD (vessel density)",
        border=0,
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.ln(6)

    if data.get("error"):
        pdf.set_font("Helvetica", "", 11)
        pdf.multi_cell(
            0,
            8,
            _latin1_cell(f"Engine error: {data.get('error')}"),
            border=0,
        )
        pdf.output(output_path)
        return

    patient_ids = data.get("patient_ids") or []
    sup_files = data.get("superficial_files") or []
    deep_files = data.get("deep_files") or []
    n = len(patient_ids)
    temp_files = []

    if n == 0:
        pdf.set_font("Helvetica", "I", 11)
        pdf.cell(
            0,
            10,
            "No VD cases in this result payload.",
            border=0,
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        pdf.output(output_path)
        return

    vsl_only = str(data.get("vd_layout") or "") == VD_LAYOUT_VSL_DENSITY_ONLY

    for i in range(n):
        if i > 0:
            pdf.add_page()

        sf = sup_files[i] if i < len(sup_files) else ""
        df = deep_files[i] if i < len(deep_files) else ""

        pdata = get_vd_metrics_for_file(data, sf) if sf else {}
        if not pdata:
            pdata = {
                "patient_id": patient_ids[i],
                "faz_area": _idx_list(data.get("faz_areas"), i, 0.0),
                "faz_circularity": _idx_list(data.get("faz_circularities"), i, 0.0),
                "superficial_whole": _idx_list(data.get("superficial_whole"), i, 0.0),
                "deep_whole": _idx_list(data.get("deep_whole"), i, 0.0),
                "superficial_sectors": {
                    "superior": _idx_list(data.get("superficial_superior"), i, 0.0),
                    "temporal": _idx_list(data.get("superficial_temporal"), i, 0.0),
                    "nasal": _idx_list(data.get("superficial_nasal"), i, 0.0),
                    "inferior": _idx_list(data.get("superficial_inferior"), i, 0.0),
                },
                "deep_sectors": {
                    "superior": _idx_list(data.get("deep_superior"), i, 0.0),
                    "temporal": _idx_list(data.get("deep_temporal"), i, 0.0),
                    "nasal": _idx_list(data.get("deep_nasal"), i, 0.0),
                    "inferior": _idx_list(data.get("deep_inferior"), i, 0.0),
                },
            }
        pid = pdata.get("patient_id", patient_ids[i])
        faz_a = pdata.get("faz_area", 0.0)
        faz_c = pdata.get("faz_circularity", 0.0)
        sw = pdata.get("superficial_whole", 0.0)
        dw = pdata.get("deep_whole", 0.0)

        pdf.set_font("Helvetica", "B", 13)
        pdf.cell(
            0,
            10,
            _latin1_cell(f"Case {i + 1} / {n}"),
            border=0,
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        pdf.set_font("Helvetica", "", 11)
        pdf.cell(
            0,
            8,
            _latin1_cell(f"Patient / ID: {pid}"),
            border=0,
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        pdf.cell(
            0,
            8,
            _latin1_cell(f"Superficial file: {sf or _dash()}"),
            border=0,
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        if not vsl_only:
            pdf.cell(
                0,
                8,
                _latin1_cell(f"Deep file: {df or _dash()}"),
                border=0,
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )
        pdf.ln(4)

        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(
            0,
            9,
            "Key Metrics",
            border=0,
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        pdf.set_font("Helvetica", "", 11)
        sw_disp = float(sw) if isinstance(sw, (int, float)) else 0.0
        dw_disp = float(dw) if isinstance(dw, (int, float)) else 0.0
        _metrics_table_row(pdf, "FAZ Area (mm2)", _round_fmt(faz_a, 3))
        _metrics_table_row(pdf, "FAZ Circularity (0-1)", _round_fmt(faz_c, 3))
        if vsl_only:
            _metrics_table_row(pdf, "Vsl Density (%)", f"{_round_fmt(sw_disp, 2)} %")
            fd_s = _idx_list(data.get("fractal_dimension_superficial"), i, 0.0)
            t_s = _idx_list(data.get("tortuosity_superficial"), i, 0.0)
            _metrics_table_row(pdf, "Fractal dimension", _round_fmt(fd_s, 3))
            _metrics_table_row(pdf, "Tortuosity", _round_fmt(t_s, 3))
        else:
            _metrics_table_row(pdf, "Superficial VD whole (%)", f"{_round_fmt(sw_disp, 2)} %")
            _metrics_table_row(pdf, "Deep VD whole (%)", f"{_round_fmt(dw_disp, 2)} %")

            fd_s = _idx_list(data.get("fractal_dimension_superficial"), i, 0.0)
            fd_d = _idx_list(data.get("fractal_dimension_deep"), i, 0.0)
            t_s = _idx_list(data.get("tortuosity_superficial"), i, 0.0)
            t_d = _idx_list(data.get("tortuosity_deep"), i, 0.0)
            _metrics_table_row(pdf, "Fractal dimension SCP", _round_fmt(fd_s, 3))
            _metrics_table_row(pdf, "Fractal dimension DCP", _round_fmt(fd_d, 3))
            _metrics_table_row(pdf, "Tortuosity SCP", _round_fmt(t_s, 3))
            _metrics_table_row(pdf, "Tortuosity DCP", _round_fmt(t_d, 3))
        pdf.ln(6)

        ss = pdata.get("superficial_sectors") if pdata else {}
        ds = pdata.get("deep_sectors") if pdata else {}
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(
            0,
            9,
            "Vsl Density by region (%)" if vsl_only else "Vessel density by region (%)",
            border=0,
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(55, 7, "Region", border=1, new_x=XPos.RIGHT, new_y=YPos.TOP)
        if vsl_only:
            pdf.cell(120, 7, "Vsl Density", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_font("Helvetica", "", 10)
            reg_rows_simple = [
                ("Whole", sw_disp),
                ("Superior", ss.get("superior") if ss else 0),
                ("Temporal", ss.get("temporal") if ss else 0),
                ("Nasal", ss.get("nasal") if ss else 0),
                ("Inferior", ss.get("inferior") if ss else 0),
            ]
            for rlab, ua in reg_rows_simple:
                pdf.cell(55, 7, rlab, border=1, new_x=XPos.RIGHT, new_y=YPos.TOP)
                pdf.cell(120, 7, f"{_round_fmt(ua, 2)} %", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        else:
            pdf.cell(65, 7, "Superficial (%)", border=1, new_x=XPos.RIGHT, new_y=YPos.TOP)
            pdf.cell(65, 7, "Deep (%)", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_font("Helvetica", "", 10)
            reg_rows = [
                ("Whole", sw_disp, dw_disp),
                (
                    "Superior",
                    ss.get("superior") if ss else 0,
                    ds.get("superior") if ds else 0,
                ),
                (
                    "Temporal",
                    ss.get("temporal") if ss else 0,
                    ds.get("temporal") if ds else 0,
                ),
                ("Nasal", ss.get("nasal") if ss else 0, ds.get("nasal") if ds else 0),
                (
                    "Inferior",
                    ss.get("inferior") if ss else 0,
                    ds.get("inferior") if ds else 0,
                ),
            ]
            for rlab, ua, ub in reg_rows:
                pdf.cell(55, 7, rlab, border=1, new_x=XPos.RIGHT, new_y=YPos.TOP)
                pdf.cell(65, 7, f"{_round_fmt(ua, 2)} %", border=1, new_x=XPos.RIGHT, new_y=YPos.TOP)
                pdf.cell(65, 7, f"{_round_fmt(ub, 2)} %", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        sup_b64 = _idx_list_opt(data.get("superficial_visualization_b64"), i)
        deep_b64 = _idx_list_opt(data.get("deep_visualization_b64"), i)
        sup_path = _persist_image_for_pdf(sup_b64) if sup_b64 else None
        deep_path = _persist_image_for_pdf(deep_b64) if deep_b64 else None
        if sup_path:
            temp_files.append(sup_path)
        if deep_path:
            temp_files.append(deep_path)

        pdf.ln(8)
        pdf.set_font("Helvetica", "B", 12)
        overlay_title = (
            "Overlay (superficial / Vsl Density)"
            if vsl_only
            else "Overlay (superficial / deep, side-by-side)"
        )
        pdf.cell(
            0,
            9,
            overlay_title,
            border=0,
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        try:
            if vsl_only:
                if sup_path:
                    pdf.image(sup_path, x=pdf.l_margin, w=pdf.epw)
                else:
                    pdf.set_font("Helvetica", "I", 10)
                    pdf.cell(
                        0,
                        8,
                        "No overlay PNGs embedded in this API response.",
                        border=0,
                        new_x=XPos.LMARGIN,
                        new_y=YPos.NEXT,
                    )
            else:
                composite_path, merge_temps = _merge_vd_overlays_horizontal(sup_path, deep_path)
                for mp in merge_temps:
                    temp_files.append(mp)
                if composite_path:
                    pdf.image(composite_path, x=pdf.l_margin, w=pdf.epw)
                else:
                    pdf.set_font("Helvetica", "I", 10)
                    pdf.cell(
                        0,
                        8,
                        "No overlay PNGs embedded in this API response.",
                        border=0,
                        new_x=XPos.LMARGIN,
                        new_y=YPos.NEXT,
                    )
        except Exception:
            pdf.set_font("Helvetica", "I", 10)
            pdf.cell(
                0,
                8,
                "Overlay images could not be embedded.",
                border=0,
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )

    pdf.output(output_path)
    for tp in temp_files:
        try:
            os.unlink(tp)
        except OSError:
            pass


def _idx_list(lst: Any, i: int, default: float = 0.0) -> Any:
    if not isinstance(lst, list):
        return default
    if i < 0 or i >= len(lst):
        return default
    v = lst[i]
    return default if v is None else v


def _idx_list_opt(lst: Any, i: int) -> Optional[str]:
    if not isinstance(lst, list) or i < 0 or i >= len(lst):
        return None
    x = lst[i]
    return x if isinstance(x, str) and x.strip() else None


def generate_pdf_report(data: dict, output_path: str) -> None:
    if str(data.get("result_type") or "").upper() == "VD":
        generate_vd_pdf_report(data, output_path)
        return

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
