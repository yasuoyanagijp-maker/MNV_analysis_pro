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
from src.flet_ui.components.shared import (
    PRIMARY,
    BG_DARK,
    TEXT_MUTED,
    GLASS_BG,
    AppContext,
    safe_round,
    session_discard,
    logout_to_login,
    viewport_fit_side,
)
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
from src.utils.metadata_export import (
    export_batch_metadata_bundles,
    export_batch_pdf_reports,
)
from src.utils.grdm_access import (
    resolve_export_institution_id,
)
from src.utils.mnv_absent import is_mnv_absent_result
from src.utils.second_reader import (
    SR_FIRST_GRADER_CSV_KEY,
    SR_SCAN_ROOT_KEY,
    SR_CSV_PATH_KEY,
    find_first_grader_mnv_csvs,
    format_scale_dropdown_value,
    integrated_output_dir,
    is_second_reader,
)
from src.utils.dual_grader_merge import RPD_THRESHOLD_PCT, merge_dual_grader_csvs
from src.utils.mnv_results_chart import (
    CHART_METRIC_DEFAULT_REMAP,
    CHART_PNG_HEIGHT_PX,
    CHART_PNG_WIDTH_PX,
    SUMMARY_TABLE_COLUMNS,
    build_batch_metric_chart_pdf,
    build_batch_metric_chart_png_base64,
    chartable_numeric_columns,
    imagej_rows_from_batch,
    series_for_metric,
    smart_y_bounds,
)
from src.utils.grdm_sync_ui import make_grdm_sync_button


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

    # 第2リーダー: Save CSV (export) 後にのみ統合解析データボタンを表示する
    is_sr_session = is_second_reader(ctx.page.session)
    _sr_csv_saved = ctx.page.session.get(SR_CSV_PATH_KEY)
    _sr_csv_ready = bool(
        is_sr_session and _sr_csv_saved and Path(str(_sr_csv_saved)).is_file()
    )

    # ログアウトは結果画面・サイドバーからいつでも可能（第1→第2交代動線）。
    EXPORT_LOGOUT_READY_KEY = "export_logout_ready"

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

    grdm_sync_btn = make_grdm_sync_button(ctx.page, get_target_output_dir)

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

            # 第2リーダー: エキスポート実行時のみ統合解析データボタンを有効化
            if is_sr_session:
                sr_mnv_path = next((p for k, p in written if k == "MNV"), None)
                if sr_mnv_path is not None:
                    ctx.page.session.set(SR_CSV_PATH_KEY, str(sr_mnv_path))
                    integrated_data_btn.visible = True
                    await ctx.add_to_console(
                        "第2リーダーCSVを保存しました。「統合解析データ」ボタンが利用できます。",
                        "INFO",
                    )

            # エキスポート完了 → ログアウトして読影者を交代できる
            if written:
                ctx.page.session.set(EXPORT_LOGOUT_READY_KEY, True)
                logout_btn.visible = True
                logout_btn_detail.visible = True

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
        """Export MedSAM bundles + individual PDFs under export/ (off UI thread)."""
        try:
            if not batch_results:
                await ctx.add_to_console("Export Metadata: no results in this batch.", "WARN")
                ctx.page.update()
                return

            target_dir = get_target_output_dir()
            # Second-reader / Team YY: prefer the facility being graded
            institution = resolve_export_institution_id(
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
                f"Export Metadata & Data (+ PDFs)… institution={institution}",
                "INFO",
            )
            ctx.page.update()

            def _run_export():
                meta_summary = export_batch_metadata_bundles(
                    rows,
                    institution_id=institution,
                    rater_id=rater,
                    output_dir=target_dir,
                    source_path_hint=str(source_hint) if source_hint else None,
                    session_mask_b64=mask_b64,
                    scale_mm_hint=scale_hint,
                    device_hint=str(device_hint) if device_hint else None,
                )
                pdf_summary = export_batch_pdf_reports(
                    rows,
                    institution_id=institution,
                    output_dir=target_dir,
                )
                return meta_summary, pdf_summary

            loop = asyncio.get_running_loop()
            summary, pdf_summary = await loop.run_in_executor(None, _run_export)

            n_ok = len(summary.get("exported") or [])
            n_skip = len(summary.get("skipped") or [])
            n_err = len(summary.get("errors") or [])
            n_pdf = int(pdf_summary.get("exported_count") or 0)
            n_pdf_err = int(pdf_summary.get("error_count") or 0)
            root = summary.get("export_root") or str(target_dir / "export")
            pdf_root = pdf_summary.get("pdf_root") or str(Path(root) / "pdfs" / institution)

            lines = [
                f"Wrote {n_ok} MedSAM bundle(s) under:",
                str(root),
                "",
                f"Wrote {n_pdf} PDF report(s) under:",
                str(pdf_root),
                "",
                "MedSAM: export/images|masks|meta/{institution}/{lesion} + manifest.csv",
                "PDFs:   export/pdfs/{institution}/{lesion}.pdf",
                f"task=octa_mnv_roi; rater_id=login; institution_id={summary.get('institution_id')}",
            ]
            if n_skip:
                lines.append("")
                lines.append(f"Skipped metadata ({n_skip}):")
                for s in (summary.get("skipped") or [])[:8]:
                    lines.append(
                        f"  • {s.get('source_filename') or s.get('source')}: {s.get('reason')}"
                    )
                if n_skip > 8:
                    lines.append(f"  … and {n_skip - 8} more")
            if n_err or n_pdf_err:
                lines.append("")
                lines.append(f"Errors (metadata {n_err}, PDF {n_pdf_err}):")
                for s in (summary.get("errors") or [])[:4]:
                    lines.append(
                        f"  • meta {s.get('source_filename') or s.get('source')}: {s.get('reason')}"
                    )
                for s in (pdf_summary.get("errors") or [])[:4]:
                    lines.append(
                        f"  • pdf {s.get('source_filename') or s.get('source')}: {s.get('reason')}"
                    )

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

            level = (
                "SUCCESS"
                if (n_ok or n_pdf) and not n_err and not n_pdf_err
                else ("WARN" if (n_ok or n_pdf) else "ERROR")
            )
            await ctx.add_to_console(
                f"Export: meta {n_ok} ok / {n_skip} skip / {n_err} err; "
                f"PDF {n_pdf} ok / {n_pdf_err} err → {root}",
                level,
            )
        except Exception as ex:
            await ctx.add_to_console(f"Metadata Export Error: {ex}", "ERROR")
        ctx.page.update()

    def _find_first_grader_csv():
        """Auto-locate the first grader's MNV CSV (session hint → scan search)."""
        hint = ctx.page.session.get(SR_FIRST_GRADER_CSV_KEY)
        if hint and Path(str(hint)).is_file():
            return Path(str(hint))
        scan_root = ctx.page.session.get(SR_SCAN_ROOT_KEY)
        second_csv = ctx.page.session.get(SR_CSV_PATH_KEY)
        exclude = [Path(str(second_csv))] if second_csv else []
        if scan_root and Path(str(scan_root)).is_dir():
            candidates = find_first_grader_mnv_csvs(
                Path(str(scan_root)), exclude_paths=exclude
            )
            if candidates:
                return candidates[0]
        return None

    async def on_create_integrated_data(_=None):
        """統合解析データ: 第1グレーダーCSVを自動検索し、RPD≤20% ルールで統合CSVを作成。"""
        try:
            second_csv = ctx.page.session.get(SR_CSV_PATH_KEY)
            if not second_csv or not Path(str(second_csv)).is_file():
                await ctx.add_to_console(
                    "統合解析データ: 先にエキスポート（Save CSV）で第2リーダーCSVを保存してください。",
                    "ERROR",
                )
                ctx.page.update()
                return
            second_csv = Path(str(second_csv))

            first_csv = _find_first_grader_csv()
            if first_csv is None:
                ctx.page.open(
                    ft.AlertDialog(
                        title=ft.Text("統合解析データ", color=Colors.WHITE),
                        content=ft.Container(
                            content=ft.Text(
                                "第1グレーダーのCSVファイルが見つかりませんでした。\n"
                                "第1グレーダーの出力フォルダ（MNV_*.csv がある場所）を"
                                "スキャン対象として選択したか確認してください。",
                                size=12,
                                color=TEXT_MUTED,
                            ),
                            width=520,
                        ),
                        bgcolor=GLASS_BG,
                    )
                )
                await ctx.add_to_console(
                    "統合解析データ: 第1グレーダーCSVが見つかりません。", "ERROR"
                )
                ctx.page.update()
                return

            grader1 = "Grader1"
            reader2 = (ctx.page.session.get("username") or "").strip() or "Reader2"
            # 統合結果は第1・第2の結果フォルダと同階層の integrated_output_* に出力
            graded_inst = (ctx.page.session.get("grdm_graded_institution_id") or "").strip() or None
            scan_root = ctx.page.session.get(SR_SCAN_ROOT_KEY)
            if scan_root and Path(str(scan_root)).is_dir():
                out_dir = integrated_output_dir(Path(str(scan_root)), graded_inst)
            else:
                # scan root 不明時は第1グレーダーCSVの場所から同階層を導出
                out_dir = integrated_output_dir(first_csv.parent, graded_inst)

            await ctx.add_to_console(
                f"統合解析データ: {first_csv.name} × {second_csv.name} "
                f"(RPD≤{RPD_THRESHOLD_PCT:g}%) …",
                "INFO",
            )
            ctx.page.update()

            loop = asyncio.get_running_loop()
            summary = await loop.run_in_executor(
                None,
                lambda: merge_dual_grader_csvs(
                    first_csv,
                    second_csv,
                    out_dir,
                    rpd_threshold=RPD_THRESHOLD_PCT,
                    first_label=grader1,
                    second_label=reader2,
                ),
            )

            lines = [
                f"第1グレーダー: {first_csv}",
                f"第2リーダー:   {second_csv}",
                "",
                f"突合成功: {summary['n_matched']} 行"
                f"（第1のみ {summary['n_first_only']} / 第2のみ {summary['n_second_only']}）",
                f"採用ルール: RPD ≤ {summary['threshold_pct']:g}% → 平均値、超過 → NA（再計測）",
                f"RECHECK: 主要指標 {summary['recheck_cells']} セル / "
                f"{summary['recheck_files']} ファイル",
                "",
                "出力ファイル:",
                f"  {summary['adopted_csv']}",
                f"  {summary['recheck_csv']}",
                f"  {summary['summary_md']}",
            ]
            for w in summary.get("warnings") or []:
                lines.append(f"⚠ {w}")

            ctx.page.open(
                ft.AlertDialog(
                    title=ft.Text("統合解析データを作成しました", color=Colors.WHITE),
                    content=ft.Container(
                        content=ft.Text(
                            "\n".join(lines), selectable=True, size=12, color=TEXT_MUTED
                        ),
                        width=620,
                    ),
                    bgcolor=GLASS_BG,
                )
            )
            await ctx.add_to_console(
                f"統合解析データ完成: {Path(summary['adopted_csv']).name} "
                f"(matched={summary['n_matched']}, recheck={summary['recheck_cells']})",
                "SUCCESS",
            )
        except ValueError as ex:
            await ctx.add_to_console(f"統合解析データ エラー: {ex}", "ERROR")
        except Exception as ex:
            await ctx.add_to_console(f"統合解析データ 失敗: {ex}", "ERROR")
        ctx.page.update()

    integrated_data_btn = ft.ElevatedButton(
        "統合解析データ",
        icon=Icons.MERGE_ROUNDED,
        bgcolor=Colors.AMBER_400,
        color=Colors.BLACK,
        tooltip=(
            "第1グレーダーCSVを自動検索し、第2リーダーCSVと統合します"
            f"（RPD≤{RPD_THRESHOLD_PCT:g}%: 平均値を採用 / 超過: NA=再計測）。"
        ),
        visible=_sr_csv_ready,
        on_click=lambda _: ctx.page.run_task(on_create_integrated_data),
    )

    async def on_logout(_=None):
        """Discard auth/analysis session and return to /login (does not block on client_storage)."""
        await logout_to_login(ctx.page)

    def _make_logout_btn():
        return ft.ElevatedButton(
            "ログアウト",
            icon=Icons.LOGOUT_ROUNDED,
            bgcolor=Colors.with_opacity(0.2, Colors.RED_400),
            color=Colors.RED_300,
            tooltip=(
                "セッションを破棄してログイン画面に戻ります。"
                "続けて第2リーダーが Role を選んで二重読影を開始できます。"
            ),
            visible=True,
            on_click=lambda _: ctx.page.run_task(on_logout),
        )

    logout_btn = _make_logout_btn()          # summary view row
    logout_btn_detail = _make_logout_btn()   # MNV detail view row

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
            scales = ctx.page.session.get("mnv_batch_scales") or {}
            next_fov = scales.get(paths[next_i])
            if next_fov is None:
                name_map = ctx.page.session.get("mnv_batch_scale_names") or {}
                stem_map = ctx.page.session.get("mnv_batch_scale_stems") or {}
                next_path = Path(paths[next_i])
                next_fov = name_map.get(next_path.name) or stem_map.get(next_path.stem)
            if next_fov is None:
                # Unmatched meta → majority/default FOV, never inherit prior image.
                next_fov = ctx.page.session.get("mnv_batch_default_fov")
            if next_fov is not None:
                ctx.page.session.set("scale", float(next_fov))
                scale_txt = format_scale_dropdown_value(float(next_fov))
                try:
                    if ctx.scale_mm_ref and ctx.scale_mm_ref.current is not None:
                        ctx.scale_mm_ref.current.value = scale_txt
                except Exception:
                    pass
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
            session_discard(ctx.page.session, "mnv_batch_scales")
            session_discard(ctx.page.session, "mnv_batch_scale_stems")
            session_discard(ctx.page.session, "mnv_batch_scale_names")
            session_discard(ctx.page.session, "mnv_batch_default_fov")
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
        session_discard(ctx.page.session, "mnv_batch_scales")
        session_discard(ctx.page.session, "mnv_batch_scale_stems")
        session_discard(ctx.page.session, "mnv_batch_scale_names")
        session_discard(ctx.page.session, "mnv_batch_default_fov")
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

    def make_summary_nav_btn():
        return ft.OutlinedButton(
            "Summary",
            icon=Icons.DASHBOARD_ROUNDED,
            style=ft.ButtonStyle(color=PRIMARY),
            tooltip="Back to Global Summary",
            on_click=lambda _: ctx.page.run_task(select_result, -1),
        )

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
        # Exclude MNV-absent skips from mean morphometrics (empty/zero would bias averages).
        mnv_metric_rows = [r for r in mnv_rows if not is_mnv_absent_result(r)]
        nm = len(mnv_metric_rows)
        avg_area = safe_round(
            sum(r.get("mnv_area_mm2", 0) or 0 for r in mnv_metric_rows) / nm if nm > 0 else 0,
            3,
        )
        avg_vd = safe_round(
            sum((r.get("vessel_density", 0) or 0) for r in mnv_metric_rows) / nm * 100
            if nm > 0
            else 0,
            2,
        )

        imagej_rows = imagej_rows_from_batch(batch_results)
        has_mnv_table = len(imagej_rows) > 0

        # Build summary body as an explicit list — never insert empty expand
        # Containers / BarChart / Image(src="") (Flet 0.28 fl_chart paints a
        # solid light-grey canvas that covers tiles + table on Global Summary).
        summary_controls: list = [
            ft.Row(
                [
                    ft.Text("Batch Analytics Summary", size=32, weight=FontWeight.BOLD),
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
                        tooltip="MedSAM images/masks/meta + bulk PDFs under export/pdfs/{institution_id}/",
                        on_click=lambda _: ctx.page.run_task(on_export_metadata_data),
                    ),
                    grdm_sync_btn,
                    integrated_data_btn,
                    logout_btn,
                ],
                spacing=8,
                wrap=True,
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            ft.Text(f"Overview of {total} processed images", color=TEXT_MUTED),
        ]
        if len(batch_results) > 1 and not awaiting_mnv_batch_qc:
            summary_controls.append(
                ft.Text(
                    "Sidebar: drag handles to reorder results (CSV export follows this order).",
                    size=11,
                    color=TEXT_MUTED,
                )
            )
        summary_controls.extend(
            [
                ft.Divider(height=24, color=Colors.TRANSPARENT),
                ft.Row(
                    [
                        metric_tile(
                            "Total Files",
                            total,
                            "items",
                            Icons.FOLDER_ZIP_OUTLINED,
                            Colors.BLUE_400,
                        ),
                        metric_tile(
                            "Success Rate",
                            int(success_count / total * 100) if total > 0 else 0,
                            "%",
                            Icons.CHECK_CIRCLE_OUTLINED,
                            Colors.GREEN_400,
                        ),
                        metric_tile(
                            "Mean Area",
                            avg_area,
                            "mm²",
                            Icons.AREA_CHART_OUTLINED,
                            Colors.CYAN_400,
                        ),
                        metric_tile(
                            "Mean Density",
                            avg_vd,
                            "%",
                            Icons.GRAIN_ROUNDED,
                            Colors.AMBER_400,
                        ),
                    ],
                    spacing=15,
                ),
                ft.Divider(height=32, color=Colors.with_opacity(0.1, Colors.WHITE)),
            ]
        )

        # On-screen chart: dark-theme matplotlib PNG via ft.Image(src_base64=...).
        # Do NOT mount ft.BarChart / fl_chart — Flet 0.28 paints a full-pane
        # light-grey canvas that covers tiles + table (web + native). Never
        # Image(src="") either (empty src also greys the pane).
        if has_mnv_table and nm >= 1:
            metric_options = chartable_numeric_columns()
            default_metric = ctx.page.session.get("results_chart_metric")
            if default_metric in CHART_METRIC_DEFAULT_REMAP:
                default_metric = CHART_METRIC_DEFAULT_REMAP[default_metric]
            if default_metric not in metric_options:
                default_metric = (
                    metric_options[0]
                    if metric_options
                    else "Maturity Index (U2)"
                )
            ctx.page.session.set("results_chart_metric", default_metric)

            # Match PNG pixel aspect (CHART_PNG_*) so CONTAIN never crops title/labels.
            page_w = getattr(ctx.page, "width", None)
            try:
                chart_w = max(560, min(1000, int(float(page_w)) - 80)) if page_w else 820
            except (TypeError, ValueError):
                chart_w = 820
            chart_h = max(
                420,
                int(round(chart_w * CHART_PNG_HEIGHT_PX / float(CHART_PNG_WIDTH_PX))),
            )

            def _container_bar_fallback(metric_col: str) -> ft.Control:
                pts, vals = series_for_metric(imagej_rows, metric_col)
                if not vals:
                    return ft.Text("No numeric data for this metric.", color=TEXT_MUTED, size=12)
                y_lo, y_hi = smart_y_bounds(vals)
                span = max(y_hi - y_lo, 1e-9)
                plot_h = chart_h - 56
                bars: list = []
                for p, v in zip(pts, vals):
                    bar_h = max(4, int((float(v) - y_lo) / span * plot_h))
                    bars.append(
                        ft.Column(
                            [
                                ft.Container(height=max(0, plot_h - bar_h)),
                                ft.Container(
                                    width=18,
                                    height=bar_h,
                                    bgcolor="#00E5FF",
                                    border_radius=3,
                                    border=ft.border.all(1, "#00B8D4"),
                                ),
                                ft.Text(
                                    p.get("file") or "—",
                                    size=10,
                                    color=TEXT_MUTED,
                                    width=72,
                                    max_lines=2,
                                    text_align=ft.TextAlign.CENTER,
                                ),
                            ],
                            spacing=2,
                            tight=True,
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        )
                    )
                return ft.Container(
                    content=ft.Row(
                        bars,
                        spacing=14,
                        scroll=ft.ScrollMode.AUTO,
                        vertical_alignment=ft.CrossAxisAlignment.END,
                    ),
                    height=chart_h,
                    width=chart_w,
                    bgcolor=BG_DARK,
                    border_radius=8,
                    padding=ft.padding.only(left=8, right=8, top=8, bottom=4),
                )

            chart_body: ft.Control
            try:
                chart_b64 = build_batch_metric_chart_png_base64(
                    batch_results, default_metric, theme="dark"
                )
                # Omit src entirely — empty src="" caused grey canvas.
                # No HARD_EDGE clip: mismatched aspect previously cropped the PNG title.
                chart_body = ft.Container(
                    content=ft.Image(
                        src_base64=chart_b64,
                        width=chart_w,
                        height=chart_h,
                        fit=ft.ImageFit.CONTAIN,
                    ),
                    width=chart_w,
                    height=chart_h,
                    bgcolor=BG_DARK,
                    border_radius=8,
                    clip_behavior=ft.ClipBehavior.NONE,
                )
            except Exception as chart_ex:
                print(f"SUMMARY CHART PNG fallback: {chart_ex}", flush=True)
                chart_body = _container_bar_fallback(default_metric)

            summary_controls.append(
                ft.Column(
                    [
                        ft.Text(
                            "Batch Chart",
                            size=20,
                            weight=FontWeight.BOLD,
                            color=PRIMARY,
                        ),
                        ft.Row(
                            [
                                ft.Dropdown(
                                    label="Y-axis metric",
                                    value=default_metric,
                                    width=380,
                                    options=[
                                        ft.dropdown.Option(m)
                                        for m in metric_options[:40]
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
                        chart_body,
                    ],
                    spacing=10,
                    tight=True,
                )
            )

        if has_mnv_table:
            summary_controls.extend(
                [
                    ft.Divider(height=24, color=Colors.TRANSPARENT),
                    ft.Column(
                        [
                            ft.Text(
                                "Results Table (CSV columns)",
                                size=20,
                                weight=FontWeight.BOLD,
                                color=PRIMARY,
                            ),
                            ft.Text(
                                "Subtype / Pathophysiology and key metrics aligned with exported CSV.",
                                size=12,
                                color=TEXT_MUTED,
                            ),
                            ft.Container(
                                content=ft.DataTable(
                                    columns=[
                                        ft.DataColumn(
                                            ft.Text(col, size=11, weight=FontWeight.W_600)
                                        )
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
                                border=ft.border.all(
                                    1, Colors.with_opacity(0.08, Colors.WHITE)
                                ),
                                border_radius=12,
                            ),
                        ],
                        spacing=8,
                        tight=True,
                    ),
                ]
            )

        return ft.Column(
            controls=summary_controls,
            expand=True,
            spacing=10,
            scroll=ft.ScrollMode.AUTO,
            tight=False,
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
        # Sidebar is hidden on individual detail — show source filename here.
        _vd_src = str(res.get("source_filename") or f"Item {idx + 1}")
        ctrls = [
            ft.Row(
                [
                    ft.Column(
                        [
                            ft.Text(
                                _vd_src,
                                color=Colors.WHITE,
                                size=18,
                                weight=ft.FontWeight.W_600,
                                max_lines=2,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                            ft.Text(
                                f"Analysis type: VD | Timestamp: {res.get('analysis_timestamp', 'N/A')} — "
                                + _vd_detail_blurb,
                                color=TEXT_MUTED,
                                size=12,
                            ),
                        ],
                        expand=True,
                        spacing=4,
                    ),
                    ft.Row(
                        [
                            make_summary_nav_btn(),
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
                                tooltip="MedSAM images/masks/meta + bulk PDFs under export/pdfs/{institution_id}/",
                                on_click=lambda _: ctx.page.run_task(on_export_metadata_data),
                            ),
                            make_grdm_sync_button(ctx.page, get_target_output_dir),
                            ft.ElevatedButton(
                                "Save PDF Report",
                                icon=Icons.PICTURE_AS_PDF_ROUNDED,
                                bgcolor=PRIMARY,
                                color=Colors.BLACK,
                                on_click=lambda _, r=res: ctx.page.run_task(
                                    on_save_individual_pdf, r
                                ),
                            ),
                            logout_btn_detail,
                        ],
                        spacing=8,
                        wrap=True,
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.START,
                spacing=12,
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
            vd_side = viewport_fit_side(
                ctx.page,
                reserved_w=160 if vsl_only else 240,
                reserved_h=360,
                min_side=240,
                max_side=720 if vsl_only else 480,
            )
            if vsl_only:
                overlay_title = "Overlay (superficial / Vsl Density)"
                overlay_body = ft.Column(
                    [
                        ft.Text("Superficial", color=TEXT_MUTED, size=12),
                        (
                            ft.Image(
                                src_base64=sup_vis,
                                fit=ft.ImageFit.CONTAIN,
                                width=vd_side,
                                height=vd_side,
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
                                        src_base64=sup_vis,
                                        fit=ft.ImageFit.CONTAIN,
                                        width=vd_side,
                                        height=vd_side,
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
                                        src_base64=deep_vis,
                                        fit=ft.ImageFit.CONTAIN,
                                        width=vd_side,
                                        height=vd_side,
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

        # Sidebar is hidden on individual detail — show source filename here.
        vis_side = viewport_fit_side(
            ctx.page,
            reserved_w=120,
            reserved_h=380,
            min_side=280,
            max_side=820,
        )
        _mnv_src = str(res.get("source_filename") or f"Item {idx + 1}")
        ctrls = [
            ft.Row(
                [
                    ft.Column(
                        [
                            ft.Text(
                                _mnv_src,
                                color=Colors.WHITE,
                                size=18,
                                weight=ft.FontWeight.W_600,
                                max_lines=2,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                            ft.Text(
                                f"Analysis type: MNV | Timestamp: {res.get('analysis_timestamp', 'N/A')}",
                                color=TEXT_MUTED,
                                size=12,
                            ),
                        ],
                        expand=True,
                        spacing=4,
                    ),
                    ft.Row(
                        [
                            make_summary_nav_btn(),
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
                                tooltip="MedSAM images/masks/meta + bulk PDFs under export/pdfs/{institution_id}/",
                                on_click=lambda _: ctx.page.run_task(on_export_metadata_data),
                            ),
                            make_grdm_sync_button(ctx.page, get_target_output_dir),
                            ft.ElevatedButton(
                                "ROI再指定・再解析",
                                icon=Icons.CROP_FREE,
                                bgcolor=Colors.AMBER_400,
                                color=Colors.BLACK,
                                tooltip="ROI（抽出領域）を選択し直して、この画像の解析をやり直します",
                                on_click=lambda _: ctx.page.run_task(on_reanalyze_mnv, idx),
                            ),
                            integrated_data_btn,
                            logout_btn_detail,
                        ],
                        spacing=8,
                        wrap=True,
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.START,
                spacing=12,
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

        if is_mnv_absent_result(res):
            ctrls.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Icon(Icons.REMOVE_CIRCLE_OUTLINE, color=Colors.WHITE),
                                    ft.Text(
                                        "MNV absent (skipped)",
                                        color=Colors.WHITE,
                                        weight=FontWeight.BOLD,
                                    ),
                                ],
                                spacing=8,
                            ),
                            ft.Text(
                                "No morphometrics. Empty (all-black) mask + mnv_present=false "
                                "are stored for AI training. Quality of analysis = N/A "
                                "(not Fail). CSV column «MNV present» = 0.",
                                color=TEXT_MUTED,
                                size=12,
                            ),
                        ],
                        spacing=4,
                    ),
                    bgcolor=Colors.with_opacity(0.35, Colors.BLUE_GREY_700),
                    padding=12,
                    border_radius=10,
                    margin=ft.margin.only(top=10),
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
                                width=vis_side,
                                height=vis_side,
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
    _cur = batch_results[selected_index] if (
        awaiting_mnv_batch_qc and batch_results and 0 <= selected_index < len(batch_results)
    ) else (batch_results[0] if batch_results else None)
    if awaiting_mnv_batch_qc and is_mnv_absent_result(_cur):
        qc_help_text = (
            "MNV absent を記録しました（空マスク）。OK で陰性サンプルを確定し、最終サマリーへ進みます。"
            if is_final_mnv_image
            else "MNV absent を記録しました（空マスク）。OK で陰性サンプルを残して次の画像へ進みます。"
        )
    else:
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

    # Sidebar with filenames is the picker on Global Summary only.
    # Individual MNV detail hides the 280px column (header shows source_filename;
    # Summary button returns to Global Summary). VD-only batches have no summary
    # index (-1), so keep the sidebar as the only way to open sibling files.
    hide_result_sidebar = (
        isinstance(selected_index, int)
        and selected_index >= 0
        and not vd_only_batch
    )
    print(
        f"RESULTS LAYOUT: selected_index={selected_index} "
        f"hide_result_sidebar={hide_result_sidebar}",
        flush=True,
    )

    main_pane = ft.Container(
        content=main_body,
        expand=True,
        padding=40,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
    )

    if hide_result_sidebar:
        return ft.Row(
            [main_pane],
            expand=True,
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.STRETCH,
        )

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
            main_pane,
        ],
        expand=True,
        spacing=0,
        vertical_alignment=ft.CrossAxisAlignment.STRETCH,
    )
