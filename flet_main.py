import flet as ft
from flet import Colors, Icons, FontWeight, alignment, Animation, AnimationCurve
import time
import threading
import asyncio
import httpx
from pathlib import Path
import cv2
import numpy as np
import base64
from src.core.fast_region_growing import fast_region_growing

# --- Backend Client ---
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
        # This would normally be a backend call or local file write
        # For the alpha mockup, we simulate CSV generation
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
                writer.writerow([ids[i], s[i], d[i], f[i]])
        else:
            writer.writerow(["Metric", "Value", "Unit"])
            writer.writerow(["MNV Area", data.get("mnv_area_mm2", 0), "mm2"])
            writer.writerow(["Vessel Density", data.get("vessel_density", 0), "%"])
            writer.writerow(["Fractal Dimension", data.get("fractal_dimension", 0), "FD"])
        
        return output.getvalue()

async def main(page: ft.Page):
    # Initialize Backend Client early to avoid coroutine shadowing
    client = BackendClient()
    
    # Color Palette & Styling
    page.title = "ARIAKE OCTA - Advanced Retinal Analysis"
    page.theme_mode = ft.ThemeMode.DARK
    page.window_width = 1200
    page.window_height = 900
    page.padding = 0
    page.spacing = 0
    page.bgcolor = "#050510" # Deep dark blue
    
    # Custom Theme Colors
    PRIMARY = "#00E5FF"  # Cyan Neon
    PRIMARY_GLOW = "#00B8D4"
    BG_DARK = "#050510"
    GLASS_BG = "#151B2B"
    TEXT_MUTED = "#8B9BB4"
    
    # --- Console System ---
    log_console_ref = ft.Ref[ft.ListView]()
    intelligent_roi_ref = ft.Ref[ft.Switch]()
    scale_mm_ref = ft.Ref[ft.Dropdown]()
    analysis_type_ref = ft.Ref[ft.Dropdown]()
    
    def add_to_console(message, level="INFO"):
        colors = {"INFO": PRIMARY, "ERROR": Colors.RED_400, "WARN": Colors.AMBER_400}
        color = colors.get(level, PRIMARY)
        timestamp = time.strftime("%H:%M:%S")
        if log_console_ref.current:
            log_console_ref.current.controls.append(
                ft.Row([
                    ft.Text(f"[{timestamp}]", color=TEXT_MUTED, size=11, font_family="monospace"),
                    ft.Text(f"{level}:", color=color, size=11, weight=FontWeight.BOLD, font_family="monospace"),
                    ft.Text(message, color=Colors.WHITE, size=11, font_family="monospace"),
                ], spacing=10)
            )
            page.update()

    # --- Global Error Handler ---
    def on_error(e):
        print(f"Global Error: {e.data}")
        # Prevent recursive error loops and update failures
        if "AssertionError" in str(e.data) or "ENTITLEMENT_NOT_FOUND" in str(e.data):
             return # Skip showing snackbar for these to avoid loop
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
            pass # Last resort to prevent crash

    page.on_error = on_error

    # --- Alpha Error System ---
    def show_alpha_error(title, message, detail=None):
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

        dlg = ft.AlertDialog(
            content=ft.Container(error_content, width=650),
            actions=[
                ft.TextButton("Copy Error", on_click=lambda _: page.set_clipboard(f"{title}\n{message}\n{detail}")),
                ft.ElevatedButton("Dismiss", on_click=lambda _: page.close(dlg), bgcolor=PRIMARY, color=Colors.BLACK)
            ],
            bgcolor=GLASS_BG,
        )
        page.open(dlg)

    # --- File/Folder Processing Logic ---
    async def process_target_path(target: str):
        if not target: return
        snack = ft.SnackBar(ft.Text(f"Processing: {Path(target).name}"), bgcolor=PRIMARY)
        page.overlay.append(snack)
        snack.open = True
        page.update()
        
        # Smart Detect
        add_to_console(f"Analyzing structure: {target}", "INFO")
        info = await client.detect_type(target)
        detected_type = str(info.get("type", "unknown"))
        
        page.session.set("target_path", target)
        page.session.set("scale", float(scale_mm_ref.current.value if scale_mm_ref.current else 6.0))
        
        # Respect User Override if set on Dashboard
        analysis_mode = analysis_type_ref.current.value if analysis_type_ref else "MNV"
        
        if analysis_mode == "VD_BATCH" or analysis_mode == "VD_SINGLE" or detected_type == "VD":
             add_to_console(f"Launch Sequence: VD Analytics. Navigating...", "INFO")
             page.go("/vd")
        elif analysis_mode == "MNV" or detected_type == "MNV":
             add_to_console(f"Launch Sequence: MNV Analysis. Navigating...", "INFO")
             page.go("/roi")
        else:
            # Fallback path-based navigation
            if Path(target).is_dir():
                 add_to_console(f"Fallback: Folder detected. Navigating to VD...", "INFO")
                 page.go("/vd")
            else:
                 add_to_console(f"Fallback: File detected. Navigating to MNV...", "INFO")
                 page.go("/roi")

    async def on_file_result(e: ft.FilePickerResultEvent):
        if e.files:
            await process_target_path(e.files[0].path)
        elif e.path:
            await process_target_path(e.path)

    async def on_directory_result(e: ft.FilePickerResultEvent):
        if e.path:
            dest_dir = Path(e.path)
            res_data = page.session.get("last_result")
            is_vd = page.session.get("is_vd_result")
            
            # Export CSV
            csv_content = await client.export_csv(res_data, is_vd=is_vd)
            csv_path = dest_dir / f"ARIAKE_Results_{int(time.time())}.csv"
            with open(csv_path, "w") as f:
                f.write(csv_content)
            
            # Export Visualizations if available
            if not is_vd and res_data.get("visualization_path"):
                src_vis = res_data.get("visualization_path")
                if Path(src_vis).exists():
                    import shutil
                    shutil.copy(src_vis, dest_dir / f"MNV_Visualization_{int(time.time())}.png")
            
            add_to_console(f"Results saved to: {dest_dir}", "INFO")
            snack = ft.SnackBar(ft.Text(f"Saved to {dest_dir.name}"), bgcolor=PRIMARY)
            page.overlay.append(snack)
            snack.open = True
            page.update()

    file_picker = ft.FilePicker(on_result=on_file_result)
    directory_picker = ft.FilePicker(on_result=on_directory_result)
    page.overlay.append(file_picker)
    page.overlay.append(directory_picker)
    
    scale_mm_ref = ft.Ref[ft.Dropdown]()
    analysis_type_ref = ft.Ref[ft.Dropdown]()
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

        def hover_effect(self, e):
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

    # --- Views ---
    # --- Custom Explorer View ---
    async def show_folder_explorer(title="Select Folder", on_select=None):
        explorer_list = ft.ListView(expand=True, spacing=5)
        current_path_text = ft.Text(size=12, color=TEXT_MUTED, weight=FontWeight.BOLD)
        
        state = {"path": str(Path.home())}
        
        async def load_dir(target_path):
            state["path"] = target_path
            res = await client.list_dir(target_path)
            if "error" in res:
                add_to_console(f"Explorer Error: {res['error']}", "ERROR")
                return
            
            current_path_text.value = res.get("current_path")
            explorer_list.controls.clear()
            
            async def handle_item_click(e):
                path = e.control.data["path"]
                is_dir = e.control.data["is_dir"]
                if is_dir:
                    await load_dir(path)
                else:
                    # Could handle file selection here if needed
                    pass

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
            page.update()

        async def confirm_selection(e):
            if on_select:
                await on_select(state["path"])
            page.close(dlg)

        dlg = ft.AlertDialog(
            title=ft.Text(title, size=20, weight=FontWeight.BOLD),
            content=ft.Container(
                content=ft.Column([
                    current_path_text,
                    ft.Divider(color=Colors.with_opacity(0.1, Colors.WHITE)),
                    ft.Container(explorer_list, height=400, border=ft.border.all(1, Colors.with_opacity(0.1, Colors.WHITE)), border_radius=10),
                ], spacing=10),
                width=600,
                height=500
            ),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: page.close(dlg)),
                ft.ElevatedButton("Select Current Folder", bgcolor=PRIMARY, color=Colors.BLACK, on_click=confirm_selection)
            ],
            bgcolor=GLASS_BG,
        )
        
        page.open(dlg)
        await load_dir(state["path"])

    async def get_dashboard_view():
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

        manual_path = ft.TextField(
            label="Manual Path (Paste folder/file path here if picker fails)",
            border_color=PRIMARY,
            expand=True,
            text_size=12,
            height=40,
            on_submit=lambda e: page.run_task(process_target_path, e.control.value)
        )

        async def start_unified_analysis(e):
            if manual_path.value:
                await process_target_path(manual_path.value)
            elif analysis_type.value == "VD_BATCH":
                file_picker.get_directory_path()
            else:
                file_picker.pick_files(allow_multiple=False)

        async def upload_folder_direct(e):
             await show_folder_explorer("Select VD Batch Folder", on_select=process_target_path)

        async def upload_file_direct(e):
             # For image, we can either use custom explorer or file picker
             # Let's use custom explorer to be safe on macOS Web
             await show_folder_explorer("Select MNV Image (Navigate and choose folder, then paste filename if needed - or just use current picker)", on_select=process_target_path)

        scale_mm_ref.current = scale_mm
        analysis_type_ref.current = analysis_type

        async def handle_drop(e):
            if hasattr(e, "data") and e.data:
                try:
                    add_to_console(f"Data dropped: {e.data}", "INFO")
                    target = e.data.strip()
                    if target.startswith("[") and target.endswith("]"):
                        import ast
                        paths = ast.literal_eval(target)
                        if isinstance(paths, list) and len(paths) > 0:
                            target = paths[0]
                    await process_target_path(target)
                except Exception as ex:
                    add_to_console(f"Drop error: {str(ex)}", "ERROR")
        
        page.on_drop = handle_drop

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
                            ft.Switch(label="Intelligent ROI", value=True, active_color=PRIMARY, ref=intelligent_roi_ref),
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
                                        on_click=start_unified_analysis, # This defaults to MNV
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

    async def get_roi_view():
        target_path = page.session.get("target_path")

        if not target_path:
            return ft.Container(ft.Text("No image selected.", color=Colors.RED_400))

        add_to_console(f"ROI View: loading {target_path}", "INFO")

        status_text = ft.Text(
            "画像ロード完了後、病変部をクリック＆長押しして領域を抽出してください",
            color=TEXT_MUTED
        )
        a_value_text = ft.Text("", size=18, weight=FontWeight.BOLD, color=PRIMARY)
        load_error_text = ft.Text("", color=Colors.RED_400, visible=False)

        # --- 画像コントロール (最初は非表示) ---
        img_control = ft.Image(fit=ft.ImageFit.CONTAIN, width=500, height=500)

        state = {
            "is_pressing": False,
            "seed_point": None,
            "current_a": 0.5,
            "mask": None,
            "base_img": None,
            "new_w": 500,
            "new_h": 500,
            "scale": 1.0,
        }

        def encode_img_b64(img_arr):
            _, buf = cv2.imencode('.jpg', img_arr, [cv2.IMWRITE_JPEG_QUALITY, 75])
            return base64.b64encode(buf).decode('utf-8')

        async def process_region_growing():
            while state["is_pressing"]:
                base_img = state["base_img"]
                if state["seed_point"] and base_img is not None:
                    mask = fast_region_growing(base_img, state["seed_point"], a=state["current_a"])
                    state["mask"] = mask
                    overlay = base_img.copy()
                    overlay[mask == 255] = [0, 0, 255]
                    blended = cv2.addWeighted(overlay, 0.5, base_img, 0.5, 0)
                    cv2.circle(blended, state["seed_point"], 3, (0, 255, 0), -1)
                    img_control.src_base64 = encode_img_b64(blended)
                    a_value_text.value = f"Extraction Power (a): {state['current_a']:.1f}"
                    page.update()
                state["current_a"] += 0.2
                if state["current_a"] > 6.0:
                    state["current_a"] = 6.0
                await asyncio.sleep(0.05)

        # バックエンドに渡すための非表示スライダー
        x_slider = ft.Slider(min=0, max=10000, value=256, visible=False)
        y_slider = ft.Slider(min=0, max=10000, value=256, visible=False)
        w_slider = ft.Slider(min=1, max=10000, value=512, visible=False)
        h_slider = ft.Slider(min=1, max=10000, value=512, visible=False)

        def on_tap_down(e: ft.ContainerTapEvent):
            if state["is_pressing"] or state["base_img"] is None:
                return
            state["is_pressing"] = True
            state["seed_point"] = (int(e.local_x), int(e.local_y))
            state["current_a"] = 0.5
            status_text.value = "抽出中..."
            status_text.color = Colors.AMBER_400
            page.update()
            page.run_task(process_region_growing)

        def on_tap_up(e):
            if not state["is_pressing"]:
                return
            state["is_pressing"] = False
            status_text.value = "✅ 確定。やり直す場合は再クリック＆長押し"
            status_text.color = Colors.GREEN_400
            if state["mask"] is not None and np.sum(state["mask"]) > 0:
                inv_scale = 1.0 / state["scale"]
                orig_w = int(state["new_w"] * inv_scale)
                orig_h = int(state["new_h"] * inv_scale)
                full_mask = cv2.resize(state["mask"], (orig_w, orig_h), interpolation=cv2.INTER_NEAREST)
                _, buf = cv2.imencode('.png', full_mask)
                state["mask_b64"] = base64.b64encode(buf).decode('utf-8')
                pts = np.argwhere(state["mask"] > 0)
                y_min, x_min = pts.min(axis=0)
                y_max, x_max = pts.max(axis=0)
                x_slider.value = float(x_min * inv_scale)
                y_slider.value = float(y_min * inv_scale)
                w_slider.value = float((x_max - x_min) * inv_scale)
                h_slider.value = float((y_max - y_min) * inv_scale)
            page.update()

        gesture = ft.GestureDetector(
            content=img_control,
            on_tap_down=on_tap_down,
            on_tap_up=on_tap_up,
            on_pan_end=lambda e: on_tap_up(e),
            mouse_cursor=ft.MouseCursor.PRECISE,
        )

        # --- ft.Stack レイアウト: ローディング層 / 画像層 ---
        loading_layer = ft.Container(
            content=ft.Column(
                [
                    ft.ProgressRing(width=50, height=50, stroke_width=4, color=PRIMARY),
                    ft.Text("画像を読み込み中...", color=TEXT_MUTED, size=14),
                    load_error_text,
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=15,
            ),
            width=500, height=500,
            alignment=ft.alignment.center,
            visible=True,
        )
        image_layer = ft.Container(
            content=gesture,
            width=500, height=500,
            visible=False,  # 画像ロード完了後に表示
        )
        img_stack = ft.Container(
            content=ft.Stack([loading_layer, image_layer]),
            width=500, height=500,
            bgcolor=Colors.BLACK,
            border_radius=10,
            border=ft.border.all(1, Colors.with_opacity(0.3, PRIMARY)),
        )

        async def confirm_roi(e):
            roi = {
                "x": int(x_slider.value), "y": int(y_slider.value),
                "w": int(w_slider.value), "h": int(h_slider.value),
            }
            page.session.set("roi", roi)
            if state.get("mask_b64"):
                page.session.set("roi_mask_b64", state["mask_b64"])
            page.go("/mnv")

        # --- 非同期画像ロード (Stack visible 切り替え) ---
        async def load_image_async():
            # route_change の is_navigating=False が確実に完了するまで待機
            await asyncio.sleep(0.3)
            try:
                # run_in_executor でイベントループをブロックしない
                loop = asyncio.get_event_loop()
                base_img = await loop.run_in_executor(
                    None, lambda: cv2.imread(target_path)
                )
                if base_img is None:
                    load_error_text.value = f"❌ 読み込み失敗: {target_path}"
                    load_error_text.visible = True
                    page.update()
                    add_to_console(f"ROI: imread failed for {target_path}", "ERROR")
                    return

                orig_h, orig_w = base_img.shape[:2]
                sc = min(500 / orig_w, 500 / orig_h)
                new_w, new_h = int(orig_w * sc), int(orig_h * sc)
                resized = cv2.resize(base_img, (new_w, new_h))

                state["base_img"] = resized
                state["new_w"] = new_w
                state["new_h"] = new_h
                state["scale"] = sc

                img_control.src_base64 = encode_img_b64(resized)
                img_control.width = new_w
                img_control.height = new_h

                # visible 切り替え（content 変更なし → Flet Web 安全）
                loading_layer.visible = False
                image_layer.visible = True
                status_text.value = "병変部をクリック＆長押しして領域を抽出してください"
                add_to_console(f"ROI: image loaded OK ({new_w}x{new_h})", "INFO")
                page.update()

            except Exception as ex:
                import traceback
                load_error_text.value = f"❌ エラー: {str(ex)}"
                load_error_text.visible = True
                page.update()
                add_to_console(f"ROI load error: {traceback.format_exc()}", "ERROR")

        page.run_task(load_image_async)

        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Column([
                        ft.Text("Step 1: ROI Selection", size=32, weight=FontWeight.BOLD, color=PRIMARY),
                        ft.Text("Long-press / click & hold to expand the lesion area.", color=TEXT_MUTED),
                    ]),
                    ft.ElevatedButton(
                        "Confirm ROI & Proceed", icon=Icons.CHECK_CIRCLE,
                        height=50, bgcolor=PRIMARY, color=Colors.BLACK, on_click=confirm_roi
                    )
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Divider(height=20, color=Colors.TRANSPARENT),
                ft.Row([
                    img_stack,
                    ft.Column([
                        status_text,
                        a_value_text,
                        ft.Divider(height=20, color=Colors.TRANSPARENT),
                        ft.Icon(Icons.TOUCH_APP, size=60, color=PRIMARY),
                        ft.Text("Target the lesion, click & hold, release when covered.", color=TEXT_MUTED),
                    ], expand=True, spacing=15,
                       alignment=ft.MainAxisAlignment.CENTER,
                       horizontal_alignment=ft.CrossAxisAlignment.CENTER)
                ], spacing=40),
                x_slider, y_slider, w_slider, h_slider,
            ], spacing=10, scroll=ft.ScrollMode.ADAPTIVE),
            padding=40,
            expand=True,
            opacity=1.0,
        )


    async def get_mnv_view():
        target_path = page.session.get("target_path")
        scale = page.session.get("scale") or 6.0
        roi = page.session.get("roi")
        
        # Safe path handling
        target_name = "No scan selected"
        if target_path and target_path != "None":
            try:
                target_name = Path(target_path).name
            except:
                target_name = str(target_path)

        status_text = ft.Text("Ready to analyze." if target_path else "Please select an image.", color=TEXT_MUTED)
        progress_bar = ft.ProgressBar(width=400, value=0, visible=False)
        
        async def run_mnv_analysis(e):
            if not target_path: return
            e.control.disabled = True
            progress_bar.visible = True
            add_to_console(f"Starting MNV Analysis for {Path(target_path).name}...", "INFO")
            page.update()
            
            iroi = intelligent_roi_ref.current.value if intelligent_roi_ref.current else True
            roi_mask_b64 = page.session.get("roi_mask_b64")
            result = await client.start_mnv_analysis(target_path, scale, roi=roi, roi_mask_b64=roi_mask_b64, intelligent_roi=iroi)
            
            if "error" in result:
                err_data = result["error"]
                if isinstance(err_data, dict):
                    show_alpha_error(
                        "Analysis Engine Failure",
                        f"The {err_data.get('type', 'Unknown')} failed during processing.",
                        err_data.get("traceback")
                    )
                else:
                    show_alpha_error("Process Interrupted", str(err_data))
                
                status_text.value = "Analysis failed. See diagnostic report."
                status_text.color = Colors.RED_400
                e.control.disabled = False
            else:
                status_text.value = "Analysis Success! Loading result metrics..."
                page.session.set("last_result", result)
                await asyncio.sleep(1.0)
                page.go("/results")
            
            progress_bar.visible = False
            e.control.disabled = False
            page.update()

        auto_start_btn = ft.ElevatedButton(
            "Start MNV Pipeline", 
            icon=Icons.PLAY_CIRCLE_FILL, 
            bgcolor=PRIMARY, 
            color=Colors.BLACK,
            disabled=not target_path,
            on_click=run_mnv_analysis
        )

        return ft.Container(
            content=ft.Column([
                ft.Text("MNV Analysis Wizard", size=32, weight=FontWeight.BOLD, color=Colors.WHITE),
                ft.Text("Real-time automated segmentation and feature extraction.", color=TEXT_MUTED),
                ft.Container(height=30),
                
                ft.Row([
                    ft.Column([ft.Icon(Icons.UPLOAD_FILE, color=PRIMARY), ft.Text("Setup", size=12)], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Container(width=100, height=2, bgcolor=Colors.with_opacity(0.2, Colors.WHITE)),
                    ft.Column([ft.Icon(Icons.AUTO_AWESOME, color=PRIMARY), ft.Text("Processing", size=12)], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Container(width=100, height=2, bgcolor=Colors.with_opacity(0.2, Colors.WHITE)),
                    ft.Column([ft.Icon(Icons.QUERY_STATS, color=TEXT_MUTED), ft.Text("Summary", size=12)], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                ], alignment=ft.MainAxisAlignment.CENTER),
                
                ft.Container(
                    content=ft.Column([
                        ft.Icon(Icons.FILE_PRESENT_ROUNDED, size=80, color=PRIMARY if target_path else TEXT_MUTED),
                        ft.Text(target_name, size=18, color=Colors.WHITE),
                        ft.Text(target_path if target_path else "Launch from dashboard to select file", size=12, color=TEXT_MUTED),
                        ft.Container(height=10),
                        auto_start_btn,
                        status_text,
                        progress_bar,
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=15),
                    padding=60,
                    bgcolor=Colors.with_opacity(0.05, PRIMARY),
                    border=ft.border.all(1, Colors.with_opacity(0.2, PRIMARY)),
                    border_radius=25,
                    width=800,
                ),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, scroll=ft.ScrollMode.ADAPTIVE),
            padding=40,
            expand=True,
            opacity=1.0,
        )

    async def get_vd_view():
        target_path = page.session.get("target_path")
        
        # Real detection of cohorts if path exists
        sup_files = []
        deep_files = []
        
        if target_path and Path(target_path).is_dir():
            all_files = [f.name for f in Path(target_path).glob("*") if f.suffix.lower() in [".tif", ".tiff", ".jpg", ".png"]]
            sup_files = [f for f in all_files if any(s in f.upper() for s in ["_S", "SUPERFICIAL"])]
            deep_files = [f for f in all_files if any(s in f.upper() for s in ["_D", "DEEP"])]
        
        # Fallback to mock if empty for demo purposes
        if not sup_files:
            sup_files = [f"OCTA_Sup_{i}.tif" for i in range(1, 6)]
            deep_files = [f"OCTA_Deep_{i}.tif" for i in range(1, 5)] 
        
        async def run_batch_vd(e):
            if not target_path: return
            e.control.disabled = True
            page.update()
            
            result = await client.start_vd_analysis(target_path, (scale_mm_ref.current.value if scale_mm_ref.current else 6.0))
            
            if "error" in result:
                err_data = result["error"]
                if isinstance(err_data, dict):
                    show_alpha_error("VD Engine Failure", f"Batch analysis failed.", err_data.get("traceback"))
                else:
                    show_alpha_error("VD Error", str(err_data))
                e.control.disabled = False
            else:
                page.session.set("last_result", result)
                page.session.set("is_vd_result", True)
                page.go("/results")
            page.update()

        return ft.Container(
            content=ft.Column([
                ft.Text("VD Analysis Pairing", size=32, weight=FontWeight.BOLD, color=Colors.WHITE),
                ft.Row([
                    ft.Icon(Icons.INFO_OUTLINE, size=16, color=TEXT_MUTED),
                    ft.Text("Smart engine automatically associates scans by patient ID and suffix.", color=TEXT_MUTED, size=14),
                ]),
                ft.Divider(height=40, color=Colors.with_opacity(0.1, Colors.WHITE)),
                
                ft.Row([
                    ft.Column([
                        ft.Text(f"Superficial Cohort ({len(sup_files)})", weight=FontWeight.BOLD, color=PRIMARY),
                        ft.ListView(expand=True, spacing=10, height=400, width=400, controls=[
                            ft.ListTile(
                                leading=ft.Icon(Icons.IMAGE_OUTLINED, color=PRIMARY), 
                                title=ft.Text(f, size=14),
                                trailing=ft.Icon(Icons.CHECK_CIRCLE, color=Colors.GREEN_400, size=16)
                            ) for f in sup_files
                        ])
                    ], expand=True),
                    
                    ft.Column([
                        ft.Icon(Icons.LINK_ROUNDED, size=40, color=PRIMARY),
                        ft.Text("Auto-Pairing", size=10, color=TEXT_MUTED)
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    
                    ft.Column([
                        ft.Text(f"Deep Cohort ({len(deep_files)})", weight=FontWeight.BOLD, color=Colors.PURPLE_400),
                        ft.ListView(expand=True, spacing=10, height=400, width=400, controls=[
                            ft.ListTile(
                                leading=ft.Icon(Icons.IMAGE_OUTLINED, color=Colors.PURPLE_400), 
                                title=ft.Text(f, size=14),
                                trailing=ft.Icon(Icons.CHECK_CIRCLE, color=Colors.GREEN_400, size=16)
                            ) for f in deep_files
                        ])
                    ], expand=True),
                ], spacing=20),
                
                ft.Container(height=30),
                ft.Row([
                    ft.ElevatedButton("Validate All Pairs", icon=Icons.RULE_ROUNDED, bgcolor=GLASS_BG, color=Colors.WHITE),
                    ft.ElevatedButton("Start Batch Analysis", icon=Icons.PLAY_ARROW_ROUNDED, height=50, bgcolor=PRIMARY, color=Colors.BLACK, on_click=run_batch_vd),
                ], alignment=ft.MainAxisAlignment.END, spacing=20),
            ], spacing=10, scroll=ft.ScrollMode.ADAPTIVE),
             padding=30,
            bgcolor=GLASS_BG,
            border_radius=20,
            opacity=1.0,
        )

    async def get_results_view():
        res = page.session.get("last_result") or {}
        
        def metric_card(label, value, unit, icon, color):
            return ft.Container(
                content=ft.Column([
                    ft.Row([ft.Icon(icon, color=color, size=20), ft.Text(label, size=14, color=TEXT_MUTED)]),
                    ft.Row([
                        ft.Text(str(value), size=28, weight=FontWeight.BOLD, color=Colors.WHITE),
                        ft.Text(unit, size=14, color=TEXT_MUTED),
                    ], alignment=ft.MainAxisAlignment.START, vertical_alignment=ft.CrossAxisAlignment.BASELINE),
                ], spacing=5),
                bgcolor=GLASS_BG,
                padding=20,
                border_radius=15,
                width=230,
                border=ft.border.all(1, Colors.with_opacity(0.1, Colors.WHITE)),
            )

        is_vd = page.session.get("is_vd_result")
        
        if is_vd:
            # Table for VD batch results
            data_rows = []
            ids = res.get("patient_ids", [])
            s_whole = res.get("superficial_whole", [])
            d_whole = res.get("deep_whole", [])
            faz = res.get("faz_areas", [])
            
            for i in range(len(ids)):
                s_val = s_whole[i] if i < len(s_whole) else 0.0
                d_val = d_whole[i] if i < len(d_whole) else 0.0
                f_val = faz[i] if i < len(faz) else 0.0
                
                data_rows.append(
                    ft.DataRow(cells=[
                        ft.DataCell(ft.Text(str(ids[i]), weight=FontWeight.BOLD)),
                        ft.DataCell(ft.Text(str(safe_round(s_val, 2)))),
                        ft.DataCell(ft.Text(str(safe_round(d_val, 2)))),
                        ft.DataCell(ft.Text(str(safe_round(f_val, 3)))),
                    ])
                )
            
            main_content = ft.Column([
                ft.Text("Batch VD Statistics Summary", size=24, weight=FontWeight.BOLD, color=PRIMARY),
                ft.Container(
                    content=ft.DataTable(
                        columns=[
                            ft.DataColumn(ft.Text("Patient ID")),
                            ft.DataColumn(ft.Text("Sup. Whole (%)"), numeric=True),
                            ft.DataColumn(ft.Text("Deep Whole (%)"), numeric=True),
                            ft.DataColumn(ft.Text("FAZ Area (mm²)"), numeric=True),
                        ],
                        rows=data_rows,
                        heading_row_color=Colors.with_opacity(0.1, PRIMARY),
                        border_radius=10,
                        border=ft.border.all(1, Colors.with_opacity(0.1, Colors.WHITE)),
                    ),
                    scroll=ft.ScrollMode.ADAPTIVE,
                    height=500
                )
            ], spacing=20)
        else:
            # Standard MNV Result — 3-tab layout matching Streamlit
            # Tab 1: Basic Vessel Metrics
            basic_tab = ft.Column([
                ft.Row([
                    metric_card("MNV Area", safe_round(res.get("mnv_area_mm2", 0), 3), "mm²", Icons.AREA_CHART, Colors.CYAN_400),
                    metric_card("Vessel Density", safe_round(res.get("vessel_density", 0) * 100, 2), "%", Icons.GRAIN, Colors.GREEN_400),
                    metric_card("Fractal Dim", safe_round(res.get("fractal_dimension", 0), 3), "FD", Icons.ACCOUNT_TREE, Colors.PURPLE_400),
                    metric_card("Subtype", res.get("mnv_subtype", "N/A"), "", Icons.CATEGORY, Colors.BLUE_400),
                ], spacing=15, wrap=True),
                ft.Divider(height=20, color=Colors.TRANSPARENT),
                ft.Row([
                    metric_card("Vessel Length", safe_round(res.get("vessel_length_mm", 0), 3), "mm", Icons.STRAIGHTEN, Colors.TEAL_400),
                    metric_card("Mean Diameter", safe_round(res.get("mean_diameter_um", 0), 2), "μm", Icons.TIMELINE, Colors.ORANGE_400),
                    metric_card("Tortuosity", safe_round(res.get("tortuosity", 0), 3), "", Icons.ROUTE, Colors.AMBER_400),
                    metric_card("Trunk Pattern", res.get("trunk_pattern", "Unknown"), "", Icons.SCHEMA, Colors.PINK_400),
                ], spacing=15, wrap=True),
                ft.Divider(height=20, color=Colors.TRANSPARENT),
                ft.Text("Processed Visualizations", size=20, weight=FontWeight.BOLD),
                ft.Row([
                    ft.Container(
                        bgcolor=Colors.BLACK, width=400, height=400, border_radius=10, 
                        content=ft.Image(
                            src=res.get("visualization_path", "") if not res.get("visualization_base64") else None,
                            src_base64=res.get("visualization_base64"),
                            fit=ft.ImageFit.CONTAIN
                        )
                    ),
                    ft.Container(
                        bgcolor=Colors.BLACK, width=400, height=400, border_radius=10,
                        content=ft.Image(
                            src_base64=res.get("mask_base64"),
                            src=res.get("mask_path", "") if not res.get("mask_base64") else None,
                            fit=ft.ImageFit.CONTAIN
                        ) if (res.get("mask_base64") or res.get("mask_path")) else ft.Text("No mask visualization", color=TEXT_MUTED)
                    ),
                ], spacing=20, scroll=ft.ScrollMode.ADAPTIVE),
            ], spacing=10)

            # Tab 2: Spatial Distribution
            spatial_tab = ft.Column([
                ft.Text("Network Topology", size=20, weight=FontWeight.BOLD, color=PRIMARY),
                ft.Row([
                    metric_card("Branches", res.get("num_branches", 0), "", Icons.CALL_SPLIT, Colors.CYAN_400),
                    metric_card("Junctions", res.get("num_junctions", 0), "", Icons.HUB, Colors.GREEN_400),
                    metric_card("Endpoints", res.get("num_endpoints", 0), "", Icons.RADIO_BUTTON_CHECKED, Colors.ORANGE_400),
                    metric_card("Loops", res.get("num_loops", 0), "", Icons.LOOP, Colors.PURPLE_400),
                ], spacing=15, wrap=True),
                ft.Divider(height=20, color=Colors.TRANSPARENT),
                ft.Text("Distribution Metrics", size=20, weight=FontWeight.BOLD, color=PRIMARY),
                ft.Row([
                    metric_card("Trunk Eccentricity", safe_round(res.get("trunk_eccentricity", -1), 3), "", Icons.ADJUST, Colors.TEAL_400),
                    metric_card("Complexity Score", safe_round(res.get("complexity_score", 0), 1), "", Icons.INSIGHTS, Colors.AMBER_400),
                    metric_card("Stability Score", safe_round(res.get("stability_score", 0), 1), "", Icons.BALANCE, Colors.BLUE_400),
                    metric_card("Maturity Index", safe_round(res.get("maturity_index", 0), 1), "", Icons.VERIFIED, Colors.PINK_400),
                ], spacing=15, wrap=True),
            ], spacing=10)

            # Tab 3: Flow Deficit
            def fd_ring_card(ring_label, fd_pct, fd_count, color):
                return ft.Container(
                    content=ft.Column([
                        ft.Text(ring_label, size=18, weight=FontWeight.BOLD, color=color),
                        ft.Text(f"FD%: {safe_round(fd_pct, 2)}%", size=16, color=Colors.WHITE),
                        ft.Text(f"Count: {fd_count}", size=14, color=TEXT_MUTED),
                    ], spacing=8, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    bgcolor=GLASS_BG, padding=30, border_radius=15, width=220,
                    border=ft.border.all(1, Colors.with_opacity(0.2, color)),
                )

            fd_tab = ft.Column([
                ft.Text("Flow Deficit Analysis (Ring-based)", size=20, weight=FontWeight.BOLD, color=PRIMARY),
                ft.Row([
                    fd_ring_card("Ring 1 (Inner)", res.get("fd_percent_r1", 0), res.get("fd_number_r1", 0), Colors.RED_400),
                    fd_ring_card("Ring 2 (Middle)", res.get("fd_percent_r2", 0), res.get("fd_number_r2", 0), Colors.ORANGE_400),
                    fd_ring_card("Ring 3 (Outer)", res.get("fd_percent_r3", 0), res.get("fd_number_r3", 0), Colors.AMBER_400),
                ], spacing=20, alignment=ft.MainAxisAlignment.CENTER),
            ], spacing=15)

            main_content = ft.Tabs(
                selected_index=0,
                tabs=[
                    ft.Tab(text="Basic Metrics", icon=Icons.QUERY_STATS, content=ft.Container(content=basic_tab, padding=20)),
                    ft.Tab(text="Spatial Distribution", icon=Icons.HUB, content=ft.Container(content=spatial_tab, padding=20)),
                    ft.Tab(text="Flow Deficit", icon=Icons.WATER_DROP, content=ft.Container(content=fd_tab, padding=20)),
                ],
                expand=True,
            )

        async def handle_export(e):
            directory_picker.get_directory_path()

        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Text("Analysis Results", size=32, weight=FontWeight.BOLD, expand=True, color=Colors.WHITE),
                    ft.ElevatedButton("Export CSV", icon=Icons.SAVE_ALT_ROUNDED, on_click=handle_export),
                    ft.ElevatedButton("Interactive Report", icon=Icons.LAUNCH_ROUNDED, bgcolor=PRIMARY, color=Colors.BLACK),
                ]),
                ft.Divider(height=20, color=Colors.TRANSPARENT),
                main_content
            ], spacing=20),
            padding=40,
            expand=True,
            opacity=1.0,
        )

    async def get_login_view():
        username_field = ft.TextField(
            label="Researcher Name",
            prefix_icon=Icons.PERSON_ROUNDED,
            border_color=PRIMARY,
            focused_border_color=PRIMARY_GLOW,
            width=350,
        )
        password_field = ft.TextField(
            label="Password",
            prefix_icon=Icons.LOCK_ROUNDED,
            password=True,
            can_reveal_password=True,
            border_color=PRIMARY,
            focused_border_color=PRIMARY_GLOW,
            width=350,
        )
        
        error_text = ft.Text(color=Colors.RED_400, size=12, visible=False)

        async def login_click(e):
            if not username_field.value or not password_field.value:
                error_text.value = "Please fill in all fields."
                error_text.visible = True
                page.update()
                return
            
            e.control.disabled = True
            page.update()
            
            login_res = await client.login(username_field.value, password_field.value)
            
            if login_res.get("success"):
                page.session.set("username", username_field.value)
                page.go("/")
            else:
                error_text.value = login_res.get("message", "Login failed.")
                error_text.visible = True
                e.control.disabled = False
                page.update()

        return ft.Container(
            content=ft.Column([
                ft.Container(
                    content=ft.Column([
                        ft.Icon(Icons.SECURITY_ROUNDED, size=80, color=PRIMARY),
                        ft.Text("Researcher Access", size=28, weight=FontWeight.BOLD, color=Colors.WHITE),
                        ft.Text("ARIAKE OCTA ALPHA ACCESS", size=12, color=TEXT_MUTED),
                        ft.Container(height=20),
                        username_field,
                        password_field,
                        error_text,
                        ft.Container(height=10),
                        ft.ElevatedButton(
                            "Secure Login", 
                            height=50, 
                            width=350, 
                            bgcolor=PRIMARY, 
                            color=Colors.BLACK,
                            on_click=login_click
                        ),
                        ft.Text("Forgot Password? ariake2024", size=10, color=TEXT_MUTED),
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=15),
                    padding=60,
                    bgcolor=GLASS_BG,
                    border_radius=25,
                    border=ft.border.all(1, Colors.with_opacity(0.1, Colors.WHITE)),
                    shadow=ft.BoxShadow(blur_radius=50, color=Colors.with_opacity(0.1, PRIMARY)),
                )
            ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            expand=True,
        )
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
    
    # --- Splash Logic ---
    await asyncio.sleep(0.3)
    # Pop logo
    logo_container.scale = 1.1
    page.update()
    await asyncio.sleep(0.4)
    # Fade title
    title_container.opacity = 1
    page.update()
    await asyncio.sleep(0.6)
    # Fade subtitle
    subtitle_container.opacity = 1
    page.update()
    await asyncio.sleep(1.2)
    
    # Fade out splash
    splash.opacity = 0
    page.update()
    await asyncio.sleep(0.6)
    
    # --- Build Main UI ---
    async def build_main_ui():
        page.clean()
        
        # Navigation Rail
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

        content_area = ft.Container(expand=True)

        # Engine Console (Persistent Alpha diagnostic)
        console_area = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Text("ALPHA DIAGNOSTIC ENGINE CONSOLE", size=10, weight=FontWeight.BOLD, color=PRIMARY),
                    ft.Icon(Icons.CODE, size=12, color=PRIMARY),
                ], alignment=ft.MainAxisAlignment.START, spacing=5),
                ft.ListView(ref=log_console_ref, expand=True, spacing=2),
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
            
            # Sync Nav Rail
            route_map = {"/": 0, "/mnv": 1, "/roi": 1, "/vd": 2, "/results": 3}
            if page.route in route_map:
                nav_rail.selected_index = route_map[page.route]
            
            try:
                # Session Guard
                if not page.session.get("username") and page.route != "/login":
                    page.go("/login")
                    is_navigating = False
                    return

                page.views.clear()
                
                # Simple routing logic
                if page.route == "/login":
                    view_content = await get_login_view()
                elif page.route == "/":
                    view_content = await get_dashboard_view()
                elif page.route == "/roi":
                    view_content = await get_roi_view()
                elif page.route == "/mnv":
                    view_content = await get_mnv_view()
                elif page.route == "/vd":
                    view_content = await get_vd_view()
                elif page.route == "/results":
                    view_content = await get_results_view()
                else:
                    view_content = await get_dashboard_view()

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
                # Trigger fade in REMOVED for reliability - always visible
            except Exception as e:
                add_to_console(f"Routing Error: {str(e)}", "ERROR")
            finally:
                is_navigating = False

        page.on_route_change = route_change
        page.go("/login")

    await build_main_ui()

if __name__ == "__main__":
    ft.app(target=main)
