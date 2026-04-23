import flet as ft
import uuid
import json
from pathlib import Path
from flet import Colors, Icons, FontWeight
from components.shared import PRIMARY, TEXT_MUTED, GLASS_BG, AppContext, safe_round

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

async def get_results_view(ctx: AppContext):
    # --- DATA INITIALIZATION ---
    batch_results = ctx.page.session.get("batch_results") or []
    if not batch_results and ctx.page.session.get("last_result"):
        batch_results = [ctx.page.session.get("last_result")]

    # Selection State (Default to Summary if multiple, or the first result)
    # We use a simple list index, -1 means Summary
    selected_index = ctx.page.session.get("results_selected_index")
    if selected_index is None:
        selected_index = -1 if len(batch_results) > 1 else 0
        ctx.page.session.set("results_selected_index", selected_index)

    # --- ACTION HANDLERS ---
    async def select_result(index):
        ctx.page.session.set("results_selected_index", index)
        await ctx.page.go("/results") # Refresh view

    async def on_export_batch_csv(e):
        try:
            if not batch_results: return
            # Combine all results into one CSV string
            csv_rows = []
            # Header
            headers = ["Filename", "Type", "Area_mm2", "VesselDensity_%", "FractalDim", "Complexity", "Maturity", "Timestamp"]
            csv_rows.append(",".join(headers))
            
            for res in batch_results:
                row = [
                    res.get("source_filename", "N/A"),
                    res.get("result_type", "MNV"),
                    str(safe_round(res.get("mnv_area_mm2", 0), 4)),
                    str(safe_round(res.get("vessel_density", 0) * 100, 2)),
                    str(safe_round(res.get("fractal_dimension", 0), 4)),
                    str(safe_round(res.get("complexity_score", 0), 2)),
                    str(safe_round(res.get("maturity_index", 0), 2)),
                    res.get("analysis_timestamp", "N/A")
                ]
                csv_rows.append(",".join(row))
            
            csv_text = "\n".join(csv_rows)
            ctx.page.set_clipboard(csv_text)
            
            d = ft.AlertDialog(
                title=ft.Text("Batch CSV Export", color=Colors.WHITE),
                content=ft.Text("全件のデータをCSV形式でクリップボードにコピーしました。\nExcel等に直接貼り付けて保存できます。", color=TEXT_MUTED),
                bgcolor=GLASS_BG,
            )
            ctx.page.open(d)
        except Exception as ex:
            await ctx.add_to_console(f"Batch Export Error: {ex}", "ERROR")
        ctx.page.update()

    async def on_save_individual_pdf(res):
        from utils.report_generator import generate_pdf_report
        out_dir = _PROJECT_ROOT / "uploads"
        out_dir.mkdir(exist_ok=True)
        out_path = out_dir / f"ARIAKE_Report_{res.get('source_filename', 'result')}_{uuid.uuid4().hex[:4]}.pdf"
        try:
            generate_pdf_report(res, str(out_path))
            await ctx.add_to_console(f"Report saved: {out_path.name}", "SUCCESS")
            d = ft.AlertDialog(
                title=ft.Text("PDF Saved", color=Colors.WHITE),
                content=ft.Text(f"レポートを保存しました:\n{out_path.name}\n\n場所: {out_dir}", color=TEXT_MUTED),
                bgcolor=GLASS_BG,
            )
            ctx.page.open(d)
        except Exception as ex:
            await ctx.add_to_console(f"PDF Error: {ex}", "ERROR")
        ctx.page.update()

    # --- UI COMPONENTS ---
    
    def metric_tile(label, value, unit, icon, color):
        return ft.Container(
            content=ft.Column([
                ft.Row([ft.Icon(icon, color=color, size=16), ft.Text(label, size=12, color=TEXT_MUTED)]),
                ft.Row([
                    ft.Text(str(value), size=24, weight=FontWeight.BOLD, color=Colors.WHITE),
                    ft.Text(unit, size=12, color=TEXT_MUTED)
                ], alignment=ft.MainAxisAlignment.START, vertical_alignment=ft.CrossAxisAlignment.END)
            ], spacing=2),
            bgcolor=Colors.with_opacity(0.05, Colors.WHITE),
            padding=15,
            border_radius=12,
            border=ft.border.all(1, Colors.with_opacity(0.1, Colors.WHITE)),
            expand=True
        )

    # --- VIEWS ---

    def get_summary_content():
        # Calculate stats
        total = len(batch_results)
        success_count = len([r for r in batch_results if "error" not in r])
        avg_area = safe_round(sum(r.get("mnv_area_mm2", 0) for r in batch_results) / total if total > 0 else 0, 3)
        avg_vd = safe_round(sum(r.get("vessel_density", 0) for r in batch_results) / total * 100 if total > 0 else 0, 2)

        return ft.Column([
            ft.Row([
                ft.Text("Batch Analytics Summary", size=32, weight=FontWeight.BOLD),
                ft.Container(expand=True),
                ft.ElevatedButton("Export Combined CSV", icon=Icons.FILE_DOWNLOAD_ROUNDED, bgcolor=PRIMARY, color=Colors.BLACK, on_click=on_export_batch_csv)
            ]),
            ft.Text(f"Overview of {total} processed images", color=TEXT_MUTED),
            ft.Divider(height=40, color=Colors.TRANSPARENT),
            
            ft.Row([
                metric_tile("Total Files", total, "items", Icons.FOLDER_ZIP_OUTLINED, Colors.BLUE_400),
                metric_tile("Success Rate", int(success_count/total*100) if total>0 else 0, "%", Icons.CHECK_CIRCLE_OUTLINED, Colors.GREEN_400),
                metric_tile("Mean Area", avg_area, "mm²", Icons.AREA_CHART_OUTLINED, Colors.CYAN_400),
                metric_tile("Mean Density", avg_vd, "%", Icons.GRAIN_ROUNDED, Colors.AMBER_400),
            ], spacing=15),
            
            ft.Divider(height=40, color=Colors.with_opacity(0.1, Colors.WHITE)),
            ft.Text("File Breakdown", size=20, weight=FontWeight.BOLD, color=PRIMARY),
            
            ft.DataTable(
                columns=[
                    ft.DataColumn(ft.Text("Source File")),
                    ft.DataColumn(ft.Text("Status")),
                    ft.DataColumn(ft.Text("MNV Area")),
                    ft.DataColumn(ft.Text("Vessel Density")),
                ],
                rows=[
                    ft.DataRow(cells=[
                        ft.DataCell(ft.Text(r.get("source_filename", "Unknown"), size=13)),
                        ft.DataCell(ft.Icon(Icons.CHECK_CIRCLE, color=Colors.GREEN_400, size=18) if "error" not in r else ft.Icon(Icons.ERROR, color=Colors.RED_400, size=18)),
                        ft.DataCell(ft.Text(f"{safe_round(r.get('mnv_area_mm2', 0), 4)} mm²")),
                        ft.DataCell(ft.Text(f"{safe_round(r.get('vessel_density', 0)*100, 2)} %")),
                    ], on_select=lambda _, i=idx: select_result(i))
                    for idx, r in enumerate(batch_results)
                ],
                bgcolor=Colors.with_opacity(0.02, Colors.WHITE),
                border_radius=15,
            )
        ], scroll=ft.ScrollMode.ADAPTIVE, spacing=10)

    def get_detail_content(idx):
        res = batch_results[idx]
        is_mnv = res.get("result_type") == "MNV" or "mnv_area_mm2" in res
        
        return ft.Column([
            ft.Row([
                ft.Column([
                    ft.Text(res.get("source_filename", "Result Detail"), size=28, weight=FontWeight.BOLD),
                    ft.Text(f"Analysis Type: {'MNV' if is_mnv else 'VD'} | Timestamp: {res.get('analysis_timestamp', 'N/A')}", color=TEXT_MUTED),
                ], expand=True),
                ft.ElevatedButton("Save PDF Report", icon=Icons.PICTURE_AS_PDF_ROUNDED, bgcolor=PRIMARY, color=Colors.BLACK, on_click=lambda _: on_save_individual_pdf(res))
            ]),
            
            ft.Divider(height=20, color=Colors.TRANSPARENT),
            
            # --- SECTION: BASIC & TOPOLOGY ---
            ft.Text("Basic Metrics & Topology", size=20, weight=FontWeight.BOLD, color=PRIMARY),
            ft.Row([
                metric_tile("Area", safe_round(res.get("mnv_area_mm2", 0), 4), "mm²", Icons.AREA_CHART, Colors.CYAN_400),
                metric_tile("Density", safe_round(res.get("vessel_density", 0) * 100, 2), "%", Icons.GRAIN, Colors.GREEN_400),
                metric_tile("Branches", res.get("num_branches", 0), "pts", Icons.CALL_SPLIT, Colors.TEAL_400),
                metric_tile("Maturity", safe_round(res.get("maturity_index", 0), 1), "Idx", Icons.VERIFIED, Colors.PINK_400),
            ], spacing=15),

            # --- SECTION: ADVANCED MORPHOMETRY ---
            ft.Text("Advanced Morphometry (Spatial Distribution)", size=20, weight=FontWeight.BOLD, color=PRIMARY),
            ft.Row([
                metric_tile("Center Diam", safe_round(res.get("diameter_center_mean", 0), 1), "μm", Icons.RADIO_BUTTON_CHECKED, Colors.BLUE_400),
                metric_tile("Periph Diam", safe_round(res.get("diameter_periphery_mean", 0), 1), "μm", Icons.RADIO_BUTTON_UNCHECKED, Colors.BLUE_200),
                metric_tile("Diam Ratio", safe_round(res.get("diameter_ratio", 1), 2), "x", Icons.COMPARE_ARROWS, Colors.PURPLE_400),
                metric_tile("Uniformity", safe_round(res.get("radial_uniformity", 0), 2), "Idx", Icons.AUTO_GRAPH, Colors.AMBER_400),
            ], spacing=15),
            
            ft.Container(
                content=ft.Column([
                    ft.Text("Vessel Analysis (Clinical Mode)", weight=FontWeight.BOLD, color=PRIMARY, size=16),
                    ft.Image(src_base64=res.get("visualization_base64"), fit=ft.ImageFit.CONTAIN) if res.get("visualization_base64") else ft.Text("No Image")
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                bgcolor=Colors.BLACK, padding=20, border_radius=15, expand=True
            ),

            # --- SECTION: FLOW DEFICIT (SECTORS) ---
            ft.Text("Flow Deficit Analysis (Regional)", size=20, weight=FontWeight.BOLD, color=PRIMARY),
            ft.Row([
                metric_tile("FD R1 (Central)", safe_round(res.get("fd_percent_r1", 0), 2), "%", Icons.PIE_CHART_OUTLINE, Colors.RED_400),
                metric_tile("FD R2 (Inner)", safe_round(res.get("fd_percent_r2", 0), 2), "%", Icons.PIE_CHART_OUTLINE, Colors.ORANGE_400),
                metric_tile("FD R3 (Outer)", safe_round(res.get("fd_percent_r3", 0), 2), "%", Icons.PIE_CHART_OUTLINE, Colors.YELLOW_400),
                metric_tile("Complexity", safe_round(res.get("complexity_score", 0), 1), "Score", Icons.INSIGHTS, Colors.PINK_400),
            ], spacing=15),

            ft.Divider(height=20, color=Colors.TRANSPARENT),
        ], scroll=ft.ScrollMode.ADAPTIVE, spacing=20)

    # --- MAIN LAYOUT ASSEMBLY ---

    sidebar_items = [
        ft.Container(
            content=ft.Column([
                ft.Text("BATCH RESULTS", size=12, weight=FontWeight.BOLD, color=PRIMARY),
                ft.Divider(height=10, color=Colors.TRANSPARENT),
            ]),
            padding=ft.padding.only(left=10, bottom=10)
        ),
        ft.ListTile(
            leading=ft.Icon(Icons.DASHBOARD_ROUNDED, color=PRIMARY if selected_index == -1 else TEXT_MUTED),
            title=ft.Text("Global Summary", color=Colors.WHITE if selected_index == -1 else TEXT_MUTED),
            selected=selected_index == -1,
            on_click=lambda _: select_result(-1),
            hover_color=Colors.with_opacity(0.1, PRIMARY),
        )
    ]

    for idx, r in enumerate(batch_results):
        sidebar_items.append(
            ft.ListTile(
                leading=ft.Icon(Icons.CHECK_CIRCLE if "error" not in r else Icons.ERROR, 
                               color=Colors.GREEN_400 if "error" not in r else Colors.RED_400, size=18),
                title=ft.Text(r.get("source_filename", f"Item {idx+1}")[:20] + "...", size=13,
                             color=Colors.WHITE if selected_index == idx else TEXT_MUTED),
                selected=selected_index == idx,
                on_click=lambda _, i=idx: select_result(i),
                hover_color=Colors.with_opacity(0.1, PRIMARY),
            )
        )

    return ft.Row([
        # Sidebar
        ft.Container(
            content=ft.Column(sidebar_items, scroll=ft.ScrollMode.HIDDEN),
            width=280,
            bgcolor=Colors.with_opacity(0.05, Colors.WHITE),
            padding=20,
            border=ft.border.only(right=ft.border.BorderSide(1, Colors.with_opacity(0.1, Colors.WHITE)))
        ),
        # Main Content
        ft.Container(
            content=get_summary_content() if selected_index == -1 else get_detail_content(selected_index),
            expand=True,
            padding=40,
        )
    ], expand=True, spacing=0)
