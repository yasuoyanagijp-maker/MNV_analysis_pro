"""
VD (Vessel Density) Pipeline

Complete pipeline for vessel density analysis from paired OCT-A images
"""

from typing import Dict, Tuple, Optional

import cv2
import numpy as np

from .faz_detector import FAZDetector
from .phansalkar_filter import PhansalkarBinarizer
from .sector_splitter import SectorSplitter

# Enhanced FAZ detection modules
from ..enhanced_faz_detection import ImprovedFAZDetector
from ..auto_faz_optimizer import AutoFAZOptimizer


class VDPipeline:
    """
    血管密度解析パイプライン（高速・スクリーニング向け）

    特徴:
    - Phansalkar適応二値化（単一フィルタ）
    - FAZ自動検出
    - 4セクター（T/N/S/I）+ Center/Periphery
    - ペア画像処理（Superficial + Deep）
    - 処理時間: ~5秒/画像ペア
    - 出力: 24メトリクス

    臨床用途:
    - 糖尿病網膜症スクリーニング
    - 経時的なVD変化追跡
    - 大規模コホート研究
    """

    def __init__(self, pixel_size_mm: float = 0.00744):
        """
        Args:
            pixel_size_mm: ピクセルサイズ（mm/pixel）標準値: 0.744 μm/pixel = 0.00744 mm/pixel
            use_enhanced_faz: Enhanced FAZ検出を使用するか（True推奨）
        """
        self.pixel_size_mm = pixel_size_mm

        # VD専用モジュール
        self.filter = PhansalkarBinarizer(window_radius=15)
        self.faz_detector = FAZDetector(min_area_mm2=0.1, min_circularity=0.6)
        self.sector_splitter = SectorSplitter(n_sectors=4)

        # 処理パラメータ（VD最適化）
        self.params = {
            "phansalkar_window_radius": 15,
            "faz_min_circularity": 0.6,
            "faz_min_area_mm2": 0.1,
            "sector_center_radius_mm": 1.0,
            "eye_side": "right",  # 'right' or 'left'
        }

    def process(
        self,
        superficial_image: np.ndarray,
        deep_image: np.ndarray,
        eye_side: str = None,
        center_radius_mm: float = None,
    ) -> Dict:
        """
        VD解析を実行（6ステップ）。

        可変パラメータ（例: eye_side, center_radius_mm）は呼び出し側から上書き可能です。

        Args:
            superficial_image: 表層画像 (H×W numpy array, uint8)
            deep_image: 深層画像 (H×W numpy array, uint8)
            eye_side: 'right' または 'left'（Noneの場合はインスタンス設定を使用）
            center_radius_mm: center region radius in mm (Noneの場合はインスタンス設定を使用)

        Returns:
            dict: 24メトリクス + メタデータ

        Raises:
            ValueError: ペア画像サイズ不一致
            RuntimeError: FAZ検出失敗
        """
        # Step 1: ペア画像検証
        if superficial_image.shape != deep_image.shape:
            raise ValueError(
                f"画像ペアのサイズが一致しません: "
                f"Superficial {superficial_image.shape} vs Deep {deep_image.shape}"
            )

        # Step 2: Phansalkar二値化（両層）
        binary_sup = self.filter.binarize(superficial_image)
        binary_deep = self.filter.binarize(deep_image)

        # Step 3: FAZ検出（表層画像から）
        faz_roi, faz_metrics = self.faz_detector.detect(binary_sup, self.pixel_size_mm)
        if faz_roi is None:
            raise RuntimeError("FAZ検出に失敗しました。画像品質を確認してください。")

        # Step 4: 4セクター分割
        side_param = (
            eye_side if (eye_side is not None) else self.params.get("eye_side", "right")
        )
        center_radius_param = (
            center_radius_mm
            if (center_radius_mm is not None)
            else self.params.get("sector_center_radius_mm", 1.0)
        )

        sectors = self.sector_splitter.split_into_sectors(
            faz_roi, pixel_size_mm=self.pixel_size_mm, side=side_param
        )
        center_roi, periphery_roi = self.sector_splitter.split_center_periphery(
            faz_roi,
            center_radius_mm=center_radius_param,
            pixel_size_mm=self.pixel_size_mm,
        )

        # Step 5: セクター別VD計測
        vd_metrics = {}

        # Superficial layer - 4 sectors (percent)
        for sector_name in ["temporal", "nasal", "superior", "inferior"]:
            vd = self._calculate_vd(binary_sup, sectors[sector_name])
            vd_metrics[f"vd_superficial_{sector_name}_percent"] = vd

        # Deep layer - 4 sectors (percent)
        for sector_name in ["temporal", "nasal", "superior", "inferior"]:
            vd = self._calculate_vd(binary_deep, sectors[sector_name])
            vd_metrics[f"vd_deep_{sector_name}_percent"] = vd

        # Center/Periphery - Superficial (percent)
        vd_metrics["vd_superficial_center_percent"] = self._calculate_vd(
            binary_sup, center_roi
        )
        vd_metrics["vd_superficial_periphery_percent"] = self._calculate_vd(
            binary_sup, periphery_roi
        )

        # Center/Periphery - Deep (percent)
        vd_metrics["vd_deep_center_percent"] = self._calculate_vd(
            binary_deep, center_roi
        )
        vd_metrics["vd_deep_periphery_percent"] = self._calculate_vd(
            binary_deep, periphery_roi
        )

        # Overall VD (percent)
        h, w = binary_sup.shape
        full_roi = np.ones((h, w), dtype=bool)
        vd_metrics["vd_superficial_overall_percent"] = self._calculate_vd(
            binary_sup, full_roi
        )
        vd_metrics["vd_deep_overall_percent"] = self._calculate_vd(
            binary_deep, full_roi
        )

        # Vessel areas (mm2)
        vd_metrics["vessel_area_superficial_mm2"] = binary_sup.sum() * (
            self.pixel_size_mm**2
        )
        vd_metrics["vessel_area_deep_mm2"] = binary_deep.sum() * (self.pixel_size_mm**2)

        # Additional metrics
        avascular_area_mm2 = faz_metrics["faz_area_mm2"]
        vd_metrics["avascular_area_mm2"] = avascular_area_mm2

        # Vessel length density (簡易計算: スケルトン長さの代わりに血管ピクセル数で近似)
        vessel_pixels = binary_sup.sum() + binary_deep.sum()
        total_area_mm2 = (h * w) * (self.pixel_size_mm**2)
        vd_metrics["vessel_length_density_mm_mm2"] = vessel_pixels / total_area_mm2

        # Layer thickness difference (ダミー値、実装には追加データが必要)
        vd_metrics["layer_thickness_difference_um"] = 0.0

        # Quality score
        vd_metrics["quality_score"] = self._calculate_quality_score(
            superficial_image, deep_image
        )

        # Step 6: 結果統合
        result = {
            **faz_metrics,
            **vd_metrics,
            "pixel_size_mm": self.pixel_size_mm,
            "analysis_type": "VD",
            "image_shape": superficial_image.shape,
        }

        return result

    def _calculate_vd(self, binary_image: np.ndarray, roi_mask: np.ndarray) -> float:
        """
        血管密度を計算（%）

        Args:
            binary_image: 二値血管画像
            roi_mask: ROIマスク

        Returns:
            vd: 血管密度（%）
        """
        vessel_pixels = (binary_image & roi_mask).sum()
        roi_pixels = roi_mask.sum()

        if roi_pixels == 0:
            return 0.0

        vd = (vessel_pixels / roi_pixels) * 100
        return float(vd)

    def _calculate_quality_score(
        self, superficial: np.ndarray, deep: np.ndarray
    ) -> float:
        """
        画像品質スコアを計算（0-100）

        簡易実装: SNRとコントラストから算出
        """
        # Superficial layer quality
        sup_mean = superficial.mean()
        sup_std = superficial.std()
        sup_snr = sup_mean / (sup_std + 1e-10)

        # Deep layer quality
        deep_mean = deep.mean()
        deep_std = deep.std()
        deep_snr = deep_mean / (deep_std + 1e-10)

        # 正規化（SNR 0-10 → score 0-100）
        avg_snr = (sup_snr + deep_snr) / 2
        quality_score = min(avg_snr * 10, 100)

        return float(quality_score)

    def _detect_faz_enhanced(
        self, image: np.ndarray, binary_mask: np.ndarray
    ) -> tuple:
        """
        Enhanced FAZ検出（原画像ベース + フォールバック）

        Args:
            image: 原画像（グレースケール）
            binary_mask: 二値化された血管マスク

        Returns:
            faz_roi: FAZ領域マスク (bool) or None
            faz_metrics: FAZメトリクス辞書
        """
        # まず原画像ベースのFAZ検出を試みる（3mm画像に最適化）
        faz_mask, metrics = self._detect_faz_from_intensity(image)
        
        if faz_mask is not None and metrics.get("faz_area_mm2", 0) > 0.05:
            return faz_mask, metrics
        
        # フォールバック: ImprovedFAZDetectorを使用
        opt_params = self.auto_faz_optimizer.get_optimal_parameters(
            image.shape, self.pixel_size_mm
        )

        self.improved_faz_detector = ImprovedFAZDetector(
            min_area_mm2=opt_params.min_area_mm2 * 0.5,  # 緩和
            min_circularity=opt_params.min_circularity * 0.5,  # 緩和
        )

        faz_mask, metrics = self.improved_faz_detector.detect(
            image.astype(np.uint8),
            binary_mask,
            mm_per_pixel=self.pixel_size_mm,
        )

        unified_metrics = {
            "faz_area_mm2": metrics.get("faz_area_mm2", 0.0),
            "faz_perimeter_mm": metrics.get("faz_perimeter_mm", 0.0),
            "faz_circularity": metrics.get("faz_circularity", 0.0),
            "faz_equivalent_diameter_mm": metrics.get("faz_equivalent_diameter_mm", 0.0),
            "faz_center_y_mm": metrics.get("faz_centroid_y_px", 0.0) * self.pixel_size_mm,
            "faz_center_x_mm": metrics.get("faz_centroid_x_px", 0.0) * self.pixel_size_mm,
        }

        if faz_mask is not None and faz_mask.dtype != bool:
            faz_mask = faz_mask.astype(bool)

        return faz_mask, unified_metrics

    def _detect_faz_from_intensity(
        self, image: np.ndarray
    ) -> Tuple[Optional[np.ndarray], Dict]:
        """
        原画像の輝度分布からFAZを検出（3mm画像に最適化）
        
        OCT-Aでは血管=高輝度、FAZ=低輝度という特性を利用
        
        Args:
            image: 原画像（グレースケール）
            
        Returns:
            faz_mask: FAZ領域マスク (bool) or None
            metrics: FAZメトリクス辞書
        """
        h, w = image.shape
        center_y, center_x = h // 2, w // 2
        
        # 画像がuint8でない場合は変換
        if image.dtype != np.uint8:
            image_u8 = cv2.normalize(image, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        else:
            image_u8 = image
        
        # 1. ガウシアンブラーで血管ノイズを軽減
        blurred = cv2.GaussianBlur(image_u8, (0, 0), sigmaX=3)
        
        # 2. 画像中央付近にフォーカス（中央から半径0.75mm以内）
        search_radius_mm = 0.75
        search_radius_px = int(search_radius_mm / self.pixel_size_mm)
        
        Y, X = np.ogrid[:h, :w]
        dist_from_center = np.sqrt((Y - center_y)**2 + (X - center_x)**2)
        center_mask = dist_from_center <= search_radius_px
        
        # 3. 中央領域の輝度統計
        center_values = blurred[center_mask]
        if len(center_values) == 0:
            return None, self._empty_faz_metrics()
            
        mean_intensity = center_values.mean()
        std_intensity = center_values.std()
        
        # 4. FAZ検出（低輝度領域）
        threshold = mean_intensity - 0.5 * std_intensity
        faz_candidate = (blurred < threshold) & center_mask
        
        # 5. モルフォロジー処理
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        faz_cleaned = cv2.morphologyEx(
            faz_candidate.astype(np.uint8) * 255, cv2.MORPH_CLOSE, kernel
        )
        faz_cleaned = cv2.morphologyEx(faz_cleaned, cv2.MORPH_OPEN, kernel)
        
        # 6. 連結成分解析
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
            faz_cleaned, connectivity=8
        )
        
        if num_labels <= 1:
            return None, self._empty_faz_metrics()
        
        # 最大の連結成分を選択
        areas = stats[1:, cv2.CC_STAT_AREA]
        largest_idx = np.argmax(areas) + 1
        largest_area_px = stats[largest_idx, cv2.CC_STAT_AREA]
        largest_area_mm2 = largest_area_px * (self.pixel_size_mm ** 2)
        
        # FAZサイズの妥当性チェック（0.05 - 1.0 mm²）
        if largest_area_mm2 < 0.05 or largest_area_mm2 > 1.0:
            return None, self._empty_faz_metrics()
        
        # FAZマスク作成
        faz_mask = (labels == largest_idx)
        
        # 円形度計算
        contours, _ = cv2.findContours(
            faz_mask.astype(np.uint8) * 255, 
            cv2.RETR_EXTERNAL, 
            cv2.CHAIN_APPROX_SIMPLE
        )
        
        circularity = 0.0
        perimeter_px = 0.0
        if contours:
            cnt = contours[0]
            area = cv2.contourArea(cnt)
            perimeter_px = cv2.arcLength(cnt, True)
            if perimeter_px > 0:
                circularity = 4 * np.pi * area / (perimeter_px ** 2)
        
        # メトリクス
        metrics = {
            "faz_area_mm2": float(largest_area_mm2),
            "faz_perimeter_mm": float(perimeter_px * self.pixel_size_mm),
            "faz_circularity": float(circularity),
            "faz_equivalent_diameter_mm": float(2 * np.sqrt(largest_area_mm2 / np.pi)),
            "faz_center_y_mm": float(centroids[largest_idx][1] * self.pixel_size_mm),
            "faz_center_x_mm": float(centroids[largest_idx][0] * self.pixel_size_mm),
            "detection_method": "intensity_based",
        }
        
        return faz_mask, metrics
    
    def _empty_faz_metrics(self) -> Dict:
        """空のFAZメトリクスを返す"""
        return {
            "faz_area_mm2": 0.0,
            "faz_perimeter_mm": 0.0,
            "faz_circularity": 0.0,
            "faz_equivalent_diameter_mm": 0.0,
            "faz_center_y_mm": 0.0,
            "faz_center_x_mm": 0.0,
        }
