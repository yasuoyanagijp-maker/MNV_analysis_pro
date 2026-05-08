import flet as ft
import asyncio
import uuid
import json
import re
import sys
import time
import shutil
from pathlib import Path
from flet import Colors, Icons, FontWeight
from datetime import datetime
from src.flet_ui.components.shared import PRIMARY, TEXT_MUTED, GLASS_BG, AppContext, safe_round, session_discard

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_SRC = _PROJECT_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from src.utils.mnv_imagej_csv import (
    _metrics_to_imagej_row,
    build_csv_bytes_from_imagej_rows,
    metrics_from_session_result_row,
    qc_status_for_row,
)
from src.utils.report_generator import generate_pdf_report
from src.utils.vd_display_helpers import get_vd_metrics_for_file
from src.utils.vd_batch_csv import (
    VD_LAYOUT_VSL_DENSITY_ONLY,
    VD_SINGLE_CSV_COLUMNS,
    build_vd_batch_csv_bytes,
    is_vd_result_row,
    merge_vd_batches_for_csv,
    suggested_vd_csv_filename,
)

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

    _n_results = len(batch_results)
    if _n_results == 0:
        selected_index = -1
        ctx.page.session.set("results_selected_index", -1)
    elif isinstance(selected_index, int) and selected_index >= 0 and selected_index >= _n_results:
        # Stale index (e.g. prior integrated batch) after VD-only wizard or shorter batch
        selected_index = 0 if _n_results == 1 else -1
        ctx.page.session.set("results_selected_index", selected_index)

    # --- ACTION HANDLERS ---
    async def select_result(index):
        ctx.page.session.set("results_selected_index", index)
        # Bump query so Page.go fires route_change while already on /results (SPA same-path no-op otherwise)
        ctx.page.go("/results", rt=uuid.uuid4().hex[:12])

    def get_target_output_dir():
        out_folder = ctx.page.session.get("output_folder")
        if out_folder:
            return Path(out_folder)
            
        if batch_results:
            first_abs = batch_results[0].get("_absolute_source_path")
            if first_abs:
                input_dir = Path(first_abs).parent
                now = datetime.now()
                # Using YYYY_MM_DD for better sorting, but following user's "date/month/year" spirit with underscores
                folder_name = f"output_folder_{now.strftime('%Y_%m_%d')}"
                return input_dir / folder_name
        
        return _PROJECT_ROOT / "uploads" / "exports"

    async def on_export_batch_csv(_=None):
        try:
            if not batch_results:
                return

            vd_chunks = [r for r in batch_results if is_vd_result_row(r)]
            vd_vsl = [
                r for r in vd_chunks if r.get("vd_layout") == VD_LAYOUT_VSL_DENSITY_ONLY
            ]
            vd_full = [r for r in vd_chunks if r not in vd_vsl]

            mnv_rows = [
                r
                for r in batch_results
                if str(r.get("result_type") or "MNV") == "MNV"
            ]

            uname = (ctx.page.session.get("username") or "").strip()
            meta = {
                "Analyst": uname if uname else "Unknown",
                "Started At": str(ctx.page.session.get("analysis_started_at") or ""),
                "Ended At": time.strftime("%Y-%m-%d %H:%M:%S"),
                "Duration Sec": float(ctx.page.session.get("analysis_duration_sec") or 0.0),
                "Session ID": str(ctx.page.session.get("session_id") or ""),
            }

            vd_vsl_bytes = vd_vsl_fname = None
            if vd_vsl:
                merged_vsl = merge_vd_batches_for_csv(vd_vsl, VD_SINGLE_CSV_COLUMNS)
                if len(merged_vsl.get("patient_ids") or []) > 0:
                    vd_vsl_bytes = build_vd_batch_csv_bytes(
                        merged_vsl, meta, VD_SINGLE_CSV_COLUMNS
                    )
                    vd_vsl_fname = suggested_vd_csv_filename(
                        merged_vsl, meta["Session ID"], VD_LAYOUT_VSL_DENSITY_ONLY
                    )

            vd_full_bytes = vd_full_fname = None
            if vd_full:
                merged_full = merge_vd_batches_for_csv(vd_full)
                if len(merged_full.get("patient_ids") or []) > 0:
                    vd_full_bytes = build_vd_batch_csv_bytes(merged_full, meta)
                    vd_full_fname = suggested_vd_csv_filename(
                        merged_full, meta["Session ID"], "full"
                    )

            mnv_bytes = None
            mnv_fname = None
            if mnv_rows:
                ordered = sorted(
                    mnv_rows,
                    key=lambda x: str(x.get("source_filename") or ""),
                )
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
                mnv_bytes = build_csv_bytes_from_imagej_rows(rows, meta)
                mnv_fname = f"mnv_batch_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.csv"

            if not vd_vsl_bytes and not vd_full_bytes and not mnv_bytes:
                await ctx.add_to_console(
                    "Export CSV: no VD or MNV rows to export in this batch.",
                    "WARN",
                )
                ctx.page.update()
                return

            target_dir = get_target_output_dir()
            target_dir.mkdir(parents=True, exist_ok=True)
            
            saved: list[tuple[str, str, Path, bytes]] = []
            if mnv_bytes and mnv_fname:
                p = (target_dir / mnv_fname).resolve()
                p.write_bytes(mnv_bytes)
                saved.append(("MNV", mnv_fname, p, mnv_bytes))
            if vd_vsl_bytes and vd_vsl_fname:
                p = (target_dir / vd_vsl_fname).resolve()
                p.write_bytes(vd_vsl_bytes)
                saved.append(("VD (single)", vd_vsl_fname, p, vd_vsl_bytes))
            if vd_full_bytes and vd_full_fname:
                p = (target_dir / vd_full_fname).resolve()
                p.write_bytes(vd_full_bytes)
                saved.append(("VD (full)", vd_full_fname, p, vd_full_bytes))

            try:
                prefer = mnv_bytes or vd_full_bytes or vd_vsl_bytes
                if prefer:
                    ctx.page.set_clipboard(prefer.decode("utf-8-sig"))
            except Exception:
                pass

            is_web = bool(getattr(ctx.page, "web", False))
            base = ctx.client.base_url.rstrip("/")
            if is_web:
                # Copy to internal exports so web server can serve them
                internal_exports = _PROJECT_ROOT / "uploads" / "exports"
                internal_exports.mkdir(parents=True, exist_ok=True)
                for kind, fn, _, b in saved:
                    (internal_exports / fn).write_bytes(b)
                    ctx.page.launch_url(f"{base}/download_export/{fn}")
                    await asyncio.sleep(0.2)
            # In non-web mode, we don't open save_file_picker anymore because we saved directly to output_folder

            lines = [
                "UTF-8 BOM。MNV: ImageJ 互換列。VD (full): mainstreamer VD バッチ相当。VD (single): 浅層のみ・Vsl Density 列構成。",
                "",
            ]
            for kind, fn, outp, _ in saved:
                lines.append(f"[{kind}] {outp}")
            if not is_web:
                lines.append("")
                lines.append(f"ファイルを指定の出力フォルダに直接保存しました。")
            lines.append("")
            lines.append("※ クリップボードは MNV があれば MNV の内容を優先してコピーします。")

            help_body = "\n".join(lines)
            ctx.page.open(
                ft.AlertDialog(
                    title=ft.Text("CSV export (MNV / VD)", color=Colors.WHITE),
                    content=ft.Container(
                        content=ft.Text(help_body, selectable=True, size=12, color=TEXT_MUTED),
                        width=560,
                    ),
                    bgcolor=GLASS_BG,
                )
            )

            kinds = ",".join(s[0] for s in saved)
            await ctx.add_to_console(f"CSV export ready ({kinds})", "SUCCESS")
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
            vd_hdr = ctx.page.session.get("integrated_vd_result")
            merged = [vd_hdr] + acc if vd_hdr is not None else acc
            if vd_hdr is not None:
                session_discard(ctx.page.session, "integrated_vd_result")
            ctx.page.session.set("batch_results", merged)
            session_discard(ctx.page.session, "mnv_batch_paths")
            session_discard(ctx.page.session, "mnv_batch_index")
            session_discard(ctx.page.session, "mnv_batch_results")
            session_discard(ctx.page.session, "mnv_batch_names_preview")
            ctx.page.session.set("results_selected_index", -1)
            if vd_hdr is not None:
                await ctx.add_to_console(
                    f"Integrated batch complete: VD + {len(acc)} MNV file(s).", "SUCCESS"
                )
            else:
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

    async def on_mnv_batch_stop(_=None):
        res = ctx.page.session.get("last_result")
        if not res:
            return
            
        acc = list(ctx.page.session.get("mnv_batch_results") or [])
        acc.append(res)
        
        session_discard(ctx.page.session, "mnv_batch_awaiting_qc")
        session_discard(ctx.page.session, "roi")
        session_discard(ctx.page.session, "roi_mask_b64")
        session_discard(ctx.page.session, "last_result")
        session_discard(ctx.page.session, "batch_results")
        
        vd_hdr = ctx.page.session.get("integrated_vd_result")
        merged = [vd_hdr] + acc if vd_hdr is not None else acc
        if vd_hdr is not None:
            session_discard(ctx.page.session, "integrated_vd_result")
            
        ctx.page.session.set("batch_results", merged)
        
        session_discard(ctx.page.session, "mnv_batch_paths")
        session_discard(ctx.page.session, "mnv_batch_index")
        session_discard(ctx.page.session, "mnv_batch_results")
        session_discard(ctx.page.session, "mnv_batch_names_preview")
        ctx.page.session.set("results_selected_index", -1)
        
        await ctx.add_to_console(f"MNV batch stopped early: {len(acc)} file(s) saved.", "SUCCESS")
        ctx.page.go("/results", rt=uuid.uuid4().hex[:12])

    async def on_reanalyze_mnv(idx):
        res = batch_results[idx]
        abs_path = res.get("_absolute_source_path")
        if not abs_path or not Path(abs_path).exists():
            ctx.show_alpha_error(
                "Cannot Re-analyze", 
                "Original image path was not saved in this result or file no longer exists."
            )
            return

        ctx.page.session.set("target_path", abs_path)
        session_discard(ctx.page.session, "roi")
        session_discard(ctx.page.session, "roi_mask_b64")
        ctx.page.session.set("is_reanalysis_mode", True)
        ctx.page.session.set("reanalysis_index", idx)
        
        await ctx.add_to_console("Entering ROI re-analysis mode for a specific result.", "INFO")
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
                # Copy to internal downloads so web server can serve it
                (out_dir / fname).write_bytes(out_path.read_bytes())
                dl = f"{ctx.client.base_url.rstrip('/')}/download/{fname}"
                ctx.page.launch_url(dl)
                help_body = (
                    "PDF をダウンロード用に準備しました。\n\n"
                    f"{dl}\n\n"
                    "ブラウザで保存が始まらない場合は上記 URL をコピーして開いてください。"
                )
            else:
                target_dir = get_target_output_dir()
                target_dir.mkdir(parents=True, exist_ok=True)
                final_out = target_dir / fname
                shutil.copy2(out_path, final_out)
                help_body = f"PDF を指定の出力フォルダに保存しました:\n\n{final_out}"

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

    def _vd_at(lst, idx, default=None):
        if not isinstance(lst, list):
            return default
        if idx < 0 or idx >= len(lst):
            return default
        return lst[idx]

    def _vd_density_pct_str(val):
        """Same unit as VDAnalyzer/_measure_vessel_density (% of ROI) and mainstreamer VD QC."""
        if val is None:
            return "—"
        try:
            x = float(val)
        except (TypeError, ValueError):
            return "—"
        return f"{safe_round(x, 2)}%"

    def _vd_plain_str(val, digits: int = 3):
        if val is None:
            return "—"
        try:
            return str(safe_round(float(val), digits))
        except (TypeError, ValueError):
            return "—"

    # --- VIEWS ---

    def get_summary_content():
        def _open_summary_row_detail(i: int):
            def _tap(_):
                ctx.page.run_task(select_result, i)

            return _tap

        # Calculate stats (average area/density limited to rows that are clearly MNV)
        total = len(batch_results)
        success_count = len([r for r in batch_results if "error" not in r])
        mnv_rows = [
            r
            for r in batch_results
            if str(r.get("result_type") or "").upper() == "MNV"
        ]
        nm = len(mnv_rows)
        avg_area = safe_round(
            sum(r.get("mnv_area_mm2", 0) for r in mnv_rows) / nm if nm > 0 else 0,
            3,
        )
        avg_vd = safe_round(
            sum(r.get("vessel_density", 0) for r in mnv_rows) / nm * 100 if nm > 0 else 0,
            2,
        )

        return ft.ListView(
            controls=[
                ft.Row([
                    ft.Text("Batch Analytics Summary", size=32, weight=FontWeight.BOLD),
                    ft.Container(expand=True),
                    ft.ElevatedButton(
                        "Export CSV (MNV / VD)",
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
                                ft.DataCell(
                                    ft.Text(
                                        "—"
                                        if str(r.get("result_type") or "").upper() == "VD"
                                        else f"{safe_round(r.get('mnv_area_mm2', 0), 2)} mm²"
                                    )
                                ),
                                ft.DataCell(
                                    ft.Text(
                                        "—"
                                        if str(r.get("result_type") or "").upper() == "VD"
                                        else f"{safe_round(r.get('vessel_density', 0) * 100, 2)} %"
                                    )
                                ),
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

    def get_vd_detail_content(idx):
        """
        VD結果: mainstreamer VD QC と同じ `get_vd_metrics_for_file` 由来の数値／％表記。
        オーバーレイは API が PNG を base64 で返した場合のみ表示（Streamlit の vd_visualizations 相当）。
        """
        res = batch_results[idx]
        vsl_only = res.get("vd_layout") == VD_LAYOUT_VSL_DENSITY_ONLY
        _vd_detail_blurb = (
            "Superficial (SCP) Vsl Density only — deep-layer metrics hidden in UI; pairing still runs in engine."
            if vsl_only
            else "aligned with VDAnalyzer densities (%) & mainstreamer.run_vd_batch-style engine settings."
        )
        ctrls = [
            ft.Row(
                [
                    ft.Column(
                        [
                            ft.Text(
                                res.get("source_filename", "VD Result"),
                                size=28,
                                weight=FontWeight.BOLD,
                                color=Colors.WHITE,
                            ),
                            ft.Text(
                                f"Analysis type: VD | Timestamp: {res.get('analysis_timestamp', 'N/A')} — "
                                + _vd_detail_blurb,
                                color=TEXT_MUTED,
                                size=12,
                            ),
                        ],
                        expand=True,
                    ),
                    ft.Column(
                        [
                            ft.ElevatedButton(
                                "Save PDF Report",
                                icon=Icons.PICTURE_AS_PDF_ROUNDED,
                                bgcolor=PRIMARY,
                                color=Colors.BLACK,
                                on_click=lambda _, r=res: ctx.page.run_task(on_save_individual_pdf, r),
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.END,
                        spacing=6,
                    ),
                ]
            ),
            ft.Divider(height=20, color=Colors.TRANSPARENT),
        ]

        if "error" in res:
            ctrls.append(
                ft.Text(
                    f"Engine error: {res.get('error')}",
                    color=Colors.RED_400,
                )
            )
            return ft.ListView(controls=ctrls, expand=True, spacing=16)

        pids = res.get("patient_ids") or []
        n_cases = len(pids)
        if n_cases == 0:
            ctrls.append(ft.Text("No VD cases returned from the API.", color=TEXT_MUTED))
            return ft.ListView(controls=ctrls, expand=True, spacing=16)

        ctrls.append(
            ft.Text(
                f"{n_cases} scan(s) processed",
                color=PRIMARY,
                weight=FontWeight.W_600,
            ),
        )

        superf_files = res.get("superficial_files") or []

        for ci in range(n_cases):
            pid = _vd_at(pids, ci, "?")
            sf_name = _vd_at(superf_files, ci, "")
            dcp_fn = _vd_at(res.get("deep_files"), ci, "") or ""

            data = get_vd_metrics_for_file(res, sf_name) if sf_name else {}
            sw_val = None
            dw_val = None
            if data:
                faz_a = data.get("faz_area")
                faz_circ = data.get("faz_circularity")
                sw_val = data.get("superficial_whole")
                dw_val = data.get("deep_whole")
                s_sec = data.get("superficial_sectors") or {}
                d_sec = data.get("deep_sectors") or {}
                if vsl_only:
                    region_rows_vsl = [
                        ("Whole image", sw_val),
                        ("Superior", s_sec.get("superior")),
                        ("Temporal", s_sec.get("temporal")),
                        ("Nasal", s_sec.get("nasal")),
                        ("Inferior", s_sec.get("inferior")),
                    ]
                    region_pct_rows = None
                else:
                    region_rows_vsl = None
                    region_pct_rows = (
                        ("Whole image", sw_val, dw_val),
                        ("Superior", s_sec.get("superior"), d_sec.get("superior")),
                        ("Temporal", s_sec.get("temporal"), d_sec.get("temporal")),
                        ("Nasal", s_sec.get("nasal"), d_sec.get("nasal")),
                        ("Inferior", s_sec.get("inferior"), d_sec.get("inferior")),
                    )
            else:
                faz_a = _vd_at(res.get("faz_areas"), ci)
                faz_circ = _vd_at(res.get("faz_circularities"), ci)
                sw_val = _vd_at(res.get("superficial_whole"), ci)
                dw_val = _vd_at(res.get("deep_whole"), ci)
                if vsl_only:
                    region_rows_vsl = [
                        ("Whole image", _vd_at(res.get("superficial_whole"), ci)),
                        ("Superior", _vd_at(res.get("superficial_superior"), ci)),
                        ("Temporal", _vd_at(res.get("superficial_temporal"), ci)),
                        ("Nasal", _vd_at(res.get("superficial_nasal"), ci)),
                        ("Inferior", _vd_at(res.get("superficial_inferior"), ci)),
                    ]
                    region_pct_rows = None
                else:
                    region_rows_vsl = None
                    region_pct_rows = (
                        (
                            "Whole image",
                            _vd_at(res.get("superficial_whole"), ci),
                            _vd_at(res.get("deep_whole"), ci),
                        ),
                        (
                            "Superior",
                            _vd_at(res.get("superficial_superior"), ci),
                            _vd_at(res.get("deep_superior"), ci),
                        ),
                        (
                            "Temporal",
                            _vd_at(res.get("superficial_temporal"), ci),
                            _vd_at(res.get("deep_temporal"), ci),
                        ),
                        (
                            "Nasal",
                            _vd_at(res.get("superficial_nasal"), ci),
                            _vd_at(res.get("deep_nasal"), ci),
                        ),
                        (
                            "Inferior",
                            _vd_at(res.get("superficial_inferior"), ci),
                            _vd_at(res.get("deep_inferior"), ci),
                        ),
                    )

            fd_s = _vd_at(res.get("fractal_dimension_superficial"), ci)
            fd_d = _vd_at(res.get("fractal_dimension_deep"), ci)
            tor_s = _vd_at(res.get("tortuosity_superficial"), ci)
            tor_d = _vd_at(res.get("tortuosity_deep"), ci)

            ctrls.append(
                ft.Text(
                    f"Case {ci + 1} — Patient / ID: {pid}",
                    size=18,
                    weight=FontWeight.BOLD,
                    color=PRIMARY,
                )
            )
            if vsl_only:
                ctrls.append(
                    ft.Text(
                        f"SCP file: {sf_name or '—'}",
                        size=12,
                        color=TEXT_MUTED,
                    ),
                )
            else:
                ctrls.append(
                    ft.Text(
                        f"SCP file: {sf_name or '—'}   |   DCP file: {dcp_fn or '—'}",
                        size=12,
                        color=TEXT_MUTED,
                    ),
                )

            tile_row_a = [
                metric_tile(
                    "FAZ Area (mm²)",
                    _vd_plain_str(faz_a, 3),
                    "",
                    Icons.LENS_ROUNDED,
                    Colors.CYAN_400,
                ),
                metric_tile(
                    "FAZ Circularity",
                    _vd_plain_str(faz_circ, 3),
                    "(0–1)",
                    Icons.CIRCLE_ROUNDED,
                    Colors.TEAL_400,
                ),
            ]
            if vsl_only:
                tile_row_a.append(
                    metric_tile(
                        "Vsl Density",
                        _vd_density_pct_str(sw_val),
                        "",
                        Icons.GRAIN_ROUNDED,
                        Colors.GREEN_400,
                    ),
                )
                ctrls.append(ft.Row(tile_row_a, spacing=15))
                ctrls.append(
                    ft.Row(
                        [
                            metric_tile(
                                "Fractal dimension",
                                _vd_plain_str(fd_s, 3),
                                "",
                                Icons.INSIGHTS_ROUNDED,
                                Colors.BLUE_GREY,
                            ),
                            metric_tile(
                                "Tortuosity",
                                _vd_plain_str(tor_s, 3),
                                "",
                                Icons.SCATTER_PLOT_ROUNDED,
                                Colors.AMBER_400,
                            ),
                        ],
                        spacing=15,
                    ),
                )
            else:
                tile_row_a.extend(
                    [
                        metric_tile(
                            "Superficial VD (whole)",
                            _vd_density_pct_str(sw_val),
                            "",
                            Icons.GRAIN_ROUNDED,
                            Colors.GREEN_400,
                        ),
                        metric_tile(
                            "Deep VD (whole)",
                            _vd_density_pct_str(dw_val),
                            "",
                            Icons.GRAIN_ROUNDED,
                            Colors.BLUE_400,
                        ),
                    ],
                )
                ctrls.append(ft.Row(tile_row_a, spacing=15))
                ctrls.append(
                    ft.Row(
                        [
                            metric_tile(
                                "Fractal dim. SCP",
                                _vd_plain_str(fd_s, 3),
                                "",
                                Icons.INSIGHTS_ROUNDED,
                                Colors.BLUE_GREY,
                            ),
                            metric_tile(
                                "Fractal dim. DCP",
                                _vd_plain_str(fd_d, 3),
                                "",
                                Icons.INSIGHTS_ROUNDED,
                                Colors.BLUE_200,
                            ),
                            metric_tile(
                                "Tortuosity SCP",
                                _vd_plain_str(tor_s, 3),
                                "",
                                Icons.SCATTER_PLOT_ROUNDED,
                                Colors.AMBER_400,
                            ),
                            metric_tile(
                                "Tortuosity DCP",
                                _vd_plain_str(tor_d, 3),
                                "",
                                Icons.SCATTER_PLOT_ROUNDED,
                                Colors.ORANGE_400,
                            ),
                        ],
                        spacing=15,
                    ),
                )

            ctrls.append(
                ft.Text(
                    "Vsl Density by region (%)" if vsl_only else "Vessel density by region (%)",
                    size=17,
                    weight=FontWeight.BOLD,
                    color=PRIMARY,
                )
            )

            vd_rows_tbl = []
            if vsl_only and region_rows_vsl:
                tbl_columns = [
                    ft.DataColumn(ft.Text("Region", color=PRIMARY)),
                    ft.DataColumn(ft.Text("Vsl Density", color=PRIMARY)),
                ]
                for label, sv in region_rows_vsl:
                    vd_rows_tbl.append(
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Text(label, color=Colors.WHITE)),
                                ft.DataCell(ft.Text(_vd_density_pct_str(sv))),
                            ],
                        ),
                    )
                foot = (
                    "Regional Vsl Density uses VDAnalyzer superficial (SCP) % scale (same engine as folder VD)."
                )
            else:
                tbl_columns = [
                    ft.DataColumn(ft.Text("Region", color=PRIMARY)),
                    ft.DataColumn(ft.Text("SCP (superficial) VD", color=PRIMARY)),
                    ft.DataColumn(ft.Text("DCP (deep) VD", color=PRIMARY)),
                ]
                for label, sv, dv in region_pct_rows or ():
                    vd_rows_tbl.append(
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Text(label, color=Colors.WHITE)),
                                ft.DataCell(ft.Text(_vd_density_pct_str(sv))),
                                ft.DataCell(ft.Text(_vd_density_pct_str(dv))),
                            ],
                        ),
                    )
                foot = (
                    "Regional values use the same % scale as VDAnalyzer._measure_vessel_density "
                    "and mainstreamer VD QC charts."
                )

            ctrls.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.DataTable(
                                columns=tbl_columns,
                                rows=vd_rows_tbl,
                                bgcolor=Colors.with_opacity(0.03, Colors.WHITE),
                                border=ft.border.all(
                                    1,
                                    Colors.with_opacity(0.12, Colors.WHITE),
                                ),
                                border_radius=10,
                                heading_row_height=42,
                                data_row_min_height=40,
                                horizontal_lines=ft.border.BorderSide(
                                    1,
                                    Colors.with_opacity(0.06, Colors.WHITE),
                                ),
                            ),
                            ft.Text(foot, size=11, color=TEXT_MUTED),
                        ],
                        spacing=8,
                        tight=True,
                    ),
                    clip_behavior=ft.ClipBehavior.HARD_EDGE,
                )
            )

            sup_vis = _vd_at(res.get("superficial_visualization_b64"), ci)
            deep_vis = _vd_at(res.get("deep_visualization_b64"), ci)
            if vsl_only:
                overlay_title = "Overlay (superficial / Vsl Density)"
                overlay_body = ft.Column(
                    [
                        ft.Text("Superficial", color=TEXT_MUTED, size=12),
                        (
                            ft.Image(
                                src="",
                                src_base64=sup_vis,
                                fit=ft.ImageFit.CONTAIN,
                                width=520,
                                height=520,
                            )
                            if sup_vis
                            else ft.Text("—", color=TEXT_MUTED)
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=8,
                    tight=True,
                )
            else:
                overlay_title = "Overlay (Streamlit VD QC equivalent)"
                overlay_body = ft.Row(
                    [
                        ft.Column(
                            [
                                ft.Text("Superficial", color=TEXT_MUTED, size=12),
                                (
                                    ft.Image(
                                        src="",
                                        src_base64=sup_vis,
                                        fit=ft.ImageFit.CONTAIN,
                                        width=380,
                                        height=380,
                                    )
                                    if sup_vis
                                    else ft.Text("—", color=TEXT_MUTED)
                                ),
                            ],
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            expand=True,
                        ),
                        ft.Column(
                            [
                                ft.Text("Deep", color=TEXT_MUTED, size=12),
                                (
                                    ft.Image(
                                        src="",
                                        src_base64=deep_vis,
                                        fit=ft.ImageFit.CONTAIN,
                                        width=380,
                                        height=380,
                                    )
                                    if deep_vis
                                    else ft.Text("—", color=TEXT_MUTED)
                                ),
                            ],
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            expand=True,
                        ),
                    ],
                    spacing=20,
                )
            ctrls.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text(
                                overlay_title,
                                weight=FontWeight.BOLD,
                                color=PRIMARY,
                                size=16,
                            ),
                            overlay_body,
                        ],
                        spacing=12,
                        tight=True,
                    ),
                    bgcolor=Colors.BLACK,
                    padding=20,
                    border_radius=15,
                    border=ft.border.all(
                        1,
                        Colors.with_opacity(0.15, Colors.WHITE),
                    ),
                )
            )

            ctrls.append(ft.Divider(height=28, color=Colors.TRANSPARENT))

        return ft.ListView(controls=ctrls, expand=True, spacing=12)

    def get_mnv_detail_content(idx):
        res = batch_results[idx]
        pm = _detail_pipeline_metrics(res)
        subtype_display = str(res.get("mnv_subtype") or pm.get("mnv_subtype") or "—")
        
        # Check for abnormal stability (Uniformity)
        stability_val = res.get("stability_score") or pm.get("stability_score")
        is_abnormal_uniformity = False
        try:
            if stability_val is not None and float(stability_val) == 25.0:
                is_abnormal_uniformity = True
        except:
            pass

        ctrls = [
            ft.Row(
                [
                    ft.Column(
                        [
                            ft.Text(
                                res.get("source_filename", "Result Detail"),
                                size=28,
                                weight=FontWeight.BOLD,
                                color=Colors.WHITE,
                            ),
                            ft.Text(
                                f"Analysis type: MNV | Timestamp: {res.get('analysis_timestamp', 'N/A')}",
                                color=TEXT_MUTED,
                            ),
                        ],
                        expand=True,
                    ),
                    ft.ElevatedButton(
                        "Save PDF Report",
                        icon=Icons.PICTURE_AS_PDF_ROUNDED,
                        bgcolor=PRIMARY,
                        color=Colors.BLACK,
                        on_click=lambda _: ctx.page.run_task(on_save_individual_pdf, res),
                    ),
                    ft.ElevatedButton(
                        "ROI再指定・再解析",
                        icon=Icons.CROP_FREE,
                        bgcolor=Colors.AMBER_400,
                        color=Colors.BLACK,
                        tooltip="ROI（抽出領域）を選択し直して、この画像の解析をやり直します",
                        on_click=lambda _: ctx.page.run_task(on_reanalyze_mnv, idx),
                    ),
                ]
            )
        ]

        if is_abnormal_uniformity:
            ctrls.append(
                ft.Container(
                    content=ft.Row([
                        ft.Icon(Icons.WARNING_AMBER_ROUNDED, color=Colors.BLACK),
                        ft.Text("Caliber uniformity 異常値（25.0）です。再解析を勧めます", 
                                color=Colors.BLACK, weight=FontWeight.BOLD)
                    ], alignment=ft.MainAxisAlignment.CENTER),
                    bgcolor=Colors.AMBER_400,
                    padding=10,
                    border_radius=10,
                    margin=ft.margin.only(top=10)
                )
            )

        ctrls.extend([
            ft.Divider(height=20, color=Colors.TRANSPARENT),
            ft.Text(
                "Basic Metrics & Topology",
                size=20,
                weight=FontWeight.BOLD,
                color=PRIMARY,
            ),
            ft.Row(
                    [
                        metric_tile(
                            "Area",
                            safe_round(res.get("mnv_area_mm2", 0), 2),
                            "mm²",
                            Icons.AREA_CHART,
                            Colors.CYAN_400,
                        ),
                        metric_tile(
                            "Subtype",
                            subtype_display,
                            "",
                            Icons.CATEGORY_ROUNDED,
                            Colors.TEAL_400,
                        ),
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
                    ],
                    spacing=15,
                ),
                ft.Text(
                    "Advanced Morphometry (Spatial Distribution)",
                    size=20,
                    weight=FontWeight.BOLD,
                    color=PRIMARY,
                ),
                ft.Row(
                    [
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
                    ],
                    spacing=15,
                ),
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text(
                                "Vessel Analysis (Clinical Mode)",
                                weight=FontWeight.BOLD,
                                color=PRIMARY,
                                size=16,
                            ),
                            ft.Image(
                                src_base64=res.get("visualization_base64"),
                                fit=ft.ImageFit.CONTAIN,
                            )
                            if res.get("visualization_base64")
                            else ft.Text("No Image"),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    bgcolor=Colors.BLACK,
                    padding=20,
                    border_radius=15,
                ),
                ft.Text(
                    "Flow Deficit Analysis (Regional)",
                    size=20,
                    weight=FontWeight.BOLD,
                    color=PRIMARY,
                ),
                ft.Row(
                    [
                        metric_tile(
                            "FD R1 (Central)",
                            safe_round(res.get("fd_percent_r1", 0), 2),
                            "%",
                            Icons.PIE_CHART_OUTLINE,
                            Colors.RED_400,
                        ),
                        metric_tile(
                            "FD R2 (Inner)",
                            safe_round(res.get("fd_percent_r2", 0), 2),
                            "%",
                            Icons.PIE_CHART_OUTLINE,
                            Colors.ORANGE_400,
                        ),
                        metric_tile(
                            "FD R3 (Outer)",
                            safe_round(res.get("fd_percent_r3", 0), 2),
                            "%",
                            Icons.PIE_CHART_OUTLINE,
                            Colors.YELLOW_400,
                        ),
                    ],
                    spacing=15,
                ),
                ft.Divider(height=20, color=Colors.TRANSPARENT),
            ],
        )

        return ft.ListView(controls=ctrls, expand=True, spacing=20)

    def get_detail_content(idx):
        if not batch_results or idx < 0 or idx >= len(batch_results):
            return get_summary_content()
        res = batch_results[idx]
        if str(res.get("result_type") or "").upper() == "VD":
            return get_vd_detail_content(idx)
        return get_mnv_detail_content(idx)

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
                            ft.OutlinedButton(
                                "Stop Here",
                                icon=Icons.STOP_CIRCLE,
                                style=ft.ButtonStyle(color=Colors.RED_400),
                                tooltip="以降の画像をキャンセルし、ここまでの結果でサマリー画面へ進みます",
                                on_click=lambda _: ctx.page.run_task(on_mnv_batch_stop),
                                visible=not is_final_mnv_image,
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
