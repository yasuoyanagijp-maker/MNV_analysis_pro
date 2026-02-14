"""
Scroll-Free Single Page ROI Selection UI

スクロールなしの1ページUIを実現する最適化:
1. ✅ 余白の最小化（CSS padding/margin削減）
2. ✅ 固定高さコンテナの使用
3. ✅ ビューポート高さ（vh）の活用
4. ✅ 効率的なレイアウトコンポーネント配置
5. ✅ ワイドレイアウト設定
"""

import io
import numpy as np
import cv2
from PIL import Image, ImageDraw
import streamlit as st
from streamlit_drawable_canvas import st_canvas
from typing import Optional, Tuple

try:
    from core.roi_manager import ROIModifier
except ImportError:
    ROIModifier = None


# ============================================================================
# スクロールレスUI用のCSSスタイル
# ============================================================================
def inject_scrollfree_css():
    """
    スクロールレスUIのためのカスタムCSS
    
    主な最適化:
    - padding/marginの大幅削減
    - 固定高さコンテナ
    - オーバーフロー制御
    - ビューポート単位（vh/vw）の活用
    """
    st.markdown("""
        <style>
        /* ========================================
           全体レイアウトの最適化
           ======================================== */
        
        /* メインコンテナの余白削減 */
        .main .block-container {
            padding-top: 1rem !important;
            padding-bottom: 0.5rem !important;
            padding-left: 1rem !important;
            padding-right: 1rem !important;
            max-width: 100% !important;
        }
        
        /* ヘッダーの余白削減 */
        header {
            background-color: transparent !important;
        }
        
        /* サイドバーの最適化 */
        [data-testid="stSidebar"] {
            min-width: 240px !important;
            max-width: 260px !important;
        }
        
        [data-testid="stSidebar"] .block-container {
            padding-top: 1rem !important;
            padding-bottom: 1rem !important;
        }
        
        /* ========================================
           スクロール制御
           ======================================== */
        
        /* メインエリアのスクロール無効化 */
        .main {
            overflow-y: hidden !important;
            height: 100vh !important;
        }
        
        /* ========================================
           コンポーネントの余白最適化
           ======================================== */
        
        /* タイトル・ヘッダーの余白削減 */
        h1, h2, h3 {
            margin-top: 0.3rem !important;
            margin-bottom: 0.3rem !important;
            padding: 0 !important;
        }
        
        /* 段落の余白削減 */
        p {
            margin-bottom: 0.3rem !important;
        }
        
        /* Infoボックスの余白削減 */
        .stAlert {
            padding: 0.5rem !important;
            margin-bottom: 0.5rem !important;
        }
        
        /* Expanderの余白削減 */
        .streamlit-expanderHeader {
            padding: 0.3rem 0.5rem !important;
        }
        
        .streamlit-expanderContent {
            padding: 0.5rem !important;
        }
        
        /* ========================================
           固定高さコンテナ
           ======================================== */
        
        /* ROI描画エリア - 固定高さ */
        .roi-draw-container {
            height: calc(100vh - 180px) !important;
            overflow-y: auto !important;
            overflow-x: hidden !important;
        }
        
        /* ROIプレビューエリア - 固定高さ */
        .roi-preview-container {
            height: calc(100vh - 180px) !important;
            overflow-y: auto !important;
            overflow-x: hidden !important;
        }
        
        /* ========================================
           ボタンスタイル
           ======================================== */
        
        .stButton>button {
            width: 100%;
            padding: 0.4rem 0.8rem !important;
            margin: 0.2rem 0 !important;
            font-size: 0.9rem !important;
            border-radius: 6px;
            transition: all 0.2s ease;
        }
        
        .stButton>button:hover {
            transform: translateY(-1px);
            box-shadow: 0 2px 8px rgba(0,0,0,0.15);
        }
        
        div.stButton > button[kind="primary"] {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
        }
        
        /* ========================================
           メトリクスカード - コンパクト版
           ======================================== */
        
        [data-testid="stMetricValue"] {
            font-size: 1.3rem !important;
            font-weight: 700;
            color: #1a202c;
        }
        
        [data-testid="stMetricLabel"] {
            font-size: 0.75rem !important;
            color: #718096;
        }
        
        [data-testid="metric-container"] {
            padding: 0.3rem 0.5rem !important;
        }
        
        /* ========================================
           画像表示の最適化
           ======================================== */
        
        [data-testid="stImage"] {
            margin: 0 !important;
        }
        
        /* ========================================
           スライダーのコンパクト化
           ======================================== */
        
        .stSlider {
            padding-top: 0 !important;
            padding-bottom: 0.3rem !important;
        }
        
        /* ========================================
           カラムの隙間調整
           ======================================== */
        
        [data-testid="column"] {
            padding: 0 0.3rem !important;
        }
        
        /* ========================================
           Canvas固有の調整
           ======================================== */
        
        canvas {
            border-radius: 6px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        
        /* ========================================
           コンパクトヘッダー
           ======================================== */
        
        .compact-header {
            font-size: 1.5rem;
            font-weight: 700;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            text-align: center;
            margin: 0.3rem 0;
        }
        
        .compact-subheader {
            font-size: 0.85rem;
            color: #666;
            text-align: center;
            margin: 0.2rem 0 0.5rem 0;
        }
        
        /* ========================================
           プログレスバー
           ======================================== */
        
        .stProgress {
            height: 0.3rem !important;
        }
        
        .stProgress > div > div > div {
            background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        }
        
        /* ========================================
           チェックボックス・ラジオボタン
           ======================================== */
        
        .stCheckbox, .stRadio {
            padding: 0.2rem 0 !important;
        }
        
        </style>
    """, unsafe_allow_html=True)


# ============================================================================
# スクロールレスROI選択クラス
# ============================================================================
class ScrollFreeROICanvas:
    """
    スクロールレス1ページUIのROI選択キャンバス
    
    特徴:
    - 画面高さに収まるコンパクトレイアウト
    - 固定高さコンテナでスクロール制御
    - 効率的なスペース利用
    """
    
    def __init__(self, viewport_height_offset: int = 180):
        """
        Parameters
        ----------
        viewport_height_offset : int
            ビューポート高さからのオフセット（ピクセル）
            ヘッダーやボタンの高さを考慮
        """
        self.viewport_height_offset = viewport_height_offset
    
    def render_compact(self,
                      image_bytes: bytes,
                      key_suffix: str = "",
                      max_canvas_height: int = 500) -> Optional[np.ndarray]:
        """
        コンパクトなROI選択UIを描画
        
        Parameters
        ----------
        image_bytes : bytes
            入力画像
        key_suffix : str
            Streamlitキーの接尾辞
        max_canvas_height : int
            Canvas最大高さ（画面に収めるため）
        
        Returns
        -------
        np.ndarray or None
            ROIマスク
        """
        # 画像読み込み
        pil_image = Image.open(io.BytesIO(image_bytes))
        
        # Canvas高さを調整（画面に収めるため）
        canvas_height = min(pil_image.height, max_canvas_height)
        canvas_width = int(pil_image.width * (canvas_height / pil_image.height))
        
        # リサイズされた画像を作成
        display_image = pil_image.resize((canvas_width, canvas_height), Image.LANCZOS)
        
        # ===== コンパクトヘッダー（重複文言は非表示） =====
        st.markdown('<div class="compact-header">🎯 ROI Selection</div>', unsafe_allow_html=True)

        # Auto-close 閾値は固定（Settings UI は非表示）
        threshold = 30

        # ===== 2カラムレイアウト（高さ固定） =====
        col1, col2 = st.columns([1.2, 1])
        
        # ----- 左: 描画エリア -----
        with col1:
            st.markdown("**📐 Draw**")
            
            # Canvas
            canvas_result = st_canvas(
                fill_color="rgba(255, 0, 0, 0.3)",
                stroke_width=2,
                stroke_color="#FF0000",
                background_image=display_image,
                drawing_mode="freedraw",
                point_display_radius=0,
                height=canvas_height,
                width=canvas_width,
                key=f"canvas_compact_{key_suffix}",
            )
        
        # ----- 右: プレビューとステータス -----
        with col2:
            st.markdown("**👁️ Preview**")
            
            roi_mask, roi_info = self._process_canvas_result(
                canvas_result, pil_image, display_image, threshold
            )
            
            if roi_mask is not None:
                # プレビュー: パイプラインと同じリファインを1回だけかけ、その結果を表示
                preview_mask = self._refined_mask_for_preview(pil_image, roi_mask)
                roi_info_preview = {**roi_info, "roi_mask": preview_mask}
                preview = self._create_preview_image(
                    pil_image, preview_mask, roi_info_preview
                )
                st.image(preview, use_column_width=True, caption="ROI (refined)")
                self._display_compact_status(roi_info)
            else:
                # ROI未選択時: 元画像のみ表示
                st.info("👈 Draw ROI on the left canvas")
                st.image(
                    display_image,
                    use_column_width=True,
                    caption="Original (no ROI)",
                )
                if roi_info.get("distance_to_close"):
                    distance = roi_info["distance_to_close"]
                    st.caption(f"Distance to close: {distance:.1f}px")
        
        return roi_mask
    
    def _process_canvas_result(self,
                               canvas_result,
                               original_image: Image.Image,
                               display_image: Image.Image,
                               threshold: int) -> Tuple[Optional[np.ndarray], dict]:
        """
        Canvas結果を処理。image_data（描画ピクセル）からROI抽出が優先。
        座標のズレを防ぐため、パス解析ではなく実際のピクセルベースでマスク作成。
        """
        # 方式1: image_data（描画済み画像）から抽出 - 座標ずれなし
        roi_mask, roi_info = self._extract_roi_from_image_data(
            canvas_result, original_image, display_image
        )
        if roi_mask is not None:
            return roi_mask, roi_info

        # 方式2: json_data（パス座標）フォールバック
        return self._extract_roi_from_path_data(
            canvas_result, original_image, display_image.size, threshold
        )

    def _extract_roi_from_image_data(
        self,
        canvas_result,
        original_image: Image.Image,
        display_image: Image.Image,
    ) -> Tuple[Optional[np.ndarray], dict]:
        """描画済みキャンバス画像からROIマスクを抽出（座標ズレ防止の推奨方式）

        改善点:
        - 背景差分法でストローク検出（背景の赤成分との混同を防止）
        - 形態学的処理でストロークの隙間を閉鎖
        - flood fill 外部法で囲まれた内部領域を正確に抽出
        - 輪郭近似でプレビュー用ポイントを生成
        """
        if canvas_result.image_data is None:
            return None, {}

        canvas_img = np.array(canvas_result.image_data, dtype=np.uint8)
        if canvas_img.ndim != 3 or canvas_img.shape[2] < 3:
            return None, {}

        h_disp, w_disp = canvas_img.shape[:2]

        # --- 背景差分法でストローク検出 ---
        bg = np.array(display_image.convert("RGB"), dtype=np.uint8)
        if bg.shape[:2] != (h_disp, w_disp):
            bg = cv2.resize(bg, (w_disp, h_disp))

        canvas_rgb = canvas_img[:, :, :3]
        diff = cv2.absdiff(canvas_rgb, bg)

        # 赤チャンネルの差分 (stroke_color="#FF0000") が支配的な部分を検出
        r_diff = diff[:, :, 0].astype(np.int16)
        g_diff = diff[:, :, 1].astype(np.int16)
        b_diff = diff[:, :, 2].astype(np.int16)
        # 赤ストローク: 閾値を控えめに (15->12) で境界ピクセルの取りこぼしを抑制
        stroke_mask = (
            (r_diff > 12) & (r_diff > g_diff + 5) & (r_diff > b_diff + 5)
        ).astype(np.uint8) * 255

        # 全チャンネル差分でもフォールバック（赤以外のストローク対応）
        if stroke_mask.sum() < 500:
            diff_gray = np.max(diff, axis=2)
            stroke_mask = ((diff_gray > 18).astype(np.uint8)) * 255

        if stroke_mask.sum() < 500:
            return None, {}

        # --- 形態学的処理でストロークの隙間を閉じる（ImageJ互換: 過度な縮小を避ける）---
        # 膨張3回は interior を著しく縮小するため、閉鎖のみで隙間を埋める
        kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
        thick = cv2.morphologyEx(stroke_mask, cv2.MORPH_CLOSE, kernel_close, iterations=2)

        # --- flood fill 外部法で内部領域を抽出 ---
        # thick のストロークが閉じた境界線であれば、外部からの
        # flood fill がストローク内部に侵入しない
        h_pad, w_pad = h_disp + 2, w_disp + 2
        bordered = np.zeros((h_pad, w_pad), dtype=np.uint8)
        bordered[1:-1, 1:-1] = thick

        # 外部領域を flood fill (四隅から)
        exterior = bordered.copy()
        flood_mask = np.zeros((h_pad + 2, w_pad + 2), dtype=np.uint8)
        # (0,0) から塗り潰し: 0 のピクセルを 128 に変更
        cv2.floodFill(exterior, flood_mask, (0, 0), 128)

        # 内部 = 外部でもストロークでもない領域 (flood fill が到達しなかった 0)
        interior = bordered.copy()
        # flood fill で 128 になった部分が外部、255 がストローク、0 が内部
        interior_mask_padded = (
            (exterior[1:-1, 1:-1] == 0).astype(np.uint8) * 255
        )

        # ストローク自体も ROI に含める
        roi_canvas = cv2.bitwise_or(interior_mask_padded, stroke_mask)

        # MORPH_OPEN は境界を 1px 以上侵食するため削除（ImageJ と同等サイズにする）
        # 孤立点除去は最大連結成分の選択で十分

        # --- 最大連結成分のみ保持 ---
        contours, _ = cv2.findContours(
            roi_canvas, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        if not contours:
            return None, {}

        largest = max(contours, key=cv2.contourArea)
        min_area = max(100, h_disp * w_disp * 0.002)
        if cv2.contourArea(largest) < min_area:
            return None, {}

        mask_canvas = np.zeros((h_disp, w_disp), dtype=np.uint8)
        cv2.drawContours(mask_canvas, [largest], -1, 255, thickness=-1)

        # --- 元画像サイズにリサイズ ---
        w_orig, h_orig = original_image.width, original_image.height
        roi_mask = cv2.resize(
            mask_canvas, (w_orig, h_orig), interpolation=cv2.INTER_NEAREST
        )

        if roi_mask.sum() == 0:
            return None, {}

        # --- ROI 情報 (プレビュー用に輪郭点をスケーリング) ---
        scale_x = w_orig / w_disp
        scale_y = h_orig / h_disp

        # 輪郭を近似して点数を削減 (プレビュー描画用)
        epsilon = 0.005 * cv2.arcLength(largest, True)
        approx = cv2.approxPolyDP(largest, epsilon, True)
        contour_points = [
            (int(p[0][0] * scale_x), int(p[0][1] * scale_y)) for p in approx
        ]

        pts = np.argwhere(roi_mask > 0)
        y_min, x_min = pts.min(axis=0)
        y_max, x_max = pts.max(axis=0)

        roi_info = {
            "points": contour_points,
            "num_points": len(contour_points),
            "distance_to_close": 0,
            "is_closed": True,
            "closed_points": contour_points,
            "bbox": (x_min, y_min, x_max, y_max),
            "width": x_max - x_min,
            "height": y_max - y_min,
            "area": int(roi_mask.sum() / 255),
            "roi_mask": roi_mask,  # プレビュー用にマスクも渡す
        }
        return roi_mask, roi_info

    def _extract_roi_from_path_data(
        self,
        canvas_result,
        original_image: Image.Image,
        display_size: Tuple[int, int],
        threshold: int,
    ) -> Tuple[Optional[np.ndarray], dict]:
        """パス座標からROI抽出（フォールバック）

        Fabric.js の座標系:
        - path 座標はオブジェクトのローカル座標
        - left/top はキャンバス上のオブジェクト位置
        - scaleX/scaleY はオブジェクトのスケーリング
        - canvas座標 = path座標 * scale + left/top
        """
        if canvas_result.json_data is None:
            return None, {}

        objects = canvas_result.json_data.get("objects", [])
        if len(objects) == 0:
            return None, {}

        obj = objects[-1]
        if obj.get("type") != "path":
            return None, {}

        # Fabric.js 変換パラメータ
        left = float(obj.get("left", 0) or 0)
        top = float(obj.get("top", 0) or 0)
        obj_scale_x = float(obj.get("scaleX", 1) or 1)
        obj_scale_y = float(obj.get("scaleY", 1) or 1)

        path_data = obj.get("path", [])
        points = []
        for cmd in path_data:
            if len(cmd) < 3:
                continue
            ctype = cmd[0] if isinstance(cmd[0], str) else str(cmd[0])
            if ctype in ("M", "L"):
                x, y = float(cmd[1]), float(cmd[2])
            elif ctype == "Q" and len(cmd) >= 5:
                # Q cx cy x y - 端点は x, y
                x, y = float(cmd[3]), float(cmd[4])
            elif ctype == "C" and len(cmd) >= 7:
                # C c1x c1y c2x c2y x y - 端点は x, y
                x, y = float(cmd[5]), float(cmd[6])
            else:
                continue
            # Fabric.js 座標変換: local -> canvas
            canvas_x = x * obj_scale_x + left
            canvas_y = y * obj_scale_y + top
            points.append((canvas_x, canvas_y))

        if len(points) < 3:
            return None, {}

        # キャンバス座標 -> 元画像座標へスケーリング（四捨五入で truncation による縮小を抑制）
        img_scale_x = original_image.width / display_size[0]
        img_scale_y = original_image.height / display_size[1]
        w_orig, h_orig = original_image.width, original_image.height
        scaled_points = [
            (
                int(np.clip(round(x * img_scale_x), 0, w_orig - 1)),
                int(np.clip(round(y * img_scale_y), 0, h_orig - 1)),
            )
            for x, y in points
        ]

        start = np.array(scaled_points[0], dtype=np.float64)
        end = np.array(scaled_points[-1], dtype=np.float64)
        distance = float(np.linalg.norm(start - end))
        close_threshold = threshold * max(img_scale_x, img_scale_y)
        roi_info = {
            "points": scaled_points,
            "num_points": len(scaled_points),
            "distance_to_close": distance,
            "is_closed": distance < close_threshold,
            "threshold": threshold,
        }

        if not roi_info["is_closed"]:
            return None, roi_info

        # 閉じたポリゴンとしてマスクを作成
        if distance > 1:
            closed_points = scaled_points + [scaled_points[0]]
        else:
            closed_points = scaled_points
        roi_info["closed_points"] = closed_points

        mask = Image.new("L", (original_image.width, original_image.height), 0)
        ImageDraw.Draw(mask).polygon(closed_points, outline=255, fill=255)
        roi_mask = np.array(mask)

        pts_arr = np.array(closed_points)
        x_min, y_min = pts_arr.min(axis=0)
        x_max, y_max = pts_arr.max(axis=0)
        roi_info.update({
            "bbox": (int(x_min), int(y_min), int(x_max), int(y_max)),
            "width": int(x_max - x_min),
            "height": int(y_max - y_min),
            "area": int(roi_mask.sum() / 255),
            "roi_mask": roi_mask,
        })
        return roi_mask, roi_info

    def _refined_mask_for_preview(
        self,
        pil_image: Image.Image,
        roi_mask: np.ndarray,
    ) -> np.ndarray:
        """
        プレビュー用にパイプラインと同じリファインを1回だけかけたマスクを返す。
        ROIModifier が無い場合はそのまま roi_mask を返す。
        """
        if ROIModifier is None:
            return roi_mask
        img = np.array(pil_image.convert("L"), dtype=np.uint8)
        if roi_mask.shape[:2] != img.shape[:2]:
            roi_mask = cv2.resize(
                roi_mask, (img.shape[1], img.shape[0]),
                interpolation=cv2.INTER_NEAREST,
            )
        modifier = ROIModifier(
            iterations=5,
            search_radius=3,
            angle_threshold=0.5,
            fast_mode=True,
        )
        return modifier.modify_roi(img, roi_mask)

    def _create_preview_image(
        self,
        pil_image: Image.Image,
        roi_mask: np.ndarray,
        roi_info: dict,
    ) -> Image.Image:
        """プレビュー画像を作成（マスクベースで表示と解析を完全一致）"""
        result = pil_image.copy()
        if result.mode != "RGBA":
            result = result.convert("RGBA")

        w, h = pil_image.size

        # roi_mask から直接オーバーレイを作成（ポリゴン描画より正確）
        mask = roi_info.get("roi_mask", roi_mask)
        if mask is not None and mask.shape[:2] == (h, w):
            # RGBA オーバーレイ: ROI 内部を半透明赤で塗る
            overlay_arr = np.zeros((h, w, 4), dtype=np.uint8)
            overlay_arr[mask > 0] = [255, 0, 0, 60]

            # ROI 境界線を描画 (不透明な黄色)
            contours, _ = cv2.findContours(
                mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            boundary = np.zeros((h, w), dtype=np.uint8)
            cv2.drawContours(boundary, contours, -1, 255, 2)
            overlay_arr[boundary > 0] = [255, 255, 0, 220]

            overlay = Image.fromarray(overlay_arr, "RGBA")
            result = Image.alpha_composite(result, overlay)
        else:
            # フォールバック: closed_points からポリゴンを描画
            overlay = Image.new("RGBA", pil_image.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)
            closed_points = roi_info.get("closed_points", [])
            if len(closed_points) >= 3:
                draw.polygon(
                    closed_points,
                    fill=(255, 0, 0, 60),
                    outline=(255, 255, 0, 220),
                )
            result = Image.alpha_composite(result, overlay)

        return result
    
    def _display_compact_status(self, roi_info: dict):
        """コンパクトなステータス表示（Area/Points/Size は非表示）"""
        if roi_info.get("is_closed"):
            st.success("✓ ROI Closed", icon="✅")


# ============================================================================
# メイン統合関数
# ============================================================================
def show_scrollfree_roi_selection(
    image_bytes: bytes,
    file_id: str = "current"
) -> Optional[np.ndarray]:
    """
    スクロールレスROI選択UI（メイン関数）
    
    Parameters
    ----------
    image_bytes : bytes
        入力画像
    file_id : str
        ファイル識別子
    
    Returns
    -------
    np.ndarray or None
        ROIマスク
    """
    # CSSインジェクション
    inject_scrollfree_css()
    
    # Canvas描画
    canvas = ScrollFreeROICanvas()
    roi_mask = canvas.render_compact(
        image_bytes=image_bytes,
        key_suffix=file_id,
        max_canvas_height=500
    )
    
    return roi_mask


# ============================================================================
# デモアプリ
# ============================================================================
def demo_scrollfree_app():
    """スクロールレスUIデモ"""
    
    # ページ設定 - ワイドレイアウト
    st.set_page_config(
        page_title="Scroll-Free ROI Selection",
        page_icon="🎯",
        layout="wide",  # 重要: ワイドレイアウト
        initial_sidebar_state="collapsed"
    )
    
    # CSSインジェクション
    inject_scrollfree_css()
    
    # ファイルアップロード（サイドバー）
    with st.sidebar:
        st.markdown("### 📁 Upload")
        uploaded_file = st.file_uploader(
            "Image",
            type=["png", "jpg", "jpeg", "tif"],
            label_visibility="collapsed"
        )
    
    if uploaded_file:
        image_bytes = uploaded_file.read()
        
        # ROI選択
        roi_mask = show_scrollfree_roi_selection(
            image_bytes=image_bytes,
            file_id="demo"
        )
        
        # アクションボタン（下部固定）
        st.markdown("---")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            analyze_btn = st.button(
                "🚀 Analyze",
                type="primary",
                disabled=(roi_mask is None),
                use_container_width=True
            )
        
        with col2:
            if roi_mask is not None:
                if st.button("💾 Save Mask", use_container_width=True):
                    mask_pil = Image.fromarray(roi_mask)
                    buf = io.BytesIO()
                    mask_pil.save(buf, format='PNG')
                    st.download_button(
                        "📥 Download",
                        buf.getvalue(),
                        "roi_mask.png",
                        "image/png",
                        use_container_width=True
                    )
        
        with col3:
            if st.button("🔄 Reset", use_container_width=True):
                st.experimental_rerun()
        
        with col4:
            st.caption(f"File: {uploaded_file.name}")
    
    else:
        st.markdown('<div class="compact-header">🎯 Scroll-Free ROI Selection</div>', unsafe_allow_html=True)
        st.markdown('<div class="compact-subheader">Upload an image to start</div>', unsafe_allow_html=True)
        st.info("👈 Upload an image from the sidebar")


if __name__ == "__main__":
    demo_scrollfree_app()
