import flet as ft
from flet import Colors, Icons, FontWeight
import base64
import cv2
import numpy as np
import asyncio
from pathlib import Path
from components.shared import PRIMARY, TEXT_MUTED, AppContext, session_discard
from src.core.fast_region_growing import fast_region_growing
from src.utils.cv2_path import (
    BGR_READ_DECODE,
    BGR_READ_NOT_FOUND,
    BGR_READ_OK,
    BGR_READ_OSERROR,
    BGR_READ_PERMISSION,
    imread_bgr_outcome,
)

async def get_roi_view(ctx: AppContext):
    target_path = ctx.page.session.get("target_path")

    if not target_path:
        return ft.Container(ft.Text("No image selected.", color=Colors.RED_400))

    await ctx.add_to_console(f"ROI Subtraction Mode: loading {target_path}", "INFO")

    # State Definition
    state = {
        "mode": "draw", # "draw" or "erase"
        "base_img": None,
        "current_mask": None,
        "history_masks": [],
        "scale": 1.0,
        "new_w": 500,
        "new_h": 500,
        "drag_start": None,
    }

    # UI Controls
    status_text = ft.Text("ドラッグしてROI（抽出領域）の枠を作成してください", color=TEXT_MUTED)
    load_error_text = ft.Text("", color=Colors.RED_400, visible=False)
    # 1x1 transparent pixel placeholder to prevent "Image must have either src or src_base64 specified" error
    EMPTY_PX = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    img_control = ft.Image(src="", src_base64=EMPTY_PX, fit=ft.ImageFit.CONTAIN, width=500, height=500)
    
    selection_box = ft.Container(
        border=ft.border.all(2, Colors.AMBER_400),
        bgcolor=Colors.with_opacity(0.1, Colors.AMBER_400),
        visible=False,
        left=0, top=0, width=0, height=0
    )

    def encode_img_b64(img_arr):
        _, buf = cv2.imencode('.jpg', img_arr, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return base64.b64encode(buf).decode('utf-8')

    async def render_mask():
        if state["base_img"] is None or state["current_mask"] is None:
            return
            
        base = state["base_img"].copy()
        mask = state["current_mask"]
        
        overlay = base.copy()
        # ROI領域を緑色の半透明で表示
        overlay[mask == 255] = [0, 255, 0] # BGR format
        
        blended = cv2.addWeighted(overlay, 0.4, base, 0.6, 0)
        img_control.src_base64 = encode_img_b64(blended)
        
        undo_button.disabled = len(state["history_masks"]) <= 1
        ctx.page.update()

    async def save_state(new_mask):
        state["history_masks"].append(new_mask.copy())
        state["current_mask"] = new_mask.copy()
        await render_mask()

    async def handle_undo(e):
        if len(state["history_masks"]) > 1:
            state["history_masks"].pop() # Remove current state
            state["current_mask"] = state["history_masks"][-1].copy()
            await render_mask()
            await ctx.add_to_console("Undo performed.", "INFO")

    async def handle_reset(e):
        if state["base_img"] is not None:
            blended = state["base_img"].copy()
            state["history_masks"].clear()
            blank_mask = np.zeros((state["new_h"], state["new_w"]), dtype=np.uint8)
            await save_state(blank_mask)
            await ctx.add_to_console("Mask reset.", "INFO")

    # Interaction Events
    async def on_pan_start(e: ft.DragStartEvent):
        if state["mode"] != "draw": return
        state["drag_start"] = True
        state["freehand_points"] = [(int(e.local_x), int(e.local_y))]

    async def on_pan_update(e: ft.DragUpdateEvent):
        if state["mode"] != "draw" or not state["drag_start"]: return
        cx = np.clip(int(e.local_x), 0, state["new_w"])
        cy = np.clip(int(e.local_y), 0, state["new_h"])
        state["freehand_points"].append((cx, cy))
        
        # Live render of the line
        if len(state["freehand_points"]) > 1:
            pts = np.array(state["freehand_points"], np.int32).reshape((-1, 1, 2))
            temp_mask = state["current_mask"].copy()
            cv2.polylines(temp_mask, [pts], False, 255, 2)
            
            # Temporary render
            base = state["base_img"].copy()
            overlay = base.copy()
            overlay[temp_mask == 255] = [0, 255, 0]
            blended = cv2.addWeighted(overlay, 0.4, base, 0.6, 0)
            img_control.src_base64 = encode_img_b64(blended)
            ctx.page.update()

    async def on_pan_end(e: ft.DragEndEvent):
        if state["mode"] == "erase":
            await on_tap_up(None)
            return
            
        if state["mode"] != "draw" or not state.get("drag_start"): return
        state["drag_start"] = False
        if len(state["freehand_points"]) > 2:
            new_mask = state["current_mask"].copy()
            pts = np.array(state["freehand_points"], np.int32)
            cv2.fillPoly(new_mask, [pts], 255)
            await save_state(new_mask)
            await ctx.add_to_console("Freehand ROI section added.", "INFO")

    async def continuous_erase(x, y):
        a_power = 0.5
        while state.get("is_pressing", False):
            try:
                if state["base_img"] is not None:
                    noise_mask = fast_region_growing(state["base_img"], (x, y), a=a_power)
                    if np.sum(noise_mask) > 0:
                        temp_mask = state["current_mask"].copy()
                        temp_mask[noise_mask == 255] = 0
                        
                        # Live preview
                        base = state["base_img"].copy()
                        overlay = base.copy()
                        overlay[temp_mask == 255] = [0, 255, 0]
                        blended = cv2.addWeighted(overlay, 0.4, base, 0.6, 0)
                        img_control.src_base64 = encode_img_b64(blended)
                        
                        status_text.value = f"ノイズ除去処理中... (パワー: {a_power:.1f})"
                        ctx.page.update()
                        
                        state["temp_mask"] = temp_mask
            except Exception as e:
                await ctx.add_to_console(f"Erase Error: {e}", "ERROR")
                
            a_power += 0.2
            if a_power > 6.0:
                a_power = 6.0
            await asyncio.sleep(0.05)

    async def on_tap_down(e: ft.ContainerTapEvent):
        if state["mode"] != "erase" or state["base_img"] is None: return
        x, y = int(e.local_x), int(e.local_y)
        
        await ctx.add_to_console(f"Erase clicked at: {x}, {y}", "INFO")
        status_text.value = "ノイズ除去処理中..."
        status_text.color = Colors.AMBER_400
        state["is_pressing"] = True
        state["temp_mask"] = None
        ctx.page.update()
        
        await continuous_erase(x, y)
        
    async def on_tap_up(e):
        if state["mode"] != "erase": return
        state["is_pressing"] = False
        
        if state.get("temp_mask") is not None:
            await save_state(state["temp_mask"])
            status_text.value = "🗑️ ノイズを除去しました（やり直す場合は長押し）"
            status_text.color = Colors.GREEN_400
        else:
            status_text.value = "⚠️ 背景として抽出できる領域がありませんでした"
            status_text.color = Colors.RED_400
        ctx.page.update()

    # Define Top UI Toolbar
    undo_button = ft.IconButton(Icons.UNDO, on_click=handle_undo, disabled=True, tooltip="Undo Last Action")
    reset_button = ft.IconButton(Icons.REFRESH, on_click=handle_reset, tooltip="Reset All")

    # Replaced SegmentedButton with two robust explicit buttons
    draw_btn = ft.ElevatedButton(
        "1. Draw ROI (フリーハンド)", 
        icon=Icons.CROP_SQUARE,
        bgcolor=PRIMARY, 
        color=Colors.BLACK,
        on_click=lambda e: ctx.page.run_task(set_mode, "draw")
    )
    
    erase_btn = ft.ElevatedButton(
        "2. Erase Noise (長押し)", 
        icon=Icons.BACKSPACE,
        bgcolor=Colors.TRANSPARENT, 
        color=TEXT_MUTED,
        on_click=lambda e: ctx.page.run_task(set_mode, "erase")
    )

    async def set_mode(new_mode):
        state["mode"] = new_mode
        if new_mode == "draw":
            draw_btn.bgcolor = PRIMARY
            draw_btn.color = Colors.BLACK
            erase_btn.bgcolor = Colors.TRANSPARENT
            erase_btn.color = TEXT_MUTED
            status_text.value = "ドラッグしてROI（抽出領域）をフリーハンドで囲んでください"
        else:
            erase_btn.bgcolor = Colors.RED_400
            erase_btn.color = Colors.WHITE
            draw_btn.bgcolor = Colors.TRANSPARENT
            draw_btn.color = TEXT_MUTED
            status_text.value = "緑の領域内の「黒い隙間」を丸ごと長押ししてノイズを除去してください"
            
        status_text.color = TEXT_MUTED
        ctx.page.update()

    mode_tabs = ft.Row([draw_btn, erase_btn], spacing=10)

    # GestureDetector wrapping the image and selection frame
    gesture = ft.GestureDetector(
        content=ft.Stack([
            img_control,
            selection_box
        ], width=500, height=500),
        on_pan_start=on_pan_start,
        on_pan_update=on_pan_update,
        on_pan_end=on_pan_end,
        on_tap_down=on_tap_down,
        on_tap_up=on_tap_up,
        mouse_cursor=ft.MouseCursor.PRECISE,
    )

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
        visible=False,
    )
    
    img_stack = ft.Container(
        content=ft.Stack([loading_layer, image_layer]),
        width=500, height=500,
        bgcolor=Colors.BLACK,
        border_radius=10,
        border=ft.border.all(1, Colors.with_opacity(0.3, PRIMARY)),
    )

    async def confirm_roi(e):
        if state["current_mask"] is None or np.sum(state["current_mask"]) == 0:
            status_text.value = "⚠️ ROIが空です。領域を選択してください。"
            status_text.color = Colors.RED_400
            ctx.page.update()
            return
            
        inv_scale = 1.0 / state["scale"]
        orig_w = int(state["new_w"] * inv_scale)
        orig_h = int(state["new_h"] * inv_scale)
        full_mask = cv2.resize(state["current_mask"], (orig_w, orig_h), interpolation=cv2.INTER_NEAREST)
        
        _, buf = cv2.imencode('.png', full_mask)
        mask_b64 = base64.b64encode(buf).decode('utf-8')
        
        pts = np.argwhere(state["current_mask"] > 0)
        y_min, x_min = pts.min(axis=0)
        y_max, x_max = pts.max(axis=0)
        roi = {
            "x": int(x_min * inv_scale), 
            "y": int(y_min * inv_scale),
            "w": int((x_max - x_min) * inv_scale), 
            "h": int((y_max - y_min) * inv_scale),
        }
        
        ctx.page.session.set("roi", roi)
        ctx.page.session.set("roi_mask_b64", mask_b64)
        session_discard(ctx.page.session, "vd_analysis_explicit_path")
        ctx.page.go("/mnv")

    async def load_image_async():
        await asyncio.sleep(0.1)
        try:
            # Secondary cleansing just in case
            clean_path = target_path.strip().strip("'").strip('"')
            print(f"DEBUG: ROI Selection Attempting to load: {clean_path}", flush=True)

            p = Path(clean_path)
            loop = asyncio.get_event_loop()
            base_img, read_reason = await loop.run_in_executor(
                None, lambda: imread_bgr_outcome(clean_path)
            )
            if base_img is None or read_reason != BGR_READ_OK:
                try:
                    sz = p.stat().st_size if p.exists() else 0
                except OSError:
                    sz = -1
                print(
                    f"DEBUG: ROI load failed reason={read_reason} exists={p.exists()} st_size={sz}",
                    flush=True,
                )
                if read_reason == BGR_READ_PERMISSION:
                    load_error_text.value = (
                        "❌ macOS がこのファイルの読み取りを拒否しています（Permission / OneDrive）。"
                        " 同じパスでも、ターミナルや Cursor の「フルディスクアクセス」が無いと失敗することがあります。"
                        " システム設定 → プライバシーとセキュリティ → フルディスクアクセス で、使っているターミナル（または Python）を許可するか、"
                        "画像をプロジェクトの uploads/ などローカルフォルダへコピーしてから指定してください。"
                    )
                    await ctx.add_to_console(
                        "read_bytes: Operation not permitted — 多くは TCC / OneDrive。午前は別ターミナルで起動していた可能性。",
                        "ERROR",
                    )
                elif read_reason == BGR_READ_NOT_FOUND:
                    load_error_text.value = f"❌ ファイルが見つかりません: {clean_path}"
                elif read_reason == BGR_READ_DECODE:
                    load_error_text.value = f"❌ 画像をデコードできません（破損・非対応形式）: {clean_path}"
                elif read_reason == BGR_READ_OSERROR:
                    load_error_text.value = f"❌ ファイル読み取りエラー: {clean_path}"
                else:
                    load_error_text.value = (
                        f"❌ 画像の読み込みに失敗しました: {clean_path}"
                    )
                    await ctx.add_to_console(
                        "形式・OneDrive 未同期・パスを確認してください。",
                        "ERROR",
                    )
                load_error_text.visible = True
                ctx.page.update()
                return

            orig_h, orig_w = base_img.shape[:2]
            sc = min(500 / orig_w, 500 / orig_h)
            new_w, new_h = int(orig_w * sc), int(orig_h * sc)
            resized = cv2.resize(base_img, (new_w, new_h))

            state["base_img"] = resized
            state["new_w"] = new_w
            state["new_h"] = new_h
            state["scale"] = sc
            
            # Initialize empty mask and push to history
            blank_mask = np.zeros((new_h, new_w), dtype=np.uint8)
            state["history_masks"].clear()
            await save_state(blank_mask)

            img_control.width = new_w
            img_control.height = new_h

            loading_layer.visible = False
            image_layer.visible = True
            ctx.page.update()

        except Exception as ex:
            import traceback

            print(f"DEBUG: ROI load_image_async exception: {ex}", flush=True)
            print(traceback.format_exc(), flush=True)
            load_error_text.value = f"❌ エラー: {str(ex)}"
            load_error_text.visible = True
            ctx.page.update()

    # Load image initially
    await load_image_async()

    batch_paths = ctx.page.session.get("mnv_batch_paths") or []
    batch_idx = int(ctx.page.session.get("mnv_batch_index") or 0)
    preview_names = ctx.page.session.get("mnv_batch_names_preview")
    batch_caption = ""
    if batch_paths:
        batch_caption = f"MNV folder batch — image {batch_idx + 1} of {len(batch_paths)}: {Path(target_path).name}"
        if isinstance(preview_names, list) and preview_names:
            batch_caption += "\nキュー · " + " · ".join(str(n) for n in preview_names) + " （いずれも MNV）"

    return ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Column([
                    ft.Text("Step 1: ROI Refinement (Subtraction)", size=32, weight=FontWeight.BOLD, color=PRIMARY),
                    ft.Text(
                        batch_caption or "Draw ROI and click dark areas to erase background noise.",
                        color=TEXT_MUTED,
                    ),
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
                    ft.Row([mode_tabs]),
                    ft.Row([undo_button, reset_button]),
                    ft.Divider(height=20, color=Colors.TRANSPARENT),
                    ft.Container(
                        content=ft.Column([
                            ft.Row([ft.Icon(Icons.CROP_SQUARE, color=PRIMARY), ft.Text("1. ドラッグして囲む", color=Colors.WHITE)]),
                            ft.Row([ft.Icon(Icons.BACKSPACE, color=Colors.RED_400), ft.Text("2. 黒い背景をクリックして削る", color=Colors.WHITE)]),
                            ft.Row([ft.Icon(Icons.UNDO, color=Colors.AMBER_400), ft.Text("3. ミスしたらUndoで戻る", color=Colors.WHITE)])
                        ], spacing=10),
                        padding=20,
                        bgcolor=Colors.with_opacity(0.05, Colors.WHITE),
                        border_radius=10
                    )
                ], expand=True, spacing=15,
                   alignment=ft.MainAxisAlignment.START,
                   horizontal_alignment=ft.CrossAxisAlignment.START)
            ], spacing=40, vertical_alignment=ft.CrossAxisAlignment.START),
        ], spacing=10, scroll=ft.ScrollMode.ADAPTIVE),
        padding=40,
        expand=True,
        opacity=1.0,
    )
