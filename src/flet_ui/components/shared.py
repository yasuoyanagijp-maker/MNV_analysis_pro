import asyncio
import flet as ft
from flet import Colors, Icons, FontWeight, Animation, AnimationCurve
import time
import httpx
from pathlib import Path
from typing import Awaitable, Callable, List, Optional
import uuid

# Custom Theme Colors
PRIMARY = "#00E5FF"  # Cyan Neon
PRIMARY_GLOW = "#00B8D4"
BG_DARK = "#050510"
GLASS_BG = "#151B2B"
TEXT_MUTED = "#8B9BB4"

# Product branding (user-facing). Package/bundle IDs may still use ARIAKE_OCTA paths.
APP_DISPLAY_NAME = "ARIAKE OCTA Pro"
APP_WINDOW_TITLE = "ARIAKE OCTA Pro - Advanced Retinal Analysis"
APP_LOGIN_TITLE = "ARIAKE OCTA Pro"
APP_LOGIN_SUBTITLE = "Researcher Access"


def session_discard(session, key: str) -> None:
    """Remove key if present. Flet SessionStorage has remove() only (no dict-like pop())."""
    if session.contains_key(key):
        session.remove(key)


# Session keys dropped on logout. Keep in sync with results_screen / second_reader.
LOGOUT_SESSION_KEYS = (
    "username",
    "user",
    "reader_role",
    "second_reader_scan_root",
    "second_reader_first_grader_csv",
    "second_reader_csv_path",
    # Final-reader (最終読影者) RECHECK context — must not leak into the next
    # login on the same terminal (別読影者の integrated 出力へ書いてしまう).
    "final_reader_md_path",
    "final_reader_targets",
    "final_reader_recheck_csv",
    "final_reader_adopted_csv",
    "final_reader_prefix",
    "final_reader_csv_path",
    "export_logout_ready",
    "grdm_graded_institution_id",
    "grdm_pending_institution_id",
    "batch_results",
    "last_result",
    "results_selected_index",
    "batch_csv_auto_saved",
    "output_csv_paths",
    "output_folder",
    "original_input_dir",
    "target_path",
    "original_target_path",
    "roi",
    "roi_mask_b64",
    "mnv_batch_paths",
    "mnv_batch_index",
    "mnv_batch_results",
    "mnv_batch_names_preview",
    "mnv_batch_awaiting_qc",
    "mnv_batch_scales",
    "mnv_batch_scale_stems",
    "mnv_batch_scale_names",
    "mnv_batch_default_fov",
    "mnv_select_all_images",
    "analysis_started_at",
    "analysis_ended_at",
    "analysis_duration_sec",
)


def persist_client_storage_async(page: ft.Page, items: dict) -> None:
    """Write client_storage without blocking the UI event loop.

    Sync ``client_storage.get/set/remove`` uses ``threading.Event.wait`` on the
    Flet UI thread, so the browser reply cannot be processed and each call
    times out after 5s (logout/login appear frozen).
    """

    async def _run():
        cs = getattr(page, "client_storage", None)
        if cs is None:
            return
        for key, value in items.items():
            try:
                await cs.set_async(key, value)
            except Exception as ex:
                print(f"client_storage set_async {key} failed: {ex}", flush=True)

    try:
        page.run_task(_run)
    except Exception as ex:
        print(f"persist_client_storage_async schedule failed: {ex}", flush=True)


def viewport_fit_side(
    page,
    *,
    reserved_w: float = 360,
    reserved_h: float = 280,
    min_side: int = 240,
    max_side: int = 880,
) -> int:
    """Largest square (px) that should fit in the current page without scrolling.

    Uses ``page.width`` / ``page.height`` (web viewport) with ``page.window``
    as fallback for native Flet. Conservative reserved chrome keeps the image
    fully visible below headers, 1/N banners, and action buttons.
    """
    win = getattr(page, "window", None)
    raw_w = getattr(page, "width", None) or getattr(win, "width", None) or 1400
    raw_h = getattr(page, "height", None) or getattr(win, "height", None) or 900
    try:
        w = float(raw_w)
    except (TypeError, ValueError):
        w = 1400.0
    try:
        h = float(raw_h)
    except (TypeError, ValueError):
        h = 900.0
    side = min(w - reserved_w, h - reserved_h)
    return int(max(min_side, min(max_side, side)))


async def logout_to_login(page: ft.Page) -> None:
    """Discard auth/analysis session and navigate to /login.

    Never call synchronous ``page.client_storage`` here — it deadlocks the
    Flet web event loop for up to 5s per RPC.
    """
    session = page.session
    print("LOGOUT: discarding session and navigating to /login", flush=True)
    for key in LOGOUT_SESSION_KEYS:
        try:
            session_discard(session, key)
        except Exception:
            pass
    try:
        from src.utils.grdm_access import clear_grdm_session_institutions

        clear_grdm_session_institutions(session, None)
    except Exception:
        pass

    async def _clear_cs():
        cs = getattr(page, "client_storage", None)
        if cs is None:
            return
        for key in ("grdm_graded_institution_id", "grdm_pending_institution_id"):
            try:
                await cs.remove_async(key)
            except Exception:
                pass

    try:
        page.run_task(_clear_cs)
    except Exception:
        pass
    try:
        page.go("/login", rt=uuid.uuid4().hex[:10])
        print("LOGOUT: page.go(/login) issued", flush=True)
    except Exception as ex:
        print(f"LOGOUT: page.go failed: {ex}", flush=True)


class BackendClient:
    def __init__(self, base_url="http://127.0.0.1:8000"):
        self.base_url = base_url

    async def detect_type(self, path: str):
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(f"{self.base_url}/detect", params={"path": path})
                return response.json()
            except Exception as e:
                return {"type": "unknown", "error": str(e)}

    async def start_mnv_analysis(self, image_path: str, scale: float, roi: dict = None, roi_mask_b64: str = None, intelligent_roi: bool = False, use_self_as_fd: bool = False):
        async with httpx.AsyncClient(timeout=300.0) as client:
            try:
                payload = {
                    "image_path": image_path,
                    "scale_mm": scale,
                    "intelligent_roi": bool(intelligent_roi),
                    "use_self_as_fd": bool(use_self_as_fd),
                }
                if roi_mask_b64:
                    payload["roi_mask_b64"] = roi_mask_b64
                elif roi:
                    payload["roi"] = roi
                response = await client.post(
                    f"{self.base_url}/analyze/mnv",
                    json=payload
                )
                if response.status_code != 200:
                    return {"error": response.json().get("detail", "Unknown API Error")}
                return response.json()
            except Exception as e:
                return {"error": f"Connection Failed: {str(e)}"}

    async def start_vd_analysis(
        self,
        input_dir: str,
        scale: float,
        *,
        side: str = "right",
        sup_suffix: str = "1.tif",
        deep_suffix: str = "2.tif",
        single_image_mode: bool = False,
        single_image_explicit_path: str = None,
    ):
        async with httpx.AsyncClient(timeout=600.0) as client:
            try:
                payload = {
                    "input_dir": str(input_dir),
                    "output_dir": "auto",  # Backend handles this
                    "scale_mm": scale,
                    "side": side,
                    "sup_suffix": sup_suffix,
                    "deep_suffix": deep_suffix,
                    "single_image_mode": single_image_mode,
                }
                if single_image_explicit_path:
                    payload["single_image_explicit_path"] = single_image_explicit_path
                response = await client.post(
                    f"{self.base_url}/analyze/vd",
                    json=payload
                )
                if response.status_code != 200:
                    return {"error": response.json().get("detail", "Unknown VD API Error")}
                return response.json()
            except Exception as e:
                return {"error": f"VD Connection Failed: {str(e)}"}

    async def start_vd_analysis_with_progress(
        self,
        input_dir: str,
        scale: float,
        *,
        side: str = "right",
        sup_suffix: str = "1.tif",
        deep_suffix: str = "2.tif",
        single_image_mode: bool = False,
        single_image_explicit_path: str = None,
        progress_callback: Optional[Callable[..., Awaitable[None]]] = None,
    ):
        """VD with background job + polling so UI can update a progress bar."""
        async with httpx.AsyncClient(timeout=600.0) as client:
            try:
                payload = {
                    "input_dir": str(input_dir),
                    "output_dir": "auto",
                    "scale_mm": scale,
                    "side": side,
                    "sup_suffix": sup_suffix,
                    "deep_suffix": deep_suffix,
                    "single_image_mode": single_image_mode,
                }
                if single_image_explicit_path:
                    payload["single_image_explicit_path"] = single_image_explicit_path
                start_resp = await client.post(
                    f"{self.base_url}/analyze/vd/start",
                    json=payload,
                )
                if start_resp.status_code != 200:
                    return {"error": start_resp.json().get("detail", "Unknown VD start error")}
                job_id = start_resp.json().get("job_id")
                if not job_id:
                    return {"error": "VD start did not return job_id"}

                while True:
                    status_resp = await client.get(
                        f"{self.base_url}/analyze/vd/status/{job_id}",
                    )
                    if status_resp.status_code != 200:
                        return {
                            "error": status_resp.json().get(
                                "detail", "VD progress poll failed"
                            )
                        }
                    snap = status_resp.json()
                    if progress_callback is not None:
                        cb = progress_callback(
                            int(snap.get("current") or 0),
                            int(snap.get("total") or 1),
                            str(snap.get("message") or ""),
                        )
                        if asyncio.iscoroutine(cb):
                            await cb
                    st = snap.get("status")
                    if st == "completed":
                        result = snap.get("result")
                        return result if result is not None else {"error": "Empty VD result"}
                    if st == "failed":
                        return {"error": snap.get("error") or "VD analysis failed"}
                    await asyncio.sleep(0.35)
            except Exception as e:
                return {"error": f"VD Connection Failed: {str(e)}"}

    async def login(self, username, password):
        async with httpx.AsyncClient() as client:
            try:
                payload = {"researcher_name": username, "password": password}
                response = await client.post(f"{self.base_url}/login", json=payload)
                return response.json()
            except Exception as e:
                return {"success": False, "message": f"Connection Error: {str(e)}"}
    
    async def list_dir(self, path=None):
        async with httpx.AsyncClient() as client:
            try:
                params = {"path": path} if path else {}
                response = await client.get(f"{self.base_url}/ls", params=params)
                return response.json()
            except Exception as e:
                return {"error": str(e)}
    
    async def export_csv(self, data, is_vd=False):
        import csv
        import io
        output = io.StringIO()
        writer = csv.writer(output)
        
        if is_vd:
            writer.writerow(["Patient ID", "Sup. Whole", "Deep Whole", "FAZ Area"])
            ids = data.get("patient_ids", [])
            s = data.get("superficial_whole", [])
            d = data.get("deep_whole", [])
            f = data.get("faz_areas", [])
            for i in range(len(ids)):
                s_val = s[i] if i < len(s) else 0.0
                d_val = d[i] if i < len(d) else 0.0
                f_val = f[i] if i < len(f) else 0.0
                writer.writerow([ids[i], s_val, d_val, f_val])
        else:
            writer.writerow(["Metric", "Value", "Unit"])
            writer.writerow(["MNV Area", data.get("mnv_area_mm2", 0), "mm2"])
            writer.writerow(["Vessel Density", data.get("vessel_density", 0), "%"])
            writer.writerow(["Fractal Dimension", data.get("fractal_dimension", 0), "FD"])
        
        return output.getvalue()


class AppContext:
    def __init__(self, page: ft.Page, client: BackendClient):
        self.page = page
        self.client = client
        self.log_console_ref = ft.Ref()
        self.scale_mm_ref = ft.Ref()
        self.analysis_type_ref = ft.Ref()
        self.vd_sup_suffix_ref = ft.Ref()
        self.vd_deep_suffix_ref = ft.Ref()
        self.vd_side_ref = ft.Ref()
        self.file_picker = None
        self.directory_picker = None
        self.output_directory_picker = None
        self.save_file_picker = None
        self.process_target_path = None # Function reference
        # Wired by dashboard: async (folder_path_str) → queue & go ROI (web + manual path paste)
        self.folder_batch_loader: Optional[Callable[[str], Awaitable[None]]] = None

    async def add_to_console(self, message, level="INFO"):
        colors = {"INFO": PRIMARY, "ERROR": Colors.RED_400, "WARN": Colors.AMBER_400}
        color = colors.get(level, PRIMARY)
        timestamp = time.strftime("%H:%M:%S")
        if self.log_console_ref.current:
            self.log_console_ref.current.controls.append(
                ft.Row([
                    ft.Text(f"[{timestamp}]", color=TEXT_MUTED, size=11, font_family="monospace"),
                    ft.Text(f"{level}:", color=color, size=11, weight=FontWeight.BOLD, font_family="monospace"),
                    ft.Text(message, color=Colors.WHITE, size=11, font_family="monospace"),
                ], spacing=10)
            )
            try:
                self.page.update()
            except Exception as e:
                print(f"Console Update Failed: {e}")

    def show_alpha_error(self, title, message, detail=None):
        error_content = ft.Column([
            ft.Row([
                ft.Icon(Icons.REPORT_PROBLEM_ROUNDED, color=Colors.AMBER_400, size=30),
                ft.Text(title, size=20, weight=FontWeight.BOLD, color=Colors.WHITE),
            ], spacing=10),
            ft.Text(message, color=TEXT_MUTED),
        ], spacing=10, tight=True)

        if detail:
            error_content.controls.append(
                ft.ExpansionTile(
                    title=ft.Text("Diagnostic Traceback", size=12, color=Colors.AMBER_200),
                    controls=[
                        ft.Container(
                            content=ft.Text(detail, size=11, font_family="monospace", color=TEXT_MUTED),
                            padding=15,
                            bgcolor=Colors.BLACK,
                            border_radius=10,
                            width=600
                        )
                    ]
                )
            )

        async def on_copy(e):
            self.page.set_clipboard(f"{title}\n{message}\n{detail}")
            
        async def on_dismiss(e):
            self.page.close(dlg)

        dlg = ft.AlertDialog(
            content=ft.Container(error_content, width=650),
            actions=[
                ft.TextButton("Copy Error", on_click=on_copy),
                ft.ElevatedButton("Dismiss", on_click=on_dismiss, bgcolor=PRIMARY, color=Colors.BLACK)
            ],
            bgcolor=GLASS_BG,
        )
        self.page.open(dlg) 


class HoverButton(ft.Container):
    def __init__(self, icon, title, subtitle, on_click):
        super().__init__()
        self.content = ft.Column([
            ft.Icon(icon, size=60, color=PRIMARY),
            ft.Text(title, size=24, weight=FontWeight.W_800, color=Colors.WHITE),
            ft.Text(subtitle, size=14, color=TEXT_MUTED, text_align=ft.TextAlign.CENTER),
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.CENTER, spacing=15)
        self.width = 380
        self.height = 250
        self.bgcolor = Colors.with_opacity(0.05, PRIMARY)
        self.border_radius = 20
        self.border = ft.border.all(1, Colors.with_opacity(0.2, PRIMARY))
        self.padding = 30
        self.ink = True
        self.on_click = on_click
        self.on_hover = self.hover_effect
        self.animate = Animation(300, AnimationCurve.EASE_OUT)
        self.animate_scale = Animation(200, AnimationCurve.BOUNCE_OUT)
        self.scale = 1.0

    async def hover_effect(self, e):
        if e.data == "true":
            self.bgcolor = Colors.with_opacity(0.12, PRIMARY)
            self.border = ft.border.all(2, PRIMARY)
            self.scale = 1.03
            self.shadow = ft.BoxShadow(spread_radius=1, blur_radius=25, color=Colors.with_opacity(0.4, PRIMARY))
        else:
            self.bgcolor = Colors.with_opacity(0.05, PRIMARY)
            self.border = ft.border.all(1, Colors.with_opacity(0.2, PRIMARY))
            self.scale = 1.0
            self.shadow = None
        self.update()


def safe_round(val, digits):
    try:
        return round(float(val), digits)
    except (TypeError, ValueError):
        return 0.0
