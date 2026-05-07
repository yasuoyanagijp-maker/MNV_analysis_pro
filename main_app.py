import flet as ft
from flet import Colors, Icons, FontWeight, Animation, AnimationCurve
import asyncio
import uuid
import traceback
import os
from pathlib import Path

# Components
from src.flet_ui.components.shared import PRIMARY, PRIMARY_GLOW, BG_DARK, TEXT_MUTED, BackendClient, AppContext, session_discard
from src.flet_ui.pages.login import get_login_view
from src.flet_ui.pages.dashboard import get_dashboard_view
from src.flet_ui.pages.results_screen import get_results_view
from src.flet_ui.pages.roi_selection import get_roi_view
from src.flet_ui.pages.mnv_wizard import get_mnv_view

# Configure Uploads
UPLOAD_ROOT = Path("uploads")
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)

DEV_MODE = os.environ.get("DEV_MODE") == "1"


def _flet_use_web() -> bool:
    """
    FLET_USE_WEB: default 1 = browser (WEB_BROWSER / page.web True).
    Set 0 or native|desktop|flet for a native Flet window and OS file dialogs.
    """
    v = (os.environ.get("FLET_USE_WEB") or "1").strip().lower()
    if v in ("0", "false", "no", "n", "native", "desktop", "flet", "flet_app"):
        return False
    return True

async def main(page: ft.Page):
    print("MAIN_START: Initializing app", flush=True)
    page.title = "ARIAKE OCTA - Advanced Retinal Analysis"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = BG_DARK
    page.window.width = 1400
    page.window.height = 900
    page.padding = 0
    
    ctx = AppContext(page, BackendClient())
    
    # Initialize Global Pickers
    # Initialize Global Pickers
    ctx.file_picker = ft.FilePicker()
    ctx.directory_picker = ft.FilePicker()
    ctx.save_file_picker = ft.FilePicker()
    page.overlay.extend([ctx.file_picker, ctx.directory_picker, ctx.save_file_picker])
    
    is_navigating = False

    async def process_target_path(path: str):
        if not path: return
        # Clean path from quotes that often come from copy-pasting or some shell outputs
        path = path.strip().strip("'").strip('"')
        p = Path(path)
        print(f"DEBUG: Processing path: {path}", flush=True)
        try:
            is_dir = p.is_dir()
        except OSError as ose:
            await ctx.add_to_console(f"Cannot access path: {ose}", "ERROR")
            return

        if is_dir:
            loader = getattr(ctx, "folder_batch_loader", None)
            if loader is not None:
                try:
                    await loader(str(p.resolve()))
                except Exception as ex:
                    print(f"DEBUG: folder_batch_loader failed: {ex}", flush=True)
                    await ctx.add_to_console(f"Folder batch failed: {ex}", "ERROR")
            else:
                await ctx.add_to_console(
                    "Folder path paste: open the dashboard (home), then paste again or use Select Folder.",
                    "WARN",
                )
            return

        # Single file
        atype = "MNV"
        if ctx.analysis_type_ref.current:
            atype = ctx.analysis_type_ref.current.value or "MNV"

        if atype == "INTEGRATED":
            await ctx.add_to_console(
                "Integrated Analysis (VD + MNV) requires a folder. Use Select Folder or paste a directory path.",
                "WARN",
            )
            return

        page.session.set("target_path", str(p.absolute()))

        if atype == "MNV":
            session_discard(page.session, "vd_analysis_explicit_path")
            page.go("/roi")
            return

        if atype == "VD_SINGLE":
            session_discard(page.session, "roi")
            session_discard(page.session, "roi_mask_b64")
            page.session.set("vd_analysis_explicit_path", str(p.resolve()))
            page.go("/mnv")
            return

    ctx.process_target_path = process_target_path

    # Debug Mock Data injection
    if DEV_MODE:
        print("!!! [SECURITY WARNING] DEV_MODE IS ACTIVE. LOGIN BYPASSED. !!!", flush=True)
        page.session.set("username", "DEV_USER")
        page.session.set("user", {"username": "DEV_USER", "is_admin": True})
        
        # Inject mock result for instant debugging of /results
        mock_res = {
            "result_type": "MNV",
            "source_filename": "TEST_SCAN_001.png",
            "analysis_timestamp": "2024-04-20 10:00:00",
            "mnv_area_mm2": 0.456,
            "maturity_index": 85.5,
            "visualization_base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=" 
        }
        page.session.set("batch_results", [mock_res])
        page.session.set("last_result", mock_res)

    async def route_change(e):
        nonlocal is_navigating
        if is_navigating: return
        is_navigating = True
        
        route_full = page.route or ""
        base_route = route_full.split("?", 1)[0]
        print(f"DEBUG: NAVIGATING TO {route_full}", flush=True)

        try:
            # Login Guard (Bypassed in DEV_MODE)
            if not DEV_MODE:
                current_user = page.session.get("user") or page.session.get("username")
                if not current_user and base_route != "/login":
                    print(f"DEBUG: Redirecting to /login from {route_full}", flush=True)
                    page.go("/login")
                    is_navigating = False
                    return

            page.views.clear()

            if base_route == "/login":
                view_content = await get_login_view(ctx)
            elif base_route == "/":
                view_content = await get_dashboard_view(ctx)
            elif base_route == "/results":
                view_content = await get_results_view(ctx)
            elif base_route == "/roi":
                view_content = await get_roi_view(ctx)
            elif base_route == "/mnv":
                view_content = await get_mnv_view(ctx)
            else:
                view_content = ft.Text(f"404: {route_full}")

            # Custom Sidebar Implementation (Replacement for NavigationRail to avoid crashes)
            sidebar = ft.Container(
                content=ft.Column([
                    ft.Container(height=20),
                    ft.Icon(Icons.AUTO_AWESOME_ROUNDED, color=PRIMARY, size=40),
                    ft.Container(height=30),
                    ft.IconButton(Icons.HOME_ROUNDED, on_click=lambda _: page.go("/"), tooltip="Home", icon_color=PRIMARY if base_route == "/" else TEXT_MUTED),
                    ft.IconButton(Icons.ANALYTICS_ROUNDED, on_click=lambda _: page.go("/"), tooltip="Analysis", icon_color=PRIMARY if base_route in ["/mnv", "/roi"] else TEXT_MUTED),
                    ft.IconButton(Icons.REMOVE_RED_EYE_ROUNDED, on_click=lambda _: page.go("/results", rt=uuid.uuid4().hex[:10]), tooltip="Results", icon_color=PRIMARY if base_route == "/results" else TEXT_MUTED),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=20),
                width=80,
                bgcolor="#0A0A15",
                border=ft.border.only(right=ft.border.BorderSide(1, Colors.with_opacity(0.1, Colors.WHITE))),
            )

            page.views.append(
                ft.View(
                    route_full,
                    [
                        ft.Row([
                            sidebar if base_route != "/login" else ft.Container(width=0),
                            ft.Container(
                                content=view_content,
                                expand=True,
                                bgcolor=BG_DARK,
                                padding=20
                            )
                        ], expand=True, spacing=0)
                    ],
                    padding=0,
                    bgcolor=BG_DARK
                )
            )
            page.update()
        except Exception as ex:
            print(f"CRITICAL UI ERROR: {traceback.format_exc()}", flush=True)
            page.views.append(ft.View("/error", [ft.Text(f"Error: {str(ex)}", color="red")]))
            page.update()
        finally:
            is_navigating = False

    page.on_route_change = route_change
    
    if DEV_MODE:
        page.go("/results")
    else:
        page.go("/login")

if __name__ == "__main__":
    port = int(os.environ.get("FLET_PORT", 8550))
    use_web = _flet_use_web()
    print(
        f"Flet: FLET_USE_WEB={os.environ.get('FLET_USE_WEB', '1')} -> "
        f"{'web browser' if use_web else 'native window'}",
        flush=True,
    )
    app_kwargs = {
        "target": main,
        "view": ft.AppView.WEB_BROWSER if use_web else ft.AppView.FLET_APP,
        "port": port,
        "upload_dir": str(UPLOAD_ROOT),
    }
    if use_web:
        # Flet builds open_in_browser URL as http://{url_host}:port/... (see flet app.__run_web_server).
        # host=0.0.0.0 makes url_host 0.0.0.0, which most browsers will not load (blank tab). Local dev: 127.0.0.1.
        # Override bind address with FLET_SERVER_IP (e.g. 0.0.0.0 for LAN); open http://127.0.0.1:PORT on same machine.
        app_kwargs["host"] = os.environ.get("FLET_SERVER_IP", "127.0.0.1")
    ft.app(**app_kwargs)
