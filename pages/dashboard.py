import flet as ft
from flet import Colors, Icons, FontWeight
import time
from pathlib import Path
from components.shared import PRIMARY, TEXT_MUTED, GLASS_BG, AppContext

async def get_dashboard_view(ctx: AppContext):
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

    async def on_manual_submit(e):
        await ctx.process_target_path(e.control.value)

    manual_path = ft.TextField(
        label="Manual Path (Paste folder/file path here if picker fails)",
        border_color=PRIMARY,
        expand=True,
        text_size=12,
        height=40,
        on_submit=on_manual_submit
    )

    async def start_unified_analysis(e):
        if manual_path.value:
            await ctx.process_target_path(manual_path.value)
        elif analysis_type.value == "VD_BATCH":
            if ctx.directory_picker:
                ctx.directory_picker.get_directory_path()
        else:
            if ctx.file_picker:
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
                        on_click=handle_item_click,
                        subtitle=ft.Text(item["path"], size=10, color=TEXT_MUTED) if item["name"] == ".." else None
                    )
                )
            ctx.page.update()

        async def confirm_selection(e):
            ctx.page.close(dlg)
            if on_select:
                final_path = state.get("selected_file") or state["path"]
                await on_select(final_path)

        async def cancel_selection(e):
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
                ft.TextButton("Cancel", on_click=cancel_selection),
                ft.ElevatedButton("Confirm Selection", bgcolor=PRIMARY, color=Colors.BLACK, on_click=confirm_selection)
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
                        manual_path
                    ], spacing=20, vertical_alignment=ft.CrossAxisAlignment.END),
                    ft.Divider(height=40, color=Colors.TRANSPARENT),
                    ft.Text("2. Launch Analytics", size=20, weight=FontWeight.BOLD, color=PRIMARY),
                    ft.Row([
                        ft.Container(
                            content=ft.Column([
                                ft.Icon(Icons.DRIVE_FOLDER_UPLOAD_ROUNDED, size=60, color=PRIMARY),
                                ft.Text("Upload/Pick Folder", size=16, color=Colors.WHITE),
                                ft.ElevatedButton(
                                    "Select VD Folder", 
                                    icon=Icons.FOLDER_OPEN,
                                    bgcolor=PRIMARY, 
                                    color=Colors.BLACK,
                                    on_click=upload_folder_direct,
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
                                    "Select MNV Image", 
                                    icon=Icons.IMAGE_OUTLINED,
                                    bgcolor=Colors.AMBER_400, 
                                    color=Colors.BLACK,
                                    on_click=upload_file_direct,
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
