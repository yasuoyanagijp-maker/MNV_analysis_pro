import flet as ft
import uuid
from pathlib import Path
from flet import Colors, Icons, FontWeight
from components.shared import PRIMARY, TEXT_MUTED, GLASS_BG, AppContext, safe_round

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


async def get_results_view(ctx: AppContext):
    print("!!! [DEBUG] get_results_view has been called !!!", flush=True)
    try:
        res = ctx.page.session.get("last_result") or {}
        # バッチ直後: last_result が入っていなければ batch_results の先頭を表示
        if not res and ctx.page.session.get("batch_results"):
            br = ctx.page.session.get("batch_results")
            if isinstance(br, list) and len(br) > 0:
                res = br[0]

        r_type = res.get("result_type")
        is_mnv = r_type == "MNV" or (r_type is None and "mnv_area_mm2" in res)
        is_vd = r_type == "VD" or (r_type is None and ctx.page.session.get("is_vd_result"))

        async def on_export_csv(e):
            try:
                csv_text = await ctx.client.export_csv(res, is_vd=bool(is_vd and not is_mnv))
                ctx.page.set_clipboard(csv_text)
                d = ft.AlertDialog(
                    title=ft.Text("Export CSV", color=Colors.WHITE),
                    content=ft.Text(
                        "CSV をクリップボードにコピーしました。Excel 等に貼り付けて保存できます。\n\n"
                        "表示画面をそのまま PDF 化するには、ブラウザの「印刷」"
                        "（Mac: Cmd+P、Windows: Ctrl+P）を使うこともできます。",
                        color=TEXT_MUTED,
                    ),
                    bgcolor=GLASS_BG,
                )

                def close(_):
                    ctx.page.close(d)

                d.actions = [ft.TextButton("OK", on_click=close, style=ft.ButtonStyle(color=PRIMARY))]
                ctx.page.open(d)
            except Exception as ex:
                await ctx.add_to_console(f"Export CSV: {ex}", "ERROR")
            ctx.page.update()

        async def on_save_pdf(e):
            if not is_mnv:
                d = ft.AlertDialog(
                    title=ft.Text("Save Report", color=Colors.WHITE),
                    content=ft.Text("PDF レポート生成は MNV 結果向けのテンプレートです。VD 等は Export CSV をご利用ください。", color=TEXT_MUTED),
                    bgcolor=GLASS_BG,
                )
                d.actions = [ft.TextButton("OK", on_click=lambda _: ctx.page.close(d), style=ft.ButtonStyle(color=PRIMARY))]
                ctx.page.open(d)
                ctx.page.update()
                return
            from utils.report_generator import generate_pdf_report

            out_dir = _PROJECT_ROOT / "uploads"
            out_dir.mkdir(exist_ok=True)
            out = out_dir / f"ARIAKE_report_{uuid.uuid4().hex[:8]}.pdf"
            try:
                generate_pdf_report(res, str(out))
            except Exception as ex:
                d = ft.AlertDialog(
                    title=ft.Text("PDF エラー", color=Colors.RED_400),
                    content=ft.Text(str(ex), color=TEXT_MUTED),
                    bgcolor=GLASS_BG,
                )
                d.actions = [ft.TextButton("OK", on_click=lambda _: ctx.page.close(d), style=ft.ButtonStyle(color=PRIMARY))]
                ctx.page.open(d)
                ctx.page.update()
                return
            d = ft.AlertDialog(
                title=ft.Text("PDF 保存", color=Colors.WHITE),
                content=ft.Text(
                    f"次の場所に保存しました:\n{out}\n\nFinder で表示: open コマンド、または上記フォルダを開いてください。",
                    color=TEXT_MUTED,
                ),
                bgcolor=GLASS_BG,
            )
            d.actions = [ft.TextButton("OK", on_click=lambda _: ctx.page.close(d), style=ft.ButtonStyle(color=PRIMARY))]
            ctx.page.open(d)
            ctx.page.update()

        def metric_card(label, value, unit, icon, color):
            return ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Icon(icon, color=color, size=20),
                                ft.Text(label, size=14, color=TEXT_MUTED),
                            ]
                        ),
                        ft.Row(
                            [
                                ft.Text(str(value), size=28, weight=FontWeight.BOLD, color=Colors.WHITE),
                                ft.Text(unit, size=14, color=TEXT_MUTED),
                            ],
                            alignment=ft.MainAxisAlignment.START,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                    ],
                    spacing=5,
                ),
                bgcolor=GLASS_BG,
                padding=20,
                border_radius=15,
                width=230,
                border=ft.border.all(1, Colors.with_opacity(0.1, Colors.WHITE)),
            )

        header_section = ft.Column(
            [
                ft.Row(
                    [
                        ft.Text(
                            "Analysis Report - MNV Quantitative" if is_mnv else "Analysis Report",
                            size=32,
                            weight=FontWeight.BOLD,
                            expand=True,
                            color=Colors.WHITE,
                        ),
                        ft.ElevatedButton(
                            "Export CSV",
                            icon=Icons.SAVE_ALT_ROUNDED,
                            on_click=on_export_csv,
                        ),
                        ft.ElevatedButton(
                            "Save Report",
                            icon=Icons.PICTURE_AS_PDF_ROUNDED,
                            bgcolor=PRIMARY,
                            color=Colors.BLACK,
                            on_click=on_save_pdf,
                        ),
                    ]
                ),
                ft.Text(
                    "印刷: この画面のままブラウザの「印刷」",
                    size=12,
                    color=TEXT_MUTED,
                ),
                ft.Row(
                    [
                        (
                            ft.Icon(Icons.INSERT_DRIVE_FILE_OUTLINED, color=Colors.AMBER_400, size=16)
                            if res.get("source_filename")
                            else ft.Container()
                        ),
                        ft.Text(
                            f"Source: {res.get('source_filename', 'N/A')}",
                            size=14,
                            color=Colors.AMBER_400,
                            weight=FontWeight.BOLD,
                        ),
                        ft.VerticalDivider(width=20, color=Colors.TRANSPARENT),
                        (
                            ft.Icon(Icons.ACCESS_TIME, color=TEXT_MUTED, size=16)
                            if res.get("analysis_timestamp")
                            else ft.Container()
                        ),
                        ft.Text(
                            f"Analyzed at: {res.get('analysis_timestamp', 'N/A')}",
                            size=14,
                            color=TEXT_MUTED,
                        ),
                    ],
                    spacing=5,
                    visible=is_mnv or is_vd,
                ),
                ft.Divider(height=20, color=Colors.with_opacity(0.2, Colors.WHITE)),
            ]
        )

        if not res or (not is_mnv and not is_vd):
            print("!!! [DEBUG] No result data found in session !!!", flush=True)
            return ft.Container(
                content=ft.Column(
                    [
                        ft.Icon(Icons.DATA_EXPLORATION_OUTLINED, size=100, color=TEXT_MUTED),
                        ft.Text(
                            "No analysis results found in current session.",
                            size=24,
                            weight=FontWeight.BOLD,
                            color=Colors.WHITE,
                        ),
                        ft.Text("The session may have been reset due to a page reload.", color=TEXT_MUTED),
                        ft.ElevatedButton("Go to Dashboard", icon=Icons.HOME, on_click=lambda _: ctx.page.go("/")),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                alignment=ft.alignment.center,
                expand=True,
            )

        if is_mnv:
            viz_b64 = res.get("visualization_base64")
            mask_b64 = res.get("mask_base64")

            def viz_image():
                if viz_b64:
                    return ft.Image(src="", src_base64=viz_b64, fit=ft.ImageFit.CONTAIN)
                return ft.Container(
                    ft.Text("No visualization image", color=TEXT_MUTED), alignment=ft.alignment.center
                )

            def mask_image():
                if mask_b64:
                    return ft.Image(src="", src_base64=mask_b64, fit=ft.ImageFit.CONTAIN)
                return ft.Container(
                    ft.Text("No mask visualization", color=TEXT_MUTED), alignment=ft.alignment.center
                )

            main_items = [
                header_section,
                ft.Text("Basic Metrics", size=22, weight=FontWeight.BOLD, color=PRIMARY),
                ft.Row(
                    [
                        metric_card("MNV Area", safe_round(res.get("mnv_area_mm2", 0), 3), "mm²", Icons.AREA_CHART, Colors.CYAN_400),
                        metric_card("Vessel Density", safe_round(res.get("vessel_density", 0) * 100, 2), "%", Icons.GRAIN, Colors.GREEN_400),
                        metric_card("Fractal Dim", safe_round(res.get("fractal_dimension", 0), 3), "FD", Icons.ACCOUNT_TREE, Colors.PURPLE_400),
                        metric_card("Subtype", res.get("mnv_subtype", "N/A"), "", Icons.CATEGORY, Colors.BLUE_400),
                    ],
                    spacing=15,
                    wrap=True,
                ),
                ft.Row(
                    [
                        metric_card("Vessel Length", safe_round(res.get("vessel_length_mm", 0), 3), "mm", Icons.STRAIGHTEN, Colors.TEAL_400),
                        metric_card("Mean Diameter", safe_round(res.get("mean_diameter_um", 0), 2), "μm", Icons.TIMELINE, Colors.ORANGE_400),
                        metric_card("Tortuosity", safe_round(res.get("tortuosity", 0), 3), "", Icons.ROUTE, Colors.AMBER_400),
                        metric_card("Trunk Pattern", res.get("trunk_pattern", "Unknown"), "", Icons.SCHEMA, Colors.PINK_400),
                    ],
                    spacing=15,
                    wrap=True,
                ),
                ft.Text("Processed Visualizations", size=20, weight=FontWeight.BOLD, color=PRIMARY),
                ft.Row(
                    [
                        ft.Container(
                            bgcolor=Colors.BLACK, width=400, height=400, border_radius=10, content=viz_image()
                        ),
                        ft.Container(
                            bgcolor=Colors.BLACK, width=400, height=400, border_radius=10, content=mask_image()
                        ),
                    ],
                    spacing=20,
                ),
                ft.Text("Topology & Maturity", size=22, weight=FontWeight.BOLD, color=PRIMARY),
                ft.Row(
                    [
                        metric_card("Branches", res.get("num_branches", 0), "", Icons.CALL_SPLIT, Colors.CYAN_400),
                        metric_card("Junctions", res.get("num_junctions", 0), "", Icons.HUB, Colors.GREEN_400),
                        metric_card("Endpoints", res.get("num_endpoints", 0), "", Icons.RADIO_BUTTON_CHECKED, Colors.ORANGE_400),
                        metric_card("Loops", res.get("num_loops", 0), "", Icons.LOOP, Colors.PURPLE_400),
                    ],
                    spacing=15,
                    wrap=True,
                ),
                ft.Row(
                    [
                        metric_card("Maturity Index", safe_round(res.get("maturity_index", 0), 1), "", Icons.VERIFIED, Colors.PINK_400),
                        metric_card("Complexity", safe_round(res.get("complexity_score", 0), 1), "", Icons.INSIGHTS, Colors.AMBER_400),
                        metric_card("Stability", safe_round(res.get("stability_score", 0), 1), "", Icons.BALANCE, Colors.BLUE_400),
                    ],
                    spacing=15,
                    wrap=True,
                ),
            ]
        else:
            main_items = [
                header_section,
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Icon(Icons.DATA_EXPLORATION_OUTLINED, size=100, color=TEXT_MUTED),
                            ft.Text(
                                "No analysis results found. Please start an analysis from the dashboard.",
                                color=TEXT_MUTED,
                                size=18,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    alignment=ft.alignment.center,
                    padding=100,
                ),
            ]

        return ft.Container(
            content=ft.Column(
                main_items,
                scroll=ft.ScrollMode.ADAPTIVE,
                expand=True,
                spacing=20,
            ),
            padding=40,
            expand=True,
        )
    except Exception as e:
        import traceback

        error_msg = traceback.format_exc()
        print(error_msg, flush=True)
        return ft.Container(
            content=ft.Column(
                [
                    ft.Text("CRITICAL ERROR IN RESULTS VIEW", size=24, weight=FontWeight.BOLD, color=Colors.WHITE),
                    ft.Container(
                        content=ft.Text(error_msg, font_family="monospace", size=12),
                        bgcolor=Colors.BLACK,
                        padding=10,
                        border_radius=5,
                    ),
                ],
                scroll=ft.ScrollMode.ADAPTIVE,
            ),
            bgcolor=Colors.RED_900,
            padding=40,
            expand=True,
        )
