"""
Sector splitting for VD analysis

4 sectors (Temporal/Nasal/Superior/Inferior) + Center/Periphery division
"""

from typing import Dict, Tuple

import numpy as np
from skimage import measure


class SectorSplitter:
    """
    4セクター（T/N/S/I）+ Center/Periphery 分割

    ImageJマクロの対応箇所:
    - processVDFile() 内のROI分割
    - makeRotatedRectangle() による4セクター作成
    """

    def __init__(self, n_sectors: int = 4):
        """
        Args:
            n_sectors: セクター数（通常4）
        """
        self.n_sectors = n_sectors

    def split_into_sectors(
        self, faz_roi: np.ndarray, pixel_size_mm: float = 0.00744, side: str = "right"
    ) -> Dict[str, np.ndarray]:
        """
        4セクター（Temporal/Nasal/Superior/Inferior）に分割

        Args:
            faz_roi: FAZ領域マスク (H×W bool)
            pixel_size_mm: ピクセルサイズ（mm/pixel）
            side: 'right' または 'left'（左右眼の区別）

        Returns:
            sectors: {
                'temporal': (H×W bool),
                'nasal': (H×W bool),
                'superior': (H×W bool),
                'inferior': (H×W bool)
            }

        アルゴリズム:
            1. FAZ中心を基準にドーナツ型ROIを作成（ETDRS準拠: 1-3mm）
            2. 対角線で4分割
            3. 左右眼で Temporal/Nasal を反転
        """
        h, w = faz_roi.shape

        # FAZ中心座標
        props = measure.regionprops(faz_roi.astype(int))[0]
        cy, cx = props.centroid

        # ドーナツ型ROI（内径=画像半径/4、外径=画像半径/2）
        Y, X = np.ogrid[:h, :w]
        dist_from_center = np.sqrt((Y - cy) ** 2 + (X - cx) ** 2)
        inner_radius = min(h, w) / 4
        outer_radius = min(h, w) / 2
        ring_mask = (dist_from_center >= inner_radius) & (
            dist_from_center <= outer_radius
        )

        # 角度計算（-180~180度）
        angle = np.arctan2(Y - cy, X - cx) * 180 / np.pi

        # 4セクター作成
        sectors = {}
        sectors["superior"] = ring_mask & (angle > 45) & (angle <= 135)
        sectors["inferior"] = ring_mask & ((angle > -135) & (angle <= -45))

        if side == "right":
            # 右眼: Temporal=右側, Nasal=左側
            sectors["temporal"] = ring_mask & ((angle > -45) & (angle <= 45))
            sectors["nasal"] = ring_mask & ((angle > 135) | (angle <= -135))
        else:
            # 左眼: Temporal=左側, Nasal=右側
            sectors["nasal"] = ring_mask & ((angle > -45) & (angle <= 45))
            sectors["temporal"] = ring_mask & ((angle > 135) | (angle <= -135))

        return sectors

    def split_center_periphery(
        self,
        faz_roi: np.ndarray,
        center_radius_mm: float = 1.0,
        pixel_size_mm: float = 0.00744,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Center/Periphery 分割

        Args:
            faz_roi: FAZ領域マスク
            center_radius_mm: 中心部半径（mm）
            pixel_size_mm: ピクセルサイズ（mm/pixel）

        Returns:
            center_roi: 中心部マスク (H×W bool)
            periphery_roi: 周辺部マスク (H×W bool)
        """
        h, w = faz_roi.shape

        # FAZ中心座標
        props = measure.regionprops(faz_roi.astype(int))[0]
        cy, cx = props.centroid

        # 中心からの距離（mm）
        Y, X = np.ogrid[:h, :w]
        dist_mm = np.sqrt((Y - cy) ** 2 + (X - cx) ** 2) * pixel_size_mm

        # Center: FAZ中心から指定半径以内
        center_roi = dist_mm <= center_radius_mm

        # Periphery: Center外かつ画像の半分以内
        max_radius_mm = (min(h, w) / 2) * pixel_size_mm
        periphery_roi = (dist_mm > center_radius_mm) & (dist_mm <= max_radius_mm)

        return center_roi, periphery_roi

    def get_sector_areas(
        self, sectors: Dict[str, np.ndarray], pixel_size_mm: float = 0.00744
    ) -> Dict[str, float]:
        """
        各セクターの面積を計算

        Args:
            sectors: セクター辞書
            pixel_size_mm: ピクセルサイズ（mm/pixel）

        Returns:
            areas: {'temporal': mm2, 'nasal': mm2, ...}
        """
        areas = {}
        for name, mask in sectors.items():
            area_px = mask.sum()
            area_mm2 = area_px * (pixel_size_mm**2)
            areas[name] = float(area_mm2)

        return areas
