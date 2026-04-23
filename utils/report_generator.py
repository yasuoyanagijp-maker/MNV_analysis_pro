import os
from fpdf import FPDF
from pathlib import Path
import base64
import tempfile
from datetime import datetime

class AnalysisReport(FPDF):
    def header(self):
        # Arial bold 15
        self.set_font('Helvetica', 'B', 15)
        # Move to the right
        self.cell(80)
        # Title
        self.cell(30, 10, 'ARIAKE OCTA - Quantitative Analysis Report', 0, 0, 'C')
        # Line break
        self.ln(20)

    def footer(self):
        # Position at 1.5 cm from bottom
        self.set_y(-15)
        # Arial italic 8
        self.set_font('Helvetica', 'I', 8)
        # Page number
        self.cell(0, 10, f'Page {self.page_no()} / {{nb}}', 0, 0, 'C')

def generate_pdf_report(data: dict, output_path: str):
    pdf = AnalysisReport()
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.set_font('Helvetica', '', 12)

    # General Information
    pdf.set_font('Helvetica', 'B', 14)
    pdf.cell(0, 10, 'General Information', 0, 1)
    pdf.set_font('Helvetica', '', 11)
    pdf.cell(0, 8, f"Source File: {data.get('source_filename', 'N/A')}", 0, 1)
    pdf.cell(0, 8, f"Analysis Date: {data.get('analysis_timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}", 0, 1)
    pdf.cell(0, 8, f"MNV Subtype: {data.get('mnv_subtype', 'N/A')}", 0, 1)
    pdf.ln(10)

    # Primary Metrics
    pdf.set_font('Helvetica', 'B', 14)
    pdf.cell(0, 10, 'Quantitative Metrics', 0, 1)
    pdf.set_font('Helvetica', '', 11)
    
    metrics = [
        ("MNV Area", f"{data.get('mnv_area_mm2', 0):.4f} mm2"),
        ("Vessel Density", f"{data.get('vessel_density', 0)*100:.2f} %"),
        ("Vessel Length", f"{data.get('vessel_length_mm', 0):.3f} mm"),
        ("Fractal Dimension", f"{data.get('fractal_dimension', 0):.4f}"),
        ("Maturity Index", f"{data.get('maturity_index', 0):.1f}"),
        ("Complexity Score", f"{data.get('complexity_score', 0):.1f}"),
        ("Stability Score", f"{data.get('stability_score', 0):.1f}"),
    ]
    
    for label, val in metrics:
        pdf.cell(60, 8, label, 1)
        pdf.cell(60, 8, val, 1)
        pdf.ln()
    
    pdf.ln(10)

    # Visualizations
    pdf.set_font('Helvetica', 'B', 14)
    pdf.cell(0, 10, 'Visualizations', 0, 1)
    
    viz_b64 = data.get("visualization_base64")
    mask_b64 = data.get("mask_base64")
    
    temp_files = []
    
    try:
        if viz_b64:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                tmp.write(base64.b64decode(viz_b64))
                temp_files.append(tmp.name)
                pdf.image(tmp.name, x=10, y=None, w=90)
        
        if mask_b64:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                tmp.write(base64.b64decode(mask_b64))
                temp_files.append(tmp.name)
                # If we already added an image, place this next to it or below
                pdf.image(tmp.name, x=110, y=pdf.get_y() - 90 if viz_b64 else None, w=90)
                
    except Exception as e:
        pdf.set_font('Helvetica', 'I', 10)
        pdf.cell(0, 10, f"Error embedding images: {str(e)}", 0, 1)
    
    # Clean up temp files
    pdf.output(output_path)
    
    for f in temp_files:
        try:
            os.unlink(f)
        except:
            pass
