import flet as ft
from flet import Colors, Icons, FontWeight
from pathlib import Path
from components.shared import PRIMARY, TEXT_MUTED, GLASS_BG, AppContext, safe_round

async def get_results_view(ctx: AppContext):
    res = ctx.page.session.get("last_result") or {}
    
    def metric_card(label, value, unit, icon, color):
        return ft.Container(
            content=ft.Column([
                ft.Row([ft.Icon(icon, color=color, size=20), ft.Text(label, size=14, color=TEXT_MUTED)]),
                ft.Row([
                    ft.Text(str(value), size=28, weight=FontWeight.BOLD, color=Colors.WHITE),
                    ft.Text(unit, size=14, color=TEXT_MUTED),
                ], alignment=ft.MainAxisAlignment.START, vertical_alignment=ft.CrossAxisAlignment.BASELINE),
            ], spacing=5),
            bgcolor=GLASS_BG,
            padding=20,
            border_radius=15,
            width=230,
            border=ft.border.all(1, Colors.with_opacity(0.1, Colors.WHITE)),
        )

    is_vd = ctx.page.session.get("is_vd_result")
    
    if is_vd:
        data_rows = []
        ids = res.get("patient_ids", [])
        s_whole = res.get("superficial_whole", [])
        d_whole = res.get("deep_whole", [])
        faz = res.get("faz_areas", [])
        
        for i in range(len(ids)):
            s_val = s_whole[i] if i < len(s_whole) else 0.0
            d_val = d_whole[i] if i < len(d_whole) else 0.0
            f_val = faz[i] if i < len(faz) else 0.0
            
            data_rows.append(
                ft.DataRow(cells=[
                    ft.DataCell(ft.Text(str(ids[i]), weight=FontWeight.BOLD)),
                    ft.DataCell(ft.Text(str(safe_round(s_val, 2)))),
                    ft.DataCell(ft.Text(str(safe_round(d_val, 2)))),
                    ft.DataCell(ft.Text(str(safe_round(f_val, 3)))),
                ])
            )
        
        main_content = ft.Column([
            ft.Text("Batch VD Statistics Summary", size=24, weight=FontWeight.BOLD, color=PRIMARY),
            ft.Container(
                content=ft.DataTable(
                    columns=[
                        ft.DataColumn(ft.Text("Patient ID")),
                        ft.DataColumn(ft.Text("Sup. Whole (%)"), numeric=True),
                        ft.DataColumn(ft.Text("Deep Whole (%)"), numeric=True),
                        ft.DataColumn(ft.Text("FAZ Area (mm²)"), numeric=True),
                    ],
                    rows=data_rows,
                    heading_row_color=Colors.with_opacity(0.1, PRIMARY),
                    border_radius=10,
                    border=ft.border.all(1, Colors.with_opacity(0.1, Colors.WHITE)),
                ),
                scroll=ft.ScrollMode.ADAPTIVE,
                height=500
            )
        ], spacing=20)
    else:
        viz_b64 = res.get("visualization_base64")
        mask_b64 = res.get("mask_base64")
        viz_path = (res.get("visualization_path") or "").strip()
        mask_path = (res.get("mask_path") or "").strip()
        use_viz_fs = (
            not ctx.page.web
            and not viz_b64
            and bool(viz_path)
            and Path(viz_path).is_file()
        )
        use_mask_fs = (
            not ctx.page.web
            and not mask_b64
            and bool(mask_path)
            and Path(mask_path).is_file()
        )

        def viz_image():
            if viz_b64:
                return ft.Image(src_base64=viz_b64, fit=ft.ImageFit.CONTAIN)
            if use_viz_fs:
                return ft.Image(src=viz_path, fit=ft.ImageFit.CONTAIN)
            return ft.Center(
                ft.Text(
                    "No visualization image (check API / engine output).",
                    color=TEXT_MUTED,
                    text_align=ft.TextAlign.CENTER,
                )
            )

        def mask_image():
            if mask_b64:
                return ft.Image(src_base64=mask_b64, fit=ft.ImageFit.CONTAIN)
            if use_mask_fs:
                return ft.Image(src=mask_path, fit=ft.ImageFit.CONTAIN)
            return ft.Center(ft.Text("No mask visualization", color=TEXT_MUTED))

        basic_tab = ft.Column([
            ft.Row([
                metric_card("MNV Area", safe_round(res.get("mnv_area_mm2", 0), 3), "mm²", Icons.AREA_CHART, Colors.CYAN_400),
                metric_card("Vessel Density", safe_round(res.get("vessel_density", 0) * 100, 2), "%", Icons.GRAIN, Colors.GREEN_400),
                metric_card("Fractal Dim", safe_round(res.get("fractal_dimension", 0), 3), "FD", Icons.ACCOUNT_TREE, Colors.PURPLE_400),
                metric_card("Subtype", res.get("mnv_subtype", "N/A"), "", Icons.CATEGORY, Colors.BLUE_400),
            ], spacing=15, wrap=True),
            ft.Divider(height=20, color=Colors.TRANSPARENT),
            ft.Row([
                metric_card("Vessel Length", safe_round(res.get("vessel_length_mm", 0), 3), "mm", Icons.STRAIGHTEN, Colors.TEAL_400),
                metric_card("Mean Diameter", safe_round(res.get("mean_diameter_um", 0), 2), "μm", Icons.TIMELINE, Colors.ORANGE_400),
                metric_card("Tortuosity", safe_round(res.get("tortuosity", 0), 3), "", Icons.ROUTE, Colors.AMBER_400),
                metric_card("Trunk Pattern", res.get("trunk_pattern", "Unknown"), "", Icons.SCHEMA, Colors.PINK_400),
            ], spacing=15, wrap=True),
            ft.Divider(height=20, color=Colors.TRANSPARENT),
            ft.Text("Processed Visualizations", size=20, weight=FontWeight.BOLD),
            ft.Row([
                ft.Container(
                    bgcolor=Colors.BLACK, width=400, height=400, border_radius=10,
                    content=viz_image(),
                ),
                ft.Container(
                    bgcolor=Colors.BLACK, width=400, height=400, border_radius=10,
                    content=mask_image(),
                ),
            ], spacing=20, scroll=ft.ScrollMode.ADAPTIVE),
        ], spacing=10)

        spatial_tab = ft.Column([
            ft.Text("Network Topology", size=20, weight=FontWeight.BOLD, color=PRIMARY),
            ft.Row([
                metric_card("Branches", res.get("num_branches", 0), "", Icons.CALL_SPLIT, Colors.CYAN_400),
                metric_card("Junctions", res.get("num_junctions", 0), "", Icons.HUB, Colors.GREEN_400),
                metric_card("Endpoints", res.get("num_endpoints", 0), "", Icons.RADIO_BUTTON_CHECKED, Colors.ORANGE_400),
                metric_card("Loops", res.get("num_loops", 0), "", Icons.LOOP, Colors.PURPLE_400),
            ], spacing=15, wrap=True),
            ft.Divider(height=20, color=Colors.TRANSPARENT),
            ft.Text("Distribution Metrics", size=20, weight=FontWeight.BOLD, color=PRIMARY),
            ft.Row([
                metric_card("Trunk Eccentricity", safe_round(res.get("trunk_eccentricity", -1), 3), "", Icons.ADJUST, Colors.TEAL_400),
                metric_card("Complexity Score", safe_round(res.get("complexity_score", 0), 1), "", Icons.INSIGHTS, Colors.AMBER_400),
                metric_card("Stability Score", safe_round(res.get("stability_score", 0), 1), "", Icons.BALANCE, Colors.BLUE_400),
                metric_card("Maturity Index", safe_round(res.get("maturity_index", 0), 1), "", Icons.VERIFIED, Colors.PINK_400),
            ], spacing=15, wrap=True),
        ], spacing=10)

        def fd_ring_card(ring_label, fd_pct, fd_count, color):
            return ft.Container(
                content=ft.Column([
                    ft.Text(ring_label, size=18, weight=FontWeight.BOLD, color=color),
                    ft.Text(f"FD%: {safe_round(fd_pct, 2)}%", size=16, color=Colors.WHITE),
                    ft.Text(f"Count: {fd_count}", size=14, color=TEXT_MUTED),
                ], spacing=8, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                bgcolor=GLASS_BG, padding=30, border_radius=15, width=220,
                border=ft.border.all(1, Colors.with_opacity(0.2, color)),
            )

        fd_tab = ft.Column([
            ft.Text("Flow Deficit Analysis (Ring-based)", size=20, weight=FontWeight.BOLD, color=PRIMARY),
            ft.Row([
                fd_ring_card("Ring 1 (Inner)", res.get("fd_percent_r1", 0), res.get("fd_number_r1", 0), Colors.RED_400),
                fd_ring_card("Ring 2 (Middle)", res.get("fd_percent_r2", 0), res.get("fd_number_r2", 0), Colors.ORANGE_400),
                fd_ring_card("Ring 3 (Outer)", res.get("fd_percent_r3", 0), res.get("fd_number_r3", 0), Colors.AMBER_400),
            ], spacing=20, alignment=ft.MainAxisAlignment.CENTER),
        ], spacing=15)

        main_content = ft.Column([
            ft.Container(content=ft.Text("Basic Metrics", size=22, weight=ft.FontWeight.BOLD, color=PRIMARY), padding=ft.padding.only(top=20)),
            ft.Container(content=basic_tab, padding=20, bgcolor=GLASS_BG, border_radius=15),
            ft.Container(content=ft.Text("Spatial Distribution", size=22, weight=ft.FontWeight.BOLD, color=PRIMARY), padding=ft.padding.only(top=30)),
            ft.Container(content=spatial_tab, padding=20, bgcolor=GLASS_BG, border_radius=15),
            ft.Container(content=ft.Text("Flow Deficit", size=22, weight=ft.FontWeight.BOLD, color=PRIMARY), padding=ft.padding.only(top=30)),
            ft.Container(content=fd_tab, padding=20, bgcolor=GLASS_BG, border_radius=15),
        ], scroll=ft.ScrollMode.ADAPTIVE, expand=True)

    async def handle_export(e):
        if ctx.directory_picker:
            ctx.directory_picker.get_directory_path()

    return ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Text("Analysis Results", size=32, weight=FontWeight.BOLD, expand=True, color=Colors.WHITE),
                ft.ElevatedButton("Export CSV", icon=Icons.SAVE_ALT_ROUNDED, on_click=handle_export),
                ft.ElevatedButton("Interactive Report", icon=Icons.LAUNCH_ROUNDED, bgcolor=PRIMARY, color=Colors.BLACK),
            ]),
            ft.Divider(height=20, color=Colors.TRANSPARENT),
            main_content
        ], spacing=20),
        padding=40,
        expand=True,
        opacity=1.0,
    )
