"""
Flow Deficit Ring Analyzer

Flow Deficit（血流欠損領域）の3環解析を行うモジュール。
病変中心から3つの同心円リング（0-0.2mm, 0.2-0.4mm, 0.4-0.6mm）に分割し、
各リングでFD領域の面積、密度、個数を計算。

Author: ARIAKE OCTA Analysis Team
Date: 2026-01-22
"""

from typing import Dict, List

import numpy as np
from scipy import ndimage


class FlowDeficitRingAnalyzer:
    """
    Flow Deficit 3環解析器

    MNV病変内の血流欠損領域を検出し、
    3つの同心円リングで統計を計算。
    """

    def __init__(
        self,
        ring_widths_mm: List[float] = None,
        min_fd_area_mm2: float = 0.001,
        pixel_size_mm: float = 0.003,
    ):
        """
        Parameters
        ----------
        ring_widths_mm : list of float
            各リングの外側半径 [ring1, ring2, ring3] (mm)
            デフォルト: [0.2, 0.4, 0.6]
        min_fd_area_mm2 : float
            最小FD面積 (mm²)。これより小さい領域は除外
        pixel_size_mm : float
            1ピクセルのサイズ (mm)
        """
        if ring_widths_mm is None:
            ring_widths_mm = [0.2, 0.4, 0.6]

        self.ring_widths_mm = ring_widths_mm
        self.min_fd_area_mm2 = min_fd_area_mm2
        self.pixel_size_mm = pixel_size_mm

        # ピクセル単位
        self.ring_widths_pixels = [int(w / pixel_size_mm) for w in ring_widths_mm]
        self.min_fd_area_pixels = int(min_fd_area_mm2 / (pixel_size_mm**2))

    def analyze(
        self, binary_image: np.ndarray, lesion_center: tuple, lesion_mask: np.ndarray
    ) -> Dict:
        """
        Flow Deficit 3環解析を実行

        Parameters
        ----------
        binary_image : np.ndarray
            血管二値化画像 (0 or 255)
        lesion_center : tuple
            病変中心座標 (center_y, center_x) ピクセル単位
        lesion_mask : np.ndarray
            病変マスク (bool)

        Returns
        -------
        dict
            解析結果
            - ring1_*: Ring 1 (0-0.2mm) の統計
            - ring2_*: Ring 2 (0.2-0.4mm) の統計
            - ring3_*: Ring 3 (0.4-0.6mm) の統計
            - overall_*: 全体統計
        """
        center_y, center_x = lesion_center

        # Flow Deficit マスク（病変内の血管がない領域）
        binary = (binary_image > 127).astype(bool)
        fd_mask = lesion_mask & (~binary)

        # 3つのリングマスクを作成
        ring_masks = self._create_ring_masks(
            binary_image.shape, center_y, center_x, self.ring_widths_pixels
        )

        # 各リングでFD解析
        ring_results = []
        for i, ring_mask in enumerate(ring_masks):
            ring_fd = fd_mask & ring_mask
            result = self._analyze_ring(ring_fd, ring_mask, ring_idx=i + 1)
            ring_results.append(result)

        # 全体統計
        overall_fd_area = np.sum(fd_mask) * (self.pixel_size_mm**2)
        overall_lesion_area = np.sum(lesion_mask) * (self.pixel_size_mm**2)
        overall_fd_ratio = (
            overall_fd_area / overall_lesion_area * 100
            if overall_lesion_area > 0
            else 0.0
        )

        # 結果を統合
        result = {
            # Ring 1 (0-0.2mm)
            "ring1_fd_area_mm2": ring_results[0]["fd_area_mm2"],
            "ring1_fd_ratio_percent": ring_results[0]["fd_ratio_percent"],
            "ring1_fd_count": ring_results[0]["fd_count"],
            "ring1_avg_fd_area_mm2": ring_results[0]["avg_fd_area_mm2"],
            # Ring 2 (0.2-0.4mm)
            "ring2_fd_area_mm2": ring_results[1]["fd_area_mm2"],
            "ring2_fd_ratio_percent": ring_results[1]["fd_ratio_percent"],
            "ring2_fd_count": ring_results[1]["fd_count"],
            "ring2_avg_fd_area_mm2": ring_results[1]["avg_fd_area_mm2"],
            # Ring 3 (0.4-0.6mm)
            "ring3_fd_area_mm2": ring_results[2]["fd_area_mm2"],
            "ring3_fd_ratio_percent": ring_results[2]["fd_ratio_percent"],
            "ring3_fd_count": ring_results[2]["fd_count"],
            "ring3_avg_fd_area_mm2": ring_results[2]["avg_fd_area_mm2"],
            # Overall
            "overall_fd_area_mm2": overall_fd_area,
            "overall_fd_ratio_percent": overall_fd_ratio,
            # マスク
            "fd_mask": fd_mask,
            "ring_masks": ring_masks,
        }

        return result

    def _create_ring_masks(
        self, shape: tuple, center_y: float, center_x: float, ring_radii: List[int]
    ) -> List[np.ndarray]:
        """
        同心円リングマスクを作成

        Parameters
        ----------
        shape : tuple
            画像サイズ (height, width)
        center_y, center_x : float
            中心座標
        ring_radii : list of int
            各リングの外側半径 [r1, r2, r3] (ピクセル)

        Returns
        -------
        list of np.ndarray
            3つのリングマスク (bool)
        """
        y_indices, x_indices = np.ogrid[: shape[0], : shape[1]]

        distances = np.sqrt((y_indices - center_y) ** 2 + (x_indices - center_x) ** 2)

        # Ring 1: 0 ~ r1
        ring1 = distances <= ring_radii[0]

        # Ring 2: r1 ~ r2
        ring2 = (distances > ring_radii[0]) & (distances <= ring_radii[1])

        # Ring 3: r2 ~ r3
        ring3 = (distances > ring_radii[1]) & (distances <= ring_radii[2])

        return [ring1, ring2, ring3]

    def _analyze_ring(
        self, fd_mask: np.ndarray, ring_mask: np.ndarray, ring_idx: int
    ) -> Dict:
        """
        1つのリングのFD解析

        Parameters
        ----------
        fd_mask : np.ndarray
            リング内のFlow Deficitマスク (bool)
        ring_mask : np.ndarray
            リングマスク (bool)
        ring_idx : int
            リング番号 (1, 2, 3)

        Returns
        -------
        dict
            リング統計
        """
        # FD領域の連結成分ラベリング
        labeled_fd, num_fd = ndimage.label(fd_mask)

        # 小さいFD領域を除外
        filtered_fd_mask = np.zeros_like(fd_mask)
        fd_areas = []

        for label_id in range(1, num_fd + 1):
            component = labeled_fd == label_id
            area_pixels = np.sum(component)

            if area_pixels >= self.min_fd_area_pixels:
                filtered_fd_mask |= component
                area_mm2 = area_pixels * (self.pixel_size_mm**2)
                fd_areas.append(area_mm2)

        # 統計計算
        fd_count = len(fd_areas)
        fd_total_area = sum(fd_areas) if fd_areas else 0.0
        avg_fd_area = fd_total_area / fd_count if fd_count > 0 else 0.0

        # リング面積
        ring_area_pixels = np.sum(ring_mask)
        ring_area_mm2 = ring_area_pixels * (self.pixel_size_mm**2)

        # FD比率
        fd_ratio = fd_total_area / ring_area_mm2 * 100 if ring_area_mm2 > 0 else 0.0

        return {
            "fd_area_mm2": fd_total_area,
            "fd_ratio_percent": fd_ratio,
            "fd_count": fd_count,
            "avg_fd_area_mm2": avg_fd_area,
            "ring_area_mm2": ring_area_mm2,
        }


def create_analyzer(pixel_size_mm: float = 0.003) -> FlowDeficitRingAnalyzer:
    """
    デフォルトパラメータで解析器を作成

    Parameters
    ----------
    pixel_size_mm : float
        ピクセルサイズ (mm)

    Returns
    -------
    FlowDeficitRingAnalyzer
        Flow Deficit解析器
    """
    return FlowDeficitRingAnalyzer(
        ring_widths_mm=[0.2, 0.4, 0.6],
        min_fd_area_mm2=0.001,
        pixel_size_mm=pixel_size_mm,
    )
