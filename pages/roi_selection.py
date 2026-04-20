import flet as ft
from flet import Colors, Icons, FontWeight
import base64
import cv2
import numpy as np
import asyncio
from pathlib import Path
from components.shared import PRIMARY, TEXT_MUTED, AppContext
from src.core.fast_region_growing import fast_region_growing

async def get_roi_view(ctx: AppContext):
    target_path = ctx.page.session.get("target_path")

    if not target_path:
        return ft.Container(ft.Text("No image selected.", color=Colors.RED_400))

    ctx.add_to_console(f"ROI View: loading {target_path}", "INFO")

    status_text = ft.Text(
        "画像ロード完了後、病変部をクリック＆長押しして領域を抽出してください",
        color=TEXT_MUTED
    )
    a_value_text = ft.Text("", size=18, weight=FontWeight.BOLD, color=PRIMARY)
    load_error_text = ft.Text("", color=Colors.RED_400, visible=False)

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
                ctx.page.update()
            state["current_a"] += 0.2
            if state["current_a"] > 6.0:
                state["current_a"] = 6.0
            await asyncio.sleep(0.05)

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
        ctx.page.update()
        ctx.page.run_task(process_region_growing)

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
        ctx.page.update()

    gesture = ft.GestureDetector(
        content=img_control,
        on_tap_down=on_tap_down,
        on_tap_up=on_tap_up,
        on_pan_end=lambda e: on_tap_up(e),
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
        roi = {
            "x": int(x_slider.value), "y": int(y_slider.value),
            "w": int(w_slider.value), "h": int(h_slider.value),
        }
        ctx.page.session.set("roi", roi)
        if state.get("mask_b64"):
            ctx.page.session.set("roi_mask_b64", state["mask_b64"])
        ctx.page.go("/mnv")

    async def load_image_async():
        await asyncio.sleep(0.3)
        try:
            loop = asyncio.get_event_loop()
            base_img = await loop.run_in_executor(
                None, lambda: cv2.imread(target_path)
            )
            if base_img is None:
                load_error_text.value = f"❌ 読み込み失敗: {target_path}"
                load_error_text.visible = True
                ctx.page.update()
                ctx.add_to_console(f"ROI: imread failed for {target_path}", "ERROR")
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

            loading_layer.visible = False
            image_layer.visible = True
            status_text.value = "病変部をクリック＆長押しして領域を抽出してください"
            ctx.add_to_console(f"ROI: image loaded OK ({new_w}x{new_h})", "INFO")
            ctx.page.update()

        except Exception as ex:
            import traceback
            load_error_text.value = f"❌ エラー: {str(ex)}"
            load_error_text.visible = True
            ctx.page.update()
            ctx.add_to_console(f"ROI load error: {traceback.format_exc()}", "ERROR")

    ctx.page.run_task(load_image_async)

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
