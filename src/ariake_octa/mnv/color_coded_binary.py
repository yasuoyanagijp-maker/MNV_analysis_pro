"""
Color-Coded Binary Visualization Module

血管二値画像を血管太さに応じて擬似カラー表示。
Distance Transformで太さを計算し、ヒートマップ表示。

Author: ARIAKE OCTA Analysis Team
Date: 2026-01-22
"""

import cv2
import numpy as np
from scipy import ndimage


class ColorCodedBinary:
    """
    擬似カラー可視化器

    血管の太さをDistance Transformで計算し、
    色で可視化（太い=赤、細い=緑）。
    """

    def __init__(
        self, saturation_percentile: float = 0.35, colormap: int = cv2.COLORMAP_JET
    ):
        """
        Parameters
        ----------
        saturation_percentile : float
            コントラスト強調のための飽和パーセンタイル (0-1)
        colormap : int
            OpenCVのカラーマップ (COLORMAP_JET, COLORMAP_HOT, etc.)
        """
        self.saturation_percentile = saturation_percentile
        self.colormap = colormap

    def create_color_coded(
        self, binary_vessel: np.ndarray, enhance_contrast: bool = True
    ) -> np.ndarray:
        """
        擬似カラー画像を作成

        Parameters
        ----------
        binary_vessel : np.ndarray
            血管二値画像 (0 or 255)
        enhance_contrast : bool
            コントラスト強調を行うか

        Returns
        -------
        np.ndarray
            擬似カラー画像 (H×W×3, uint8)
        """
        # 二値化確認
        binary = (binary_vessel > 127).astype(bool)

        if not np.any(binary):
            # 血管なし: 黒画像を返す
            return np.zeros((*binary.shape, 3), dtype=np.uint8)

        # Distance Transform（血管の太さ）
        distance = ndimage.distance_transform_edt(binary)

        # コントラスト強調
        if enhance_contrast:
            distance = self._enhance_contrast(distance, binary)

        # 正規化（0-255）
        if distance.max() > 0:
            distance_normalized = (distance / distance.max() * 255).astype(np.uint8)
        else:
            distance_normalized = np.zeros_like(distance, dtype=np.uint8)

        # 非血管領域を0に
        distance_normalized[~binary] = 0

        # カラーマップ適用
        color_coded = cv2.applyColorMap(distance_normalized, self.colormap)

        # 非血管領域を黒に
        color_coded[~binary] = [0, 0, 0]

        return color_coded

    def _enhance_contrast(self, distance: np.ndarray, mask: np.ndarray) -> np.ndarray:
        """
        コントラスト強調

        Parameters
        ----------
        distance : np.ndarray
            Distance Transform結果
        mask : np.ndarray
            血管マスク

        Returns
        -------
        np.ndarray
            コントラスト強調後の距離画像
        """
        # 血管領域のみの値を取得
        vessel_distances = distance[mask]

        if len(vessel_distances) == 0:
            return distance

        # パーセンタイル計算
        saturation_value = np.percentile(
            vessel_distances, (1 - self.saturation_percentile) * 100
        )

        # 飽和
        distance_enhanced = distance.copy()
        distance_enhanced = np.clip(distance_enhanced, 0, saturation_value)

        return distance_enhanced

    def create_with_overlay(
        self, original_image: np.ndarray, binary_vessel: np.ndarray, alpha: float = 0.7
    ) -> np.ndarray:
        """
        元画像とのオーバーレイ表示

        Parameters
        ----------
        original_image : np.ndarray
            元画像 (グレースケール)
        binary_vessel : np.ndarray
            血管二値画像
        alpha : float
            擬似カラーの不透明度 (0-1)

        Returns
        -------
        np.ndarray
            オーバーレイ画像 (H×W×3, uint8)
        """
        # 擬似カラー生成
        color_coded = self.create_color_coded(binary_vessel)

        # 元画像をRGBに変換
        if len(original_image.shape) == 2:
            original_rgb = cv2.cvtColor(original_image, cv2.COLOR_GRAY2BGR)
        else:
            original_rgb = original_image.copy()

        # 血管領域のみオーバーレイ
        binary = (binary_vessel > 127).astype(bool)
        overlay = original_rgb.copy()
        overlay[binary] = (
            alpha * color_coded[binary] + (1 - alpha) * original_rgb[binary]
        ).astype(np.uint8)

        return overlay


class ColorMapPresets:
    """
    カラーマッププリセット
    """

    @staticmethod
    def jet() -> int:
        """JET (青→緑→黄→赤)"""
        return cv2.COLORMAP_JET

    @staticmethod
    def hot() -> int:
        """HOT (黒→赤→黄→白)"""
        return cv2.COLORMAP_HOT

    @staticmethod
    def rainbow() -> int:
        """RAINBOW (紫→青→緑→黄→赤)"""
        return cv2.COLORMAP_RAINBOW

    @staticmethod
    def turbo() -> int:
        """TURBO (改良版JET)"""
        return cv2.COLORMAP_TURBO


def create_visualizer(
    saturation_percentile: float = 0.35, colormap: str = "jet"
) -> ColorCodedBinary:
    """
    デフォルトパラメータで可視化器を作成

    Parameters
    ----------
    saturation_percentile : float
        飽和パーセンタイル
    colormap : str
        カラーマップ名 ('jet', 'hot', 'rainbow', 'turbo')

    Returns
    -------
    ColorCodedBinary
        擬似カラー可視化器
    """
    colormap_dict = {
        "jet": cv2.COLORMAP_JET,
        "hot": cv2.COLORMAP_HOT,
        "rainbow": cv2.COLORMAP_RAINBOW,
        "turbo": cv2.COLORMAP_TURBO,
    }

    colormap_id = colormap_dict.get(colormap.lower(), cv2.COLORMAP_JET)

    return ColorCodedBinary(
        saturation_percentile=saturation_percentile, colormap=colormap_id
    )
