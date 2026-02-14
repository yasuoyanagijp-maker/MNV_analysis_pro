"""
FAZ (Foveal Avascular Zone) detection

ImageJ equivalent: processVDFile() FAZ detection
Enhanced FAZ Segmentation with multiple methods
"""

from typing import Dict, Optional, Tuple

import numpy as np
from skimage import measure, morphology


class FAZDetector:
    """
    FAZ（Foveal Avascular Zone）自動検出

    ImageJマクロの対応箇所:
    - processVDFile() 内のFAZ検出
    - doWand() によるシード領域検出
    """

    def __init__(
        self,
        min_area_mm2: float = 0.1,
        min_circularity: float = 0.6,
        search_radius: int = 15,
    ):
        """
        Args:
            min_area_mm2: 最小FAZ面積（mm²）
            min_circularity: 最小円形度（0-1）
            search_radius: シード点探索半径（ピクセル）
        """
        self.min_area_mm2 = min_area_mm2
        self.min_circularity = min_circularity
        self.search_radius = search_radius

    def detect(
        self, binary_image: np.ndarray, pixel_size_mm: float = 0.00744
    ) -> Tuple[Optional[np.ndarray], Dict]:
        """
        FAZを検出

        Args:
            binary_image: 二値化済み血管画像 (H×W bool)
            pixel_size_mm: ピクセルサイズ（mm/pixel）

        Returns:
            faz_roi: FAZ領域マスク (H×W bool) or None
            metrics: {
                'faz_area_mm2': float,
                'faz_perimeter_mm': float,
                'faz_circularity': float,
                'faz_equivalent_diameter_mm': float,
                'faz_center_y_mm': float,
                'faz_center_x_mm': float
            }

        Raises:
            RuntimeError: FAZ検出失敗

        アルゴリズム:
            1. 画像中央から最も近い黒ピクセルをシード点とする
            2. Connected Components解析で連結領域を検出
            3. 最大の穴（黒領域）をFAZとする
            4. 円形度フィルタ（> 0.6）
        """
        h, w = binary_image.shape
        center_y, center_x = h // 2, w // 2

        # 中央付近の黒ピクセルを探索（血管がない領域 = False）
        inverted = ~binary_image
        seed_found = False
        seed_y, seed_x = center_y, center_x

        for r in range(1, self.search_radius + 1):
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    y, x = center_y + dy, center_x + dx
                    if 0 <= y < h and 0 <= x < w and inverted[y, x]:
                        seed_y, seed_x = y, x
                        seed_found = True
                        break
                if seed_found:
                    break
            if seed_found:
                break

        if not seed_found:
            return None, self._empty_metrics()

        # Connected Components解析
        labeled = measure.label(inverted, connectivity=2)
        seed_label = labeled[seed_y, seed_x]

        if seed_label == 0:
            return None, self._empty_metrics()

        faz_roi = labeled == seed_label

        # 形態学的処理（小さな穴を埋める） — use new skimage API
        faz_roi = morphology.remove_small_holes(faz_roi, area_threshold=50)
        faz_roi = morphology.binary_closing(faz_roi, morphology.disk(2))

        # 領域プロパティ計算
        props = measure.regionprops(faz_roi.astype(int))[0]

        # 円形度計算
        area_px = props.area
        perimeter_px = props.perimeter
        circularity = 4 * np.pi * area_px / (perimeter_px**2) if perimeter_px > 0 else 0

        # 円形度チェック
        if circularity < self.min_circularity:
            return None, self._empty_metrics()

        # メトリクス計算（ピクセル → mm変換）
        area_mm2 = area_px * (pixel_size_mm**2)
        perimeter_mm = perimeter_px * pixel_size_mm
        equivalent_diameter_mm = np.sqrt(4 * area_mm2 / np.pi)

        # 面積チェック
        if area_mm2 < self.min_area_mm2:
            return None, self._empty_metrics()

        # 中心座標（mm）
        centroid = props.centroid
        center_y_mm = centroid[0] * pixel_size_mm
        center_x_mm = centroid[1] * pixel_size_mm

        metrics = {
            "faz_area_mm2": float(area_mm2),
            "faz_perimeter_mm": float(perimeter_mm),
            "faz_circularity": float(circularity),
            "faz_equivalent_diameter_mm": float(equivalent_diameter_mm),
            "faz_center_y_mm": float(center_y_mm),
            "faz_center_x_mm": float(center_x_mm),
        }

        return faz_roi, metrics

    def _empty_metrics(self) -> Dict:
        """空のメトリクスを返す"""
        return {
            "faz_area_mm2": 0.0,
            "faz_perimeter_mm": 0.0,
            "faz_circularity": 0.0,
            "faz_equivalent_diameter_mm": 0.0,
            "faz_center_y_mm": 0.0,
            "faz_center_x_mm": 0.0,
        }
