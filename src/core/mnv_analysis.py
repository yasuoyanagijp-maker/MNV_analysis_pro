"""
MNV解析モジュール
空間分布解析、動脈化検出、パターン分類
"""

import logging
import time
from typing import Dict, Tuple

import numpy as np
from scipy import stats as scipy_stats

logger = logging.getLogger(__name__)


class SpatialDistributionAnalyzer:
    """
    空間分布解析クラス
    analyzeSpatialDistribution に対応
    """

    def __init__(self, mm_per_pixel: float, pixel_size_um: float):
        """
        Parameters:
        -----------
        mm_per_pixel : float
            ピクセルあたりのmm
        pixel_size_um : float
            ピクセルサイズ（μm）
        """
        self.mm_per_pixel = mm_per_pixel
        self.pixel_size_um = pixel_size_um
        # 画像サイズクラス: "small" or "large"（MNVPipeline側で設定）
        self.size_class: str = "small"

    def analyze(
        self,
        distance_map: np.ndarray,
        thick_vessel_map: np.ndarray,
        mnv_roi: np.ndarray,
    ) -> Dict[str, any]:
        """
        空間分布の完全解析

        Parameters:
        -----------
        distance_map : np.ndarray
            距離マップ
        thick_vessel_map : np.ndarray
            太い血管マップ（二値）
        mnv_roi : np.ndarray
            MNVのROIマスク

        Returns:
        --------
        results : dict
            空間分布解析結果
        """
        t0 = time.perf_counter()

        # ROIの中心と半径を取得
        center_x, center_y, radius = self._get_roi_center_and_radius(mnv_roi)
        logger.debug(
            f"[Spatial] 1. get_roi_center_and_radius: {time.perf_counter()-t0:.3f}s"
        )
        t1 = time.perf_counter()

        # 中心部と周辺部のROIを作成 (ImageJ互換: 多角形ROIの縮小)
        center_mask, periphery_mask = self._create_region_masks(
            mnv_roi, center_x, center_y, radius
        )
        logger.debug(f"[Spatial] 2. create_region_masks: {time.perf_counter()-t1:.3f}s")
        t2 = time.perf_counter()

        # 血管径の統計
        diameter_stats = self._analyze_diameter_distribution(
            distance_map, center_mask, periphery_mask
        )
        logger.debug(
            f"[Spatial] 3. diameter_distribution: {time.perf_counter()-t2:.3f}s | "
            f"center_mean={diameter_stats['center_mean']:.1f} um, "
            f"periphery_mean={diameter_stats['periphery_mean']:.1f} um, "
            f"ratio={diameter_stats['ratio']:.3f}"
        )
        t3 = time.perf_counter()

        # 太い血管の分布
        thick_vessel_stats = self._analyze_thick_vessel_distribution(
            thick_vessel_map, center_mask, periphery_mask
        )
        logger.debug(
            f"[Spatial] 4. thick_vessel_distribution: {time.perf_counter()-t3:.3f}s | "
            f"center_ratio={thick_vessel_stats['center_ratio']:.1f}%, "
            f"periphery_ratio={thick_vessel_stats['periphery_ratio']:.1f}%"
        )
        t4 = time.perf_counter()

        # Trunk血管の分布解析
        trunk_stats = self._analyze_trunk_distribution(
            thick_vessel_map, center_x, center_y, radius
        )
        logger.debug(
            f"[Spatial] 5. trunk_distribution: {time.perf_counter()-t4:.3f}s | "
            f"eccentricity={trunk_stats['eccentricity']:.3f}, "
            f"angular_cv={trunk_stats['angular_cv']:.3f}, "
            f"radial_uniformity={trunk_stats['radial_uniformity']:.3f}"
        )
        t5 = time.perf_counter()

        # 放射状プロファイル
        radial_profile = self._calculate_radial_profile(
            distance_map, mnv_roi, center_x, center_y, radius
        )
        logger.debug(
            f"[Spatial] 6. radial_profile: {time.perf_counter()-t5:.3f}s | "
            f"gradient={radial_profile['gradient']:.4f}, "
            f"diameters={[f'{d:.1f}' for d in radial_profile['diameters']]}"
        )
        t6 = time.perf_counter()

        # 安定性スコア
        stability_score = self._calculate_stability_score(radial_profile)
        center_area = int(np.sum(center_mask > 0))
        periphery_area = int(np.sum(periphery_mask > 0))
        logger.debug(
            f"[Spatial] 7. stability_score: {time.perf_counter()-t6:.3f}s | "
            f"score={stability_score:.1f}, "
            f"center_mask={center_area}px, periphery_mask={periphery_area}px"
        )
        logger.debug(f"[Spatial] Step 4 subtotal: {time.perf_counter()-t0:.3f}s")

        # FD is computed once on refined_skeleton: overall in Step 3, Center/Periphery in Step 6.
        # ImageJ uses a single skeleton (Cleaned_Skeleton/newskeleton1) for branch and FD.
        # No duplicate FD here from distance_map skeleton.

        results = {
            "center_x": center_x,
            "center_y": center_y,
            "radius": radius,
            "center_mask": center_mask,
            "periphery_mask": periphery_mask,
            "diameter_center_mean": diameter_stats["center_mean"],
            "diameter_periphery_mean": diameter_stats["periphery_mean"],
            "diameter_center_periphery_ratio": diameter_stats["ratio"],
            "diameter_radial_gradient": radial_profile["gradient"],
            "thick_vessel_center_ratio": thick_vessel_stats["center_ratio"],
            "thick_vessel_periphery_ratio": thick_vessel_stats["periphery_ratio"],
            "trunk_eccentricity": trunk_stats["eccentricity"],
            "angular_distribution_cv": trunk_stats["angular_cv"],
            "radial_uniformity": trunk_stats["radial_uniformity"],
            "stability_score": stability_score,
            "radial_profile": radial_profile,
            "size_class": self.size_class,
        }

        return results

    def _get_roi_center_and_radius(
        self, roi_mask: np.ndarray
    ) -> Tuple[int, int, float]:
        """
        ROIの中心座標と半径を取得

        Parameters:
        -----------
        roi_mask : np.ndarray
            ROIマスク

        Returns:
        --------
        center_x : int
        center_y : int
        radius : float
        """
        # ROIの境界ボックス
        y_coords, x_coords = np.where(roi_mask > 0)

        if len(x_coords) == 0:
            h, w = roi_mask.shape
            return w // 2, h // 2, min(w, h) // 2

        x_min, x_max = x_coords.min(), x_coords.max()
        y_min, y_max = y_coords.min(), y_coords.max()

        center_x = int((x_min + x_max) / 2)
        center_y = int((y_min + y_max) / 2)

        # 半径を推定（面積から）
        roi_area = np.sum(roi_mask > 0)
        radius = np.sqrt(roi_area / np.pi)

        return center_x, center_y, radius

    def _create_region_masks(
        self,
        mnv_roi: np.ndarray,
        center_x: int,
        center_y: int,
        radius: float,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        中心部と周辺部のマスクを作成 (ImageJ互換: ROIの縮小 + XOR).
        center は元のROIの形を変えずに内側へ縮小した領域（距離変換による erosion）。

        ImageJ: center = Enlarge(ROI, -shrinkPixels), periphery = XOR(ROI, center)
        shrinkPixels = estimatedRadius - centerRadius = (2/3)*radius

        距離変換を用いて高速化: binary_erosion(disk(r)) は
        distance_transform_edt(roi) >= r と等価。大径の disk では距離変換が
        劇的に高速 (O(n) vs O(n*r^2))。

        Parameters:
        -----------
        mnv_roi : np.ndarray
            MNVのROIマスク (0/255 or bool)
        center_x, center_y : int
            中心座標 (trunk解析用、マスクはROIから算出)
        radius : float
            面積から推定した半径 (sqrt(area/pi))

        Returns:
        --------
        center_mask : np.ndarray
            中心部マスク (縮小多角形)
        periphery_mask : np.ndarray
            周辺部マスク (ドーナツ)
        """
        from scipy.ndimage import distance_transform_edt

        roi_binary = (mnv_roi > 0).astype(np.uint8)
        # ImageJ: radius>=20 -> centerRadius=radius/3; radius<20 -> 40% (line 4218-4224)
        if radius < 20:
            center_radius = radius * 0.4
        else:
            center_radius = radius / 3
        shrink_pixels = max(0, int(radius - center_radius))

        if shrink_pixels <= 0:
            center_mask = roi_binary.copy()
            periphery_mask = np.zeros_like(roi_binary)
        else:
            # Crop to ROI bbox + margin
            y_coords, x_coords = np.where(roi_binary > 0)
            if len(x_coords) == 0:
                center_mask = roi_binary.copy()
                periphery_mask = np.zeros_like(roi_binary)
            else:
                margin = shrink_pixels + 2
                y_min, y_max = int(y_coords.min()), int(y_coords.max())
                x_min, x_max = int(x_coords.min()), int(x_coords.max())
                h, w = roi_binary.shape
                y_lo = max(0, y_min - margin)
                y_hi = min(h, y_max + 1 + margin)
                x_lo = max(0, x_min - margin)
                x_hi = min(w, x_max + 1 + margin)
                roi_crop = roi_binary[y_lo:y_hi, x_lo:x_hi].astype(np.uint8)

                # Distance transform: dist[p] = distance from p to nearest background.
                # erosion(disk(r)) <=> dist >= r (pixel kept if >= r from boundary).
                dist = distance_transform_edt(roi_crop)
                center_crop = (dist >= shrink_pixels).astype(np.uint8)
                periphery_crop = (
                    (roi_crop.astype(bool) & ~center_crop.astype(bool))
                ).astype(np.uint8)

                center_mask = np.zeros_like(roi_binary)
                periphery_mask = np.zeros_like(roi_binary)
                center_mask[y_lo:y_hi, x_lo:x_hi] = center_crop
                periphery_mask[y_lo:y_hi, x_lo:x_hi] = periphery_crop

        return center_mask * 255, periphery_mask * 255

    def _analyze_diameter_distribution(
        self,
        distance_map: np.ndarray,
        center_mask: np.ndarray,
        periphery_mask: np.ndarray,
    ) -> Dict[str, float]:
        """
        径の分布を解析

        Parameters:
        -----------
        distance_map : np.ndarray
            距離マップ
        center_mask : np.ndarray
            中心部マスク
        periphery_mask : np.ndarray
            周辺部マスク

        Returns:
        --------
        stats : dict
            統計量
        """
        # 中心部の平均径
        center_distances = distance_map[center_mask > 0]
        center_distances = center_distances[~np.isnan(center_distances)]
        center_mean = center_distances.mean() if len(center_distances) > 0 else 0

        # 周辺部の平均径
        periphery_distances = distance_map[periphery_mask > 0]
        periphery_distances = periphery_distances[~np.isnan(periphery_distances)]
        periphery_mean = (
            periphery_distances.mean() if len(periphery_distances) > 0 else 0
        )

        # μm単位に変換（距離×2=径）
        center_mean_um = center_mean * 2 * self.pixel_size_um
        periphery_mean_um = periphery_mean * 2 * self.pixel_size_um

        # 比率
        if periphery_mean > 0:
            ratio = center_mean / periphery_mean
        else:
            ratio = 1.0

        return {
            "center_mean": center_mean_um,
            "periphery_mean": periphery_mean_um,
            "ratio": ratio,
        }

    def _analyze_thick_vessel_distribution(
        self,
        thick_vessel_map: np.ndarray,
        center_mask: np.ndarray,
        periphery_mask: np.ndarray,
    ) -> Dict[str, float]:
        """
        太い血管の分布を解析

        Parameters:
        -----------
        thick_vessel_map : np.ndarray
            太い血管マップ
        center_mask : np.ndarray
            中心部マスク
        periphery_mask : np.ndarray
            周辺部マスク

        Returns:
        --------
        stats : dict
            統計量
        """
        # 中心部の割合
        center_total = np.sum(center_mask > 0)
        center_thick = np.sum((thick_vessel_map > 0) & (center_mask > 0))
        center_ratio = (center_thick / center_total * 100) if center_total > 0 else 0

        # 周辺部の割合
        periphery_total = np.sum(periphery_mask > 0)
        periphery_thick = np.sum((thick_vessel_map > 0) & (periphery_mask > 0))
        periphery_ratio = (
            (periphery_thick / periphery_total * 100) if periphery_total > 0 else 0
        )

        return {
            "center_ratio": center_ratio,
            "periphery_ratio": periphery_ratio,
        }

    def _analyze_trunk_distribution(
        self,
        thick_vessel_map: np.ndarray,
        center_x: int,
        center_y: int,
        radius: float,
    ) -> Dict[str, float]:
        """
        Trunk血管の分布を解析

        Parameters:
        -----------
        thick_vessel_map : np.ndarray
            太い血管マップ
        center_x, center_y : int
            中心座標
        radius : float
            半径

        Returns:
        --------
        stats : dict
            Trunk分布統計
        """
        from skimage.morphology import skeletonize

        # Crop to ROI bbox + margin to speed up skeletonize (avoids full-image cost)
        thick_binary = thick_vessel_map > 0
        y_pts, x_pts = np.where(thick_binary)
        if len(x_pts) < 10:
            return {"eccentricity": -1, "angular_cv": -1, "radial_uniformity": -1}
        margin = int(max(radius * 0.5, 20))
        h, w = thick_vessel_map.shape
        y_lo = max(0, int(y_pts.min()) - margin)
        y_hi = min(h, int(y_pts.max()) + 1 + margin)
        x_lo = max(0, int(x_pts.min()) - margin)
        x_hi = min(w, int(x_pts.max()) + 1 + margin)
        crop = thick_binary[y_lo:y_hi, x_lo:x_hi]

        skeleton_crop = skeletonize(crop)
        skeleton_crop = (skeleton_crop * 255).astype(np.uint8)

        # Trunk vascular pixel coordinates (crop-local)
        y_coords_crop, x_coords_crop = np.where(skeleton_crop > 0)
        x_coords = x_coords_crop + x_lo
        y_coords = y_coords_crop + y_lo

        if len(x_coords) < 10:
            return {
                "eccentricity": -1,
                "angular_cv": -1,
                "radial_uniformity": -1,
            }

        # 重心計算
        trunk_center_x = x_coords.mean()
        trunk_center_y = y_coords.mean()

        # Eccentricity（偏心度）
        eccentricity_dist = np.sqrt(
            (trunk_center_x - center_x) ** 2 + (trunk_center_y - center_y) ** 2
        )
        eccentricity = eccentricity_dist / radius
        eccentricity = np.clip(eccentricity, 0, 1)

        # Angular Distribution（角度分布）- vectorized
        sectors = 8
        dx = x_coords.astype(np.float64) - center_x
        dy = y_coords.astype(np.float64) - center_y
        angles = np.arctan2(dy, dx) * 180 / np.pi
        angles[angles < 0] += 360
        sector_idx = (angles / (360.0 / sectors)).astype(np.intp)
        sector_idx = np.clip(sector_idx, 0, sectors - 1)
        sector_counts = np.bincount(sector_idx, minlength=sectors)[:sectors]

        # Angular CV
        angular_cv = self._calculate_angular_cv(sector_counts, sectors)

        # Radial Uniformity
        radial_uniformity = self._calculate_radial_uniformity(sector_counts, sectors)

        return {
            "eccentricity": eccentricity,
            "angular_cv": angular_cv,
            "radial_uniformity": radial_uniformity,
        }

    def _calculate_angular_cv(self, sector_counts: np.ndarray, sectors: int) -> float:
        """
        角度分布のCVを計算

        Parameters:
        -----------
        sector_counts : np.ndarray
            各セクタのカウント
        sectors : int
            セクタ数

        Returns:
        --------
        cv : float
            変動係数
        """
        non_zero_sectors = sector_counts[sector_counts > 0]

        min_sectors = 3 if sectors >= 8 else 2

        if len(non_zero_sectors) < min_sectors:
            return -1

        mean_count = non_zero_sectors.mean()
        std_count = non_zero_sectors.std()

        cv = std_count / mean_count if mean_count > 0 else 0
        cv = min(cv, 2.0)  # 上限

        return cv

    def _calculate_radial_uniformity(
        self, sector_counts: np.ndarray, sectors: int
    ) -> float:
        """
        放射状均一性を計算

        Parameters:
        -----------
        sector_counts : np.ndarray
            各セクタのカウント
        sectors : int
            セクタ数

        Returns:
        --------
        uniformity : float
            均一性指数（0-1）
        """
        occupied_sectors = np.sum(sector_counts > 0)

        if occupied_sectors < 3:
            return 0

        # 占有率
        occupation_ratio = occupied_sectors / sectors

        # 分布の均一性
        non_zero = sector_counts[sector_counts > 0]
        if len(non_zero) >= 3:
            mean_count = non_zero.mean()
            std_count = non_zero.std()
            cv = std_count / mean_count if mean_count > 0 else 1

            if cv < 0.5:
                distribution_uniformity = 1.0
            elif cv < 1.0:
                distribution_uniformity = 0.7
            else:
                distribution_uniformity = 0.4
        else:
            distribution_uniformity = 0.5

        # 総合均一性
        uniformity = occupation_ratio * distribution_uniformity

        return uniformity

    def _calculate_radial_profile(
        self,
        distance_map: np.ndarray,
        roi_mask: np.ndarray,
        center_x: int,
        center_y: int,
        radius: float,
    ) -> Dict[str, any]:
        """
        放射状プロファイルを計算

        Parameters:
        -----------
        distance_map : np.ndarray
            距離マップ
        roi_mask : np.ndarray
            ROIマスク
        center_x, center_y : int
            中心座標
        radius : float
            半径

        Returns:
        --------
        profile : dict
            'diameters': 各ビンの平均径（μm）
            'gradient': 線形勾配
        """
        num_bins = 10
        bin_width = radius / num_bins

        # Work with ROI pixels only to avoid full-size arrays (faster for sparse ROI)
        y_coords, x_coords = np.where(roi_mask > 0)
        if len(x_coords) == 0:
            diameters = [0.0] * num_bins
        else:
            dist = np.sqrt(
                (x_coords.astype(np.float64) - center_x) ** 2
                + (y_coords.astype(np.float64) - center_y) ** 2
            )
            values = distance_map[y_coords, x_coords].astype(np.float64)
            valid = ~np.isnan(values)
            diameters = []
            for bin_idx in range(num_bins):
                inner_r = bin_idx * bin_width
                outer_r = (bin_idx + 1) * bin_width
                in_ring = valid & (dist >= inner_r) & (dist < outer_r)
                ring_vals = values[in_ring]
                if len(ring_vals) > 0:
                    mean_diameter_um = ring_vals.mean() * 2 * self.pixel_size_um
                else:
                    mean_diameter_um = 0.0
                diameters.append(mean_diameter_um)

        # 線形勾配を計算
        x_vals = np.arange(num_bins)
        y_vals = np.array(diameters)

        if np.sum(y_vals) > 0:
            slope, intercept, r_value, p_value, std_err = scipy_stats.linregress(
                x_vals, y_vals
            )
            gradient = slope
        else:
            gradient = 0

        return {"diameters": diameters, "gradient": gradient}

    def _calculate_stability_score(self, radial_profile: Dict) -> float:
        """
        安定性スコアを計算
        calculateMetrics に対応

        Parameters:
        -----------
        radial_profile : dict
            放射状プロファイル

        Returns:
        --------
        score : float
            安定性スコア（0-100）
        """
        from core import pattern_metrics

        diameters = np.array(radial_profile["diameters"], dtype=float)
        if diameters.size == 0 or np.sum(diameters) == 0.0:
            return 0.0

        score = pattern_metrics.calculate_stability_metrics(
            diameters, size_class=self.size_class
        )
        return float(score)


class TrunkVesselClassifier:
    """
    Trunk血管パターン分類
    classifyMNVbyLoopsDetailedのTrunk分類部分に対応
    """

    @staticmethod
    def classify_trunk_pattern(
        eccentricity: float,
        angular_cv: float,
        radial_uniformity: float,
        thick_vessel_center_ratio: float,
        diameter_ratio: float,
    ) -> Dict[str, any]:
        """
        Trunk血管パターンを分類

        Parameters:
        -----------
        eccentricity : float
            偏心度（0-1）
        angular_cv : float
            角度分布CV
        radial_uniformity : float
            放射状均一性（0-1）
        thick_vessel_center_ratio : float
            中心部太血管割合（%）
        diameter_ratio : float
            中心/周辺径比

        Returns:
        --------
        classification : dict
            'pattern': パターン名（MEDUSA/INTERMEDIATE/SEAFAN）
            'score': スコア（0-100）
            'confidence': 信頼度
        """
        # TIER 1: Eccentricity（40%）
        if eccentricity < 0.20:
            tier1_score = 0  # Strong central
        elif eccentricity < 0.35:
            tier1_score = 15
        elif eccentricity < 0.50:
            tier1_score = 25
        else:
            tier1_score = 40  # Strong eccentric

        tier1_max = 40

        # TIER 2: Radial Uniformity（30%）
        if angular_cv < 0:
            # Angular CVが無効な場合
            if radial_uniformity >= 0:
                if radial_uniformity > 0.50:
                    tier2_score = 5
                else:
                    tier2_score = 25
            else:
                tier2_score = 15
        else:
            if radial_uniformity > 0.75:
                tier2_score = 0  # Omnidirectional
            elif radial_uniformity > 0.60:
                tier2_score = 10
            elif radial_uniformity > 0.40:
                tier2_score = 20
            else:
                tier2_score = 30  # Unidirectional

        tier2_max = 30

        # TIER 3: Central Density（20%）
        if thick_vessel_center_ratio > 15:
            tier3_score = 0  # Dense central
        elif thick_vessel_center_ratio > 10:
            tier3_score = 7
        elif thick_vessel_center_ratio > 5:
            tier3_score = 13
        else:
            tier3_score = 20  # Sparse central

        tier3_max = 20

        # TIER 4: Diameter Ratio（10%）
        if diameter_ratio > 1.4:
            tier4_score = 0  # Central dominance
        elif diameter_ratio > 1.2:
            tier4_score = 3
        elif diameter_ratio > 1.0:
            tier4_score = 7
        else:
            tier4_score = 10  # Peripheral dominance

        tier4_max = 10

        # 総合スコア
        total_score = tier1_score + tier2_score + tier3_score + tier4_score
        max_score = tier1_max + tier2_max + tier3_max + tier4_max

        # パターン判定
        if total_score < 30:
            pattern = "MEDUSA"
        elif total_score < 60:
            pattern = "INTERMEDIATE"
        else:
            pattern = "SEAFAN"

        # 信頼度
        # 実装簡略化のため固定値
        confidence = "MODERATE"

        return {
            "pattern": pattern,
            "score": total_score,
            "max_score": max_score,
            "confidence": confidence,
            "tier1_score": tier1_score,
            "tier2_score": tier2_score,
            "tier3_score": tier3_score,
            "tier4_score": tier4_score,
        }
