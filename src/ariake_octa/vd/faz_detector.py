"""
FAZ (Foveal Avascular Zone) detection

ImageJ equivalent: processVDFile() FAZ detection
Enhanced FAZ Segmentation with multiple methods
"""

from typing import Dict, Optional, Tuple

import cv2
import numpy as np
from skimage import filters, measure, morphology


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
        remove_small_particles: bool = True,
        max_particle_size: int = 1000,
    ):
        """
        Args:
            min_area_mm2: 最小FAZ面積（mm²）
            min_circularity: 最小円形度（0-1）
            search_radius: シード点探索半径（ピクセル）
            remove_small_particles: 小粒子を除去するか（ImageJ互換）
            max_particle_size: 除去する粒子の最大サイズ（ピクセル）
        """
        self.min_area_mm2 = min_area_mm2
        self.min_circularity = min_circularity
        self.search_radius = search_radius
        self.remove_small_particles = remove_small_particles
        self.max_particle_size = max_particle_size

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
            1. 血管画像を軽くclosingして断片化を軽減
            2. 画像中央付近の非血管領域を探索
            3. Connected Components解析で連結領域を検出
            4. 中央に最も近い大きな非血管領域をFAZとする
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

        # 形態学的処理（小さな穴を埋める）
        # Note: scikit-image API varies by version
        # 0.19-0.20: area_threshold
        # 0.21+: max_size
        try:
            faz_roi = morphology.remove_small_holes(faz_roi, max_size=50)
        except TypeError:
            # Fallback for older scikit-image versions
            faz_roi = morphology.remove_small_holes(faz_roi, area_threshold=50)
        
        faz_roi = morphology.closing(faz_roi, morphology.disk(2))

        # ImageJ互換: FAZ領域内の小粒子を除去
        # ImageJ: "Analyze Particles...", "size=0-1000 circularity=0.0-1.0 show=[Nothing] exclude clear add"
        if self.remove_small_particles:
            faz_roi = self._remove_small_particles_from_faz(faz_roi)

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

    def _remove_small_particles_from_faz(self, faz_roi: np.ndarray) -> np.ndarray:
        """
        FAZ領域内の小粒子を除去（ImageJ互換）

        ImageJの処理:
        - run("Analyze Particles...", "size=0-1000 circularity=0.0-1.0 show=[Nothing] exclude clear add");
        - 検出された小粒子を黒で塗りつぶす

        Args:
            faz_roi: FAZ領域マスク (H×W bool)

        Returns:
            cleaned_roi: 小粒子除去後のFAZ領域マスク (H×W bool)
        """
        # FAZ領域内の白ピクセル（血管の断片など）を検出
        # FAZ領域内で白い部分（False = 血管）を探す
        inside_faz = faz_roi.astype(np.uint8)

        # FAZ領域の反転：FAZ内部の穴（白い部分）を検出対象にする
        # FAZ領域 = True（黒背景では白）
        # FAZ内の穴（血管断片） = False（黒背景では黒）
        # → 反転して穴を白にする
        inverted_inside = ~faz_roi

        # Connected components解析でFAZ内部の穴を検出
        labeled_holes = measure.label(inverted_inside, connectivity=2, background=False)
        regions = measure.regionprops(labeled_holes)

        # 小さい穴（0-1000ピクセル）を塗りつぶす（FAZに統合）
        cleaned_roi = faz_roi.copy()
        for region in regions:
            if 0 < region.area <= self.max_particle_size:
                # この領域をFAZに含める（Trueにする）
                coords = region.coords
                for coord in coords:
                    cleaned_roi[coord[0], coord[1]] = True

        return cleaned_roi

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


class EnhancedFAZSegmentation:
    """Enhanced FAZ segmentation with multiple detection methods"""

    def __init__(
        self,
        method="morphological",
        min_area_mm2=0.1,
        max_area_mm2=1.5,
        min_circularity=0.5,
        pixel_size_mm=0.00744,
        remove_small_particles=True,
        max_particle_size=1000,
    ):
        self.method = method
        self.min_area_mm2 = min_area_mm2
        self.max_area_mm2 = max_area_mm2
        self.min_circularity = min_circularity
        self.pixel_size_mm = pixel_size_mm
        self.remove_small_particles = remove_small_particles
        self.max_particle_size = max_particle_size

    def segment(self, vessel_image, binary_mask=None):
        """Segment FAZ - uses morphological method"""
        faz_mask = self._morphological_method(vessel_image, binary_mask)

        if faz_mask is None:
            return None, self._empty_metrics()

        is_valid, metrics = self._validate_and_measure(faz_mask)
        return (faz_mask, metrics) if is_valid else (None, self._empty_metrics())

    def _morphological_method(self, vessel_image, binary_mask=None):
        """Morphological FAZ detection"""
        if binary_mask is None:
            threshold = filters.threshold_otsu(vessel_image)
            binary_mask = vessel_image > threshold

        inverted = ~binary_mask
        h, w = inverted.shape
        center_y, center_x = h // 2, w // 2

        # Find seed point near center
        seed_found = False
        for r in range(1, min(h, w) // 4):
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
            return None

        labeled = measure.label(inverted, connectivity=2)
        seed_label = labeled[seed_y, seed_x]

        if seed_label == 0:
            return None

        faz_mask = labeled == seed_label
        faz_mask = morphology.remove_small_holes(faz_mask, area_threshold=50)
        faz_mask = morphology.closing(faz_mask, morphology.disk(2))

        # ImageJ互換: FAZ領域内の小粒子を除去
        if self.remove_small_particles:
            faz_mask = self._remove_small_particles_from_faz(faz_mask)

        return faz_mask

    def _remove_small_particles_from_faz(self, faz_roi: np.ndarray) -> np.ndarray:
        """
        FAZ領域内の小粒子を除去（ImageJ互換）

        ImageJの処理:
        - run("Analyze Particles...", "size=0-1000 circularity=0.0-1.0 show=[Nothing] exclude clear add");
        - 検出された小粒子を黒で塗りつぶす

        Args:
            faz_roi: FAZ領域マスク (H×W bool)

        Returns:
            cleaned_roi: 小粒子除去後のFAZ領域マスク (H×W bool)
        """
        # FAZ領域の反転：FAZ内部の穴（白い部分 = 血管断片）を検出
        inverted_inside = ~faz_roi

        # Connected components解析でFAZ内部の穴を検出
        labeled_holes = measure.label(inverted_inside, connectivity=2, background=False)
        regions = measure.regionprops(labeled_holes)

        # 小さい穴（0-1000ピクセル）を塗りつぶす（FAZに統合）
        cleaned_roi = faz_roi.copy()
        for region in regions:
            if 0 < region.area <= self.max_particle_size:
                # この領域をFAZに含める（Trueにする）
                coords = region.coords
                for coord in coords:
                    cleaned_roi[coord[0], coord[1]] = True

        return cleaned_roi

    def _validate_and_measure(self, faz_mask):
        """Validate and measure FAZ"""
        labeled_mask = measure.label(faz_mask.astype(int), connectivity=2)
        regions = measure.regionprops(labeled_mask)

        if not regions:
            return False, self._empty_metrics()

        props = regions[0]
        area_px = props.area
        perimeter_px = props.perimeter
        area_mm2 = area_px * (self.pixel_size_mm**2)
        perimeter_mm = perimeter_px * self.pixel_size_mm
        circularity = 4 * np.pi * area_px / (perimeter_px**2) if perimeter_px > 0 else 0

        if area_mm2 < self.min_area_mm2 or area_mm2 > self.max_area_mm2:
            return False, self._empty_metrics()
        if circularity < self.min_circularity:
            return False, self._empty_metrics()

        metrics = {
            "faz_area_mm2": float(area_mm2),
            "faz_perimeter_mm": float(perimeter_mm),
            "faz_circularity": float(circularity),
            "faz_equivalent_diameter_mm": float(np.sqrt(4 * area_mm2 / np.pi)),
            "faz_center_y_mm": float(props.centroid[0] * self.pixel_size_mm),
            "faz_center_x_mm": float(props.centroid[1] * self.pixel_size_mm),
            "segmentation_method": self.method,
        }

        return True, metrics

    def _empty_metrics(self):
        return {
            "faz_area_mm2": 0.0,
            "faz_perimeter_mm": 0.0,
            "faz_circularity": 0.0,
            "faz_equivalent_diameter_mm": 0.0,
            "faz_center_y_mm": 0.0,
            "faz_center_x_mm": 0.0,
            "segmentation_method": "none",
        }


class FAZVisualization:
    """FAZ visualization utilities"""

    @staticmethod
    def draw_faz_contour(image, faz_mask, color=(0, 255, 0), thickness=2):
        """Draw FAZ contour on image"""
        if image.ndim == 2:
            result = np.stack([image] * 3, axis=-1)
        else:
            result = image.copy()

        if result.max() <= 1.0:
            result = (result * 255).astype(np.uint8)

        contours = measure.find_contours(faz_mask.astype(float), 0.5)

        for contour in contours:
            contour = contour.astype(np.int32)
            for i in range(len(contour) - 1):
                pt1 = (contour[i][1], contour[i][0])
                pt2 = (contour[i + 1][1], contour[i + 1][0])
                cv2.line(result, pt1, pt2, color, thickness)

        return result
