"""
RGB Visualization Module

MNV解析結果をRGB合成画像として可視化。
赤チャンネル: 拡張血管（Arteriolarization）
緑チャンネル: 正常血管
青チャンネル: 背景

Author: ARIAKE OCTA Analysis Team
Date: 2026-01-22
"""

from typing import Dict, Optional, Tuple

import cv2
import numpy as np


class VisualizationRGB:
    """
    RGB合成可視化器

    MNV病変を3チャンネルRGB画像として可視化。
    各チャンネルで異なる血管成分を強調表示。
    """

    def __init__(
        self,
        pixel_size_mm: float = 0.003,
        scale_bar_length_mm: float = 0.5,
        font_scale: float = 0.6,
        font_thickness: int = 1,
    ):
        """
        Parameters
        ----------
        pixel_size_mm : float
            ピクセルサイズ (mm)
        scale_bar_length_mm : float
            スケールバーの長さ (mm)
        font_scale : float
            テキストのフォントスケール
        font_thickness : int
            テキストの太さ
        """
        self.pixel_size_mm = pixel_size_mm
        self.scale_bar_length_mm = scale_bar_length_mm
        self.font_scale = font_scale
        self.font_thickness = font_thickness

    def create_rgb_visualization(
        self,
        original_image: np.ndarray,
        binary_vessel: np.ndarray,
        lesion_mask: np.ndarray,
        metrics: Optional[Dict] = None,
        highskew_mask: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        """
        RGB合成可視化を作成 (ImageJ createVisualizationRGB互換)

        ImageJ減算法: R=元画像, G=元画像-Dilated_HighSkew, B=元画像-binary
        色の意味（ImageJ 仕様・正）:
          - 正常血管(binary): 黄色 (B=0 のため R+G が支配的)
          - 拡張血管(highskew): 赤 (G=B=0 のため R のみ)
          - 背景: グレー (R=G=B=元画像)

        Parameters
        ----------
        original_image : np.ndarray
            元画像 (グレースケール)
        binary_vessel : np.ndarray
            血管二値画像
        lesion_mask : np.ndarray
            病変マスク (ROI境界描画用)
        metrics : dict, optional
            表示する統計情報
        highskew_mask : np.ndarray, optional
            dilated_highSkew_for_visualization (ImageJ互換の拡張血管マスク)
            指定時は赤チャンネルに使用。未指定時は簡易版 _detect_dilated_vessels を使用

        Returns
        -------
        np.ndarray
            RGB画像 (H×W×3, uint8)
        """
        # ImageJ createVisualizationRGB (3973-4021): subtractive method
        # R = original, G = original - Dilated_HighSkew, B = original - binary
        #
        # ★ ImageJ 互換: crop_reference は ROI クロップのみ表示
        #   ROI 内のみ減算を適用し、ROI 外は元画像のまま（グレー）
        #
        # ★ チャンネル順序: RGB (ImageJ と同じ)
        h, w = original_image.shape
        orig = np.clip(
            original_image.astype(np.float32), 0, 255
        )  # ensure float for subtraction

        roi_in = (lesion_mask > 0) if np.any(lesion_mask) else np.ones((h, w), dtype=bool)

        # R channel: original
        r_ch = np.clip(orig, 0, 255).astype(np.uint8)

        # G channel: ROI 内のみ orig - Dilated_HighSkew
        if highskew_mask is not None and np.any(highskew_mask > 0):
            hsk = (
                highskew_mask.astype(np.float32)
                if highskew_mask.dtype != np.float32
                else highskew_mask.copy()
            )
            hsk = np.clip(hsk, 0, 255)
            g_sub = np.clip(orig - hsk, 0, 255).astype(np.uint8)
        else:
            dilated_vessels = self._detect_dilated_vessels(binary_vessel)
            hsk = dilated_vessels.astype(np.float32) * 255
            g_sub = np.clip(orig - hsk, 0, 255).astype(np.uint8)
        g_ch = np.where(roi_in, g_sub, orig).astype(np.uint8)

        # B channel: ROI 内のみ orig - binary
        bin_float = (binary_vessel > 0).astype(np.float32) * 255
        b_sub = np.clip(orig - bin_float, 0, 255).astype(np.uint8)
        b_ch = np.where(roi_in, b_sub, orig).astype(np.uint8)

        # RGB order (ImageJ 互換: c1=R, c2=G, c3=B)
        rgb_image = np.stack([r_ch, g_ch, b_ch], axis=-1)

        # 病変境界の黄色枠は描画しない（ImageJ crop_reference は枠なし表示）
        # 従来: _draw_lesion_boundary で ROI 輪郭を黄色描画 → 削除

        # スケールバー追加
        rgb_image = self._add_scale_bar(rgb_image)

        # 統計情報のテキストオーバーレイ
        if metrics:
            rgb_image = self._add_text_overlay(rgb_image, metrics)

        return rgb_image

    def _detect_dilated_vessels(
        self, binary_vessel: np.ndarray, dilation_threshold: int = 3
    ) -> np.ndarray:
        """
        拡張血管を検出（太い血管）

        Parameters
        ----------
        binary_vessel : np.ndarray
            血管二値画像
        dilation_threshold : int
            膨張回数のしきい値

        Returns
        -------
        np.ndarray
            拡張血管マスク (bool)
        """
        # 距離変換で血管の太さを推定
        from scipy import ndimage

        distance = ndimage.distance_transform_edt(binary_vessel)

        # しきい値以上の太さを拡張血管とする
        dilated_mask = distance >= dilation_threshold

        return dilated_mask

    def _draw_lesion_boundary(
        self,
        rgb_image: np.ndarray,
        lesion_mask: np.ndarray,
        color: Tuple[int, int, int] = (0, 255, 255),  # 黄色 (RGB: R=0でなくBGRでもない → 後述)
    ) -> np.ndarray:
        """
        病変境界を描画

        Parameters
        ----------
        rgb_image : np.ndarray
            RGB画像 (RGB 順)
        lesion_mask : np.ndarray
            病変マスク (0/255 の uint8)
        color : tuple
            境界線の色 (R, G, B) - RGB 順

        Returns
        -------
        np.ndarray
            境界線を追加したRGB画像
        """
        # lesion_mask を確実に 0/255 の uint8 に変換 (uint8*255 オーバーフロー防止)
        if lesion_mask.dtype == bool:
            lesion_uint8 = lesion_mask.astype(np.uint8) * 255
        elif lesion_mask.max() <= 1:
            lesion_uint8 = (lesion_mask * 255).astype(np.uint8)
        else:
            lesion_uint8 = np.where(lesion_mask > 0, 255, 0).astype(np.uint8)

        contours, _ = cv2.findContours(
            lesion_uint8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        # ★ cv2.drawContours の color は配列のチャンネル順に依存
        # rgb_image は RGB 順なので color=(R, G, B) で指定
        # 黄色 = (255, 255, 0) in RGB
        cv2.drawContours(rgb_image, contours, -1, (255, 255, 0), 2)

        return rgb_image

    def _add_scale_bar(
        self,
        rgb_image: np.ndarray,
        position: str = "bottom-right",
        color: Tuple[int, int, int] = (255, 255, 0),  # 黄色
        thickness: int = 3,
    ) -> np.ndarray:
        """
        スケールバーを追加

        Parameters
        ----------
        rgb_image : np.ndarray
            RGB画像
        position : str
            位置 ('bottom-right', 'bottom-left', etc.)
        color : tuple
            スケールバーの色 (R, G, B)
        thickness : int
            スケールバーの太さ

        Returns
        -------
        np.ndarray
            スケールバー付きRGB画像
        """
        h, w = rgb_image.shape[:2]

        # スケールバーの長さ（ピクセル）
        bar_length_px = int(self.scale_bar_length_mm / self.pixel_size_mm)

        # 位置計算
        margin = 20
        if position == "bottom-right":
            x1 = w - margin - bar_length_px
            x2 = w - margin
            y = h - margin
        elif position == "bottom-left":
            x1 = margin
            x2 = margin + bar_length_px
            y = h - margin
        else:
            x1 = w - margin - bar_length_px
            x2 = w - margin
            y = h - margin

        # スケールバー描画
        cv2.line(rgb_image, (x1, y), (x2, y), color, thickness)

        # テキスト（長さ表示）
        text = f"{self.scale_bar_length_mm} mm"
        text_size = cv2.getTextSize(
            text, cv2.FONT_HERSHEY_SIMPLEX, self.font_scale * 0.7, self.font_thickness
        )[0]

        text_x = x1 + (bar_length_px - text_size[0]) // 2
        text_y = y - 5

        cv2.putText(
            rgb_image,
            text,
            (text_x, text_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            self.font_scale * 0.7,
            color,
            self.font_thickness,
            cv2.LINE_AA,
        )

        return rgb_image

    def _add_text_overlay(
        self,
        rgb_image: np.ndarray,
        metrics: Dict,
        position: str = "top-left",
        bg_color: Tuple[int, int, int] = (0, 0, 0),  # 黒
        text_color: Tuple[int, int, int] = (255, 255, 0),  # 黄色
    ) -> np.ndarray:
        """
        統計情報のテキストオーバーレイ

        Parameters
        ----------
        rgb_image : np.ndarray
            RGB画像
        metrics : dict
            統計情報
        position : str
            テキスト位置
        bg_color : tuple
            背景色 (R, G, B)
        text_color : tuple
            テキスト色 (R, G, B)

        Returns
        -------
        np.ndarray
            テキスト付きRGB画像
        """
        # 表示するメトリクス選択
        lines = []

        if "lesion_area_mm2" in metrics:
            lines.append(f"Lesion: {metrics['lesion_area_mm2']:.3f} mm2")

        if "vessel_density_percent" in metrics:
            lines.append(f"VD: {metrics['vessel_density_percent']:.1f}%")

        if "skeleton_num_junctions" in metrics:
            lines.append(f"Junctions: {metrics['skeleton_num_junctions']}")

        if "overall_fd_ratio_percent" in metrics:
            lines.append(f"FD: {metrics['overall_fd_ratio_percent']:.1f}%")

        # テキスト描画
        margin = 10
        line_height = 25
        y_offset = margin + 20

        for i, line in enumerate(lines):
            y = y_offset + i * line_height

            # 背景矩形（半透明効果のため2回描画）
            text_size = cv2.getTextSize(
                line, cv2.FONT_HERSHEY_SIMPLEX, self.font_scale, self.font_thickness
            )[0]

            cv2.rectangle(
                rgb_image,
                (margin - 5, y - text_size[1] - 5),
                (margin + text_size[0] + 5, y + 5),
                bg_color,
                -1,
            )

            # テキスト描画
            cv2.putText(
                rgb_image,
                line,
                (margin, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                self.font_scale,
                text_color,
                self.font_thickness,
                cv2.LINE_AA,
            )

        return rgb_image


def create_visualizer(pixel_size_mm: float = 0.003) -> VisualizationRGB:
    """
    デフォルトパラメータで可視化器を作成

    Parameters
    ----------
    pixel_size_mm : float
        ピクセルサイズ (mm)

    Returns
    -------
    VisualizationRGB
        RGB可視化器
    """
    return VisualizationRGB(
        pixel_size_mm=pixel_size_mm,
        scale_bar_length_mm=0.5,
        font_scale=0.6,
        font_thickness=1,
    )
