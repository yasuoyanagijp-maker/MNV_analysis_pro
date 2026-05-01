import flet as ft
import uuid
import json
import re
import sys
import time
from pathlib import Path
from flet import Colors, Icons, FontWeight
from components.shared import PRIMARY, TEXT_MUTED, GLASS_BG, AppContext, safe_round, session_discard

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SRC = _PROJECT_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from utils.mnv_imagej_csv import (
    _metrics_to_imagej_row,
    build_csv_bytes_from_imagej_rows,
    metrics_from_session_result_row,
    qc_status_for_row,
)
from utils.report_generator import generate_pdf_report

async def get_results_view(ctx: AppContext):
    # --- DATA INITIALIZATION ---
    batch_results = ctx.page.session.get("batch_results") or []
    if not batch_results and ctx.page.session.get("last_result"):
        batch_results = [ctx.page.session.get("last_result")]

    awaiting_mnv_batch_qc = bool(ctx.page.session.get("mnv_batch_awaiting_qc"))

    # Selection State (Default to Summary if multiple, or the first result)
    # We use a simple list index, -1 means Summary
    selected_index = ctx.page.session.get("results_selected_index")
    if selected_index is None:
        selected_index = -1 if len(batch_results) > 1 else 0
        ctx.page.session.set("results_selected_index", selected_index)
    if awaiting_mnv_batch_qc and batch_results:
        selected_index = 0
        ctx.page.session.set("results_selected_index", 0)

    # --- ACTION HANDLERS ---
    async def select_result(index):
        ctx.page.session.set("results_selected_index", index)
        # Bump query so Page.go fires route_change while already on /results (SPA same-path no-op otherwise)
        ctx.page.go("/results", rt=uuid.uuid4().hex[:12])

    async def on_export_batch_csv(_=None):
        try:
            if not batch_results:
                return
            mnv_rows = [
                r
                for r in batch_results
                if str(r.get("result_type") or "MNV") == "MNV"
            ]
            if not mnv_rows:
                await ctx.add_to_console(
                    "Export combined CSV: no MNV rows in this batch (VD-only batches are skipped).",
                    "WARN",
                )
                ctx.page.update()
                return
            ordered = sorted(
                mnv_rows,
                key=lambda x: str(x.get("source_filename") or ""),
            )
            uname = (ctx.page.session.get("username") or "").strip()
            meta = {
                "Analyst": uname if uname else "Unknown",
                "Started At": str(ctx.page.session.get("analysis_started_at") or ""),
                "Ended At": time.strftime("%Y-%m-%d %H:%M:%S"),
                "Duration Sec": float(ctx.page.session.get("analysis_duration_sec") or 0.0),
                "Session ID": str(ctx.page.session.get("session_id") or ""),
            }
            rows = []
            for idx, r in enumerate(ordered):
                fn = str(r.get("source_filename") or "N/A")
                success = "error" not in r
                metrics = metrics_from_session_result_row(r)
                rows.append(
                    _metrics_to_imagej_row(
                        fn,
                        idx,
                        qc_status_for_row(r),
                        success,
                        metrics,
                    )
                )
            csv_bytes = build_csv_bytes_from_imagej_rows(rows, meta)
            exports_dir = _PROJECT_ROOT / "uploads" / "exports"
            exports_dir.mkdir(parents=True, exist_ok=True)
            fname = f"mnv_batch_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.csv"
            out_path = (exports_dir / fname).resolve()
            out_path.write_bytes(csv_bytes)

            try:
                ctx.page.set_clipboard(csv_bytes.decode("utf-8-sig"))
            except Exception:
                pass

            is_web = bool(getattr(ctx.page, "web", False))
            if is_web:
                export_url = f"{ctx.client.base_url.rstrip('/')}/download_export/{fname}"
                ctx.page.launch_url(export_url)
            elif ctx.save_file_picker:

                async def on_csv_save_pick(e: ft.FilePickerResultEvent):
                    if not getattr(e, "path", None):
                        return
                    try:
                        Path(e.path).write_bytes(csv_bytes)
                        await ctx.add_to_console(f"CSV saved: {Path(e.path).name}", "SUCCESS")
                    except Exception as sav_ex:
                        await ctx.add_to_console(f"CSV save failed: {sav_ex}", "ERROR")
                    ctx.page.update()

                def sync_csv_pick(ev: ft.FilePickerResultEvent):
                    ctx.page.run_task(on_csv_save_pick, ev)

                ctx.save_file_picker.on_result = sync_csv_pick
                ctx.save_file_picker.save_file(
                    dialog_title="Export combined CSV",
                    file_name=fname,
                    allowed_extensions=["csv"],
                )

            if is_web:
                help_body = (
                    "ImageJ 互換の全列 CSV を uploads/exports に保存しました（UTF-8 BOM、mainstreamer と同一列）。\n\n"
                    f"{out_path}\n\n"
                    "ブラウザではバックエンドのダウンロード URL を開きます（Safari でも data: URL より表示・保存しやすいです）。\n"
                    f"{ctx.client.base_url.rstrip('/')}/download_export/{fname}\n\n"
                    "※ クリップボードへの自動コピーは環境によりブロックされることがあります。"
                )
            else:
                help_body = (
                    "ImageJ 互換の全列 CSV を次のファイルに書き出しました（mainstreamer と同一列）:\n\n"
                    f"{out_path}\n\n"
                    "保存ダイアログで任意の場所にもコピーを保存できます。\n"
                    "（クリップボードへの転送も試みましたが、環境により無効です。）"
                )

            d = ft.AlertDialog(
                title=ft.Text("Batch CSV Export", color=Colors.WHITE),
                content=ft.Container(
                    content=ft.Text(
                        help_body,
                        selectable=True,
                        size=12,
                        color=TEXT_MUTED,
                    ),
                    width=520,
                ),
                bgcolor=GLASS_BG,
            )
            ctx.page.open(d)
        except Exception as ex:
            await ctx.add_to_console(f"Batch Export Error: {ex}", "ERROR")
        ctx.page.update()

    async def on_mnv_batch_ok(_=None):
        res = ctx.page.session.get("last_result")
        if not res:
            await ctx.add_to_console(
                "MNV batch OK: missing last_result (session); cannot finalize this step. Try analyzing again.",
                "ERROR",
            )
            ctx.page.update()
            return
        paths = ctx.page.session.get("mnv_batch_paths") or []
        idx = int(ctx.page.session.get("mnv_batch_index") or 0)
        acc = list(ctx.page.session.get("mnv_batch_results") or [])
        acc.append(res)
        ctx.page.session.set("mnv_batch_results", acc)
        session_discard(ctx.page.session, "mnv_batch_awaiting_qc")
        next_i = idx + 1
        ctx.page.session.set("mnv_batch_index", next_i)
        session_discard(ctx.page.session, "roi")
        session_discard(ctx.page.session, "roi_mask_b64")
        session_discard(ctx.page.session, "last_result")
        session_discard(ctx.page.session, "batch_results")
        session_discard(ctx.page.session, "results_selected_index")
        if next_i < len(paths):
            ctx.page.session.set("target_path", paths[next_i])
            await ctx.add_to_console(f"MNV batch: accepted. Opening ROI for file {next_i + 1}/{len(paths)}.", "INFO")
            ctx.page.go("/roi")
        else:
            ctx.page.session.set("batch_results", acc)
            session_discard(ctx.page.session, "mnv_batch_paths")
            session_discard(ctx.page.session, "mnv_batch_index")
            session_discard(ctx.page.session, "mnv_batch_results")
            session_discard(ctx.page.session, "mnv_batch_names_preview")
            ctx.page.session.set("results_selected_index", -1)
            await ctx.add_to_console(f"MNV batch complete: {len(acc)} file(s).", "SUCCESS")
            ctx.page.go("/results", rt=uuid.uuid4().hex[:12])

    async def on_mnv_batch_redo(_=None):
        session_discard(ctx.page.session, "mnv_batch_awaiting_qc")
        session_discard(ctx.page.session, "roi")
        session_discard(ctx.page.session, "roi_mask_b64")
        session_discard(ctx.page.session, "last_result")
        session_discard(ctx.page.session, "batch_results")
        session_discard(ctx.page.session, "results_selected_index")
        await ctx.add_to_console("MNV batch: redo ROI for the same image.", "INFO")
        ctx.page.go("/roi")

    async def on_save_individual_pdf(res):
        out_dir = _PROJECT_ROOT / "uploads"
        out_dir.mkdir(exist_ok=True)
        raw_name = str(res.get("source_filename") or "result")
        stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(raw_name).stem).strip("._") or "report"
        stem = stem[:60]
        fname = f"ARIAKE_Report_{stem}_{uuid.uuid4().hex[:8]}.pdf"
        out_path = (out_dir / fname).resolve()
        try:
            generate_pdf_report(res, str(out_path))
            is_web = bool(getattr(ctx.page, "web", False))
            # Open download URL before any await — browsers block navigation opened after an
            # async barrier (trusted user gesture is lost).
            if is_web:
                dl = f"{ctx.client.base_url.rstrip('/')}/download/{fname}"
                ctx.page.launch_url(dl)
                help_body = (
                    "PDF をサーバーの uploads に保存し、ダウンロード用の URL を開きました。\n\n"
                    f"{out_path}\n\n"
                    f"{dl}\n\n"
                    "ブラウザで保存が始まらない場合は上記 URL をコピーして開いてください。"
                )
            elif ctx.save_file_picker:
                pdf_bytes = out_path.read_bytes()

                async def on_pdf_save_pick(e: ft.FilePickerResultEvent):
                    if not getattr(e, "path", None):
                        return
                    try:
                        Path(e.path).write_bytes(pdf_bytes)
                        await ctx.add_to_console(f"PDF saved: {Path(e.path).name}", "SUCCESS")
                    except Exception as sav_ex:
                        await ctx.add_to_console(f"PDF save failed: {sav_ex}", "ERROR")
                    ctx.page.update()

                def sync_pdf_pick(ev: ft.FilePickerResultEvent):
                    ctx.page.run_task(on_pdf_save_pick, ev)

                ctx.save_file_picker.on_result = sync_pdf_pick
                ctx.save_file_picker.save_file(
                    dialog_title="Save PDF report",
                    file_name=fname,
                    allowed_extensions=["pdf"],
                )
                help_body = (
                    f"PDF を次に保存しました（コピーを任意の場所に保存できます）:\n\n{out_path}\n\n"
                    "保存ダイアログで別名・別フォルダにも書き出せます。"
                )
            else:
                help_body = f"PDF を保存しました:\n\n{out_path}"

            await ctx.add_to_console(f"Report saved: {out_path.name}", "SUCCESS")

            d = ft.AlertDialog(
                title=ft.Text("PDF Saved", color=Colors.WHITE),
                content=ft.Container(
                    content=ft.Text(help_body, selectable=True, size=12, color=TEXT_MUTED),
                    width=520,
                ),
                bgcolor=GLASS_BG,
            )
            ctx.page.open(d)
        except Exception as ex:
            await ctx.add_to_console(f"PDF Error: {ex}", "ERROR")
        ctx.page.update()

    # --- UI COMPONENTS ---
    
    def metric_tile(label, value, unit, icon, color):
        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(icon, color=color, size=16),
                            ft.Container(
                                content=ft.Text(
                                    label,
                                    size=11,
                                    color=TEXT_MUTED,
                                    max_lines=3,
                                ),
                                expand=True,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.START,
                    ),
                    ft.Row(
                        [
                            ft.Container(
                                content=ft.Text(
                                    str(value),
                                    size=22,
                                    weight=FontWeight.BOLD,
                                    color=Colors.WHITE,
                                ),
                                expand=True,
                            ),
                            ft.Text(unit, size=12, color=TEXT_MUTED),
                        ],
                        alignment=ft.MainAxisAlignment.START,
                        vertical_alignment=ft.CrossAxisAlignment.END,
                    ),
                ],
                spacing=2,
            ),
            bgcolor=Colors.with_opacity(0.05, Colors.WHITE),
            padding=15,
            border_radius=12,
            border=ft.border.all(1, Colors.with_opacity(0.1, Colors.WHITE)),
            expand=True,
        )

    def _detail_pipeline_metrics(r: dict) -> dict:
        return metrics_from_session_result_row(r)

    def _detail_avdi(r: dict):
        m = _detail_pipeline_metrics(r)
        vd, mi = m.get("vessel_density"), m.get("mean_intensity")
        if vd is not None and mi is not None:
            try:
                return safe_round(float(vd) * float(mi) * 100, 2)
            except (TypeError, ValueError):
                pass
        return "—"

    def _detail_float_metric(m: dict, key: str, digits: int = 2):
        v = m.get(key)
        if v is None:
            return "—"
        try:
            return safe_round(float(v), digits)
        except (TypeError, ValueError):
            return str(v)

    # --- VIEWS ---

    def get_summary_content():
        def _open_summary_row_detail(i: int):
            def _tap(_):
                ctx.page.run_task(select_result, i)

            return _tap

        # Calculate stats
        total = len(batch_results)
        success_count = len([r for r in batch_results if "error" not in r])
        avg_area = safe_round(sum(r.get("mnv_area_mm2", 0) for r in batch_results) / total if total > 0 else 0, 3)
        avg_vd = safe_round(sum(r.get("vessel_density", 0) for r in batch_results) / total * 100 if total > 0 else 0, 2)

        return ft.ListView(
            controls=[
                ft.Row([
                    ft.Text("Batch Analytics Summary", size=32, weight=FontWeight.BOLD),
                    ft.Container(expand=True),
                    ft.ElevatedButton(
                        "Export Combined CSV",
                        icon=Icons.FILE_DOWNLOAD_ROUNDED,
                        bgcolor=PRIMARY,
                        color=Colors.BLACK,
                        on_click=lambda _: ctx.page.run_task(on_export_batch_csv),
                    ),
                ]),
                ft.Text(f"Overview of {total} processed images", color=TEXT_MUTED),
                ft.Divider(height=40, color=Colors.TRANSPARENT),
                ft.Row([
                    metric_tile("Total Files", total, "items", Icons.FOLDER_ZIP_OUTLINED, Colors.BLUE_400),
                    metric_tile("Success Rate", int(success_count / total * 100) if total > 0 else 0, "%", Icons.CHECK_CIRCLE_OUTLINED, Colors.GREEN_400),
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
                        ft.DataRow(
                            cells=[
                                ft.DataCell(
                                    ft.Text(r.get("source_filename", "Unknown"), size=13),
                                    on_tap=_open_summary_row_detail(idx),
                                ),
                                ft.DataCell(
                                    ft.Icon(Icons.CHECK_CIRCLE, color=Colors.GREEN_400, size=18)
                                    if "error" not in r
                                    else ft.Icon(Icons.ERROR, color=Colors.RED_400, size=18),
                                ),
                                ft.DataCell(ft.Text(f"{safe_round(r.get('mnv_area_mm2', 0), 2)} mm²")),
                                ft.DataCell(ft.Text(f"{safe_round(r.get('vessel_density', 0) * 100, 2)} %")),
                            ],
                        )
                        for idx, r in enumerate(batch_results)
                    ],
                    bgcolor=Colors.with_opacity(0.02, Colors.WHITE),
                    border_radius=15,
                ),
            ],
            expand=True,
            spacing=10,
        )

    def get_detail_content(idx):
        res = batch_results[idx]
        is_mnv = res.get("result_type") == "MNV" or "mnv_area_mm2" in res
        pm = _detail_pipeline_metrics(res)
        subtype_display = str(res.get("mnv_subtype") or pm.get("mnv_subtype") or "—")

        return ft.ListView(
            controls=[
                ft.Row([
                    ft.Column([
                        ft.Text(res.get("source_filename", "Result Detail"), size=28, weight=FontWeight.BOLD),
                        ft.Text(
                            f"Analysis Type: {'MNV' if is_mnv else 'VD'} | Timestamp: {res.get('analysis_timestamp', 'N/A')}",
                            color=TEXT_MUTED,
                        ),
                    ], expand=True),
                    ft.ElevatedButton(
                        "Save PDF Report",
                        icon=Icons.PICTURE_AS_PDF_ROUNDED,
                        bgcolor=PRIMARY,
                        color=Colors.BLACK,
                        on_click=lambda _: ctx.page.run_task(on_save_individual_pdf, res),
                    ),
                ]),
                ft.Divider(height=20, color=Colors.TRANSPARENT),
                ft.Text("Basic Metrics & Topology", size=20, weight=FontWeight.BOLD, color=PRIMARY),
                ft.Row([
                    metric_tile("Area", safe_round(res.get("mnv_area_mm2", 0), 2), "mm²", Icons.AREA_CHART, Colors.CYAN_400),
                    metric_tile("Subtype", subtype_display, "", Icons.CATEGORY_ROUNDED, Colors.TEAL_400),
                    metric_tile(
                        "Complexity",
                        safe_round(res.get("complexity_score", 0), 2),
                        "",
                        Icons.HUB_ROUNDED,
                        Colors.PURPLE_400,
                    ),
                    metric_tile(
                        "Vsl Density",
                        _detail_avdi(res),
                        "",
                        Icons.BUBBLE_CHART_ROUNDED,
                        Colors.GREEN_400,
                    ),
                ], spacing=15),
                ft.Text("Advanced Morphometry (Spatial Distribution)", size=20, weight=FontWeight.BOLD, color=PRIMARY),
                ft.Row([
                    metric_tile(
                        "End Density",
                        _detail_float_metric(pm, "endpoint_density"),
                        "",
                        Icons.TIMELINE_ROUNDED,
                        Colors.BLUE_400,
                    ),
                    metric_tile(
                        "Branch Density",
                        _detail_float_metric(pm, "branch_density"),
                        "",
                        Icons.ACCOUNT_TREE_ROUNDED,
                        Colors.BLUE_200,
                    ),
                    metric_tile(
                        "Uniformity",
                        safe_round(res.get("stability_score", 0), 2),
                        "",
                        Icons.BALANCE_ROUNDED,
                        Colors.AMBER_400,
                    ),
                    metric_tile(
                        "Maturity Index",
                        safe_round(res.get("maturity_index", 0), 2),
                        "",
                        Icons.VERIFIED,
                        Colors.PINK_400,
                    ),
                ], spacing=15),
                ft.Container(
                    content=ft.Column([
                        ft.Text("Vessel Analysis (Clinical Mode)", weight=FontWeight.BOLD, color=PRIMARY, size=16),
                        ft.Image(src_base64=res.get("visualization_base64"), fit=ft.ImageFit.CONTAIN)
                        if res.get("visualization_base64")
                        else ft.Text("No Image"),
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    bgcolor=Colors.BLACK,
                    padding=20,
                    border_radius=15,
                ),
                ft.Text("Flow Deficit Analysis (Regional)", size=20, weight=FontWeight.BOLD, color=PRIMARY),
                ft.Row([
                    metric_tile("FD R1 (Central)", safe_round(res.get("fd_percent_r1", 0), 2), "%", Icons.PIE_CHART_OUTLINE, Colors.RED_400),
                    metric_tile("FD R2 (Inner)", safe_round(res.get("fd_percent_r2", 0), 2), "%", Icons.PIE_CHART_OUTLINE, Colors.ORANGE_400),
                    metric_tile("FD R3 (Outer)", safe_round(res.get("fd_percent_r3", 0), 2), "%", Icons.PIE_CHART_OUTLINE, Colors.YELLOW_400),
                ], spacing=15),
                ft.Divider(height=20, color=Colors.TRANSPARENT),
            ],
            expand=True,
            spacing=20,
        )

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
            on_click=lambda _: ctx.page.run_task(select_result, -1),
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
                on_click=lambda _, i=idx: ctx.page.run_task(select_result, i),
                hover_color=Colors.with_opacity(0.1, PRIMARY),
            )
        )

    paths_mnv = ctx.page.session.get("mnv_batch_paths") or []
    idx_mnv = int(ctx.page.session.get("mnv_batch_index") or 0)
    qc_banner = None
    # Current QC step is for image index idx_mnv (0-based); last folder image => open combined summary next.
    is_final_mnv_image = awaiting_mnv_batch_qc and paths_mnv and (idx_mnv + 1 >= len(paths_mnv))
    ok_button_label = "OK — open final report" if is_final_mnv_image else "OK — next image"
    qc_help_text = (
        "これがフォルダ内の最後の画像です。OK で全件サマリー（個別詳細との切り替え・Combined CSV・各PDF）に進みます。"
        if is_final_mnv_image
        else "Review this result. OK continues to the next image (ROI again). Redo ROI reopens the ROI editor for the same file without keeping this run."
    )
    if awaiting_mnv_batch_qc and paths_mnv:
        qc_banner = ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        f"MNV batch — image {idx_mnv + 1} of {len(paths_mnv)}",
                        size=18,
                        weight=FontWeight.BOLD,
                        color=PRIMARY,
                    ),
                    ft.Text(qc_help_text, size=12, color=TEXT_MUTED),
                    ft.Row(
                        [
                            ft.ElevatedButton(
                                ok_button_label,
                                icon=Icons.FACT_CHECK_ROUNDED if is_final_mnv_image else Icons.CHECK_CIRCLE,
                                bgcolor=PRIMARY,
                                color=Colors.BLACK,
                                on_click=lambda _: ctx.page.run_task(on_mnv_batch_ok),
                            ),
                            ft.OutlinedButton(
                                "Redo ROI",
                                icon=Icons.CROP_FREE,
                                style=ft.ButtonStyle(color=Colors.AMBER_400),
                                on_click=lambda _: ctx.page.run_task(on_mnv_batch_redo),
                            ),
                        ],
                        spacing=16,
                    ),
                ],
                spacing=10,
            ),
            padding=20,
            bgcolor=Colors.with_opacity(0.12, PRIMARY),
            border_radius=12,
            border=ft.border.all(1, Colors.with_opacity(0.35, PRIMARY)),
        )

    main_scroll = get_summary_content() if selected_index == -1 else get_detail_content(selected_index)
    if qc_banner is not None:
        main_body = ft.Column(
            [
                qc_banner,
                ft.Container(content=main_scroll, expand=True),
            ],
            expand=True,
            spacing=20,
        )
    else:
        main_body = main_scroll

    return ft.Row(
        [
            ft.Container(
                content=ft.Column(sidebar_items, scroll=ft.ScrollMode.AUTO, expand=True),
                width=280,
                bgcolor=Colors.with_opacity(0.05, Colors.WHITE),
                padding=20,
                border=ft.border.only(
                    right=ft.border.BorderSide(1, Colors.with_opacity(0.1, Colors.WHITE))
                ),
            ),
            ft.Container(
                content=main_body,
                expand=True,
                padding=40,
                clip_behavior=ft.ClipBehavior.HARD_EDGE,
            ),
        ],
        expand=True,
        spacing=0,
        vertical_alignment=ft.CrossAxisAlignment.STRETCH,
    )
