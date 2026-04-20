import flet as ft
from flet import Colors, Icons, FontWeight, alignment, Animation, AnimationCurve
import asyncio
import uuid
from pathlib import Path

# Components
from components.shared import PRIMARY, BG_DARK, TEXT_MUTED, BackendClient, AppContext

# Pages
from pages.dashboard import get_dashboard_view
from pages.roi_selection import get_roi_view
from pages.mnv_wizard import get_mnv_view
from pages.vd_pairing import get_vd_view
from pages.results_screen import get_results_view
from pages.login import get_login_view

UPLOAD_ROOT = Path(__file__).resolve().parent / "uploads"

def _pick_first_image_in_dir(d: Path):
    patterns = (
        "*.tif", "*.tiff", "*.TIF", "*.TIFF",
        "*.png", "*.PNG", "*.jpg", "*.jpeg", "*.JPEG", "*.bmp",
    )
    found = []
    for pat in patterns:
        found.extend(d.glob(pat))
    if not found:
        return None
    found.sort(key=lambda x: x.name.lower())
    return found[0]

async def main(page: ft.Page):
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    
    # Initialize Backend Client and App Context
    client = BackendClient()
    ctx = AppContext(page, client)
    
    # Color Palette & Styling
    page.title = "ARIAKE OCTA - Advanced Retinal Analysis"
    page.theme_mode = ft.ThemeMode.DARK
    page.window_width = 1200
    page.window_height = 900
    page.padding = 0
    page.spacing = 0
    page.bgcolor = BG_DARK

    def on_error(e):
        print(f"Global Error: {e.data}")
        if "AssertionError" in str(e.data) or "ENTITLEMENT_NOT_FOUND" in str(e.data):
             return 
        try:
            snack = ft.SnackBar(
                content=ft.Row([
                    ft.Icon(Icons.ERROR_OUTLINE, color=Colors.RED_400),
                    ft.Text(f"Error: {e.data}", color=Colors.WHITE, expand=True)
                ]),
                bgcolor=Colors.RED_900,
                duration=4000,
            )
            page.overlay.append(snack)
            snack.open = True
            page.update()
        except:
            pass

    page.on_error = on_error

    async def process_target_path(target: str):
        if not target:
            return
        target = str(Path(target).expanduser()).strip()
        p = Path(target)
        if not p.exists():
            ctx.add_to_console(f"Path does not exist: {target}", "ERROR")
            return

        analysis_mode = ctx.analysis_type_ref.current.value if ctx.analysis_type_ref.current else "MNV"

        if analysis_mode == "MNV" and p.is_dir():
            picked = _pick_first_image_in_dir(p)
            if picked is None:
                ctx.add_to_console("No TIFF/PNG/JPEG images in selected folder.", "ERROR")
                return
            target = str(picked.resolve())
            p = picked
            ctx.add_to_console(f"Folder selected → using {p.name}", "INFO")
        elif analysis_mode == "MNV" and not p.is_file():
            ctx.add_to_console("MNV requires an image file or a folder that contains images.", "ERROR")
            return

        snack = ft.SnackBar(ft.Text(f"Processing: {Path(target).name}"), bgcolor=PRIMARY)
        page.overlay.append(snack)
        snack.open = True
        page.update()

        ctx.add_to_console(f"Analyzing structure: {target}", "INFO")
        info = await client.detect_type(target)
        detected_type = str(info.get("type", "unknown"))

        page.session.set("target_path", target)
        page.session.set("scale", float(ctx.scale_mm_ref.current.value if ctx.scale_mm_ref.current else 6.0))

        if analysis_mode == "VD_BATCH" or analysis_mode == "VD_SINGLE" or detected_type == "VD":
            ctx.add_to_console("Launch Sequence: VD Analytics. Navigating...", "INFO")
            page.go("/vd")
        elif analysis_mode == "MNV" or detected_type == "MNV":
            ctx.add_to_console("Launch Sequence: MNV Analysis. Navigating...", "INFO")
            page.go("/roi")
        else:
            if Path(target).is_dir():
                ctx.add_to_console("Fallback: Folder detected. Navigating to VD...", "INFO")
                page.go("/vd")
            else:
                ctx.add_to_console("Fallback: File detected. Navigating to MNV...", "INFO")
                page.go("/roi")

    ctx.process_target_path = process_target_path

    async def on_file_result(e: ft.FilePickerResultEvent):
        if e.files:
            f = e.files[0]
            client_path = (f.path or "").strip()
            if client_path and Path(client_path).exists():
                await process_target_path(client_path)
                return
            try:
                unique_name = f"{uuid.uuid4().hex}_{f.name}"
                ctx.file_picker.upload(
                    [
                        ft.FilePickerUploadFile(
                            name=f.name,
                            upload_url=page.get_upload_url(unique_name, 600),
                        )
                    ]
                )
                ctx.add_to_console(f"Uploading {f.name}…", "INFO")
            except Exception as ex:
                ctx.add_to_console(f"Could not start upload: {ex}", "ERROR")
        elif e.path:
            await process_target_path(e.path)

    def on_upload_complete(e: ft.FilePickerUploadEvent):
        if e.error:
            ctx.add_to_console(f"Upload error: {e.error}", "ERROR")
            return
        if e.progress is not None and e.progress < 1.0:
            return
        dest = (UPLOAD_ROOT / e.file_name).resolve()
        if not dest.is_file():
            ctx.add_to_console(f"Upload finished but file missing: {dest}", "ERROR")
            return
        ctx.add_to_console(f"Upload saved: {dest.name}", "INFO")
        page.run_task(process_target_path, str(dest))

    async def on_directory_result(e: ft.FilePickerResultEvent):
        if e.path:
            dest_dir = Path(e.path)
            res_data = page.session.get("last_result")
            is_vd = page.session.get("is_vd_result")
            
            import time
            csv_content = await client.export_csv(res_data, is_vd=is_vd)
            csv_path = dest_dir / f"ARIAKE_Results_{int(time.time())}.csv"
            with open(csv_path, "w") as f:
                f.write(csv_content)
            
            if not is_vd and res_data.get("visualization_path"):
                src_vis = res_data.get("visualization_path")
                if Path(src_vis).exists():
                    import shutil
                    shutil.copy(src_vis, dest_dir / f"MNV_Visualization_{int(time.time())}.png")
            
            ctx.add_to_console(f"Results saved to: {dest_dir}", "INFO")
            snack = ft.SnackBar(ft.Text(f"Saved to {dest_dir.name}"), bgcolor=PRIMARY)
            page.overlay.append(snack)
            snack.open = True
            page.update()

    file_picker = ft.FilePicker(on_result=on_file_result, on_upload=on_upload_complete)
    directory_picker = ft.FilePicker(on_result=on_directory_result)
    page.overlay.append(file_picker)
    page.overlay.append(directory_picker)
    
    ctx.file_picker = file_picker
    ctx.directory_picker = directory_picker

    # Splash Screen Elements
    logo_icon = ft.Icon(Icons.REMOVE_RED_EYE_OUTLINED, size=150, color=PRIMARY)
    logo_container = ft.Container(content=logo_icon, scale=0.8, animate_scale=Animation(1500, AnimationCurve.ELASTIC_OUT))
    
    title_text = ft.Text("ARIAKE OCTA", size=60, weight=FontWeight.W_900, color=Colors.WHITE)
    title_container = ft.Container(content=title_text, opacity=1.0)
    
    subtitle_text = ft.Text("INITIALIZING BIOMARKER ENGINE...", size=14, color=PRIMARY)
    subtitle_container = ft.Container(content=subtitle_text, opacity=1.0)
    
    splash = ft.Container(
        content=ft.Column([
            logo_container,
            ft.Container(height=20),
            title_container,
            ft.Container(height=10),
            subtitle_container,
        ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        expand=True,
        bgcolor=BG_DARK,
        alignment=alignment.center,
        animate_opacity=Animation(800, AnimationCurve.EASE_OUT)
    )

    page.add(splash)
    
    await asyncio.sleep(0.3)
    logo_container.scale = 1.1
    page.update()
    await asyncio.sleep(0.4)
    title_container.opacity = 1
    page.update()
    await asyncio.sleep(0.6)
    subtitle_container.opacity = 1
    page.update()
    await asyncio.sleep(1.2)
    
    splash.opacity = 0
    page.update()
    await asyncio.sleep(0.6)
    
    # Application Layout
    async def build_main_ui():
        page.clean()
        
        nav_rail = ft.NavigationRail(
            selected_index=0,
            label_type=ft.NavigationRailLabelType.ALL,
            min_width=100,
            min_extended_width=400,
            bgcolor=BG_DARK,
            destinations=[
                ft.NavigationRailDestination(icon=Icons.HOME_ROUNDED, selected_icon=Icons.HOME, label="Home"),
                ft.NavigationRailDestination(icon=Icons.ANALYTICS_ROUNDED, selected_icon=Icons.ANALYTICS, label="MNV Analysis"),
                ft.NavigationRailDestination(icon=Icons.COMPARE_ARROWS_ROUNDED, selected_icon=Icons.COMPARE_ARROWS, label="VD Pairing"),
                ft.NavigationRailDestination(icon=Icons.REMOVE_RED_EYE_ROUNDED, selected_icon=Icons.REMOVE_RED_EYE, label="Results"),
            ],
            on_change=lambda e: page.go(["/", "/mnv", "/vd", "/results"][e.control.selected_index]),
        )

        console_area = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Text("ALPHA DIAGNOSTIC ENGINE CONSOLE", size=10, weight=FontWeight.BOLD, color=PRIMARY),
                    ft.Icon(Icons.CODE, size=12, color=PRIMARY),
                ], alignment=ft.MainAxisAlignment.START, spacing=5),
                ft.ListView(ref=ctx.log_console_ref, expand=True, spacing=2),
            ]),
            height=150,
            bgcolor="#0A0A15",
            padding=15,
            border=ft.border.only(top=ft.border.BorderSide(1, Colors.with_opacity(0.1, Colors.WHITE))),
        )

        is_navigating = False

        async def route_change(route):
            nonlocal is_navigating
            if is_navigating: return
            is_navigating = True
            
            route_map = {"/": 0, "/mnv": 1, "/roi": 1, "/vd": 2, "/results": 3}
            if page.route in route_map:
                nav_rail.selected_index = route_map[page.route]
            
            try:
                if not page.session.get("username") and page.route != "/login":
                    page.go("/login")
                    is_navigating = False
                    return

                page.views.clear()
                
                if page.route == "/login":
                    view_content = await get_login_view(ctx)
                elif page.route == "/":
                    view_content = await get_dashboard_view(ctx)
                elif page.route == "/roi":
                    view_content = await get_roi_view(ctx)
                elif page.route == "/mnv":
                    view_content = await get_mnv_view(ctx)
                elif page.route == "/vd":
                    view_content = await get_vd_view(ctx)
                elif page.route == "/results":
                    view_content = await get_results_view(ctx)
                else:
                    view_content = await get_dashboard_view(ctx)

                page.views.append(
                    ft.View(
                        page.route,
                        [
                            ft.Column([
                                ft.Row([
                                    nav_rail,
                                    ft.VerticalDivider(width=1, color=Colors.with_opacity(0.1, Colors.WHITE)),
                                    view_content
                                ], expand=True),
                                console_area
                            ], expand=True, spacing=0)
                        ],
                        bgcolor=BG_DARK,
                        padding=0
                    )
                )
                page.update()
            except Exception as e:
                ctx.add_to_console(f"Routing Error: {str(e)}", "ERROR")
            finally:
                is_navigating = False

        page.on_route_change = route_change
        page.go("/login")

    await build_main_ui()

if __name__ == "__main__":
    import os
    port = int(os.environ.get("FLET_PORT", 8550))
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    ft.app(
        target=main,
        view=ft.AppView.WEB_BROWSER,
        port=port,
        host="0.0.0.0",
        upload_dir=str(UPLOAD_ROOT),
    )
