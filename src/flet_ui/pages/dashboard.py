import flet as ft
from flet import Colors, Icons, FontWeight
import time
from pathlib import Path
from typing import List
import shutil
from datetime import datetime
import asyncio
from src.flet_ui.components.shared import PRIMARY, TEXT_MUTED, GLASS_BG, AppContext, session_discard
from src.utils.app_paths import get_upload_dir, sanitize_path_component
from src.utils.cv2_path import (
    BGR_READ_OK,
    BGR_READ_PERMISSION,
    imread_bgr_outcome,
)
from src.utils.batch_input_filter import select_mnv_images_for_batch
from src.utils.vd_batch_csv import VD_LAYOUT_VSL_DENSITY_ONLY
from src.utils.batch_csv_export import mark_analysis_started
from src.utils.institution_config import (
    INSTITUTION_PRESETS,
    load_persisted_institution_id,
    persist_institution_id,
)
from src.utils.vd_folder_preflight import (
    scan_vd_folder_pairs,
    vd_pair_suffixes_configured,
)
from src.utils.second_reader import (
    SR_FIRST_GRADER_CSV_KEY,
    SR_SCAN_ROOT_KEY,
    SR_CSV_PATH_KEY,
    bind_fov_to_batch_paths,
    format_scale_dropdown_value,
    is_second_reader,
    load_meta_fov_by_stem,
    resolve_image_fov_map,
    resolve_second_reader_scan,
    second_reader_output_dir,
)


def _prepare_results_session(page, all_results, *, vd_only: bool = False) -> None:
    """Write batch results to session and clear cross-run state before /results."""
    page.session.set("batch_results", all_results)
    page.session.set("last_result", all_results[0] if all_results else None)
    session_discard(page.session, "integrated_vd_result")
    session_discard(page.session, "batch_csv_auto_saved")
    if vd_only:
        session_discard(page.session, "mnv_batch_awaiting_qc")
        session_discard(page.session, "mnv_batch_paths")
        session_discard(page.session, "mnv_batch_index")
        session_discard(page.session, "mnv_batch_results")
        session_discard(page.session, "mnv_batch_names_preview")
        session_discard(page.session, "mnv_batch_scales")
        session_discard(page.session, "mnv_batch_scale_stems")
        session_discard(page.session, "mnv_batch_scale_names")
        session_discard(page.session, "results_selected_index")
        if all_results:
            page.session.set("results_selected_index", 0)


def _queue_kind_is_vd(queue_kind: str) -> bool:
    k = str(queue_kind or "").strip().upper()
    return k in ("VD", "VD_SINGLE", "INTEGRATED")


def _resolve_vd_pair_mode(page, sup_field, deep_field) -> bool:
    """
    Pair mode when wizard/session requests SCP/DCP pairs and both suffixes are set.
    Cleared deep suffix => single-image mode (each file analyzed independently).
    """
    sup = (sup_field.value if hasattr(sup_field, "value") else sup_field or "").strip() or "1.tif"
    deep = (deep_field.value if hasattr(deep_field, "value") else deep_field or "").strip() or "2.tif"
    if not vd_pair_suffixes_configured(sup, deep):
        return False
    flag = page.session.get("vd_use_pair_mode")
    if flag is None:
        return True
    return bool(flag)


async def get_dashboard_view(ctx: AppContext):
    # --- UI STATE ELEMENTS (Defined early for handler reference) ---
    batch_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Filename", color=PRIMARY)),
            ft.DataColumn(ft.Text("Type", color=PRIMARY)),
            ft.DataColumn(ft.Text("Size", color=PRIMARY)),
            ft.DataColumn(ft.Text("Status", color=PRIMARY)),
        ],
        rows=[],
        bgcolor=Colors.with_opacity(0.02, Colors.WHITE),
        border_radius=10,
    )
    
    batch_progress = ft.ProgressBar(
        value=0,
        width=800,
        color=PRIMARY,
        bgcolor=Colors.with_opacity(0.15, Colors.WHITE),
        visible=False,
    )
    batch_status_text = ft.Text("", color=TEXT_MUTED, size=12)
    
    def _is_web() -> bool:
        return bool(getattr(ctx.page, "web", False))

    # --- Ensure pickers on overlay (on_result wired after load_batch_from_directory; FilePicker API is sync only) ---
    if ctx.directory_picker not in ctx.page.overlay:
        ctx.page.overlay.append(ctx.directory_picker)
    ctx.page.update()
    
    analysis_type = ft.Dropdown(
        label="Analysis Type",
        options=[
            ft.dropdown.Option("MNV", "MNV Analysis"),
            ft.dropdown.Option("VD_SINGLE", "VD Analysis — single SCP/DCP"),
            ft.dropdown.Option("INTEGRATED", "Integrated Analysis (VD + MNV)"),
        ],
        value="MNV",
        width=300,
        border_color=PRIMARY,
    )
    
    scale_mm = ft.Dropdown(
        label="Image Scale (mm)",
        options=[ft.dropdown.Option(str(float(i))) for i in range(1, 13)],
        value="6.0",
        width=150,
        border_color=PRIMARY,
    )

    vd_sup_suffix = ft.TextField(
        label="VD sup. suffix",
        value="1.tif",
        width=140,
        tooltip="Superficial layer filename suffix (same as Streamlit / VDAnalyzer).",
        border_color=PRIMARY,
    )
    vd_deep_suffix = ft.TextField(
        label="VD deep suffix",
        value="2.tif",
        width=140,
        tooltip="Deep layer filename suffix.",
        border_color=PRIMARY,
    )
    vd_side = ft.Dropdown(
        label="VD eye side",
        options=[ft.dropdown.Option("right"), ft.dropdown.Option("left")],
        value="right",
        width=120,
        border_color=PRIMARY,
    )
    _vd_pair_mode_sess = ctx.page.session.get("vd_use_pair_mode")
    vd_pair_mode_switch = ft.Switch(
        label="SCP/DCP pair mode",
        value=bool(_vd_pair_mode_sess) if _vd_pair_mode_sess is not None else True,
        active_color=PRIMARY,
        tooltip=(
            "ON: match superficial+deep by suffix (like Integrated); unpaired files are skipped. "
            "OFF: analyze each image independently (legacy VD single-folder mode)."
        ),
    )

    def _on_vd_pair_mode_change(e):
        ctx.page.session.set("vd_use_pair_mode", bool(e.control.value))

    vd_pair_mode_switch.on_change = _on_vd_pair_mode_change

    _mnv_select_all_sess = ctx.page.session.get("mnv_select_all_images")
    mnv_select_all_switch = ft.Switch(
        label="MNV: analyze all images",
        value=bool(_mnv_select_all_sess),
        active_color=PRIMARY,
        tooltip=(
            "OFF: auto-select MNV images (exclude *1/*2/*4 and image1/2/4). "
            "ON: include every image in the folder."
        ),
    )

    def _on_mnv_select_all_change(e):
        ctx.page.session.set("mnv_select_all_images", bool(e.control.value))

    mnv_select_all_switch.on_change = _on_mnv_select_all_change

    def _mnv_image_selection_mode() -> str:
        return "all" if bool(ctx.page.session.get("mnv_select_all_images")) else "auto"

    manual_path = ft.TextField(
        label="Optional path (folder on server host — paste if you already know the path)",
        border_color=PRIMARY,
        expand=True,
        text_size=12,
        height=40,
    )

    async def on_manual_submit(_=None):
        raw = (manual_path.value or "").strip().strip("'").strip('"')
        if not raw:
            return
        await ctx.process_target_path(raw)

    manual_path.on_submit = lambda _: ctx.page.run_task(on_manual_submit)

    output_path_input = ft.TextField(
        label="Output Folder (Optional — defaults to <input_dir>/output_folder_date)",
        border_color=PRIMARY,
        expand=True,
        text_size=12,
        height=40,
        value=ctx.page.session.get("output_folder") or "",
    )

    _inst_persisted = load_persisted_institution_id(
        ctx.page.session, getattr(ctx.page, "client_storage", None)
    )
    _inst_preset_codes = {c for c, _ in INSTITUTION_PRESETS if c != "CUSTOM"}
    _inst_initial = (
        _inst_persisted
        if _inst_persisted in _inst_preset_codes
        else ("CUSTOM" if _inst_persisted else "ARIAKE_OHANACHAYA")
    )
    institution_dd = ft.Dropdown(
        label="Institution code",
        width=280,
        border_color=PRIMARY,
        value=_inst_initial,
        options=[
            ft.dropdown.Option(code, f"{code} — {label}")
            for code, label in INSTITUTION_PRESETS
        ],
        tooltip="Tags export/{institution_id}/… for multi-site ML datasets.",
    )
    institution_custom = ft.TextField(
        label="Custom institution code",
        width=220,
        border_color=PRIMARY,
        text_size=12,
        height=40,
        value=_inst_persisted if _inst_initial == "CUSTOM" else "",
        visible=(_inst_initial == "CUSTOM"),
        hint_text="UPPER_SNAKE",
    )

    def _sync_institution_session(_=None):
        raw = (
            (institution_custom.value or "").strip()
            if institution_dd.value == "CUSTOM"
            else (institution_dd.value or "")
        )
        if institution_dd.value == "CUSTOM" and not raw:
            return
        persist_institution_id(
            raw,
            ctx.page.session,
            getattr(ctx.page, "client_storage", None),
        )

    def _on_institution_dd_change(e):
        institution_custom.visible = institution_dd.value == "CUSTOM"
        _sync_institution_session()
        ctx.page.update()

    institution_dd.on_change = _on_institution_dd_change
    institution_custom.on_blur = lambda _: _sync_institution_session()
    institution_custom.on_submit = lambda _: _sync_institution_session()

    async def _on_output_picker_result(e: ft.FilePickerResultEvent):
        if e.path:
            output_path_input.value = e.path
            ctx.page.session.set("output_folder", e.path)
            ctx.page.update()

    ctx.output_directory_picker.on_result = _on_output_picker_result

    async def handle_select_output_folder(_=None):
        print("DEBUG: [OUTPUT_FOLDER] Clicked", flush=True)
        async def _set_out_path(p):
            output_path_input.value = p
            ctx.page.session.set("output_folder", p)
            ctx.page.update()
        # Always allow server explorer as fallback or primary in restricted environments
        await show_folder_explorer("Select Output Folder (Server Path)", on_select=_set_out_path)

    async def start_unified_analysis(e):
        print(f"DEBUG: [START_ANALYSIS] Clicked. Mode: {analysis_type.value}", flush=True)
        if manual_path.value:
            await ctx.process_target_path(manual_path.value)
        else:
            # Native OS pickers can be flaky in frozen apps; use server explorer by default
            await show_folder_explorer(
                "Select folder/file (Server Path Explorer)",
                on_select=ctx.process_target_path,
            )

    async def show_folder_explorer(title="Select Folder", on_select=None):
        explorer_list = ft.ListView(expand=True, spacing=5)
        current_path_text = ft.Text(size=12, color=TEXT_MUTED, weight=FontWeight.BOLD)
        how_to_text = ft.Text(
            "How to select: open the folder that contains your images, then press Confirm "
            "(do not need to click each image). If you click an image by mistake, Confirm "
            "still uses that image’s folder for batch analysis.",
            size=11,
            color=TEXT_MUTED,
        )
        selection_hint = ft.Text(
            "Current folder will be used on Confirm.",
            size=11,
            color=PRIMARY,
        )

        state = {"path": str(Path.home()), "selected_file": None}

        async def load_dir(target_path):
            state["path"] = target_path
            state["selected_file"] = None
            selection_hint.value = (
                f"Ready: analyze images in this folder → {Path(target_path).name}"
            )
            res = await ctx.client.list_dir(target_path)
            if "error" in res:
                await ctx.add_to_console(f"Explorer Error: {res['error']}", "ERROR")
                return

            current_path_text.value = res.get("current_path")
            explorer_list.controls.clear()

            async def handle_item_click(e):
                path = e.control.data["path"]
                is_dir = e.control.data["is_dir"]
                if is_dir:
                    await load_dir(path)
                else:
                    state["selected_file"] = path
                    parent_name = Path(path).parent.name
                    selection_hint.value = (
                        f"Image clicked — Confirm will analyze the whole folder "
                        f"「{parent_name}」(not only this file)."
                    )
                    ctx.page.update()

            for item in res.get("items", []):
                icon = Icons.FOLDER_ROUNDED if item["is_dir"] else Icons.INSERT_DRIVE_FILE_OUTLINED
                color = PRIMARY if item["is_dir"] else Colors.WHITE

                explorer_list.controls.append(
                    ft.ListTile(
                        leading=ft.Icon(icon, color=color),
                        title=ft.Text(item["name"], size=14),
                        data={"path": item["path"], "is_dir": item["is_dir"]},
                        on_click=lambda e: ctx.page.run_task(handle_item_click, e),
                        subtitle=ft.Text(item["path"], size=10, color=TEXT_MUTED) if item["name"] == ".." else None
                    )
                )
            ctx.page.update()

        async def confirm_selection(_=None):
            ctx.page.close(dlg)
            if on_select:
                try:
                    # Prefer current folder; if a file was clicked, still pass that path —
                    # load_batch_from_directory normalizes files → parent folder.
                    final_path = state.get("selected_file") or state["path"]
                    await on_select(final_path)
                except Exception as ex:
                    import traceback

                    print(traceback.format_exc(), flush=True)
                    await ctx.add_to_console(f"Confirm selection failed: {ex}", "ERROR")

        async def cancel_selection(_=None):
            ctx.page.close(dlg)

        dlg = ft.AlertDialog(
            title=ft.Text(title, size=20, weight=FontWeight.BOLD),
            content=ft.Container(
                content=ft.Column([
                    how_to_text,
                    current_path_text,
                    selection_hint,
                    ft.Divider(color=Colors.with_opacity(0.1, Colors.WHITE)),
                    ft.Container(explorer_list, height=360, border=ft.border.all(1, Colors.with_opacity(0.1, Colors.WHITE)), border_radius=10),
                ], spacing=10),
                width=620,
                height=520
            ),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: ctx.page.run_task(cancel_selection)),
                ft.ElevatedButton(
                    "Confirm Selection",
                    bgcolor=PRIMARY,
                    color=Colors.BLACK,
                    on_click=lambda _: ctx.page.run_task(confirm_selection),
                ),
            ],
            bgcolor=GLASS_BG,
        )

        ctx.page.open(dlg)
        await load_dir(state["path"])

    async def upload_folder_direct(e):
         await show_folder_explorer("Select VD Batch Folder", on_select=ctx.process_target_path)

    async def upload_file_direct(e):
         await show_folder_explorer("Select MNV Image (Navigate and choose folder, then paste filename if needed - or just use current picker)", on_select=ctx.process_target_path)

    ctx.scale_mm_ref.current = scale_mm
    ctx.analysis_type_ref.current = analysis_type
    ctx.vd_sup_suffix_ref.current = vd_sup_suffix
    ctx.vd_deep_suffix_ref.current = vd_deep_suffix
    ctx.vd_side_ref.current = vd_side

    async def handle_drop(e):
        if hasattr(e, "data") and e.data:
            try:
                await ctx.add_to_console(f"Data dropped: {e.data}", "INFO")
                target = e.data.strip()
                if target.startswith("[") and target.endswith("]"):
                    import ast
                    paths = ast.literal_eval(target)
                    if isinstance(paths, list) and len(paths) > 0:
                        target = paths[0]
                await ctx.process_target_path(target)
            except Exception as ex:
                await ctx.add_to_console(f"Drop error: {str(ex)}", "ERROR")
    
    ctx.page.on_drop = handle_drop

    async def _log_vd_pair_scan(folder: Path, sup: str, deep: str, *, require_pairs: bool) -> bool:
        """Log SCP/DCP naming check; return False if pair mode requires pairs but none found."""
        scan = scan_vd_folder_pairs(folder, sup, deep)
        for line in scan.console_lines():
            level = "WARN" if scan.unpaired_superficial and "Unpaired" in line else "INFO"
            await ctx.add_to_console(line, level)
        if require_pairs and not scan.pair_mode_viable:
            await ctx.add_to_console(
                f"VD pair preflight failed: no SCP+DCP pairs in {folder.name} "
                f"(sup={sup!r}, deep={deep!r}). Adjust suffixes or disable pair mode.",
                "ERROR",
            )
            return False
        return True

    async def run_batch_preflight():
        """
        Validate queued files before analysis so failures are actionable.
        Returns list[bool] aligned with batch_table.rows indicating readiness.
        """
        readiness = [True] * len(batch_table.rows)
        sup = (vd_sup_suffix.value or "").strip() or "1.tif"
        deep = (vd_deep_suffix.value or "").strip() or "2.tif"
        for i, row in enumerate(batch_table.rows):
            file_path = row.data["path"].strip().strip("'").strip('"')
            p = Path(file_path)
            if not p.exists():
                readiness[i] = False
                row.cells[3].content.value = "Missing"
                row.cells[3].content.color = Colors.RED_400
                await ctx.add_to_console(f"Preflight: file not found [{p.name}]", "ERROR")
                continue
            if p.is_dir():
                queue_kind = row.data.get("queue_kind") or ""
                use_pairs = row.data.get("vd_pair_mode")
                if use_pairs is None:
                    use_pairs = _resolve_vd_pair_mode(ctx.page, vd_sup_suffix, vd_deep_suffix)
                if _queue_kind_is_vd(queue_kind) and use_pairs:
                    ok = await _log_vd_pair_scan(p, sup, deep, require_pairs=True)
                    if not ok:
                        readiness[i] = False
                        row.cells[3].content.value = "No pairs"
                        row.cells[3].content.color = Colors.RED_400
                        continue
                row.cells[3].content.value = "Ready"
                row.cells[3].content.color = PRIMARY
                continue
            img, reason = imread_bgr_outcome(file_path)
            if img is None or reason != BGR_READ_OK:
                readiness[i] = False
                row.cells[3].content.value = "Unreadable"
                row.cells[3].content.color = Colors.RED_400
                if reason == BGR_READ_PERMISSION:
                    await ctx.add_to_console(
                        f"Preflight: permission denied [{p.name}] (CloudStorage/TCC). Consider staging copy.",
                        "ERROR",
                    )
                else:
                    await ctx.add_to_console(
                        f"Preflight: read failed [{p.name}] (reason={reason})",
                        "ERROR",
                    )
            else:
                row.cells[3].content.value = "Ready"
                row.cells[3].content.color = PRIMARY
        ctx.page.update()
        return readiness

    def _set_batch_progress_overall(
        row_index: int,
        total_rows: int,
        vd_current: int,
        vd_total: int,
        message: str,
    ) -> None:
        vd_total = max(int(vd_total), 1)
        vd_current = min(max(int(vd_current), 0), vd_total)
        overall = (row_index + vd_current / vd_total) / max(int(total_rows), 1)
        batch_progress.value = min(max(overall, 0.0), 1.0)
        pct = int(round(overall * 100))
        batch_status_text.value = (
            f"VD {vd_current}/{vd_total} ({pct}%) — {message}"
            if total_rows == 1
            else f"Batch row {row_index + 1}/{total_rows} · VD {vd_current}/{vd_total} ({pct}%) — {message}"
        )

    async def _run_vd_analysis_ui(
        vd_dir: str,
        scale: float,
        *,
        side: str,
        sup_suffix: str,
        deep_suffix: str,
        single_image_mode: bool,
        row_index: int,
        total_rows: int,
    ):
        async def _on_prog(cur, tot, msg):
            _set_batch_progress_overall(row_index, total_rows, cur, tot, msg)
            ctx.page.update()

        return await ctx.client.start_vd_analysis_with_progress(
            vd_dir,
            scale,
            side=side,
            sup_suffix=sup_suffix,
            deep_suffix=deep_suffix,
            single_image_mode=single_image_mode,
            progress_callback=_on_prog,
        )

    # --- BATCH PROCESSING LOGIC ---
    async def run_batch_analysis(e):
        if not batch_table.rows:
            return
            
        start_button.disabled = True
        batch_progress.visible = True
        batch_progress.value = 0
        mark_analysis_started(ctx.page.session)
        ctx.page.update()

        all_results = []
        total = len(batch_table.rows)
        vd_folder_cache = {}

        def _vd_cache_key(vd_dir: str, single: bool) -> tuple:
            sup = (vd_sup_suffix.value or "").strip() or "1.tif"
            deep = (vd_deep_suffix.value or "").strip() or "2.tif"
            side = (vd_side.value or "right").strip() or "right"
            return (vd_dir, single, sup, deep, side)

        await ctx.add_to_console(f"Starting batch analysis for {total} files...", "INFO")
        readiness = await run_batch_preflight()
        runnable = sum(1 for ok in readiness if ok)
        if runnable == 0:
            await ctx.add_to_console("Preflight failed for all files. Batch aborted.", "ERROR")
            start_button.disabled = False
            batch_progress.visible = False
            ctx.page.update()
            return
        if runnable < total:
            await ctx.add_to_console(
                f"Preflight: {total - runnable} file(s) will be skipped due to read errors.",
                "WARN",
            )
        
        for i, row in enumerate(batch_table.rows):
            file_path = row.data["path"].strip().strip("'").strip('"')
            filename = Path(file_path).name
            analysis_mode = row.data.get("queue_kind") or row.cells[1].content.value
            if not readiness[i]:
                fail_row = {
                    "error": "Preflight failed (unreadable/missing)",
                    "source_filename": filename,
                    "status": "failed",
                }
                if _queue_kind_is_vd(analysis_mode):
                    fail_row["result_type"] = "VD"
                all_results.append(fail_row)
                batch_progress.value = (i + 1) / total
                ctx.page.update()
                continue
            
            batch_status_text.value = f"Processing ({i+1}/{total}): {filename}..."
            row.cells[3].content.value = "Processing..."
            row.cells[3].content.color = Colors.AMBER_400
            ctx.page.update()
            
            try:
                if analysis_mode == "MNV":
                    _fd_self = ctx.page.session.get("mnv_fd_self_ref") or False
                    res = await ctx.client.start_mnv_analysis(
                        image_path=file_path,
                        scale=float(scale_mm.value),
                        use_self_as_fd=bool(_fd_self),
                    )
                else:
                    pfp = Path(file_path)
                    vd_dir = str(pfp.resolve()) if pfp.is_dir() else str(pfp.parent.resolve())
                    use_pairs = row.data.get("vd_pair_mode")
                    if use_pairs is None:
                        use_pairs = _resolve_vd_pair_mode(ctx.page, vd_sup_suffix, vd_deep_suffix)
                    single_im = not use_pairs
                    ck = _vd_cache_key(vd_dir, single_im)
                    if ck in vd_folder_cache:
                        res = vd_folder_cache[ck]
                        batch_progress.value = (i + 1) / total
                    else:
                        _set_batch_progress_overall(
                            i, total, 0, 1, f"Starting VD ({Path(vd_dir).name})…"
                        )
                        ctx.page.update()
                        res = await _run_vd_analysis_ui(
                            vd_dir,
                            float(scale_mm.value),
                            side=str(vd_side.value or "right"),
                            sup_suffix=(vd_sup_suffix.value or "").strip() or "1.tif",
                            deep_suffix=(vd_deep_suffix.value or "").strip() or "2.tif",
                            single_image_mode=single_im,
                            row_index=i,
                            total_rows=total,
                        )
                        vd_folder_cache[ck] = res

                if "error" in res:
                    raise Exception(res["error"])

                row.cells[3].content.value = "Success"
                row.cells[3].content.color = Colors.GREEN_400
                if analysis_mode == "MNV":
                    res["_absolute_source_path"] = file_path
                    try:
                        res["scale_mm"] = float(scale_mm.value)
                        res["fov_mm"] = res["scale_mm"]
                    except (TypeError, ValueError):
                        pass
                    all_results.append(res)
                else:
                    out = dict(res)
                    out["_absolute_source_path"] = file_path
                    if not Path(file_path).is_dir():
                        out["source_filename"] = filename
                    if single_im:
                        out["vd_layout"] = VD_LAYOUT_VSL_DENSITY_ONLY
                    all_results.append(out)
                
            except Exception as ex:
                print(f"Batch Error on {filename}: {str(ex)}")
                row.cells[3].content.value = "Failed"
                row.cells[3].content.color = Colors.RED_400
                await ctx.add_to_console(f"Failed [{filename}]: {str(ex)}", "ERROR")
                fail_row = {"error": str(ex), "source_filename": filename, "status": "failed"}
                if _queue_kind_is_vd(analysis_mode):
                    fail_row["result_type"] = "VD"
                all_results.append(fail_row)
            
            batch_progress.value = (i + 1) / total
            ctx.page.update()

        await ctx.add_to_console(f"Batch analysis complete. {len(all_results)} results processed.", "INFO")
        vd_only = bool(batch_table.rows) and all(
            not (str(row.data.get("queue_kind") or row.cells[1].content.value or "").strip().upper() == "MNV")
            for row in batch_table.rows
        )
        _prepare_results_session(ctx.page, all_results, vd_only=vd_only)
        
        batch_status_text.value = "All tasks completed."
        start_button.disabled = False
        ctx.page.update()
        ctx.page.go("/results")

    start_button = ft.ElevatedButton(
        "Start Batch Analysis", 
        icon=Icons.PLAY_CIRCLE_FILL_ROUNDED,
        bgcolor=PRIMARY, 
        color=Colors.BLACK,
        on_click=lambda _: ctx.page.run_task(run_batch_analysis, None),
        width=300
    )

    batch_container = ft.Container(
        content=ft.Column([
            ft.Text("3. Batch Preview & Queue", size=20, weight=FontWeight.BOLD, color=PRIMARY),
            ft.Text("Verify the files below before starting automated batch analysis.", color=TEXT_MUTED),
            ft.Container(content=batch_table, padding=10),
            ft.Row([
                start_button,
                ft.TextButton("Clear Queue", icon=Icons.DELETE_SWEEP, on_click=lambda _: clear_batch_queue()),
            ], spacing=20),
            batch_progress,
            batch_status_text
        ], spacing=15),
        padding=30,
        bgcolor=GLASS_BG,
        border_radius=20,
        visible=False
    )

    def clear_batch_queue():
        batch_table.rows.clear()
        batch_container.visible = False
        session_discard(ctx.page.session, "batch_csv_auto_saved")
        ctx.page.update()

    async def run_integrated_folder_analysis(root_abs: str, image_paths_on_disk: List[Path]):
        """VD (SCP+DCP pairs) first; each MNV candidate then uses the same ROI queue as MNV-only batch."""
        start_button.disabled = True
        batch_progress.visible = True
        batch_progress.value = 0
        batch_status_text.value = "Integrated: running VD (pairs)…"
        mark_analysis_started(ctx.page.session)
        ctx.page.update()

        scale_f = float(scale_mm.value or 6)
        side_s = str(vd_side.value or "right").strip() or "right"
        sup = (vd_sup_suffix.value or "").strip() or "1.tif"
        deep = (vd_deep_suffix.value or "").strip() or "2.tif"

        mnv_candidates = sorted(
            select_mnv_images_for_batch(
                list(image_paths_on_disk),
                mode=_mnv_image_selection_mode(),
                fallback_all_if_empty=False,
            ),
            key=lambda p: p.name.lower(),
        )

        root_path = Path(root_abs)
        if not await _log_vd_pair_scan(root_path, sup, deep, require_pairs=True):
            batch_progress.visible = False
            batch_status_text.value = "Integrated: VD preflight failed (no SCP/DCP pairs)."
            start_button.disabled = False
            ctx.page.update()
            return

        await ctx.add_to_console(
            f"Integrated ({root_path.name}): VD pairing (sup={sup}, deep={deep}); "
            f"then ROI-backed MNV for {len(mnv_candidates)} file(s) if present.",
            "INFO",
        )

        async def _on_integrated_vd(cur, tot, msg):
            _set_batch_progress_overall(0, 1, cur, tot, msg)
            ctx.page.update()

        vd_res = await ctx.client.start_vd_analysis_with_progress(
            root_abs,
            scale_f,
            side=side_s,
            sup_suffix=sup,
            deep_suffix=deep,
            single_image_mode=False,
            progress_callback=_on_integrated_vd,
        )
        if "error" in vd_res:
            await ctx.add_to_console(f"Integrated: VD failed — {vd_res['error']}", "ERROR")
            vd_bundle = {
                "result_type": "VD",
                "source_filename": f"{Path(root_abs).name} (vd_batch)",
                "error": vd_res["error"],
                "status": "failed",
            }
        else:
            vd_bundle = dict(vd_res)
            vd_bundle.setdefault("result_type", "VD")
            vd_bundle["_absolute_source_path"] = root_abs

        batch_progress.value = 1.0
        batch_status_text.value = "VD phase complete."
        ctx.page.update()

        def _finalize_vd_only_to_results():
            _prepare_results_session(ctx.page, [vd_bundle], vd_only=True)

        if not mnv_candidates:
            await ctx.add_to_console(
                "Integrated: no MNV candidate files after filter (*1/*2/*4). Opening results (VD only).",
                "WARN",
            )
            batch_progress.visible = False
            batch_status_text.value = "Integrated run complete (VD only)."
            start_button.disabled = False
            _finalize_vd_only_to_results()
            ctx.page.update()
            await ctx.add_to_console("Integrated analysis complete (VD only).", "INFO")
            ctx.page.go("/results")
            return

        paths_ordered = [str(p.resolve()) for p in mnv_candidates]
        preview_names = [Path(p).name for p in paths_ordered]
        ctx.page.session.set("integrated_vd_result", vd_bundle)
        ctx.page.session.set("mnv_batch_paths", paths_ordered)
        ctx.page.session.set("mnv_batch_index", 0)
        ctx.page.session.set("mnv_batch_results", [])
        ctx.page.session.set("mnv_batch_names_preview", preview_names)
        session_discard(ctx.page.session, "mnv_batch_awaiting_qc")
        session_discard(ctx.page.session, "last_result")
        session_discard(ctx.page.session, "batch_results")
        session_discard(ctx.page.session, "results_selected_index")
        ctx.page.session.set("target_path", paths_ordered[0])
        ctx.page.session.set("scale", scale_f)
        session_discard(ctx.page.session, "roi")
        session_discard(ctx.page.session, "roi_mask_b64")

        batch_progress.visible = False
        batch_status_text.value = f"VD done — ROI for MNV 1/{len(paths_ordered)}"
        start_button.disabled = False
        await ctx.add_to_console(
            f"Integrated: VD完了 → MNV {len(paths_ordered)} 件。画像ごとに ROI を指定してください。",
            "INFO",
        )
        ctx.page.update()
        await asyncio.sleep(0.35)
        ctx.page.go("/roi")

    async def _load_batch_from_directory_core(fspath):
        if not fspath:
            return

        """Build batch queue from a server-side directory path. Used by desktop FilePicker and web explorer."""
        p = Path(fspath)
        # Forgiving UX: if the user clicked an image then Confirm, use its parent folder
        # (common “normalize selection to container” pattern for batch tools).
        if p.is_file():
            parent = p.parent
            await ctx.add_to_console(
                f"File selected ({p.name}) — using parent folder for batch: {parent}",
                "INFO",
            )
            p = parent
        if not p.is_dir():
            await ctx.add_to_console(f"Not a directory: {fspath}", "ERROR")
            return

        # Save resolved input directory for output path determination later
        ctx.page.session.set("original_input_dir", str(p.resolve()))
        await ctx.add_to_console(f"Scanning directory: {p.name}", "INFO")

        patterns = ["*.tif", "*.tiff", "*.png", "*.jpg", "*.jpeg"]
        files = []
        for pat in patterns:
            files.extend(list(p.glob(pat)))
        files.sort(key=lambda x: x.name.lower())

        if not files:
            await ctx.add_to_console("No supported images found in directory.", "ERROR")
            return

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        staging_root = get_upload_dir() / "batch_staging" / stamp
        staging_root.mkdir(parents=True, exist_ok=True)
        await ctx.add_to_console(
            f"OneDrive-safe staging: copying {len(files)} file(s) to {staging_root}", "INFO",
        )
        staged_files = []
        for src in files:
            dst = staging_root / src.name
            if dst.exists():
                dst = staging_root / f"{src.stem}_{len(staged_files):03d}{src.suffix}"
            try:
                shutil.copy2(src, dst)
                staged_files.append(dst)
            except Exception as ex:
                await ctx.add_to_console(f"Stage copy failed [{src.name}]: {ex}", "ERROR")
        files = staged_files
        if not files:
            await ctx.add_to_console("Staging failed for all files. Batch queue not created.", "ERROR")
            return

        batch_table.rows.clear()
        batch_plan = analysis_type.value

        if batch_plan == "MNV":
            session_discard(ctx.page.session, "integrated_vd_result")
            raw_count = len(files)
            sel_mode = _mnv_image_selection_mode()
            files = select_mnv_images_for_batch(files, mode=sel_mode)
            if not files:
                await ctx.add_to_console(
                    "MNV folder filter removed all files (*1/*2/*4 and image1/2/4 patterns). Nothing to analyze.",
                    "ERROR",
                )
                return
            if sel_mode == "auto" and len(files) < raw_count:
                await ctx.add_to_console(
                    f"MNV auto-select: {raw_count} → {len(files)} file(s) (suffix rules).",
                    "INFO",
                )
            elif sel_mode == "all":
                await ctx.add_to_console(
                    f"MNV all-images mode: {len(files)} file(s) queued.",
                    "INFO",
                )
            paths_ordered = [str(f.resolve()) for f in files]
            preview_names = [Path(p).name for p in paths_ordered]
            # Rebind FOV onto staged paths (export abs paths no longer match).
            stem_to_fov = ctx.page.session.get("mnv_batch_scale_stems") or {}
            name_to_fov = ctx.page.session.get("mnv_batch_scale_names") or {}
            if stem_to_fov or name_to_fov:
                ctx.page.session.set(
                    "mnv_batch_scales",
                    bind_fov_to_batch_paths(paths_ordered, stem_to_fov, name_to_fov),
                )
            ctx.page.session.set("mnv_batch_paths", paths_ordered)
            ctx.page.session.set("mnv_batch_index", 0)
            ctx.page.session.set("mnv_batch_results", [])
            ctx.page.session.set("mnv_batch_names_preview", preview_names)
            session_discard(ctx.page.session, "mnv_batch_awaiting_qc")
            session_discard(ctx.page.session, "last_result")
            session_discard(ctx.page.session, "batch_results")
            session_discard(ctx.page.session, "results_selected_index")
            ctx.page.session.set("target_path", paths_ordered[0])
            scales = ctx.page.session.get("mnv_batch_scales") or {}
            first_fov = scales.get(paths_ordered[0])
            if first_fov is None:
                first_fov = name_to_fov.get(Path(paths_ordered[0]).name)
            if first_fov is None:
                first_fov = stem_to_fov.get(Path(paths_ordered[0]).stem)
            if first_fov is not None:
                ctx.page.session.set("scale", float(first_fov))
                scale_mm.value = format_scale_dropdown_value(float(first_fov))
            else:
                ctx.page.session.set("scale", float(scale_mm.value))
            session_discard(ctx.page.session, "roi")
            session_discard(ctx.page.session, "roi_mask_b64")
            batch_table.rows.clear()
            for fp_str in paths_ordered:
                pf = Path(fp_str)
                try:
                    mb = pf.stat().st_size / (1024 * 1024)
                    sz_txt = f"{mb:.2f} MB"
                except OSError:
                    sz_txt = "—"
                batch_table.rows.append(
                    ft.DataRow(
                        cells=[
                            ft.DataCell(ft.Text(pf.name, size=12)),
                            ft.DataCell(ft.Text("MNV", size=10, color=PRIMARY)),
                            ft.DataCell(ft.Text(sz_txt, size=11, color=TEXT_MUTED)),
                            ft.DataCell(ft.Text("ROI queue", color=PRIMARY, size=11)),
                        ],
                        data={"path": fp_str, "queue_kind": "MNV"},
                    )
                )
            batch_container.visible = True
            ctx.page.update()
            await ctx.add_to_console(
                f"MNV batch: {len(paths_ordered)} file(s). Opening ROI for image 1 — draw ROI, then confirm and run analysis.",
                "INFO",
            )
            await asyncio.sleep(0.35)
            ctx.page.go("/roi")
            return
        elif batch_plan == "INTEGRATED":
            root_dir = files[0].parent
            total_mb = sum(f.stat().st_size for f in files) / (1024 * 1024)
            sup = (vd_sup_suffix.value or "").strip() or "1.tif"
            deep = (vd_deep_suffix.value or "").strip() or "2.tif"
            batch_table.rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(
                            ft.Text(
                                f"Integrated VD+MNV: {len(files)} images in {root_dir.name} | "
                                f"sup={sup} deep={deep}",
                                size=12,
                            )
                        ),
                        ft.DataCell(ft.Text("Integrated", size=10, color=PRIMARY)),
                        ft.DataCell(ft.Text(f"{total_mb:.1f} MB (total)", size=11, color=TEXT_MUTED)),
                        ft.DataCell(ft.Text("running…", color=PRIMARY, size=11)),
                    ],
                    data={"path": str(root_dir.resolve()), "queue_kind": "INTEGRATED"},
                )
            )
            batch_container.visible = True
            ctx.page.update()
            await run_integrated_folder_analysis(str(root_dir.resolve()), files)
            return
        elif batch_plan == "VD_SINGLE":
            session_discard(ctx.page.session, "mnv_batch_awaiting_qc")
            session_discard(ctx.page.session, "mnv_batch_paths")
            session_discard(ctx.page.session, "mnv_batch_index")
            session_discard(ctx.page.session, "mnv_batch_results")
            session_discard(ctx.page.session, "mnv_batch_names_preview")
            session_discard(ctx.page.session, "mnv_batch_scales")
            session_discard(ctx.page.session, "mnv_batch_scale_stems")
            session_discard(ctx.page.session, "mnv_batch_scale_names")
            session_discard(ctx.page.session, "last_result")
            session_discard(ctx.page.session, "batch_results")
            session_discard(ctx.page.session, "results_selected_index")
            session_discard(ctx.page.session, "integrated_vd_result")
            root_dir = files[0].parent
            total_mb = sum(f.stat().st_size for f in files) / (1024 * 1024)
            sup = (vd_sup_suffix.value or "").strip() or "1.tif"
            deep = (vd_deep_suffix.value or "").strip() or "2.tif"
            use_pairs = _resolve_vd_pair_mode(ctx.page, vd_sup_suffix, vd_deep_suffix)
            ctx.page.session.set("vd_use_pair_mode", use_pairs)
            scan = scan_vd_folder_pairs(root_dir, sup, deep)
            for line in scan.console_lines():
                await ctx.add_to_console(line, "INFO")
            if use_pairs and not scan.pair_mode_viable:
                await ctx.add_to_console(
                    "VD batch aborted: pair mode enabled but no valid SCP+DCP pairs found.",
                    "ERROR",
                )
                return
            if use_pairs:
                type_label = "VD (SCP/DCP pairs)"
                summary = (
                    f"VD pair batch: {scan.pair_count} pair(s) in {root_dir.name} | "
                    f"sup={sup} deep={deep} | {scan.total_images} image(s) in folder"
                )
            else:
                type_label = "VD (single-image)"
                summary = (
                    f"VD single-image batch: {len(files)} file(s) in {root_dir.name} | "
                    "each file analyzed independently"
                )
            batch_table.rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(summary, size=12)),
                        ft.DataCell(ft.Text(type_label, size=10, color=Colors.BLUE_400)),
                        ft.DataCell(ft.Text(f"{total_mb:.1f} MB (total)", size=11, color=TEXT_MUTED)),
                        ft.DataCell(ft.Text("Ready", color=PRIMARY, size=11)),
                    ],
                    data={
                        "path": str(root_dir.resolve()),
                        "queue_kind": batch_plan,
                        "vd_pair_mode": use_pairs,
                    },
                )
            )
        else:
            await ctx.add_to_console(f"Unknown analysis type: {batch_plan}", "ERROR")
            return

        batch_container.visible = True
        ctx.page.update()
        await ctx.add_to_console(f"Found {len(files)} images. Auto-starting analysis...", "INFO")
        await run_batch_analysis(None)

    async def load_second_reader_batch(fspath):
        """
        第2リーダー: メタデータフォルダの親フォルダを自動スキャンし、
        エキスポート済み画像を通常の MNV 読影キューへ投入する。
        """
        if not fspath:
            return
        raw = str(fspath).strip().strip("'").strip('"')
        try:
            scan = resolve_second_reader_scan(Path(raw))
        except ValueError as ex:
            await ctx.add_to_console(f"第2リーダー スキャン失敗: {ex}", "ERROR")
            return

        await ctx.add_to_console(
            f"第2リーダー スキャン: {scan.export_dir} — 画像 {len(scan.images)} 件 / "
            f"メタデータ {len(scan.meta_files)} 件",
            "INFO",
        )
        for w in scan.warnings:
            await ctx.add_to_console(f"第2リーダー スキャン: {w}", "WARN")

        path_to_fov, default_fov, fov_warnings = resolve_image_fov_map(
            scan.images, scan.meta_files
        )
        for w in fov_warnings:
            await ctx.add_to_console(f"第2リーダー FOV: {w}", "WARN")
        if default_fov is not None:
            scale_txt = format_scale_dropdown_value(default_fov)
            scale_mm.value = scale_txt
            ctx.page.session.set("scale", float(default_fov))
            await ctx.add_to_console(
                f"第2リーダー: export/meta の FOV からスケールを {scale_txt} mm に設定しました。",
                "INFO",
            )
        # Keep stem/name maps so FOV survives OneDrive-safe staging (new paths).
        stem_to_fov = load_meta_fov_by_stem(scan.meta_files)
        name_to_fov = {
            img.name: float(stem_to_fov[img.stem])
            for img in scan.images
            if img.stem in stem_to_fov
        }
        if stem_to_fov:
            ctx.page.session.set("mnv_batch_scale_stems", stem_to_fov)
            ctx.page.session.set("mnv_batch_scale_names", name_to_fov)
        else:
            session_discard(ctx.page.session, "mnv_batch_scale_stems")
            session_discard(ctx.page.session, "mnv_batch_scale_names")
        if path_to_fov:
            ctx.page.session.set("mnv_batch_scales", path_to_fov)
        else:
            session_discard(ctx.page.session, "mnv_batch_scales")

        if scan.first_grader_csvs:
            first_csv = scan.first_grader_csvs[0]
            ctx.page.session.set(SR_FIRST_GRADER_CSV_KEY, str(first_csv))
            await ctx.add_to_console(
                f"第1グレーダーCSVを検出: {first_csv.name}", "INFO"
            )
        else:
            session_discard(ctx.page.session, SR_FIRST_GRADER_CSV_KEY)
            await ctx.add_to_console(
                "第1グレーダーCSVが見つかりません。統合時に再検索します。", "WARN"
            )

        # Second-reader outputs go next to (not inside) the first grader's files
        out_dir = second_reader_output_dir(scan.scan_root)
        ctx.page.session.set(SR_SCAN_ROOT_KEY, str(scan.scan_root))
        ctx.page.session.set("output_folder", str(out_dir))
        output_path_input.value = str(out_dir)
        session_discard(ctx.page.session, SR_CSV_PATH_KEY)

        # Exported lesion images are analyzed one by one — no suffix filtering
        analysis_type.value = "MNV"
        ctx.page.session.set("mnv_select_all_images", True)
        mnv_select_all_switch.value = True
        ctx.page.update()

        await _load_batch_from_directory_core(str(scan.images_dir))

    async def load_batch_from_directory(fspath):
        if is_second_reader(ctx.page.session):
            await load_second_reader_batch(fspath)
            return
        await _load_batch_from_directory_core(fspath)

    ctx.folder_batch_loader = load_batch_from_directory
    ctx.process_target_path = load_batch_from_directory

    async def _directory_picker_result_async(e: ft.FilePickerResultEvent):
        if not e.path:
            print("DEBUG: [ON_RESULT] Folder selection cancelled.", flush=True)
            return
        print(f"DEBUG: [ON_RESULT] Folder selection event received: {e.path}", flush=True)
        await load_batch_from_directory(e.path)

    def _directory_picker_result(e: ft.FilePickerResultEvent):
        ctx.page.run_task(_directory_picker_result_async, e)

    ctx.directory_picker.on_result = _directory_picker_result

    async def handle_select_folder(_=None):
        print("DEBUG: [SELECT_FOLDER] Clicked", flush=True)
        await show_folder_explorer("Select batch folder (Server Path)", on_select=load_batch_from_directory)

    async def handle_second_reader_start(_=None):
        await show_folder_explorer(
            "第2リーダー: 第1グレーダーの出力フォルダ（export の親フォルダ）を選択",
            on_select=load_second_reader_batch,
        )

    # ─────────────────────────────────────────────────────────────────────
    # Guided Launch Analysis Wizard
    # ─────────────────────────────────────────────────────────────────────
    async def show_launch_wizard(_=None):
        """3-step modal that enforces analysis type + scale before folder selection."""
        _pm = ctx.page.session.get("vd_use_pair_mode")
        wizard = {
            "step": 1,
            "analysis_type": analysis_type.value or "MNV",
            "scale_mm": scale_mm.value or "6.0",
            "vd_sup": vd_sup_suffix.value or "1.tif",
            "vd_deep": vd_deep_suffix.value or "2.tif",
            "vd_side_val": vd_side.value or "right",
            "vd_use_pairs": bool(_pm) if _pm is not None else True,
            "mnv_fd_self_ref": bool(ctx.page.session.get("mnv_fd_self_ref") or False),
            "mnv_select_all_images": bool(ctx.page.session.get("mnv_select_all_images")),
        }
        ACCENT = PRIMARY
        CARD_W = 158

        def _type_card(label, subtitle, icon_name, key):
            sel = wizard["analysis_type"] == key
            async def _pick(_=None):
                wizard["analysis_type"] = key
                _refresh()
            return ft.GestureDetector(
                on_tap=lambda _: ctx.page.run_task(_pick),
                content=ft.Container(
                    content=ft.Column([
                        ft.Icon(icon_name, size=34,
                                color=ACCENT if sel else Colors.WHITE70),
                        ft.Text(label, size=13, weight=FontWeight.BOLD,
                                color=Colors.WHITE, text_align=ft.TextAlign.CENTER),
                        ft.Text(subtitle, size=10, color=TEXT_MUTED,
                                text_align=ft.TextAlign.CENTER),
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
                    width=CARD_W, padding=18,
                    border=ft.border.all(2 if sel else 1,
                                        ACCENT if sel else Colors.with_opacity(0.2, Colors.WHITE)),
                    border_radius=16,
                    bgcolor=Colors.with_opacity(0.12 if sel else 0.04,
                                               ACCENT if sel else Colors.WHITE),
                    animate=ft.Animation(150, ft.AnimationCurve.EASE_OUT),
                ),
            )

        scale_field = ft.TextField(
            value=wizard["scale_mm"], label="Scale (mm)", width=130,
            border_color=ACCENT, suffix_text="mm",
            keyboard_type=ft.KeyboardType.NUMBER,
            on_change=lambda e: wizard.update({"scale_mm": e.control.value or "6.0"}),
        )

        def _scale_btn(label, val):
            sel = wizard["scale_mm"] == val
            async def _pick(_=None):
                wizard["scale_mm"] = val
                scale_field.value = val
                _refresh()
            return ft.ElevatedButton(
                label,
                bgcolor=ACCENT if sel else Colors.with_opacity(0.1, Colors.WHITE),
                color=Colors.BLACK if sel else Colors.WHITE,
                width=105,
                on_click=lambda _: ctx.page.run_task(_pick),
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
            )

        vd_sup_f = ft.TextField(label="Superficial suffix", value=wizard["vd_sup"],
                                width=160, border_color=ACCENT,
                                on_change=lambda e: wizard.update({"vd_sup": e.control.value}))
        vd_deep_f = ft.TextField(label="Deep suffix", value=wizard["vd_deep"],
                                 width=160, border_color=ACCENT,
                                 on_change=lambda e: wizard.update({"vd_deep": e.control.value}))
        vd_side_dd = ft.Dropdown(
            label="Eye side", value=wizard["vd_side_val"],
            options=[ft.dropdown.Option("right"), ft.dropdown.Option("left")],
            width=130, border_color=ACCENT,
            on_change=lambda e: wizard.update({"vd_side_val": e.control.value}),
        )
        vd_pair_sw = ft.Switch(
            value=wizard["vd_use_pairs"],
            active_color=ACCENT,
            on_change=lambda e: wizard.update({"vd_use_pairs": bool(e.control.value)}),
        )
        fd_switch = ft.Switch(
            value=wizard["mnv_fd_self_ref"], active_color=ACCENT,
            on_change=lambda e: wizard.update({"mnv_fd_self_ref": e.control.value}),
        )
        mnv_select_switch = ft.Switch(
            value=wizard["mnv_select_all_images"],
            active_color=ACCENT,
            on_change=lambda e: wizard.update({"mnv_select_all_images": bool(e.control.value)}),
        )

        def _build_content():
            step = wizard["step"]
            atype = wizard["analysis_type"]
            if step == 1:
                return ft.Column([
                    ft.Text("Select the analysis type:", color=TEXT_MUTED, size=13),
                    ft.Row([
                        _type_card("MNV Analysis", "Neovascularization\nsingle image",
                                   Icons.BLUR_CIRCULAR_ROUNDED, "MNV"),
                        _type_card("VD Analysis", "Vessel density\nSCP/DCP pairs",
                                   Icons.GRID_ON_ROUNDED, "VD_SINGLE"),
                        _type_card("Integrated\nVD + MNV", "Full pipeline\nboth analyses",
                                   Icons.AUTO_AWESOME_ROUNDED, "INTEGRATED"),
                    ], spacing=14, alignment=ft.MainAxisAlignment.CENTER),
                ], spacing=20)
            elif step == 2:
                return ft.Column([
                    ft.Text("Select image capture scale:", color=TEXT_MUTED, size=13),
                    ft.Text("Quick select:", color=TEXT_MUTED, size=12),
                    ft.Row([_scale_btn("3 mm", "3.0"),
                            _scale_btn("4.5 mm", "4.5"),
                            _scale_btn("6 mm", "6.0")], spacing=10),
                    ft.Text("Or enter manually:", color=TEXT_MUTED, size=12),
                    scale_field,
                ], spacing=14)
            elif step == 2.5:
                if atype == "MNV":
                    return ft.Column([
                        ft.Text("Flow Deficit (FD) Analysis Options", size=15,
                                weight=FontWeight.BOLD, color=Colors.WHITE),
                        ft.Container(
                            content=ft.Column([
                                ft.Row([
                                    ft.Icon(Icons.INFO_OUTLINE_ROUNDED,
                                            color=Colors.AMBER_400, size=18),
                                    ft.Text(
                                        "Single MNV mode: no paired CC image (*4.tif) required.",
                                        color=Colors.AMBER_400, size=12),
                                ], spacing=8),
                                ft.Divider(color=Colors.with_opacity(0.1, Colors.WHITE)),
                                ft.Row([
                                    ft.Column([
                                        ft.Text("Use same image for FD Analysis",
                                                size=14, weight=FontWeight.W_500,
                                                color=Colors.WHITE),
                                        ft.Text(
                                            "Self-referential CC: FD R1/R2/R3 computed\n"
                                            "using the MNV image itself as CC source.",
                                            size=11, color=TEXT_MUTED),
                                    ], expand=True),
                                    fd_switch,
                                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                            ], spacing=10),
                            padding=18,
                            bgcolor=Colors.with_opacity(0.05, Colors.WHITE),
                            border_radius=12,
                            border=ft.border.all(1, Colors.with_opacity(0.1, Colors.WHITE)),
                        ),
                        ft.Text("• OFF: All FD values = 0 (standard when no CC image).",
                                size=11, color=TEXT_MUTED),
                        ft.Text("• ON: Useful for standalone scans without a dedicated CC image.",
                                size=11, color=TEXT_MUTED),
                        ft.Divider(height=8, color=Colors.with_opacity(0.08, Colors.WHITE)),
                        ft.Container(
                            content=ft.Column([
                                ft.Row([
                                    ft.Column([
                                        ft.Text("Image selection",
                                                size=14, weight=FontWeight.W_500,
                                                color=Colors.WHITE),
                                        ft.Text(
                                            "Auto: exclude *1/*2/*4 and image1/2/4.\n"
                                            "All images: analyze every file in the folder.",
                                            size=11, color=TEXT_MUTED),
                                    ], expand=True),
                                    ft.Column([
                                        ft.Text("自動選択", size=11, color=TEXT_MUTED),
                                        mnv_select_switch,
                                        ft.Text("全ての画像解析", size=11, color=TEXT_MUTED),
                                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=4),
                                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                            ], spacing=8),
                            padding=18,
                            bgcolor=Colors.with_opacity(0.05, Colors.WHITE),
                            border_radius=12,
                            border=ft.border.all(1, Colors.with_opacity(0.1, Colors.WHITE)),
                        ),
                    ], spacing=12)
                else:
                    return ft.Column([
                        ft.Text("VD Analysis Settings", size=15,
                                weight=FontWeight.BOLD, color=Colors.WHITE),
                        ft.Text("Configure file suffixes for SCP/DCP image pairs:",
                                color=TEXT_MUTED, size=13),
                        ft.Row([vd_sup_f, vd_deep_f, vd_side_dd], spacing=14),
                        ft.Row(
                            [
                                ft.Column(
                                    [
                                        ft.Text(
                                            "SCP/DCP pair mode (Integrated-style)",
                                            size=14,
                                            weight=FontWeight.W_500,
                                            color=Colors.WHITE,
                                        ),
                                        ft.Text(
                                            "ON: matched pairs only; unpaired skipped. "
                                            "OFF: each file analyzed independently.",
                                            size=11,
                                            color=TEXT_MUTED,
                                        ),
                                    ],
                                    expand=True,
                                ),
                                vd_pair_sw,
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        ft.Text(
                            "Default suffixes: superficial=1.tif, deep=2.tif. "
                            "Clear deep suffix to force single-image mode.",
                            size=11, color=TEXT_MUTED),
                    ], spacing=14)
            else:  # step == 3
                _labels = {"MNV": "MNV Analysis",
                           "VD_SINGLE": "VD Analysis (single folder)",
                           "INTEGRATED": "Integrated VD + MNV"}
                def _row(icon, lbl, val):
                    return ft.Row([
                        ft.Icon(icon, size=16, color=ACCENT),
                        ft.Text(f"{lbl}:", size=13, color=TEXT_MUTED, width=120),
                        ft.Text(val, size=13, weight=FontWeight.W_500,
                                color=Colors.WHITE),
                    ], spacing=8)
                rows = [
                    _row(Icons.SCIENCE_ROUNDED, "Analysis", _labels[atype]),
                    _row(Icons.STRAIGHTEN_ROUNDED, "Scale",
                         f"{wizard['scale_mm']} mm"),
                ]
                if atype == "MNV":
                    fd_lbl = ("ON (self-referential)"
                              if wizard["mnv_fd_self_ref"] else "OFF (FD = 0)")
                    rows.append(_row(Icons.WATER_DROP_ROUNDED, "FD Analysis", fd_lbl))
                    sel_lbl = ("全ての画像解析"
                               if wizard["mnv_select_all_images"] else "自動選択 (suffix filter)")
                    rows.append(_row(Icons.FILTER_LIST_ROUNDED, "MNV images", sel_lbl))
                elif atype in ("VD_SINGLE", "INTEGRATED"):
                    pair_txt = "pair mode ON" if wizard.get("vd_use_pairs", True) else "single-image mode"
                    rows.append(_row(Icons.SETTINGS_ROUNDED, "VD suffixes",
                                     f"sup={wizard['vd_sup']}  deep={wizard['vd_deep']}  ({pair_txt})"))
                    rows.append(_row(Icons.REMOVE_RED_EYE_ROUNDED, "Eye side",
                                     wizard["vd_side_val"]))
                return ft.Column([
                    ft.Text("Settings confirmed — select your data folder:",
                            color=TEXT_MUTED, size=13),
                    ft.Container(
                        content=ft.Column(rows, spacing=10), padding=16,
                        bgcolor=Colors.with_opacity(0.05, Colors.WHITE),
                        border_radius=12,
                        border=ft.border.all(1, Colors.with_opacity(0.15, ACCENT)),
                    ),
                    ft.Text(
                        "Click ‘Select Folder →’, open the folder that holds your OCTA images, "
                        "then Confirm. You do not need to click individual images — "
                        "if you do, the whole folder is still analyzed.",
                        size=12,
                        color=TEXT_MUTED,
                    ),
                ], spacing=14)

        def _step_lbl():
            atype = wizard["analysis_type"]
            return {
                1: "Step 1 of 3 — Analysis Type",
                2: "Step 2 of 3 — Image Scale",
                2.5: ("Step 2.5 — FD Options" if atype == "MNV"
                      else "Step 2.5 — VD Settings"),
                3: "Step 3 of 3 — Confirm & Select Folder",
            }.get(wizard["step"], "")

        dlg = ft.AlertDialog(
            modal=True, bgcolor=GLASS_BG,
            title=ft.Text("", size=18, weight=FontWeight.BOLD, color=Colors.WHITE),
            content=ft.Container(width=560, height=380),
            actions=[], actions_alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        async def _cancel(_=None):
            ctx.page.close(dlg)

        async def _back(_=None):
            s = wizard["step"]
            wizard["step"] = {2: 1, 2.5: 2, 3: 2.5}.get(s, 1)
            _refresh()

        async def _next(_=None):
            s = wizard["step"]
            if s == 2:
                try:
                    v = float(wizard["scale_mm"])
                    wizard["scale_mm"] = str(v) if v > 0 else "6.0"
                except (ValueError, TypeError):
                    wizard["scale_mm"] = "6.0"
            wizard["step"] = {1: 2, 2: 2.5, 2.5: 3}.get(s, 3)
            _refresh()

        async def _select_folder(_=None):
            analysis_type.value = wizard["analysis_type"]
            scale_mm.value = wizard["scale_mm"]
            vd_sup_suffix.value = wizard["vd_sup"]
            vd_deep_suffix.value = wizard["vd_deep"]
            vd_side.value = wizard["vd_side_val"]
            ctx.page.session.set("vd_use_pair_mode", bool(wizard.get("vd_use_pairs", True)))
            vd_pair_mode_switch.value = bool(wizard.get("vd_use_pairs", True))
            ctx.page.session.set("mnv_fd_self_ref", wizard["mnv_fd_self_ref"])
            ctx.page.session.set("mnv_select_all_images", bool(wizard["mnv_select_all_images"]))
            mnv_select_all_switch.value = bool(wizard["mnv_select_all_images"])
            ctx.page.close(dlg)
            await show_folder_explorer("Select Analysis Folder",
                                       on_select=load_batch_from_directory)

        HEIGHT = {1: 310, 2: 330, 2.5: 370, 3: 340}

        def _refresh():
            step = wizard["step"]
            dlg.title = ft.Text(_step_lbl(), size=18,
                                weight=FontWeight.BOLD, color=Colors.WHITE)
            dlg.content = ft.Container(
                content=_build_content(), width=560,
                height=HEIGHT.get(step, 340),
                padding=ft.padding.symmetric(vertical=10, horizontal=4),
            )
            back_btn = (ft.TextButton("← Back",
                                      on_click=lambda _: ctx.page.run_task(_back))
                        if step > 1 else ft.Container(width=80))
            if step == 3:
                act = ft.ElevatedButton(
                    "Select Folder →", icon=Icons.FOLDER_OPEN,
                    bgcolor=ACCENT, color=Colors.BLACK,
                    on_click=lambda _: ctx.page.run_task(_select_folder))
            else:
                act = ft.ElevatedButton(
                    "Next →", bgcolor=ACCENT, color=Colors.BLACK,
                    on_click=lambda _: ctx.page.run_task(_next))
            dlg.actions = [
                ft.TextButton("Cancel",
                              on_click=lambda _: ctx.page.run_task(_cancel)),
                ft.Row([back_btn, act], spacing=10),
            ]
            ctx.page.update()

        _refresh()
        ctx.page.open(dlg)

    _is_sr = is_second_reader(ctx.page.session)
    second_reader_card = ft.Container(
        visible=_is_sr,
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(Icons.PEOPLE_ALT_ROUNDED, size=28, color=Colors.AMBER_400),
                        ft.Text(
                            "第2リーダー（二重読影）モード",
                            size=15,
                            weight=FontWeight.BOLD,
                            color=Colors.WHITE,
                        ),
                    ],
                    spacing=10,
                ),
                ft.Text(
                    "第1グレーダーの出力フォルダ（メタデータ export の親フォルダ）を選択すると、"
                    "エキスポート済み画像を自動スキャンして順次読影します。"
                    "読影完了後に Save CSV を押すと「統合解析データ」ボタンが表示され、"
                    "第1グレーダーCSVと RPD≤20% ルールで統合できます。",
                    size=11,
                    color=TEXT_MUTED,
                ),
                ft.ElevatedButton(
                    "第2リーダー読影を開始（自動スキャン）",
                    icon=Icons.TRAVEL_EXPLORE_ROUNDED,
                    bgcolor=Colors.AMBER_400,
                    color=Colors.BLACK,
                    on_click=lambda _: ctx.page.run_task(handle_second_reader_start),
                    width=340,
                ),
            ],
            spacing=10,
        ),
        padding=18,
        bgcolor=Colors.with_opacity(0.08, Colors.AMBER_400),
        border=ft.border.all(2, Colors.with_opacity(0.45, Colors.AMBER_400)),
        border_radius=16,
    )

    return ft.Container(
        content=ft.Column([
            ft.Container(
                content=ft.Row(
                    [
                        ft.Column(
                            [
                                ft.Text(
                                    "ARIAKE OCTA",
                                    size=26,
                                    weight=FontWeight.W_800,
                                    color=Colors.WHITE,
                                ),
                                ft.Text(
                                    "Unified Analytics Command Center"
                                    + (" — 第2リーダー" if _is_sr else ""),
                                    size=12,
                                    color=TEXT_MUTED,
                                ),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                margin=ft.margin.only(bottom=12, top=0),
            ),

            second_reader_card,
            ft.Divider(height=10, color=Colors.TRANSPARENT) if _is_sr else ft.Container(height=0),

            ft.Container(
                content=ft.Column([
                    # ── Primary action ────────────────────────────────────
                    ft.Text("Launch Analysis", size=16,
                            weight=FontWeight.BOLD, color=PRIMARY),
                    ft.Container(
                        visible=_is_web(),
                        content=ft.Text(
                            "Web mode: folder browser uses server-side paths. "
                            "Paths must exist on the host running the API.",
                            size=11, color=TEXT_MUTED,
                        ),
                    ),
                    ft.Row(
                        [
                            ft.Container(
                                content=ft.Column(
                                    [
                                        ft.Icon(Icons.ROCKET_LAUNCH_ROUNDED,
                                                size=40, color=PRIMARY),
                                        ft.Text("Guided Analysis Wizard",
                                                size=15, color=Colors.WHITE,
                                                weight=FontWeight.BOLD),
                                        ft.Text(
                                            "Select analysis type, scale, and options "
                                            "before choosing your data folder.",
                                            size=11, color=TEXT_MUTED,
                                            text_align=ft.TextAlign.CENTER,
                                        ),
                                        ft.ElevatedButton(
                                            "Launch Analysis",
                                            icon=Icons.PLAY_ARROW_ROUNDED,
                                            bgcolor=PRIMARY,
                                            color=Colors.BLACK,
                                            on_click=lambda _: ctx.page.run_task(
                                                show_launch_wizard),
                                            width=260,
                                            style=ft.ButtonStyle(
                                                shape=ft.RoundedRectangleBorder(
                                                    radius=10)),
                                        ),
                                    ],
                                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                    spacing=8,
                                ),
                                padding=ft.padding.symmetric(horizontal=24, vertical=18),
                                bgcolor=Colors.with_opacity(0.07, PRIMARY),
                                border=ft.border.all(
                                    2, Colors.with_opacity(0.35, PRIMARY)),
                                border_radius=16,
                                width=520,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),

                    ft.Divider(height=10, color=Colors.TRANSPARENT),

                    # ── Advanced Settings (collapsible) ───────────────────
                    ft.ExpansionTile(
                        title=ft.Text("⚙  Advanced Settings",
                                      size=14, color=TEXT_MUTED),
                        subtitle=ft.Text(
                            "Direct access to analysis type, scale, VD suffixes, "
                            "and output path — for expert use.",
                            size=11, color=Colors.with_opacity(0.5, TEXT_MUTED),
                        ),
                        initially_expanded=False,
                        tile_padding=ft.padding.symmetric(horizontal=0),
                        controls=[
                            ft.Column([
                                ft.Row([
                                    analysis_type,
                                    scale_mm,
                                    manual_path,
                                ], spacing=20,
                                    vertical_alignment=ft.CrossAxisAlignment.END),
                                ft.Row([
                                    output_path_input,
                                    ft.IconButton(
                                        Icons.FOLDER_OPEN,
                                        on_click=lambda _: ctx.page.run_task(
                                            handle_select_output_folder),
                                        tooltip="Select Output Folder",
                                    ),
                                ], spacing=10,
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER),
                                ft.Row(
                                    [institution_dd, institution_custom],
                                    spacing=16,
                                    vertical_alignment=ft.CrossAxisAlignment.END,
                                ),
                                ft.Text(
                                    "Institution code → export/images|masks|meta/{institution_id}/ "
                                    "(Login name = rater_id). Override with env ARIAKE_INSTITUTION_ID.",
                                    size=11, color=TEXT_MUTED,
                                ),
                                ft.Row(
                                    [vd_sup_suffix, vd_deep_suffix, vd_side, vd_pair_mode_switch],
                                    spacing=16,
                                    vertical_alignment=ft.CrossAxisAlignment.END,
                                ),
                                ft.Row(
                                    [mnv_select_all_switch],
                                    spacing=16,
                                    vertical_alignment=ft.CrossAxisAlignment.END,
                                ),
                                ft.Text(
                                    "MNV: auto-select excludes *1/*2/*4; toggle ON for all images.  "
                                    "VD: pair mode matches SCP+DCP by suffix (like Integrated); "
                                    "single-image mode analyzes every file.  "
                                    "Integrated: VD pairs first, then MNV ROI queue.",
                                    size=11, color=TEXT_MUTED,
                                ),
                                ft.ElevatedButton(
                                    "Select Folder (Advanced)",
                                    icon=Icons.FOLDER_OPEN,
                                    bgcolor=Colors.with_opacity(0.15, PRIMARY),
                                    color=PRIMARY,
                                    on_click=lambda _: ctx.page.run_task(
                                        handle_select_folder),
                                    width=260,
                                ),
                            ], spacing=12),
                        ],
                    ),

                    ft.Divider(height=10, color=Colors.TRANSPARENT),
                    batch_container,
                ], spacing=10),
                padding=16,
                bgcolor=GLASS_BG,
                border_radius=16,
            )
        ], scroll=ft.ScrollMode.ADAPTIVE, spacing=0),
        padding=ft.padding.symmetric(horizontal=28, vertical=16),
        expand=True,
        opacity=1.0,
    )
