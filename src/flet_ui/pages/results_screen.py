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
from src.utils.app_paths import get_exports_dir

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
    is_vd_result_row,
)
from src.utils.batch_csv_export import (
    batch_export_meta_from_session,
    collect_batch_csv_exports,
    write_batch_csv_exports,
)
from src.utils.metadata_export import export_batch_metadata_bundles
from src.utils.institution_config import resolve_institution_id
from src.utils.mnv_results_chart import (
    SUMMARY_TABLE_COLUMNS,
    build_batch_metric_chart_pdf,
    chartable_numeric_columns,
    imagej_rows_from_batch,
    series_for_metric,
    smart_y_bounds,
)

async def get_results_view(ctx: AppContext):
    # --- DATA INITIALIZATION ---
    batch_results = ctx.page.session.get("batch_results") or []
    if not batch_results and ctx.page.session.get("last_result"):
        batch_results = [ctx.page.session.get("last_result")]

    vd_only_batch = bool(batch_results) and all(
        is_vd_result_row(r) or str(r.get("result_type") or "").upper() == "VD"
        for r in batch_results
    )

    awaiting_mnv_batch_qc = bool(ctx.page.session.get("mnv_batch_awaiting_qc")) and not vd_only_batch

    # Selection State (Default to Summary if multiple, or the first result)
    # We use a simple list index, -1 means Summary
    selected_index = ctx.page.session.get("results_selected_index")
    if selected_index is None:
        if vd_only_batch:
            selected_index = 0
        else:
            selected_index = -1 if len(batch_results) > 1 else 0
        ctx.page.session.set("results_selected_index", selected_index)
    if awaiting_mnv_batch_qc and batch_results:
        selected_index = 0
        ctx.page.session.set("results_selected_index", 0)
    elif vd_only_batch and selected_index == -1:
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

    def _adjust_selection_after_reorder(sel: int, old_i: int, new_i: int) -> int:
        if sel < 0:
            return sel
        if sel == old_i:
            return new_i
        if old_i < new_i:
            if old_i < sel <= new_i:
                return sel - 1
        elif new_i <= sel < old_i:
            return sel + 1
        return sel

    async def _rewrite_csv_after_reorder():
        session_discard(ctx.page.session, "batch_csv_auto_saved")
        try:
            br = ctx.page.session.get("batch_results") or []
            if not br or bool(ctx.page.session.get("mnv_batch_awaiting_qc")):
                return
            meta = batch_export_meta_from_session(ctx.page.session)
            target_dir = get_target_output_dir()
            written = write_batch_csv_exports(br, meta, target_dir, session=ctx.page.session)
            if written:
                ctx.page.session.set("batch_csv_auto_saved", True)
                names = ", ".join(p.name for _, p in written)
                await ctx.add_to_console(
                    f"CSV order updated ({names})",
                    "INFO",
                )
        except Exception as ex:
            await ctx.add_to_console(f"CSV reorder save failed: {ex}", "WARN")

    async def on_batch_reorder(e: ft.OnReorderEvent):
        if awaiting_mnv_batch_qc:
            return
        old_i, new_i = e.old_index, e.new_index
        if old_i is None or new_i is None or old_i == new_i:
            return
        br = list(ctx.page.session.get("batch_results") or [])
        if not br or old_i < 0 or old_i >= len(br) or new_i < 0 or new_i >= len(br):
            return
        item = br.pop(old_i)
        br.insert(new_i, item)
        ctx.page.session.set("batch_results", br)
        sel = int(ctx.page.session.get("results_selected_index") or -1)
        ctx.page.session.set(
            "results_selected_index",
            _adjust_selection_after_reorder(sel, old_i, new_i),
        )
        await _rewrite_csv_after_reorder()
        ctx.page.go("/results", rt=uuid.uuid4().hex[:12])

    def get_target_output_dir():
        out_folder = ctx.page.session.get("output_folder")
        if out_folder:
            return Path(out_folder)
            
        # Use original input directory if available (avoids saving into hidden staging area)
        original_dir = ctx.page.session.get("original_input_dir")
        if original_dir:
            input_dir = Path(original_dir)
            now = datetime.now()
            folder_name = f"output_folder_{now.strftime('%Y_%m_%d')}"
            return input_dir / folder_name
            
        return get_exports_dir()

    if (
        batch_results
        and not awaiting_mnv_batch_qc
        and not ctx.page.session.contains_key("batch_csv_auto_saved")
    ):
        try:
            meta = batch_export_meta_from_session(ctx.page.session)
            target_dir = get_target_output_dir()
            written = write_batch_csv_exports(
                batch_results, meta, target_dir, session=ctx.page.session
            )
            if written:
                ctx.page.session.set("batch_csv_auto_saved", True)
                names = ", ".join(p.name for _, p in written)
                await ctx.add_to_console(
                    f"Results CSV saved to {target_dir} ({names})",
                    "SUCCESS",
                )
        except Exception as ex:
            await ctx.add_to_console(f"Auto CSV save failed: {ex}", "WARN")

    async def on_export_batch_csv(_=None):
        try:
            if not batch_results:
                return

            meta = batch_export_meta_from_session(ctx.page.session)
            payloads = collect_batch_csv_exports(batch_results, meta)
            if not payloads:
                await ctx.add_to_console(
                    "Export CSV: no VD or MNV rows to export in this batch.",
                    "WARN",
                )
                ctx.page.update()
                return

            target_dir = get_target_output_dir()
            written = write_batch_csv_exports(
                batch_results, meta, target_dir, session=ctx.page.session
            )
            payload_by_kind = {k: (fn, data) for k, fn, data in payloads}
            saved: list[tuple[str, str, Path, bytes]] = []
            for kind, path in written:
                fn, data = payload_by_kind[kind]
                saved.append((kind, fn, path, data))

            mnv_bytes = next((b for k, _, _, b in saved if k == "MNV"), None)
            vd_full_bytes = next((b for k, _, _, b in saved if k == "VD (full)"), None)
            vd_vsl_bytes = next((b for k, _, _, b in saved if k == "VD (single)"), None)

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
                internal_exports = get_exports_dir()
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

    async def on_export_metadata_data(_=None):
        """Export image_raw + mask_roi + meta.json under export/{institution}/{lesion}/ (off UI thread)."""
        try:
            if not batch_results:
                await ctx.add_to_console("Export Metadata: no results in this batch.", "WARN")
                ctx.page.update()
                return

            target_dir = get_target_output_dir()
            institution = resolve_institution_id(
                ctx.page.session,
                getattr(ctx.page, "client_storage", None),
            )
            rater = (ctx.page.session.get("username") or "").strip() or "Unknown"
            source_hint = (
                ctx.page.session.get("target_path")
                or ctx.page.session.get("original_target_path")
            )
            mask_b64 = ctx.page.session.get("roi_mask_b64")
            try:
                scale_hint = float(ctx.page.session.get("scale") or 0) or None
            except (TypeError, ValueError):
                scale_hint = None
            device_hint = ctx.page.session.get("device")
            # Snapshot rows so the worker does not touch live session state
            rows = [dict(r) if isinstance(r, dict) else r for r in batch_results]

            await ctx.add_to_console(
                f"Export Metadata & Data… institution={institution}",
                "INFO",
            )
            ctx.page.update()

            loop = asyncio.get_running_loop()
            summary = await loop.run_in_executor(
                None,
                lambda: export_batch_metadata_bundles(
                    rows,
                    institution_id=institution,
                    rater_id=rater,
                    output_dir=target_dir,
                    source_path_hint=str(source_hint) if source_hint else None,
                    session_mask_b64=mask_b64,
                    scale_mm_hint=scale_hint,
                    device_hint=str(device_hint) if device_hint else None,
                ),
            )

            n_ok = len(summary.get("exported") or [])
            n_skip = len(summary.get("skipped") or [])
            n_err = len(summary.get("errors") or [])
            root = summary.get("export_root") or str(target_dir / "export")

            lines = [
                f"Wrote {n_ok} bundle(s) under:",
                str(root),
                "",
                "Each lesion: image_raw.png, mask_roi.png, meta.json",
                f"rater_id = login username; institution_id = {summary.get('institution_id')}",
            ]
            if n_skip:
                lines.append("")
                lines.append(f"Skipped ({n_skip}):")
                for s in (summary.get("skipped") or [])[:8]:
                    lines.append(f"  • {s.get('source')}: {s.get('reason')}")
                if n_skip > 8:
                    lines.append(f"  … and {n_skip - 8} more")
            if n_err:
                lines.append("")
                lines.append(f"Errors ({n_err}):")
                for s in (summary.get("errors") or [])[:5]:
                    lines.append(f"  • {s.get('source')}: {s.get('reason')}")

            ctx.page.open(
                ft.AlertDialog(
                    title=ft.Text("Export Metadata & Data", color=Colors.WHITE),
                    content=ft.Container(
                        content=ft.Text(
                            "\n".join(lines),
                            selectable=True,
                            size=12,
                            color=TEXT_MUTED,
                        ),
                        width=560,
                    ),
                    bgcolor=GLASS_BG,
                )
            )

            level = "SUCCESS" if n_ok and not n_err else ("WARN" if n_ok else "ERROR")
            await ctx.add_to_console(
                f"Metadata export: {n_ok} ok, {n_skip} skipped, {n_err} errors → {root}",
                level,
            )
        except Exception as ex:
            await ctx.add_to_console(f"Metadata Export Error: {ex}", "ERROR")
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
            session_discard(ctx.page.session, "batch_csv_auto_saved")
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

        session_discard(ctx.page.session, "batch_csv_auto_saved")
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

    async def on_export_chart_pdf(metric_col: str):
        try:
            mnv_only = [
                r for r in batch_results
                if not is_vd_result_row(r)
                and str(r.get("result_type") or "MNV") == "MNV"
            ]
            if not mnv_only:
                await ctx.add_to_console("Chart export: no MNV rows in batch.", "WARN")
                return
            pdf_bytes = build_batch_metric_chart_pdf(mnv_only, metric_col)
            safe_metric = re.sub(r"[^A-Za-z0-9._-]+", "_", metric_col).strip("._")[:40] or "metric"
            fname = f"MNV_Chart_{safe_metric}_{uuid.uuid4().hex[:8]}.pdf"
            out_dir = _PROJECT_ROOT / "uploads"
            out_dir.mkdir(exist_ok=True)
            out_path = (out_dir / fname).resolve()
            out_path.write_bytes(pdf_bytes)
            is_web = bool(getattr(ctx.page, "web", False))
            if is_web:
                dl = f"{ctx.client.base_url.rstrip('/')}/download/{fname}"
                ctx.page.launch_url(dl)
                help_body = f"Chart PDF ready:\n\n{dl}"
            else:
                target_dir = get_target_output_dir()
                target_dir.mkdir(parents=True, exist_ok=True)
                final_out = target_dir / fname
                shutil.copy2(out_path, final_out)
                help_body = f"Chart PDF saved:\n\n{final_out}"
            await ctx.add_to_console(f"Chart PDF exported: {fname}", "SUCCESS")
            ctx.page.open(
                ft.AlertDialog(
                    title=ft.Text("Chart PDF exported", color=Colors.WHITE),
                    content=ft.Container(
                        content=ft.Text(help_body, selectable=True, size=12, color=TEXT_MUTED),
                        width=520,
                    ),
                    bgcolor=GLASS_BG,
                )
            )
        except Exception as ex:
            await ctx.add_to_console(f"Chart PDF export failed: {ex}", "ERROR")
        ctx.page.update()

    async def on_chart_metric_change(metric_col: str):
        ctx.page.session.set("results_chart_metric", metric_col)
        ctx.page.go("/results", rt=uuid.uuid4().hex[:12])

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

    def _summary_subtype_cell(r: dict) -> str:
        if is_vd_result_row(r):
            return "—"
        if "error" in r:
            return "Error"
        pm = metrics_from_session_result_row(r)
        return str(r.get("mnv_subtype") or pm.get("mnv_subtype") or "—")

    def _summary_maturity_index_cell(r: dict) -> str:
        if is_vd_result_row(r):
            return "—"
        if "error" in r:
            return "—"
        pm = metrics_from_session_result_row(r)
        val = r.get("maturity_index")
        if val is None:
            val = pm.get("maturity_index")
        if val is None:
            return "—"
        try:
            return str(safe_round(float(val), 2))
        except (TypeError, ValueError):
            return str(val)

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

        imagej_rows = imagej_rows_from_batch(batch_results)
        has_mnv_table = len(imagej_rows) > 0

        table_block = ft.Container()
        if has_mnv_table:
            table_block = ft.Column(
                [
                    ft.Text("Results Table (CSV columns)", size=20, weight=FontWeight.BOLD, color=PRIMARY),
                    ft.Text(
                        "Subtype / Pathophysiology and key metrics aligned with exported CSV.",
                        size=12,
                        color=TEXT_MUTED,
                    ),
                    ft.Container(
                        content=ft.DataTable(
                            columns=[
                                ft.DataColumn(ft.Text(col, size=11, weight=FontWeight.W_600))
                                for col in SUMMARY_TABLE_COLUMNS
                            ],
                            rows=[
                                ft.DataRow(
                                    cells=[
                                        ft.DataCell(
                                            ft.Text(
                                                str(row.get(col, ""))[:48],
                                                size=11,
                                                tooltip=str(row.get(col, "")),
                                            ),
                                            on_tap=_open_summary_row_detail(idx)
                                            if col == "File"
                                            else None,
                                        )
                                        for col in SUMMARY_TABLE_COLUMNS
                                    ],
                                )
                                for idx, row in enumerate(imagej_rows)
                            ],
                            bgcolor=Colors.with_opacity(0.02, Colors.WHITE),
                            border_radius=12,
                            column_spacing=18,
                            heading_row_height=44,
                            data_row_min_height=40,
                        ),
                        padding=8,
                        border=ft.border.all(1, Colors.with_opacity(0.08, Colors.WHITE)),
                        border_radius=12,
                    ),
                ],
                spacing=8,
            )

        chart_block = ft.Container()
        if has_mnv_table and nm >= 1:
            metric_options = chartable_numeric_columns()
            default_metric = ctx.page.session.get("results_chart_metric")
            if default_metric not in metric_options:
                default_metric = metric_options[0] if metric_options else "Maturity Index"
            chart_points, values = series_for_metric(imagej_rows, default_metric)
            y_min, y_max = smart_y_bounds(values) if values else (0.0, 1.0)
            chart_height = 380
            bar_groups = [
                ft.BarChartGroup(
                    x=i,
                    bar_rods=[
                        ft.BarChartRod(
                            from_y=y_min,
                            to_y=val,
                            width=16,
                            color=PRIMARY,
                            border_radius=4,
                        )
                    ],
                )
                for i, val in enumerate(values)
            ]
            bottom_labels = [
                ft.ChartAxisLabel(
                    value=i,
                    label=ft.Column(
                        [
                            ft.Text(
                                pt["file"],
                                size=9,
                                text_align=ft.TextAlign.CENTER,
                            ),
                            ft.Text(
                                pt["subtype"],
                                size=8,
                                color=TEXT_MUTED,
                                text_align=ft.TextAlign.CENTER,
                            ),
                            ft.Text(
                                pt["pathophysiology"],
                                size=8,
                                color=TEXT_MUTED,
                                text_align=ft.TextAlign.CENTER,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=0,
                        tight=True,
                    ),
                )
                for i, pt in enumerate(chart_points)
            ]
            chart_block = ft.Column(
                [
                    ft.Text("Batch Chart", size=20, weight=FontWeight.BOLD, color=PRIMARY),
                    ft.Row(
                        [
                            ft.Dropdown(
                                label="Y-axis metric",
                                value=default_metric,
                                width=360,
                                options=[
                                    ft.dropdown.Option(m) for m in metric_options[:40]
                                ],
                                border_color=PRIMARY,
                                on_change=lambda e: ctx.page.run_task(
                                    on_chart_metric_change, e.control.value
                                ),
                            ),
                            ft.ElevatedButton(
                                "Export PDF",
                                icon=Icons.PICTURE_AS_PDF_ROUNDED,
                                bgcolor=PRIMARY,
                                color=Colors.BLACK,
                                on_click=lambda _, m=default_metric: ctx.page.run_task(
                                    on_export_chart_pdf, m
                                ),
                            ),
                        ],
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.END,
                    ),
                    ft.Container(
                        content=ft.BarChart(
                            bar_groups=bar_groups,
                            border=ft.border.all(1, Colors.with_opacity(0.12, Colors.WHITE)),
                            left_axis=ft.ChartAxis(
                                labels_size=40,
                                title=ft.Text(default_metric, size=11),
                                title_size=12,
                            ),
                            bottom_axis=ft.ChartAxis(labels=bottom_labels, labels_size=72),
                            min_y=y_min,
                            max_y=y_max,
                            interactive=True,
                            expand=True,
                        ),
                        height=chart_height,
                        padding=12,
                        bgcolor=Colors.with_opacity(0.03, Colors.WHITE),
                        border_radius=12,
                    ),
                ],
                spacing=10,
            )

        reorder_hint = ft.Container()
        if len(batch_results) > 1 and not awaiting_mnv_batch_qc:
            reorder_hint = ft.Text(
                "Sidebar: drag handles to reorder results (CSV export follows this order).",
                size=11,
                color=TEXT_MUTED,
            )

        return ft.ListView(
            controls=[
                ft.Row([
                    ft.Text("Batch Analytics Summary", size=32, weight=FontWeight.BOLD),
                    ft.Container(expand=True),
                    ft.ElevatedButton(
                        "Save CSV",
                        icon=Icons.FILE_DOWNLOAD_ROUNDED,
                        bgcolor=PRIMARY,
                        color=Colors.BLACK,
                        on_click=lambda _: ctx.page.run_task(on_export_batch_csv),
                    ),
                    ft.ElevatedButton(
                        "Export Metadata & Data",
                        icon=Icons.FOLDER_SPECIAL_ROUNDED,
                        bgcolor=Colors.with_opacity(0.2, PRIMARY),
                        color=PRIMARY,
                        tooltip="export/{institution_id}/{lesion_id}/ → image_raw, mask_roi, meta.json",
                        on_click=lambda _: ctx.page.run_task(on_export_metadata_data),
                    ),
                ], spacing=8),
                ft.Text(f"Overview of {total} processed images", color=TEXT_MUTED),
                reorder_hint,
                ft.Divider(height=24, color=Colors.TRANSPARENT),
                ft.Row([
                    metric_tile("Total Files", total, "items", Icons.FOLDER_ZIP_OUTLINED, Colors.BLUE_400),
                    metric_tile("Success Rate", int(success_count / total * 100) if total > 0 else 0, "%", Icons.CHECK_CIRCLE_OUTLINED, Colors.GREEN_400),
                    metric_tile("Mean Area", avg_area, "mm²", Icons.AREA_CHART_OUTLINED, Colors.CYAN_400),
                    metric_tile("Mean Density", avg_vd, "%", Icons.GRAIN_ROUNDED, Colors.AMBER_400),
                ], spacing=15),
                ft.Divider(height=32, color=Colors.with_opacity(0.1, Colors.WHITE)),
                chart_block,
                ft.Divider(height=24, color=Colors.TRANSPARENT) if has_mnv_table else ft.Container(height=0),
                table_block,
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
                    ft.Row(
                        [
                            ft.ElevatedButton(
                                "Save CSV",
                                icon=Icons.FILE_DOWNLOAD_ROUNDED,
                                bgcolor=PRIMARY,
                                color=Colors.BLACK,
                                on_click=lambda _: ctx.page.run_task(on_export_batch_csv),
                            ),
                            ft.ElevatedButton(
                                "Export Metadata & Data",
                                icon=Icons.FOLDER_SPECIAL_ROUNDED,
                                bgcolor=Colors.with_opacity(0.2, PRIMARY),
                                color=PRIMARY,
                                tooltip="export/{institution_id}/{lesion_id}/ → image_raw, mask_roi, meta.json",
                                on_click=lambda _: ctx.page.run_task(on_export_metadata_data),
                            ),
                            ft.ElevatedButton(
                                "Save PDF Report",
                                icon=Icons.PICTURE_AS_PDF_ROUNDED,
                                bgcolor=PRIMARY,
                                color=Colors.BLACK,
                                on_click=lambda _, r=res: ctx.page.run_task(
                                    on_save_individual_pdf, r
                                ),
                            ),
                        ],
                        spacing=8,
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
                        "Export Metadata & Data",
                        icon=Icons.FOLDER_SPECIAL_ROUNDED,
                        bgcolor=Colors.with_opacity(0.2, PRIMARY),
                        color=PRIMARY,
                        tooltip="export/{institution_id}/{lesion_id}/ → image_raw, mask_roi, meta.json",
                        on_click=lambda _: ctx.page.run_task(on_export_metadata_data),
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
                            "Caliber Uniformity",
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
        if is_vd_result_row(res):
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

    if len(batch_results) > 1 and not awaiting_mnv_batch_qc:
        reorder_tiles = []
        for idx, r in enumerate(batch_results):
            reorder_tiles.append(
                ft.ListTile(
                    key=str(idx),
                    leading=ft.Icon(
                        Icons.CHECK_CIRCLE if "error" not in r else Icons.ERROR,
                        color=Colors.GREEN_400 if "error" not in r else Colors.RED_400,
                        size=18,
                    ),
                    title=ft.Text(
                        r.get("source_filename", f"Item {idx+1}")[:28] + "...",
                        size=13,
                        color=Colors.WHITE if selected_index == idx else TEXT_MUTED,
                    ),
                    selected=selected_index == idx,
                    on_click=lambda _, i=idx: ctx.page.run_task(select_result, i),
                    hover_color=Colors.with_opacity(0.1, PRIMARY),
                )
            )
        sidebar_items.append(
            ft.ReorderableListView(
                controls=reorder_tiles,
                on_reorder=lambda e: ctx.page.run_task(on_batch_reorder, e),
                show_default_drag_handles=True,
                expand=True,
            )
        )
    else:
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
