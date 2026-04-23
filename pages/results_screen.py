import flet as ft
from flet import Colors, Icons, FontWeight
from components.shared import PRIMARY, TEXT_MUTED, AppContext, safe_round

async def get_results_view(ctx: AppContext):
    # Retrieve results from session
    batch_results = ctx.page.session.get("batch_results")
    last_result = ctx.page.session.get("last_result")
    
    if not batch_results and not last_result:
        return ft.Container(
            content=ft.Column([
                ft.Icon(Icons.SEARCH_OFF, size=50, color=TEXT_MUTED),
                ft.Text("No analysis results found in this session.", color=TEXT_MUTED)
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            padding=100
        )

    # Use batch_results if available, otherwise wrap last_result
    results_list = batch_results if batch_results else [last_result]
    selected_index = 0
    
    # Main content area reference
    main_content_area = ft.Column(expand=True, scroll=ft.ScrollMode.ADAPTIVE)

    def build_summary_panel(results):
        # Calculate statistics
        total = len(results)
        mnv_count = sum(1 for r in results if r.get("result_type") == "MNV")
        vd_count = sum(1 for r in results if r.get("result_type") == "VD")
        failed = sum(1 for r in results if "error" in r)
        
        avg_area = 0
        mnv_results = [r for r in results if r.get("result_type") == "MNV" and "error" not in r]
        if mnv_results:
            avg_area = sum(r.get("mnv_area_mm2", 0) for r in mnv_results) / len(mnv_results)

        return ft.Container(
            content=ft.Column([
                ft.Text("Batch Statistics Summary", size=24, weight=FontWeight.BOLD, color=PRIMARY),
                ft.Row([
                    ft.Container(
                        content=ft.Column([
                            ft.Text("Total Scans", size=12, color=TEXT_MUTED),
                            ft.Text(str(total), size=30, weight=FontWeight.W_900),
                        ]),
                        bgcolor=Colors.with_opacity(0.05, Colors.WHITE),
                        padding=20, border_radius=15, expand=True
                    ),
                    ft.Container(
                        content=ft.Column([
                            ft.Text("MNV Analyzed", size=12, color=TEXT_MUTED),
                            ft.Text(str(mnv_count), size=30, weight=FontWeight.W_900, color=Colors.AMBER_400),
                        ]),
                        bgcolor=Colors.with_opacity(0.05, Colors.WHITE),
                        padding=20, border_radius=15, expand=True
                    ),
                    ft.Container(
                        content=ft.Column([
                            ft.Text("Avg MNV Area", size=12, color=TEXT_MUTED),
                            ft.Text(f"{avg_area:.2f} mm²", size=30, weight=FontWeight.W_900, color=PRIMARY),
                        ]),
                        bgcolor=Colors.with_opacity(0.05, Colors.WHITE),
                        padding=20, border_radius=15, expand=True
                    ),
                ], spacing=20),
                ft.Text("Failure Report" if failed > 0 else "All analyses completed successfully.", 
                        color=Colors.RED_400 if failed > 0 else Colors.GREEN_400, weight=FontWeight.BOLD)
            ], spacing=20),
            padding=30,
            bgcolor=Colors.with_opacity(0.02, Colors.WHITE),
            border_radius=20,
            border=ft.border.all(1, Colors.with_opacity(0.1, Colors.WHITE))
        )

    def build_individual_result_ui(res):
        if "error" in res:
            return ft.Container(
                content=ft.Column([
                    ft.Icon(Icons.ERROR_OUTLINE, size=50, color=Colors.RED_400),
                    ft.Text(f"Analysis Failed for {res.get('source_filename', 'Unknown')}", size=20, color=Colors.RED_400),
                    ft.Text(str(res.get("error")), color=TEXT_MUTED)
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                padding=50
            )

        if res.get("result_type") == "MNV":
            # MNV specific UI
            return ft.Column([
                ft.Row([
                    ft.Column([
                        ft.Text(res.get("source_filename", "Scan Result"), size=28, weight=FontWeight.BOLD),
                        ft.Text(f"Analyzed on {res.get('analysis_timestamp')}", color=TEXT_MUTED),
                    ]),
                    ft.Container(
                        content=ft.Text("MNV GRADE A", color=Colors.BLACK, weight=FontWeight.BOLD, size=12),
                        bgcolor=PRIMARY, padding=ft.padding.symmetric(10, 5), border_radius=5
                    )
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Divider(height=40, color=Colors.with_opacity(0.1, Colors.WHITE)),
                ft.Row([
                    ft.Container(
                        content=ft.Image(src_base64=res.get("visualization_base64"), width=400, height=400, fit=ft.ImageFit.CONTAIN),
                        border=ft.border.all(1, Colors.with_opacity(0.2, PRIMARY)),
                        border_radius=15,
                        bgcolor=Colors.BLACK,
                    ),
                    ft.Column([
                        ft.Container(
                            content=ft.Column([
                                ft.Text("METRIC", size=10, color=TEXT_MUTED),
                                ft.Text(f"{res.get('mnv_area_mm2', 0):.3f} mm²", size=24, weight=FontWeight.BOLD, color=PRIMARY),
                                ft.Text("MNV AREA", size=12, color=Colors.WHITE70),
                            ]),
                            width=200, padding=20, bgcolor=Colors.with_opacity(0.05, Colors.WHITE), border_radius=15
                        ),
                        ft.Container(
                            content=ft.Column([
                                ft.Text("MATURITY", size=10, color=TEXT_MUTED),
                                ft.Text(f"{res.get('maturity_index', 0):.1f}%", size=24, weight=FontWeight.BOLD, color=Colors.AMBER_400),
                                ft.Text("INDEX score", size=12, color=Colors.WHITE70),
                            ]),
                            width=200, padding=20, bgcolor=Colors.with_opacity(0.05, Colors.WHITE), border_radius=15
                        ),
                    ], spacing=20)
                ], spacing=30, vertical_alignment=ft.CrossAxisAlignment.START)
            ])
        else:
            return ft.Text("VD Result Visualization pending...")

    async def switch_content(index):
        main_content_area.controls.clear()
        if index == -1: # Summary mode
            main_content_area.controls.append(build_summary_panel(results_list))
        else:
            main_content_area.controls.append(build_individual_result_ui(results_list[index]))
        main_content_area.update()

    # Sidebar / List
    sidebar_items = [
        ft.ListTile(
            leading=ft.Icon(Icons.BAR_CHART_ROUNDED, color=PRIMARY),
            title=ft.Text("Batch Summary", weight=FontWeight.BOLD),
            on_click=lambda _: ctx.page.run_task(switch_content, -1)
        ),
        ft.Divider(height=1, color=Colors.with_opacity(0.1, Colors.WHITE))
    ]

    for i, res in enumerate(results_list):
        fname = res.get("source_filename", f"Result {i+1}")
        sidebar_items.append(
            ft.ListTile(
                title=ft.Text(fname, size=13),
                subtitle=ft.Text(res.get("result_type", "Unknown"), size=10, color=TEXT_MUTED),
                on_click=lambda _, idx=i: ctx.page.run_task(switch_content, idx),
                dense=True
            )
        )

    # Initial View
    main_content_area.controls.append(build_individual_result_ui(results_list[0]))

    return ft.Row([
        ft.Container(
            content=ft.Column(sidebar_items, scroll=ft.ScrollMode.ADAPTIVE),
            width=250,
            bgcolor=Colors.with_opacity(0.05, Colors.WHITE),
            padding=10,
            border=ft.border.only(right=ft.border.BorderSide(1, Colors.with_opacity(0.1, Colors.WHITE)))
        ),
        ft.Container(
            content=main_content_area,
            expand=True,
            padding=40
        )
    ], expand=True)
