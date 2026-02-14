"""
MNV Lesion Detector

MNV病変の自動検出を行うモジュール。
複雑形状検出、複数病変のマージ、形態学的処理を実装。

Author: ARIAKE OCTA Analysis Team
Date: 2026-01-22
"""

from typing import Dict, Optional, Tuple

import numpy as np
from scipy import ndimage
from skimage import measure, morphology


class MNVLesionDetector:
    """
    MNV病変検出器

    複雑形状のMNV病変を検出し、中心座標と境界を決定する。
    複数の小病変を統合し、形態学的処理で境界をスムーズ化。
    """

    def __init__(
        self,
        min_area_mm2: float = 0.05,
        merge_distance_mm: float = 0.3,
        morphology_radius_mm: float = 0.05,
        pixel_size_mm: float = 0.003,
    ):
        """
        Parameters
        ----------
        min_area_mm2 : float
            最小病変面積 (mm²)。これより小さい領域は除外
        merge_distance_mm : float
            病変統合距離 (mm)。この距離内の病変を統合
        morphology_radius_mm : float
            形態学的処理の半径 (mm)。境界スムーズ化に使用
        pixel_size_mm : float
            1ピクセルのサイズ (mm)
        """
        self.min_area_mm2 = min_area_mm2
        self.merge_distance_mm = merge_distance_mm
        self.morphology_radius_mm = morphology_radius_mm
        self.pixel_size_mm = pixel_size_mm

        # ピクセル単位のパラメータ
        self.min_area_pixels = int(min_area_mm2 / (pixel_size_mm**2))
        self.merge_distance_pixels = int(merge_distance_mm / pixel_size_mm)
        self.morphology_radius_pixels = int(morphology_radius_mm / pixel_size_mm)

    def detect(
        self, binary_image: np.ndarray, fused_response: Optional[np.ndarray] = None
    ) -> Dict:
        """
        MNV病変を検出

        Parameters
        ----------
        binary_image : np.ndarray
            二値化画像 (0 or 255)
        fused_response : np.ndarray, optional
            融合フィルタ応答画像（重心計算に使用）

        Returns
        -------
        dict
            検出結果
            - lesion_mask: 病変マスク (bool)
            - center_x, center_y: 病変中心座標 (pixel)
            - center_x_mm, center_y_mm: 病変中心座標 (mm)
            - area_mm2: 病変面積 (mm²)
            - num_components: 統合前の連結成分数
            - bounding_box: (min_row, min_col, max_row, max_col)
        """
        # 二値化確認
        binary = (binary_image > 127).astype(np.uint8)

        # ステップ1: 連結成分ラベリング
        labeled, num_labels = ndimage.label(binary)

        if num_labels == 0:
            # 病変なし
            return self._empty_result(binary_image.shape)

        # ステップ2: 小領域除去
        filtered_labels = self._filter_small_components(labeled, num_labels)

        if filtered_labels.max() == 0:
            return self._empty_result(binary_image.shape)

        # ステップ3: 近接病変の統合
        merged_mask = self._merge_nearby_lesions(filtered_labels)

        # ステップ4: 形態学的処理（境界スムーズ化）
        smoothed_mask = self._smooth_boundaries(merged_mask)

        # ステップ5: 病変中心の計算
        center_y, center_x = self._compute_center(smoothed_mask, fused_response)

        # ステップ6: メトリクス計算
        area_pixels = np.sum(smoothed_mask)
        area_mm2 = area_pixels * (self.pixel_size_mm**2)

        # Bounding box
        rows, cols = np.where(smoothed_mask)
        if len(rows) > 0:
            bbox = (int(rows.min()), int(cols.min()), int(rows.max()), int(cols.max()))
        else:
            bbox = (0, 0, 0, 0)

        return {
            "lesion_mask": smoothed_mask,
            "center_x": int(center_x),
            "center_y": int(center_y),
            "center_x_mm": center_x * self.pixel_size_mm,
            "center_y_mm": center_y * self.pixel_size_mm,
            "area_mm2": area_mm2,
            "area_pixels": int(area_pixels),
            "num_components": num_labels,
            "bounding_box": bbox,
        }

    def _filter_small_components(
        self, labeled: np.ndarray, num_labels: int
    ) -> np.ndarray:
        """
        小さい連結成分を除去

        Parameters
        ----------
        labeled : np.ndarray
            ラベル画像
        num_labels : int
            ラベル数

        Returns
        -------
        np.ndarray
            フィルタ後のラベル画像
        """
        filtered = np.zeros_like(labeled)
        new_label = 1

        for label_id in range(1, num_labels + 1):
            component_mask = labeled == label_id
            area = np.sum(component_mask)

            if area >= self.min_area_pixels:
                filtered[component_mask] = new_label
                new_label += 1

        return filtered

    def _merge_nearby_lesions(self, labeled: np.ndarray) -> np.ndarray:
        """
        近接する病変を統合

        Parameters
        ----------
        labeled : np.ndarray
            ラベル画像

        Returns
        -------
        np.ndarray
            統合後のマスク (bool)
        """
        if labeled.max() == 0:
            return np.zeros_like(labeled, dtype=bool)

        # バイナリマスクに変換
        binary = labeled > 0

        # 膨張により近接領域を接続
        if self.merge_distance_pixels > 0:
            struct_elem = morphology.disk(self.merge_distance_pixels)
            dilated = morphology.binary_dilation(binary, struct_elem)

            # 連結成分ラベリング
            merged_labeled = measure.label(dilated, connectivity=2)

            # 最大面積の成分のみ保持
            if merged_labeled.max() > 0:
                areas = [
                    np.sum(merged_labeled == i)
                    for i in range(1, merged_labeled.max() + 1)
                ]
                largest_label = np.argmax(areas) + 1
                merged_mask = merged_labeled == largest_label
            else:
                merged_mask = dilated

            # 元のサイズに収縮
            merged_mask = morphology.binary_erosion(merged_mask, struct_elem)
        else:
            merged_mask = binary

        return merged_mask

    def _smooth_boundaries(self, mask: np.ndarray) -> np.ndarray:
        """
        病変境界をスムーズ化

        Parameters
        ----------
        mask : np.ndarray
            バイナリマスク

        Returns
        -------
        np.ndarray
            スムーズ化されたマスク (bool)
        """
        if self.morphology_radius_pixels <= 0:
            return mask.astype(bool)

        # Closing: 小さな穴を埋める
        struct_elem = morphology.disk(self.morphology_radius_pixels)
        closed = morphology.binary_closing(mask, struct_elem)

        # Opening: 小さな突起を除去
        smoothed = morphology.binary_opening(closed, struct_elem)

        return smoothed

    def _compute_center(
        self, mask: np.ndarray, weight_image: Optional[np.ndarray] = None
    ) -> Tuple[float, float]:
        """
        病変中心を計算

        Parameters
        ----------
        mask : np.ndarray
            病変マスク
        weight_image : np.ndarray, optional
            重み画像（フィルタ応答など）

        Returns
        -------
        tuple
            (center_y, center_x) ピクセル座標
        """
        if not np.any(mask):
            # マスクが空の場合は画像中心
            return mask.shape[0] / 2, mask.shape[1] / 2

        if weight_image is not None:
            # 加重重心
            weights = mask.astype(float) * weight_image
            total_weight = np.sum(weights)

            if total_weight > 0:
                y_indices, x_indices = np.meshgrid(
                    np.arange(mask.shape[0]), np.arange(mask.shape[1]), indexing="ij"
                )

                center_y = np.sum(y_indices * weights) / total_weight
                center_x = np.sum(x_indices * weights) / total_weight

                return center_y, center_x

        # 通常の重心
        y_coords, x_coords = np.where(mask)
        center_y = np.mean(y_coords)
        center_x = np.mean(x_coords)

        return center_y, center_x

    def _empty_result(self, shape: Tuple[int, int]) -> Dict:
        """
        病変なしの結果を返す

        Parameters
        ----------
        shape : tuple
            画像サイズ

        Returns
        -------
        dict
            空の結果
        """
        center_y, center_x = shape[0] / 2, shape[1] / 2

        return {
            "lesion_mask": np.zeros(shape, dtype=bool),
            "center_x": int(center_x),
            "center_y": int(center_y),
            "center_x_mm": center_x * self.pixel_size_mm,
            "center_y_mm": center_y * self.pixel_size_mm,
            "area_mm2": 0.0,
            "area_pixels": 0,
            "num_components": 0,
            "bounding_box": (0, 0, 0, 0),
        }


def create_detector(pixel_size_mm: float = 0.003) -> MNVLesionDetector:
    """
    デフォルトパラメータで検出器を作成

    Parameters
    ----------
    pixel_size_mm : float
        ピクセルサイズ (mm)

    Returns
    -------
    MNVLesionDetector
        病変検出器
    """
    return MNVLesionDetector(
        min_area_mm2=0.05,
        merge_distance_mm=0.3,
        morphology_radius_mm=0.05,
        pixel_size_mm=pixel_size_mm,
    )
