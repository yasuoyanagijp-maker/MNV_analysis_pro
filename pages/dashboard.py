import flet as ft
from flet import Colors, Icons, FontWeight
import time
from pathlib import Path
import shutil
from datetime import datetime
import asyncio
from components.shared import PRIMARY, TEXT_MUTED, GLASS_BG, AppContext, session_discard
from src.utils.cv2_path import (
    BGR_READ_OK,
    BGR_READ_PERMISSION,
    imread_bgr_outcome,
)
from src.utils.batch_input_filter import filter_mnv_files_for_roi_selection

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
    
    batch_progress = ft.ProgressBar(value=0, width=800, color=PRIMARY, visible=False)
    batch_status_text = ft.Text("", color=TEXT_MUTED, size=12)
    
    def _is_web() -> bool:
        return bool(getattr(ctx.page, "web", False))

    # --- Ensure pickers on overlay (on_result wired after load_batch_from_directory; FilePicker API is sync only) ---
    if ctx.directory_picker not in ctx.page.overlay:
        ctx.page.overlay.append(ctx.directory_picker)
    if ctx.file_picker not in ctx.page.overlay:
        ctx.page.overlay.append(ctx.file_picker)
    ctx.page.update()
    
    analysis_type = ft.Dropdown(
        label="Analysis Type",
        options=[
            ft.dropdown.Option("MNV", "MNV Analysis (Single Image)"),
            ft.dropdown.Option("VD_SINGLE", "VD Analysis (Single Image)"),
            ft.dropdown.Option("VD_BATCH", "VD Analysis (Batch Folder)"),
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

    manual_path = ft.TextField(
        label="Manual Path (Paste folder/file path here if picker fails)",
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

    async def start_unified_analysis(e):
        if manual_path.value:
            await ctx.process_target_path(manual_path.value)
        elif analysis_type.value == "VD_BATCH":
            if _is_web():
                print("DEBUG: [VD_BATCH] web — using server folder explorer (get_directory_path unsupported in browser)", flush=True)
                await show_folder_explorer("Select VD batch folder (server path)", on_select=load_batch_from_directory)
            elif ctx.directory_picker:
                ctx.directory_picker.get_directory_path()
        else:
            if _is_web():
                print("DEBUG: [SINGLE] web — using server path explorer", flush=True)
                await show_folder_explorer("Select image (server path)", on_select=ctx.process_target_path)
            elif ctx.file_picker:
                ctx.file_picker.pick_files(allow_multiple=False)

    async def show_folder_explorer(title="Select Folder", on_select=None):
        explorer_list = ft.ListView(expand=True, spacing=5)
        current_path_text = ft.Text(size=12, color=TEXT_MUTED, weight=FontWeight.BOLD)
        selection_hint = ft.Text("", size=11, color=PRIMARY)
        
        state = {"path": str(Path.home()), "selected_file": None}
        
        async def load_dir(target_path):
            state["path"] = target_path
            state["selected_file"] = None
            selection_hint.value = ""
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
                    selection_hint.value = f"Selected file: {path}"
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
                    current_path_text,
                    selection_hint,
                    ft.Divider(color=Colors.with_opacity(0.1, Colors.WHITE)),
                    ft.Container(explorer_list, height=400, border=ft.border.all(1, Colors.with_opacity(0.1, Colors.WHITE)), border_radius=10),
                ], spacing=10),
                width=600,
                height=500
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

    intelligent_roi_switch = ft.Switch(label="Intelligent ROI", value=True, active_color=PRIMARY)
    ctx.intelligent_roi_ref.current = intelligent_roi_switch
    staging_copy_switch = ft.Switch(
        label="Staging copy (OneDrive-safe batch)",
        value=True,
        active_color=PRIMARY,
    )

    async def run_batch_preflight():
        """
        Validate queued files before analysis so failures are actionable.
        Returns list[bool] aligned with batch_table.rows indicating readiness.
        """
        readiness = [True] * len(batch_table.rows)
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

    # --- BATCH PROCESSING LOGIC ---
    async def run_batch_analysis(e):
        if not batch_table.rows:
            return
            
        start_button.disabled = True
        batch_progress.visible = True
        batch_progress.value = 0
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
                all_results.append(
                    {"error": "Preflight failed (unreadable/missing)", "source_filename": filename, "status": "failed"}
                )
                batch_progress.value = (i + 1) / total
                ctx.page.update()
                continue
            
            batch_status_text.value = f"Processing ({i+1}/{total}): {filename}..."
            row.cells[3].content.value = "Processing..."
            row.cells[3].content.color = Colors.AMBER_400
            ctx.page.update()
            
            try:
                if analysis_mode == "MNV":
                    res = await ctx.client.start_mnv_analysis(
                        image_path=file_path,
                        scale=float(scale_mm.value),
                        intelligent_roi=intelligent_roi_switch.value
                    )
                else:
                    pfp = Path(file_path)
                    vd_dir = str(pfp.resolve()) if pfp.is_dir() else str(pfp.parent.resolve())
                    single_im = analysis_mode == "VD_SINGLE"
                    ck = _vd_cache_key(vd_dir, single_im)
                    if ck in vd_folder_cache:
                        res = vd_folder_cache[ck]
                    else:
                        res = await ctx.client.start_vd_analysis(
                            vd_dir,
                            float(scale_mm.value),
                            side=str(vd_side.value or "right"),
                            sup_suffix=(vd_sup_suffix.value or "").strip() or "1.tif",
                            deep_suffix=(vd_deep_suffix.value or "").strip() or "2.tif",
                            single_image_mode=single_im,
                        )
                        vd_folder_cache[ck] = res

                if "error" in res:
                    raise Exception(res["error"])

                row.cells[3].content.value = "Success"
                row.cells[3].content.color = Colors.GREEN_400
                if analysis_mode == "MNV":
                    all_results.append(res)
                else:
                    out = dict(res)
                    if not Path(file_path).is_dir():
                        out["source_filename"] = filename
                    all_results.append(out)
                
            except Exception as ex:
                print(f"Batch Error on {filename}: {str(ex)}")
                row.cells[3].content.value = "Failed"
                row.cells[3].content.color = Colors.RED_400
                await ctx.add_to_console(f"Failed [{filename}]: {str(ex)}", "ERROR")
                all_results.append({"error": str(ex), "source_filename": filename, "status": "failed"})
            
            batch_progress.value = (i + 1) / total
            ctx.page.update()

        await ctx.add_to_console(f"Batch analysis complete. {len(all_results)} results processed.", "INFO")
        ctx.page.session.set("batch_results", all_results)
        ctx.page.session.set("last_result", all_results[0] if all_results else None)
        
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
        ctx.page.update()

    async def load_batch_from_directory(fspath: str):
        """Build batch queue from a server-side directory path. Used by desktop FilePicker and web explorer."""
        p = Path(fspath)
        if not p.is_dir():
            await ctx.add_to_console(f"Not a directory: {fspath}", "ERROR")
            return
        await ctx.add_to_console(f"Scanning directory: {p.name}", "INFO")

        patterns = ["*.tif", "*.tiff", "*.png", "*.jpg", "*.jpeg"]
        files = []
        for pat in patterns:
            files.extend(list(p.glob(pat)))
        files.sort(key=lambda x: x.name.lower())

        if not files:
            await ctx.add_to_console("No supported images found in directory.", "ERROR")
            return

        staging_root = None
        staged_files = []
        if staging_copy_switch.value:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            staging_root = Path("uploads") / "batch_staging" / stamp
            staging_root.mkdir(parents=True, exist_ok=True)
            await ctx.add_to_console(f"Staging enabled: copying files to {staging_root}", "INFO")
            for src in files:
                dst = staging_root / src.name
                # Keep first if duplicate names exist; append suffix for collisions.
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
            raw_count = len(files)
            files = filter_mnv_files_for_roi_selection(files, "MNV")
            if not files:
                await ctx.add_to_console(
                    "MNV folder filter removed all files (*1/*2/*4 and image1/2/4 patterns). Nothing to analyze.",
                    "ERROR",
                )
                return
            if len(files) < raw_count:
                await ctx.add_to_console(
                    f"MNV folder filter: {raw_count} → {len(files)} file(s) (Streamlit-aligned suffix rules).",
                    "INFO",
                )
            paths_ordered = [str(f.resolve()) for f in files]
            preview_names = [Path(p).name for p in paths_ordered]
            ctx.page.session.set("mnv_batch_paths", paths_ordered)
            ctx.page.session.set("mnv_batch_index", 0)
            ctx.page.session.set("mnv_batch_results", [])
            ctx.page.session.set("mnv_batch_names_preview", preview_names)
            session_discard(ctx.page.session, "mnv_batch_awaiting_qc")
            session_discard(ctx.page.session, "last_result")
            session_discard(ctx.page.session, "batch_results")
            session_discard(ctx.page.session, "results_selected_index")
            ctx.page.session.set("target_path", paths_ordered[0])
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
        elif batch_plan in ("VD_BATCH", "VD_SINGLE"):
            root_dir = files[0].parent
            total_mb = sum(f.stat().st_size for f in files) / (1024 * 1024)
            sup = (vd_sup_suffix.value or "").strip() or "1.tif"
            deep = (vd_deep_suffix.value or "").strip() or "2.tif"
            mode_label = "VD (pairs)" if batch_plan == "VD_BATCH" else "VD (single)"
            batch_table.rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(
                            ft.Text(
                                f"{mode_label}: {len(files)} images in {root_dir.name} | sup={sup} deep={deep}",
                                size=12,
                            )
                        ),
                        ft.DataCell(ft.Text(mode_label, size=10, color=Colors.BLUE_400)),
                        ft.DataCell(ft.Text(f"{total_mb:.1f} MB (total)", size=11, color=TEXT_MUTED)),
                        ft.DataCell(ft.Text("Ready", color=PRIMARY, size=11)),
                    ],
                    data={"path": str(root_dir.resolve()), "queue_kind": batch_plan},
                )
            )
        else:
            await ctx.add_to_console(f"Unknown analysis type: {batch_plan}", "ERROR")
            return

        batch_container.visible = True
        ctx.page.update()
        await ctx.add_to_console(f"Found {len(files)} images. Auto-starting analysis...", "INFO")
        await run_batch_analysis(None)

    ctx.folder_batch_loader = load_batch_from_directory

    async def _directory_picker_result_async(e: ft.FilePickerResultEvent):
        if not e.path:
            print("DEBUG: [ON_RESULT] Folder selection cancelled.", flush=True)
            return
        print(f"DEBUG: [ON_RESULT] Folder selection event received: {e.path}", flush=True)
        await load_batch_from_directory(e.path)

    def _directory_picker_result(e: ft.FilePickerResultEvent):
        ctx.page.run_task(_directory_picker_result_async, e)

    async def _file_picker_result_async(e: ft.FilePickerResultEvent):
        if not e.files:
            print("DEBUG: [ON_RESULT] File selection cancelled or no files selected.", flush=True)
            return
        target = e.files[0].path
        if target:
            print(f"DEBUG: [ON_RESULT] File selected: {target}", flush=True)
            await ctx.add_to_console(f"File selected: {Path(target).name}", "INFO")
            await ctx.process_target_path(target)
        else:
            print("DEBUG: [ON_RESULT] Path is None", flush=True)

    def _file_picker_result(e: ft.FilePickerResultEvent):
        ctx.page.run_task(_file_picker_result_async, e)

    ctx.directory_picker.on_result = _directory_picker_result
    ctx.file_picker.on_result = _file_picker_result

    async def handle_select_folder(_=None):
        print("DEBUG: [FOLDER] Launching directory picker...", flush=True)
        if _is_web():
            print(
                "DEBUG: [FOLDER] page.web=True — native get_directory_path is not supported in browser; using server path explorer",
                flush=True,
            )
            await show_folder_explorer("Select batch folder (server path)", on_select=load_batch_from_directory)
            return
        if hasattr(ctx, "directory_picker") and ctx.directory_picker is not None:
            print(f"DEBUG: DirectoryPicker found: {ctx.directory_picker}", flush=True)
            print(f"DEBUG: Picker attached to page: {ctx.directory_picker.page is not None}", flush=True)
            ctx.directory_picker.get_directory_path()
            ctx.page.update()
        else:
            print("ERROR: directory_picker is None or missing from Context", flush=True)

    async def handle_select_file(_=None):
        print("DEBUG: [FILE] Launching file picker...", flush=True)
        if _is_web():
            print(
                "DEBUG: [FILE] page.web=True — using server path explorer (reliable local paths in browser mode)",
                flush=True,
            )
            await show_folder_explorer("Select image (server path)", on_select=ctx.process_target_path)
            return
        if hasattr(ctx, "file_picker") and ctx.file_picker is not None:
            print(f"DEBUG: FilePicker found: {ctx.file_picker}", flush=True)
            print(f"DEBUG: Picker attached to page: {ctx.file_picker.page is not None}", flush=True)
            ctx.file_picker.pick_files(allow_multiple=False)
            ctx.page.update()
        else:
            print("ERROR: file_picker is None or missing from Context", flush=True)

    return ft.Container(
        content=ft.Column([
            ft.Container(
                content=ft.Column([
                    ft.Text("ARIAKE OCTA", size=55, weight=FontWeight.W_900, color=Colors.WHITE),
                    ft.Text("Unified Analytics Command Center", size=18, color=TEXT_MUTED),
                ]),
                margin=ft.margin.only(bottom=50, top=20)
            ),
            
            ft.Container(
                content=ft.Column([
                    ft.Text("1. Configure Engine", size=20, weight=FontWeight.BOLD, color=PRIMARY),
                    ft.Row([
                        analysis_type,
                        scale_mm,
                        intelligent_roi_switch,
                        manual_path,
                    ], spacing=20, vertical_alignment=ft.CrossAxisAlignment.END),
                    ft.Row(
                        [
                            vd_sup_suffix,
                            vd_deep_suffix,
                            vd_side,
                        ],
                        spacing=16,
                        vertical_alignment=ft.CrossAxisAlignment.END,
                    ),
                    ft.Text(
                        "Folder batch: choose Analysis Type first. MNV applies *1/*2/*4 + image1/2/4 exclusion, then opens ROI per file; "
                        "after each result use OK for next image or Redo ROI. VD (pairs) uses sup/deep suffixes; VD (single) runs single-image mode on the folder.",
                        size=11,
                        color=TEXT_MUTED,
                    ),
                    ft.Row([staging_copy_switch], spacing=10),
                    ft.Divider(height=40, color=Colors.TRANSPARENT),
                    ft.Text("2. Launch Analytics", size=20, weight=FontWeight.BOLD, color=PRIMARY),
                    ft.Container(
                        visible=_is_web(),
                        padding=ft.padding.only(bottom=4),
                        content=ft.Text(
                            "Web mode: the OS file/folder dialog is not available (Flet). Buttons open a server-side path browser; paths must exist on the host running the API.",
                            size=12,
                            color=TEXT_MUTED,
                        ),
                    ),
                    ft.Row([
                        ft.Container(
                            content=ft.Column([
                                ft.Icon(Icons.DRIVE_FOLDER_UPLOAD_ROUNDED, size=60, color=PRIMARY),
                                ft.Text("Upload/Pick Folder", size=16, color=Colors.WHITE),
                                ft.ElevatedButton(
                                    "Select Folder", 
                                    icon=Icons.FOLDER_OPEN,
                                    bgcolor=PRIMARY, 
                                    color=Colors.BLACK,
                                    on_click=lambda _: ctx.page.run_task(handle_select_folder),
                                    width=250
                                ),
                            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=15),
                            padding=30,
                            bgcolor=Colors.with_opacity(0.05, PRIMARY),
                            border=ft.border.all(1, Colors.with_opacity(0.2, PRIMARY)),
                            border_radius=20,
                            expand=True,
                        ),
                        ft.Container(
                            content=ft.Column([
                                ft.Icon(Icons.AUTO_AWESOME_ROUNDED, size=60, color=Colors.AMBER_400),
                                ft.Text("Upload/Pick Image", size=16, color=Colors.WHITE),
                                ft.ElevatedButton(
                                    "Select Image", 
                                    icon=Icons.IMAGE_OUTLINED,
                                    bgcolor=Colors.AMBER_400, 
                                    color=Colors.BLACK,
                                    on_click=lambda _: ctx.page.run_task(handle_select_file),
                                    width=250
                                ),
                            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=15),
                            padding=30,
                            bgcolor=Colors.with_opacity(0.05, Colors.AMBER_400),
                            border=ft.border.all(1, Colors.with_opacity(0.2, Colors.AMBER_400)),
                            border_radius=20,
                            expand=True,
                        ),
                    ], spacing=20, width=850),
                    ft.Divider(height=40, color=Colors.TRANSPARENT),
                    batch_container
                ], spacing=10),
                padding=30,
                bgcolor=GLASS_BG,
                border_radius=20,
            )
        ], scroll=ft.ScrollMode.ADAPTIVE),
        padding=60,
        expand=True,
        opacity=1.0,
    )
