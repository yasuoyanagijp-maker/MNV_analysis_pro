import flet as ft
from flet import Colors, Icons, FontWeight, Animation, AnimationCurve
import time
import httpx
from pathlib import Path
from typing import List, Optional

# Custom Theme Colors
PRIMARY = "#00E5FF"  # Cyan Neon
PRIMARY_GLOW = "#00B8D4"
BG_DARK = "#050510"
GLASS_BG = "#151B2B"
TEXT_MUTED = "#8B9BB4"

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

    async def start_mnv_analysis(self, image_path: str, scale: float, roi: dict = None, roi_mask_b64: str = None, intelligent_roi: bool = True):
        async with httpx.AsyncClient(timeout=300.0) as client:
            try:
                payload = {
                    "image_path": image_path, 
                    "scale_mm": scale,
                    "intelligent_roi": bool(intelligent_roi)
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

    async def start_vd_analysis(self, input_dir: str, scale: float):
        async with httpx.AsyncClient(timeout=600.0) as client:
            try:
                payload = {
                    "input_dir": str(input_dir),
                    "output_dir": "auto", # Backend handles this
                    "scale_mm": scale
                }
                response = await client.post(
                    f"{self.base_url}/analyze/vd",
                    json=payload
                )
                if response.status_code != 200:
                    return {"error": response.json().get("detail", "Unknown VD API Error")}
                return response.json()
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
        self.intelligent_roi_ref = ft.Ref()
        self.scale_mm_ref = ft.Ref()
        self.analysis_type_ref = ft.Ref()
        self.file_picker = None
        self.directory_picker = None
        self.save_file_picker = None
        self.process_target_path = None # Function reference

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
