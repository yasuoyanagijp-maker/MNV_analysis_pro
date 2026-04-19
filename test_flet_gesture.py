import flet as ft
import cv2
import numpy as np
import base64
import asyncio
from src.core.fast_region_growing import fast_region_growing

# テスト用画像ジェネレータ
def create_test_image():
    img = np.zeros((600, 600, 3), dtype=np.uint8)
    center = (300, 300)
    for r in range(150, 0, -5):
        color = int(255 * (1.0 - r/150.0))
        cv2.circle(img, center, r, (color, color, color), -1)
    noise = np.random.normal(0, 15, (600, 600, 3)).astype(np.int8)
    img = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    return img

def encode_image_base64(img_array):
    _, buffer = cv2.imencode('.jpg', img_array, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return base64.b64encode(buffer).decode('utf-8')

async def main(page: ft.Page):
    page.title = "Fast Region Growing UX Prototype"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 20
    
    # 状態管理
    state = {
        "is_pressing": False,
        "seed_point": None,
        "current_a": 0.5,
        "base_image": create_test_image(),
        "display_image": None
    }
    
    # 画像の初期設定
    state["display_image"] = state["base_image"].copy()
    initial_b64 = encode_image_base64(state["display_image"])
    
    img_control = ft.Image(
        src_base64=initial_b64,
        width=600,
        height=600,
        fit=ft.ImageFit.CONTAIN,
    )
    
    status_text = ft.Text("シード点を長押しして領域を広げてください", size=16, color=ft.Colors.CYAN_400)
    a_value_text = ft.Text("a = 0.5", size=24, weight=ft.FontWeight.BOLD)
    
    async def process_region_growing():
        while state["is_pressing"]:
            if state["seed_point"]:
                mask = fast_region_growing(
                    state["base_image"], 
                    state["seed_point"], 
                    a=state["current_a"], 
                    window_size=5
                )
                
                # オーバーレイ描画（マスク部分を赤くする）
                overlay = state["base_image"].copy()
                overlay[mask == 255] = [0, 0, 255] # BGRで赤
                
                # 元画像とブレンドして半透明に
                blended = cv2.addWeighted(overlay, 0.5, state["base_image"], 0.5, 0)
                
                # シード点を描画
                cv2.circle(blended, state["seed_point"], 3, (0, 255, 0), -1)
                
                img_control.src_base64 = encode_image_base64(blended)
                a_value_text.value = f"a = {state['current_a']:.2f}"
                page.update()
                
            state["current_a"] += 0.2
            if state["current_a"] > 6.0: # 最大値
                state["current_a"] = 6.0
                
            await asyncio.sleep(0.05) # 50ms = 20fps程度
    
    def on_tap_down(e: ft.ContainerTapEvent):
        # 座標の取得 (ここでは画像の表示幅と実解像度が1:1である前提)
        state["is_pressing"] = True
        state["seed_point"] = (int(e.local_x), int(e.local_y))
        state["current_a"] = 0.5
        
        status_text.value = f"抽出中... シード点: {state['seed_point']}"
        status_text.color = ft.Colors.AMBER_400
        page.update()
        
        # 非同期ループの起動
        page.run_task(process_region_growing)
        
    def on_tap_up(e: ft.ContainerTapEvent):
        state["is_pressing"] = False
        status_text.value = "抽出確定。他の点を長押しで再抽出できます。"
        status_text.color = ft.Colors.GREEN_400
        page.update()
    
    def on_pan_end(e: ft.DragEndEvent):
        # タッチデバイス等で長押し終了判定が漏れた場合
        on_tap_up(None)
    
    gesture = ft.GestureDetector(
        content=img_control,
        on_tap_down=on_tap_down,
        on_tap_up=on_tap_up,
        on_pan_end=on_pan_end,
        mouse_cursor=ft.MouseCursor.CROSSHAIR
    )
    
    page.add(
        ft.Column([
            ft.Text("Region Growing Interactive UX", size=30, weight=ft.FontWeight.BOLD),
            status_text,
            a_value_text,
            ft.Container(
                content=gesture,
                border=ft.border.all(2, ft.Colors.CYAN_700),
                border_radius=10,
                width=600,
                height=600
            )
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER)
    )

if __name__ == "__main__":
    ft.app(target=main)
