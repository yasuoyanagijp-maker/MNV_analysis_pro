"""
Regional Analyzer

MNV病変のCenter/Periphery領域別解析を行うモジュール。
病変中心から0.5mm境界で領域を分割し、各領域のスケルトンメトリクスを計算。

Author: ARIAKE OCTA Analysis Team
Date: 2026-01-22
"""

import time
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from scipy import ndimage


class RegionalAnalyzer:
    """
    領域別解析器

    MNV病変をCenter/Periphery領域に分割し、
    各領域で独立にスケルトン解析を実行。
    """

    def __init__(
        self,
        center_radius_mm: float = 0.5,
        pixel_size_mm: float = 0.003,
        enable_advanced_metrics: bool = True,
    ):
        """
        Parameters
        ----------
        center_radius_mm : float
            Center領域の半径 (mm)
        pixel_size_mm : float
            1ピクセルのサイズ (mm)
        enable_advanced_metrics : bool
            If True, compute ImageJ-macro-equivalent advanced metrics when distance_map is provided
        """
        self.center_radius_mm = center_radius_mm
        self.pixel_size_mm = pixel_size_mm
        self.center_radius_pixels = int(center_radius_mm / pixel_size_mm)
        self.enable_advanced_metrics = bool(enable_advanced_metrics)
        """
        Parameters
        ----------
        center_radius_mm : float
            Center領域の半径 (mm)
        pixel_size_mm : float
            1ピクセルのサイズ (mm)
        """
        self.center_radius_mm = center_radius_mm
        self.pixel_size_mm = pixel_size_mm
        self.center_radius_pixels = int(center_radius_mm / pixel_size_mm)

    def analyze(
        self,
        binary_image: np.ndarray,
        lesion_center: tuple,
        skeleton_analyzer,
        distance_map: Optional[np.ndarray] = None,
        thick_map: Optional[np.ndarray] = None,
        branch_data: Optional[Dict] = None,
    ) -> Dict:
        """
        領域別解析を実行 (basic + optional advanced metrics)

        If enable_advanced_metrics is True and a distance_map is provided,
        additional ImageJ-macro-equivalent metrics will be computed and merged.
        """
        basic_results = self._analyze_basic(
            binary_image, lesion_center, skeleton_analyzer
        )

        # Advanced analysis
        if self.enable_advanced_metrics and distance_map is not None:
            advanced = self._analyze_advanced(
                binary_image=binary_image,
                lesion_center=lesion_center,
                distance_map=distance_map,
                thick_map=thick_map,
                branch_data=branch_data,
                skeleton_analyzer=skeleton_analyzer,
            )
            return {**basic_results, **advanced}

        return basic_results

    def _analyze_basic(
        self, binary_image: np.ndarray, lesion_center: tuple, skeleton_analyzer
    ) -> Dict:
        """
        Perform the existing basic analysis (center circle split & skeleton metrics).
        """
        center_y, center_x = lesion_center

        # 領域マスクを作成 (fixed center circle for basic)
        center_mask = self._create_circular_mask(
            binary_image.shape, center_y, center_x, self.center_radius_pixels
        )

        periphery_mask = ~center_mask

        center_results = skeleton_analyzer.analyze(binary_image, roi_mask=center_mask)

        periphery_results = skeleton_analyzer.analyze(
            binary_image, roi_mask=periphery_mask
        )

        binary = (binary_image > 127).astype(np.uint8)
        center_area_pixels = np.sum(binary * center_mask)
        periphery_area_pixels = np.sum(binary * periphery_mask)

        center_area_mm2 = center_area_pixels * (self.pixel_size_mm**2)
        periphery_area_mm2 = periphery_area_pixels * (self.pixel_size_mm**2)

        center_density = (
            center_results["total_length_mm"] / center_area_mm2
            if center_area_mm2 > 0
            else 0.0
        )

        periphery_density = (
            periphery_results["total_length_mm"] / periphery_area_mm2
            if periphery_area_mm2 > 0
            else 0.0
        )

        return {
            "center_area_mm2": center_area_mm2,
            "center_vessel_length_mm": center_results["total_length_mm"],
            "center_vessel_density": center_density,
            "center_num_branches": center_results["num_branches"],
            "center_num_junctions": center_results["num_junctions"],
            "center_num_endpoints": center_results["num_endpoints"],
            "center_num_loops": center_results["num_loops"],
            "center_avg_branch_length_mm": center_results["average_branch_length_mm"],
            "center_tortuosity_mean": center_results["tortuosity_mean"],
            "center_tortuosity_std": center_results["tortuosity_std"],
            "center_fractal_dimension": center_results["fractal_dimension"],
            "center_complexity_score": self._compute_complexity(center_results),
            "periphery_area_mm2": periphery_area_mm2,
            "periphery_vessel_length_mm": periphery_results["total_length_mm"],
            "periphery_vessel_density": periphery_density,
            "periphery_num_branches": periphery_results["num_branches"],
            "periphery_num_junctions": periphery_results["num_junctions"],
            "periphery_num_endpoints": periphery_results["num_endpoints"],
            "periphery_num_loops": periphery_results["num_loops"],
            "periphery_avg_branch_length_mm": periphery_results[
                "average_branch_length_mm"
            ],
            "periphery_tortuosity_mean": periphery_results["tortuosity_mean"],
            "periphery_tortuosity_std": periphery_results["tortuosity_std"],
            "periphery_fractal_dimension": periphery_results["fractal_dimension"],
            "periphery_complexity_score": self._compute_complexity(periphery_results),
            "center_mask": center_mask,
            "periphery_mask": periphery_mask,
            "center_skeleton": center_results["skeleton"],
            "periphery_skeleton": periphery_results["skeleton"],
        }

    def _create_circular_mask(
        self, shape: tuple, center_y: float, center_x: float, radius: float
    ) -> np.ndarray:
        """
        円形マスクを作成

        Parameters
        ----------
        shape : tuple
            画像サイズ (height, width)
        center_y, center_x : float
            中心座標
        radius : float
            半径（ピクセル）

        Returns
        -------
        np.ndarray
            円形マスク (bool)
        """
        y_indices, x_indices = np.ogrid[: shape[0], : shape[1]]

        distances = np.sqrt((y_indices - center_y) ** 2 + (x_indices - center_x) ** 2)

        mask = distances <= radius

        return mask

    def compute_roi_geometry(self, roi_coords: np.ndarray, image_shape: tuple) -> Dict:
        """
        Compute ROI geometry from polygon coordinates.

        Parameters
        ----------
        roi_coords : np.ndarray
            Polygon coordinates of the ROI. Expected shape (N, 2) or two arrays.
            Coordinates are (x, y) in pixel units.
        image_shape : tuple
            (height, width) of the image canvas where ROI was drawn.

        Returns
        -------
        dict
            {
                'mask': np.ndarray (bool) ROI mask,
                'area_pixels': int,
                'bbox': (x_min, y_min, width, height),
                'bbox_center': (center_x, center_y),
                'centroid': (centroid_y, centroid_x),
                'estimated_radius': float,
                'center_radius': float,
                'effective_center_radius': float
            }

        Notes
        -----
        - Uses bounding-box center (ImageJ's getSelectionBounds style) for
          compatibility with the original ImageJ macro.
        - Falls back to safe defaults (zero area) if roi_coords is empty or invalid.
        """
        # Normalize input
        if roi_coords is None:
            # Return defaults
            mask = np.zeros(image_shape, dtype=bool)
            return {
                "mask": mask,
                "area_pixels": 0,
                "bbox": (0, 0, 0, 0),
                "bbox_center": (0.0, 0.0),
                "centroid": (0.0, 0.0),
                "estimated_radius": 0.0,
                "center_radius": 0.0,
                "effective_center_radius": 0.0,
            }

        coords = np.asarray(roi_coords)
        if coords.size == 0:
            mask = np.zeros(image_shape, dtype=bool)
            return {
                "mask": mask,
                "area_pixels": 0,
                "bbox": (0, 0, 0, 0),
                "bbox_center": (0.0, 0.0),
                "centroid": (0.0, 0.0),
                "estimated_radius": 0.0,
                "center_radius": 0.0,
                "effective_center_radius": 0.0,
            }

        # Accept either shape (N,2) or two arrays [x_coords, y_coords]
        if coords.ndim == 1 and coords.size >= 2:
            # flat list -> not supported
            raise ValueError("roi_coords must be array-like with shape (N,2)")
        if coords.ndim == 2 and coords.shape[1] == 2:
            xs = coords[:, 0].astype(np.int32)
            ys = coords[:, 1].astype(np.int32)
        else:
            raise ValueError("roi_coords must have shape (N, 2) with (x,y) pairs")

        # Clip coordinates to image bounds
        height, width = image_shape
        xs = np.clip(xs, 0, width - 1)
        ys = np.clip(ys, 0, height - 1)

        # Rasterize polygon to mask using skimage.draw.polygon
        try:
            from skimage.draw import polygon as sk_polygon
        except Exception:
            # As fallback, create an empty mask (should install scikit-image)
            mask = np.zeros(image_shape, dtype=bool)
        else:
            rr, cc = sk_polygon(ys, xs, shape=image_shape)
            mask = np.zeros(image_shape, dtype=bool)
            mask[rr, cc] = True

        area_pixels = int(np.sum(mask))

        # Bounding box (ImageJ's selection bounds)
        x_min = int(xs.min())
        x_max = int(xs.max())
        y_min = int(ys.min())
        y_max = int(ys.max())
        bbox_w = x_max - x_min
        bbox_h = y_max - y_min
        bbox_center_x = x_min + bbox_w / 2.0
        bbox_center_y = y_min + bbox_h / 2.0

        # Centroid from mask (more accurate for irregular shapes)
        if area_pixels > 0:
            yy, xx = np.nonzero(mask)
            centroid_y = float(np.mean(yy))
            centroid_x = float(np.mean(xx))
        else:
            centroid_y = bbox_center_y
            centroid_x = bbox_center_x

        # Geometry: estimated radius and center radii
        estimated_radius = (
            float(np.sqrt(area_pixels / np.pi)) if area_pixels > 0 else 0.0
        )
        center_radius = estimated_radius / 3.0 if estimated_radius > 0 else 0.0

        # Small ROI fallback
        if estimated_radius < 20.0 and estimated_radius > 0.0:
            effective_center_radius = estimated_radius * 0.4
        else:
            effective_center_radius = center_radius

        return {
            "mask": mask,
            "area_pixels": area_pixels,
            "bbox": (x_min, y_min, bbox_w, bbox_h),
            "bbox_center": (bbox_center_x, bbox_center_y),
            "centroid": (centroid_y, centroid_x),
            "estimated_radius": estimated_radius,
            "center_radius": center_radius,
            "effective_center_radius": effective_center_radius,
        }

    def create_adaptive_masks(
        self,
        image_shape: tuple,
        roi_mask: np.ndarray,
        center: tuple,
        effective_center_radius: float,
    ) -> tuple:
        """
        Create center and periphery masks from ROI: center = ROI shrunk inward
        (shape preserved), periphery = ROI minus center.

        Uses distance transform so center is the same polygon shape as the ROI,
        just reduced in size (pixels at least effective_center_radius from boundary).

        Parameters
        ----------
        image_shape : tuple
            (height, width) of the image
        roi_mask : np.ndarray
            Boolean mask of the MNV ROI
        center : tuple
            (center_y, center_x) in pixel coordinates (unused; kept for API compatibility)
        effective_center_radius : float
            Shrink distance in pixels: center = ROI pixels >= this distance from boundary

        Returns
        -------
        (center_mask, periphery_mask)
            center_mask: boolean mask of ROI shrunk inward (same shape as ROI)
            periphery_mask: boolean mask of roi_mask minus center_mask
        """
        from scipy.ndimage import distance_transform_edt

        # Validate inputs
        if roi_mask is None or roi_mask.size == 0:
            center_mask = np.zeros(image_shape, dtype=bool)
            periphery_mask = np.zeros(image_shape, dtype=bool)
            return center_mask, periphery_mask

        roi_binary = np.asarray(roi_mask, dtype=bool)
        shrink_pixels = max(0.0, float(effective_center_radius))

        if shrink_pixels <= 0:
            center_mask = roi_binary.copy()
            periphery_mask = np.zeros_like(roi_binary)
            return center_mask, periphery_mask

        # Distance transform: distance from each pixel to nearest background.
        # Center = pixels at least shrink_pixels from boundary (ROI shape preserved).
        dist = distance_transform_edt(roi_binary.astype(np.uint8))
        max_dist = float(np.max(dist))

        if max_dist >= shrink_pixels:
            threshold = shrink_pixels
        else:
            # 細長いROI: 最初から dist.max() の 50% を閾値に
            threshold = 0.5 * max_dist if max_dist > 0 else 0.0

        center_mask = (dist >= threshold) & roi_binary
        # center が空のときのみ、距離最大のピクセルを少なくとも1つ含める
        if not np.any(center_mask):
            center_mask = (dist >= max_dist) & roi_binary

        periphery_mask = roi_binary & ~center_mask
        return center_mask, periphery_mask

    def extract_trunk_skeleton(
        self,
        thick_map: np.ndarray,
        min_pixels: Optional[int] = None,
        estimated_radius: Optional[float] = None,
    ) -> Optional[np.ndarray]:
        """
        Extract trunk skeleton coordinates from a thick vessel mask.

        Parameters
        ----------
        thick_map : np.ndarray
            Binary or grayscale image (vessels > 0)
        min_pixels : Optional[int]
            Minimum required skeleton pixels. If None, uses defaults based on estimated_radius
        estimated_radius : Optional[float]
            Estimated lesion radius (pixels) used to relax small-ROI threshold

        Returns
        -------
        coords : np.ndarray or None
            Array shape (N, 2) of (y, x) skeleton pixel coordinates, or None if insufficient
        """
        # Binarize
        bin_img = thick_map > 0

        try:
            from skimage.morphology import skeletonize
        except Exception:
            # Fallback - use a simple thinning via ndimage (less accurate)
            skeleton = ndimage.binary_erosion(bin_img) & bin_img
        else:
            skeleton = skeletonize(bin_img)

        ys, xs = np.nonzero(skeleton)
        coords = np.column_stack([ys, xs])
        nPixels = coords.shape[0]

        # Determine threshold
        if min_pixels is None:
            if estimated_radius is not None and estimated_radius < 20.0:
                threshold = 20
            else:
                threshold = 50
        else:
            threshold = int(min_pixels)

        if nPixels < threshold:
            return None

        return coords

    def classify_trunk_pixels(
        self,
        trunk_coords: np.ndarray,
        center: tuple,
        effective_center_radius: float,
        estimated_radius: float,
    ) -> tuple:
        """
        Classify trunk skeleton pixels into center and periphery by distance from lesion center.

        Parameters
        ----------
        trunk_coords : np.ndarray
            (N,2) array of (y,x) coordinates
        center : tuple
            (center_y, center_x)
        effective_center_radius : float
            radius (pixels) defining center
        estimated_radius : float
            outer radius (pixels) for periphery limit

        Returns
        -------
        (center_coords, periphery_coords, center_count, periphery_count)
        """
        if trunk_coords is None or len(trunk_coords) == 0:
            return (
                np.empty((0, 2), dtype=int),
                np.empty((0, 2), dtype=int),
                0,
                0,
            )

        center_y, center_x = center
        ys = trunk_coords[:, 0].astype(float)
        xs = trunk_coords[:, 1].astype(float)

        dists = np.sqrt((ys - center_y) ** 2 + (xs - center_x) ** 2)

        center_mask = dists <= effective_center_radius
        periphery_mask = (dists > effective_center_radius) & (dists <= estimated_radius)

        center_coords = trunk_coords[center_mask]
        periphery_coords = trunk_coords[periphery_mask]

        return (
            center_coords,
            periphery_coords,
            center_coords.shape[0],
            periphery_coords.shape[0],
        )

    def compute_trunk_eccentricity(
        self, trunk_coords: np.ndarray, lesion_center: tuple, estimated_radius: float
    ) -> float:
        """
        Compute normalized trunk eccentricity in [0, 1].

        Parameters
        ----------
        trunk_coords : np.ndarray
            (N,2) array of (y,x) skeleton coords
        lesion_center : tuple
            (center_y, center_x)
        estimated_radius : float
            Normalization radius

        Returns
        -------
        eccentricity : float
            0..1
        """
        if trunk_coords is None or trunk_coords.shape[0] == 0 or estimated_radius <= 0:
            return 0.0

        trunk_centroid = np.mean(trunk_coords, axis=0)  # (y, x)
        cy, cx = lesion_center
        ecc_dist = np.sqrt(
            (trunk_centroid[0] - cy) ** 2 + (trunk_centroid[1] - cx) ** 2
        )

        ecc = ecc_dist / estimated_radius
        if ecc < 0:
            ecc = 0.0
        if ecc > 1.0:
            ecc = 1.0

        return float(ecc)

    def calculate_angular_cv(
        self, sector_counts: np.ndarray, num_sectors: int
    ) -> float:
        """
        Calculate coefficient of variation for angular sector counts.

        Returns -1.0 if insufficient occupied sectors (dynamic minSectors rule).
        """
        # Count occupied sectors and compute mean/std over occupied
        non_zero = sector_counts > 0
        non_zero_count = int(np.sum(non_zero))

        # Dynamic min sectors: macro used minSectors=2, and if sectors>=8 then minSectors=3
        min_sectors = 2
        if num_sectors >= 8:
            min_sectors = 3

        if non_zero_count < min_sectors:
            return -1.0

        occupied_counts = sector_counts[non_zero]
        mean_count = float(np.mean(occupied_counts))
        if mean_count == 0.0:
            return -1.0

        std_count = float(np.std(occupied_counts, ddof=0))
        cv = std_count / mean_count

        # Cap to 2.0 (macro limited CV to 2.0)
        if cv > 2.0:
            cv = 2.0

        return float(cv)

    def calculate_radial_uniformity(
        self, sector_counts: np.ndarray, num_sectors: int
    ) -> float:
        """
        Compute radial uniformity metric (0..1) combining occupancy and distribution uniformity.
        """
        occupied = sector_counts > 0
        occupied_count = int(np.sum(occupied))

        if occupied_count < 3:
            return 0.0

        occupancy_fraction = occupied_count / float(num_sectors)

        occupied_counts = sector_counts[occupied]
        mean_count = float(np.mean(occupied_counts))
        variance = (
            float(np.mean((occupied_counts - mean_count) ** 2))
            if mean_count > 0
            else 0.0
        )
        std_count = float(np.sqrt(variance))
        cv = std_count / mean_count if mean_count > 0 else np.inf

        if cv < 0.5:
            distribution_uniformity = 1.0
        elif cv < 1.0:
            distribution_uniformity = 0.7
        else:
            distribution_uniformity = 0.4

        uniformity = occupancy_fraction * distribution_uniformity
        return float(uniformity)

    def compute_angular_distribution(
        self, trunk_coords: np.ndarray, center: tuple, num_sectors: int = 8
    ) -> tuple:
        """
        Compute sector counts, angular CV (with coarse fallback), and radial uniformity.

        Returns (sector_counts, angular_cv, radial_uniformity)
        """
        if trunk_coords is None or trunk_coords.shape[0] == 0:
            return np.zeros(num_sectors, dtype=int), -1.0, 0.0

        ys = trunk_coords[:, 0].astype(float)
        xs = trunk_coords[:, 1].astype(float)
        cy, cx = center

        dx = xs - cx
        dy = ys - cy
        angles = np.degrees(np.arctan2(dy, dx))
        angles[angles < 0] += 360.0

        sector_counts = np.zeros(num_sectors, dtype=int)
        sector_size = 360.0 / float(num_sectors)

        for ang in angles:
            idx = int(np.floor(ang / sector_size))
            if idx >= num_sectors:
                idx = num_sectors - 1
            sector_counts[idx] += 1

        angular_cv = self.calculate_angular_cv(sector_counts, num_sectors)

        # Fallback for small ROI: if angular_cv invalid and enough pixels, try coarse 4-sector
        if angular_cv < 0 and trunk_coords.shape[0] >= 10:
            coarse = 4
            coarse_counts = np.zeros(coarse, dtype=int)
            coarse_size = 360.0 / float(coarse)
            for ang in angles:
                idx = int(np.floor(ang / coarse_size))
                if idx >= coarse:
                    idx = coarse - 1
                coarse_counts[idx] += 1
            angular_cv_coarse = self.calculate_angular_cv(coarse_counts, coarse)
            if angular_cv_coarse >= 0:
                angular_cv = angular_cv_coarse

        radial_uniformity = self.calculate_radial_uniformity(sector_counts, num_sectors)

        return sector_counts, float(angular_cv), float(radial_uniformity)

    def calculate_stability_metrics(self, diameters: np.ndarray) -> float:
        """Delegate to common stability metrics implementation."""
        from core.pattern_metrics import calculate_stability_metrics as _calc

        return float(_calc(diameters))

    def classify_vessel_pattern(
        self,
        trunk_eccentricity: float,
        radial_uniformity: float,
        thick_center_ratio: float,
        diameter_ratio: float,
    ) -> tuple:
        """Delegate to common classification function."""
        from core.pattern_metrics import classify_vessel_pattern as _classify

        return _classify(
            trunk_eccentricity, radial_uniformity, thick_center_ratio, diameter_ratio
        )

    def calculate_trunk_distribution_score(
        self,
        trunk_ecc: float,
        angular_cv: float,
        thick_center_ratio: float,
        diameter_ratio: float,
    ) -> float:
        """Delegate to common trunk distribution score."""
        from core.pattern_metrics import \
            calculate_trunk_distribution_score as _calc

        return float(_calc(trunk_ecc, angular_cv, thick_center_ratio, diameter_ratio))

    def calculate_complexity_score(
        self,
        center_metrics: Dict,
        periphery_metrics: Dict,
        trunk_ecc: float,
        angular_cv: float,
    ) -> float:
        """Delegate complexity calculation to common function."""
        from core.pattern_metrics import \
            calculate_complexity_score_from_metrics as _calc

        return float(_calc(center_metrics, periphery_metrics, trunk_ecc, angular_cv))

    def compute_radial_diameter_profile(
        self,
        distance_map: np.ndarray,
        roi_mask: np.ndarray,
        center: tuple,
        estimated_radius: float,
        mm_per_pixel: float,
        num_bins: int = 10,
    ) -> tuple:
        """
        Compute radial diameter profile and stability score.

        Returns (radial_means (µm), gradient (µm/bin), stability_score)
        """
        h, w = distance_map.shape
        cy, cx = center
        bin_width = float(estimated_radius) / float(num_bins) if num_bins > 0 else 0.0

        # Precompute distances
        y_idx, x_idx = np.indices(distance_map.shape)
        distances_from_center = np.sqrt((y_idx - cy) ** 2 + (x_idx - cx) ** 2)

        radial_means = np.zeros(num_bins, dtype=float)

        for b in range(num_bins):
            inner_r = b * bin_width
            outer_r = (b + 1) * bin_width
            ring_mask = (
                (roi_mask.astype(bool))
                & (distances_from_center >= inner_r)
                & (distances_from_center < outer_r)
            )
            if np.any(ring_mask):
                mean_val = float(np.mean(distance_map[ring_mask]))
                radial_means[b] = mean_val * 2.0 * mm_per_pixel * 1000.0
            else:
                # fallback: use previous bin's value if available, else 0
                radial_means[b] = radial_means[b - 1] if b > 0 else 0.0

        # Linear regression for gradient
        x = np.arange(num_bins, dtype=float)
        if num_bins > 1:
            coeffs = np.polyfit(x, radial_means, 1)
            gradient = float(coeffs[0])
        else:
            gradient = 0.0

        stability = self.calculate_stability_metrics(radial_means)

        return radial_means, gradient, float(stability)

    def calculate_fractal_dimension_box_counting(self, skeleton: np.ndarray) -> float:
        """
        Compute fractal dimension using box-counting method.
        Returns 0.0 if invalid or insufficient scales.
        Uses block_reduce for vectorized box counting (aligned with FractalAnalyzer).
        """
        from skimage.measure import block_reduce

        img = (skeleton > 0).astype(np.uint8)
        height, width = img.shape
        max_dim = max(height, width)

        box_sizes = [2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 64]
        valid_sizes = [s for s in box_sizes if s <= max_dim / 4]

        if len(valid_sizes) < 3:
            return 0.0

        # Crop to non-zero bbox to reduce work for sparse regions
        rows = np.any(img > 0, axis=1)
        cols = np.any(img > 0, axis=0)
        if not np.any(rows) or not np.any(cols):
            return 0.0
        rmin, rmax = int(np.where(rows)[0][0]), int(np.where(rows)[0][-1])
        cmin, cmax = int(np.where(cols)[0][0]), int(np.where(cols)[0][-1])
        img = img[rmin : rmax + 1, cmin : cmax + 1]

        log_sizes = []
        log_counts = []

        for box_size in valid_sizes:
            reduced = block_reduce(img, (box_size, box_size), np.max)
            box_count = int(np.sum(reduced > 0))
            if box_count > 0:
                log_sizes.append(np.log(1.0 / float(box_size)))
                log_counts.append(np.log(float(box_count)))

        # Diagnostic: report valid sizes and counts for region-level FD
        try:
            print(f"[RegionalFA] valid_sizes={valid_sizes}")
            print(f"[RegionalFA] log_sizes={log_sizes}")
            print(f"[RegionalFA] log_counts={log_counts}")
        except Exception:
            pass

        if len(log_sizes) < 3:
            print("[RegionalFA] Insufficient scales for FD (len(log_sizes) < 3)")
            return 0.0

        xs = np.array(log_sizes)
        ys = np.array(log_counts)
        n = len(xs)
        sum_x = np.sum(xs)
        sum_y = np.sum(ys)
        sum_xy = np.sum(xs * ys)
        sum_x2 = np.sum(xs * xs)
        denom = n * sum_x2 - sum_x * sum_x
        if abs(denom) < 1e-12:
            return 0.0

        slope = (n * sum_xy - sum_x * sum_y) / denom

        # Diagnostic: slope and preliminary quality
        try:
            print(f"[RegionalFA] calc -> n={n}, slope={slope:.6f}")
        except Exception:
            pass

        # Validate range (ImageJ uses 0.5-2.5; relax from 1.0-2.0 for small regions)
        if slope < 0.5 or slope > 2.5:
            print(
                f"[RegionalFA] FD slope out of range: slope={slope:.6f} (expected 0.5-2.5); returning 0.0"
            )
            return 0.0

        # R^2
        intercept = (sum_y - slope * sum_x) / n
        predicted = slope * xs + intercept
        ss_tot = np.sum((ys - np.mean(ys)) ** 2)
        ss_res = np.sum((ys - predicted) ** 2)
        r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
        try:
            print(
                f"[RegionalFA] calc -> r2={r2:.6f}, ss_tot={ss_tot:.6f}, ss_res={ss_res:.6f}"
            )
        except Exception:
            pass
        if r2 < 0.8:
            print(f"[RegionalFA] Poor fit quality (R²={r2:.6f} < 0.8); returning 0.0")
            return 0.0

        return float(slope)

    def calculate_euler_number(self, skeleton: np.ndarray) -> tuple:
        """
        Calculate Euler number and number of loops (ImageJ formula).
        Euler = C - loops, loops = E - V + C.
        V = endpoints + junctions (ImageJ: junction clusters, not voxels).
        E = branches.
        """
        skel = (skeleton > 0).astype(np.uint8) * 255
        n_components = int(cv2.connectedComponents(skel, connectivity=8)[0] - 1)
        if n_components <= 0:
            return 0, 0

        kernel = np.array([[1, 1, 1], [1, 10, 1], [1, 1, 1]], dtype=np.uint8)
        filtered = cv2.filter2D(skel // 255, -1, kernel)

        # Endpoints: 1 neighbor (typically 1 pixel each)
        n_endpoints = int(np.sum((filtered == 11) & (skel > 0)))

        # Junctions: ImageJ counts junction *clusters* (connected components),
        # not voxels. Neighboring junction pixels = one junction.
        junctions_mask = (filtered >= 13) & (skel > 0)
        n_junctions = int(
            cv2.connectedComponents(
                (junctions_mask > 0).astype(np.uint8), connectivity=8
            )[0]
            - 1
        )
        n_junctions = max(0, n_junctions)
        n_vertices = n_endpoints + n_junctions

        # Branch count: remove junctions, count connected components
        skel_no_junc = skel.copy()
        skel_no_junc[junctions_mask] = 0
        n_branches = int(
            cv2.connectedComponents(skel_no_junc, connectivity=8)[0] - 1
        )
        n_edges = max(n_branches, n_components)

        n_loops = int(n_edges - n_vertices + n_components)
        if n_loops < 0:
            n_loops = 0
        euler_number = int(n_components - n_loops)
        return euler_number, n_loops

    def aggregate_branch_info_by_region(
        self,
        skeleton: np.ndarray,
        center_mask: np.ndarray,
        periphery_mask: np.ndarray,
        branch_data: Dict,
        mm_per_pixel: float,
        skeleton_diameter_um: Optional[float] = None,
    ) -> Dict:
        """
        Classify branches by midpoint into center-only, periphery-only, exclude boundary branches.

        branch_data keys expected:
          - 'endpoints': list of tuples (v1_y, v1_x, v2_y, v2_x)
          - 'lengths': list of floats (pixel units)

        Returns dict with 'center' and 'periphery' metrics.
        """
        center_branches = []
        periphery_branches = []

        endpoints = branch_data.get("endpoints", [])
        lengths = branch_data.get("lengths", [])

        height, width = skeleton.shape
        _t0 = time.perf_counter()

        for i, ep in enumerate(endpoints):
            v1_y, v1_x, v2_y, v2_x = ep
            length = float(lengths[i]) if i < len(lengths) else 0.0

            mid_y = int(round((v1_y + v2_y) / 2.0))
            mid_x = int(round((v1_x + v2_x) / 2.0))

            # clamp
            if mid_y < 0 or mid_y >= height or mid_x < 0 or mid_x >= width:
                continue

            in_center = bool(center_mask[mid_y, mid_x])
            in_periphery = bool(periphery_mask[mid_y, mid_x])

            euclidean_dist = np.sqrt((v2_y - v1_y) ** 2 + (v2_x - v1_x) ** 2)

            # Tortuosity calculation following ImageJ macro logic:
            # threshold_mm = skeleton_diameter_um / 1000.0 (fallback 0.001 mm)
            # threshold_px = threshold_mm / mm_per_pixel
            # Only compute tortuosity when euclidean_dist > threshold_px and euclidean_dist > 0
            tortuosity = 1.0
            try:
                thr_mm = (
                    float(skeleton_diameter_um) / 1000.0
                    if skeleton_diameter_um is not None
                    else 0.0
                )
            except Exception:
                thr_mm = 0.0
            if thr_mm <= 0.0:
                thr_mm = 0.001
            threshold_px = (
                thr_mm / float(mm_per_pixel) if mm_per_pixel > 0 else float("inf")
            )

            if euclidean_dist > threshold_px and euclidean_dist > 0:
                t = float(length) / float(euclidean_dist)
                if t >= 1.0 and t < 10.0:
                    tortuosity = float(t)
                else:
                    tortuosity = 1.0

            tortuosity = float(max(1.0, tortuosity))

            if in_center and not in_periphery:
                center_branches.append({"length": length, "tortuosity": tortuosity})
            elif in_periphery and not in_center:
                periphery_branches.append({"length": length, "tortuosity": tortuosity})
            else:
                # boundary or outside -> exclude
                continue

        print(f"[Step6] 1b-1 branch_iteration: {time.perf_counter()-_t0:.3f}s")
        _t1 = time.perf_counter()

        def compute_metrics(branches):
            if len(branches) == 0:
                return {
                    "count": 0,
                    "total_length_mm": 0.0,
                    "avg_tortuosity": 1.0,
                    "fractal_dimension": 0.0,
                    "euler_number": 0,
                    "n_loops": 0,
                }
            total_length_px = sum(b["length"] for b in branches)
            weighted_tort = sum(b["tortuosity"] * b["length"] for b in branches)
            total_length_mm = float(total_length_px) * mm_per_pixel
            avg_tortuosity = (
                float(weighted_tort / total_length_px) if total_length_px > 0 else 1.0
            )
            return {
                "count": len(branches),
                "total_length_mm": total_length_mm,
                "avg_tortuosity": avg_tortuosity,
            }

        center_metrics = compute_metrics(center_branches)
        periphery_metrics = compute_metrics(periphery_branches)

        # Masked skeleton images for FD/Euler
        center_skel = np.logical_and(skeleton > 0, center_mask.astype(bool)).astype(
            np.uint8
        )
        periphery_skel = np.logical_and(
            skeleton > 0, periphery_mask.astype(bool)
        ).astype(np.uint8)

        center_px = int(np.sum(center_skel > 0))
        periphery_px = int(np.sum(periphery_skel > 0))
        center_area = int(np.sum(center_mask > 0))
        periphery_area = int(np.sum(periphery_mask > 0))
        try:
            print(
                f"[Regional] center: mask_area={center_area}px, skel_px={center_px}, "
                f"branches={len(center_branches)}; "
                f"periphery: mask_area={periphery_area}px, skel_px={periphery_px}, "
                f"branches={len(periphery_branches)}"
            )
        except Exception:
            pass

        center_metrics["fractal_dimension"] = (
            self.calculate_fractal_dimension_box_counting(center_skel)
        )
        print(f"[Step6] 1b-2 fd_center: {time.perf_counter()-_t1:.3f}s")
        _t2 = time.perf_counter()
        periphery_metrics["fractal_dimension"] = (
            self.calculate_fractal_dimension_box_counting(periphery_skel)
        )
        print(f"[Step6] 1b-3 fd_periphery: {time.perf_counter()-_t2:.3f}s")
        _t3 = time.perf_counter()

        euler_c, loops_c = self.calculate_euler_number(center_skel)
        euler_p, loops_p = self.calculate_euler_number(periphery_skel)

        center_metrics["euler_number"] = euler_c
        center_metrics["n_loops"] = loops_c

        periphery_metrics["euler_number"] = euler_p
        periphery_metrics["n_loops"] = loops_p
        print(f"[Step6] 1b-4 euler: {time.perf_counter()-_t3:.3f}s")

        return {"center": center_metrics, "periphery": periphery_metrics}

    def _extract_branch_data_from_skeleton(
        self, skeleton: np.ndarray
    ) -> Dict[str, List]:
        """
        Extract branch endpoints and lengths from skeleton via connected components.

        Returns dict with 'endpoints': [(v1_y, v1_x, v2_y, v2_x), ...] and
        'lengths': [length_px, ...].
        """
        skel = (
            (skeleton > 0).astype(np.uint8) if skeleton.dtype != np.uint8 else skeleton
        )
        num_labels, labels = cv2.connectedComponents(skel, connectivity=8)

        endpoints: List[Tuple[float, float, float, float]] = []
        lengths: List[float] = []

        for i in range(1, num_labels):
            component_mask = labels == i
            y_coords, x_coords = np.where(component_mask)

            if len(x_coords) < 2:
                continue

            v1_x, v1_y = int(x_coords[0]), int(y_coords[0])
            v2_x, v2_y = int(x_coords[-1]), int(y_coords[-1])
            branch_length = len(x_coords)

            endpoints.append((float(v1_y), float(v1_x), float(v2_y), float(v2_x)))
            lengths.append(float(branch_length))

        return {"endpoints": endpoints, "lengths": lengths}

    def analyze_regions_from_skeleton(
        self,
        skeleton: np.ndarray,
        center_mask: np.ndarray,
        periphery_mask: np.ndarray,
        skeleton_diameter_um: Optional[float] = None,
        branch_data: Optional[Dict] = None,
    ) -> Dict:
        """
        Analyze center/periphery metrics from skeleton and region masks.

        Uses aggregate_branch_info_by_region with branch data. When branch_data
        is provided (from SkeletonAnalyzer.analyze_skeleton_structure), uses it
        for ImageJ-compatible per-branch analysis. Otherwise falls back to
        connected-components extraction.

        Returns flat dict with center_branch_count, vessel_length_center,
        tortuosity_center, fractal_dimension_center, euler_center, loop_center
        and periphery equivalents.
        """
        if branch_data is None:
            branch_data = self._extract_branch_data_from_skeleton(skeleton)

        if not branch_data["endpoints"]:
            return {
                "center_branch_count": 0,
                "vessel_length_center": 0.0,
                "tortuosity_center": 1.0,
                "fractal_dimension_center": 0.0,
                "euler_center": 0,
                "loop_center": 0,
                "periphery_branch_count": 0,
                "vessel_length_periphery": 0.0,
                "tortuosity_periphery": 1.0,
                "fractal_dimension_periphery": 0.0,
                "euler_periphery": 0,
                "loop_periphery": 0,
            }

        agg = self.aggregate_branch_info_by_region(
            skeleton=skeleton,
            center_mask=center_mask,
            periphery_mask=periphery_mask,
            branch_data=branch_data,
            mm_per_pixel=self.pixel_size_mm,
            skeleton_diameter_um=skeleton_diameter_um,
        )

        c = agg["center"]
        p = agg["periphery"]

        return {
            "center_branch_count": c["count"],
            "vessel_length_center": c["total_length_mm"],
            "tortuosity_center": c["avg_tortuosity"],
            "fractal_dimension_center": c["fractal_dimension"],
            "euler_center": c["euler_number"],
            "loop_center": c.get("n_loops", 0),
            "periphery_branch_count": p["count"],
            "vessel_length_periphery": p["total_length_mm"],
            "tortuosity_periphery": p["avg_tortuosity"],
            "fractal_dimension_periphery": p["fractal_dimension"],
            "euler_periphery": p["euler_number"],
            "loop_periphery": p.get("n_loops", 0),
        }

    def _analyze_advanced(
        self,
        binary_image: np.ndarray,
        lesion_center: tuple,
        distance_map: np.ndarray,
        thick_map: Optional[np.ndarray],
        branch_data: Optional[Dict],
        skeleton_analyzer,
    ) -> Dict:
        """
        Perform advanced ImageJ-macro-equivalent analysis and return extra metrics.
        """
        # lesion mask from binary
        lesion_mask = (binary_image > 127).astype(bool)
        area_pixels = int(np.sum(lesion_mask))
        estimated_radius = (
            float(np.sqrt(area_pixels / np.pi)) if area_pixels > 0 else 0.0
        )
        # center is lesion_center tuple (y,x)
        center = lesion_center
        # effective center radius
        if estimated_radius > 0 and estimated_radius < 20.0:
            effective_center_radius = estimated_radius * 0.4
        else:
            effective_center_radius = (
                estimated_radius / 3.0 if estimated_radius > 0 else 0.0
            )

        # Create adaptive masks (center/periphery inside lesion)
        center_mask, periphery_mask = self.create_adaptive_masks(
            binary_image.shape, lesion_mask, center, effective_center_radius
        )

        # Diameter means
        adv = {}
        if distance_map is not None:
            # ensure distance_map masked to lesion
            dm = distance_map.copy().astype(float)
            dm[~lesion_mask] = 0.0

            if np.any(center_mask):
                c_mean = float(np.mean(dm[center_mask]))
            else:
                c_mean = 0.0
            if np.any(periphery_mask):
                p_mean = float(np.mean(dm[periphery_mask]))
            else:
                p_mean = 0.0

            # convert to µm (distance map is pixels -> diameter = mean *2 * mm_per_pixel *1000)
            mm_per_pixel = self.pixel_size_mm
            diameter_center_mean = c_mean * 2.0 * mm_per_pixel * 1000.0
            diameter_periphery_mean = p_mean * 2.0 * mm_per_pixel * 1000.0

            adv["diameter_center_mean"] = diameter_center_mean
            adv["diameter_periphery_mean"] = diameter_periphery_mean

            if p_mean > 0:
                adv["diameter_center_periphery_ratio"] = c_mean / p_mean
            else:
                adv["diameter_center_periphery_ratio"] = 1.0

            # radial profile
            radial_means, gradient, stability = self.compute_radial_diameter_profile(
                distance_map=distance_map,
                roi_mask=lesion_mask,
                center=center,
                estimated_radius=estimated_radius,
                mm_per_pixel=mm_per_pixel,
                num_bins=10,
            )
            adv["radial_means"] = radial_means
            adv["diameter_radial_gradient"] = gradient
            adv["stability_score"] = stability
        else:
            adv["diameter_center_mean"] = 0.0
            adv["diameter_periphery_mean"] = 0.0
            adv["diameter_center_periphery_ratio"] = 1.0
            adv["radial_means"] = np.zeros(10, dtype=float)
            adv["diameter_radial_gradient"] = 0.0
            adv["stability_score"] = 0.0

        # Thick vessel ratios
        if thick_map is not None:
            th = (thick_map > 0).astype(np.uint8) * 255
            if np.any(center_mask):
                thick_center_mean = float(np.mean(th[center_mask]))
            else:
                thick_center_mean = 0.0
            if np.any(periphery_mask):
                thick_periphery_mean = float(np.mean(th[periphery_mask]))
            else:
                thick_periphery_mean = 0.0

            adv["thick_vessel_center_ratio"] = thick_center_mean / 255.0 * 100.0
            adv["thick_vessel_periphery_ratio"] = thick_periphery_mean / 255.0 * 100.0
        else:
            adv["thick_vessel_center_ratio"] = 0.0
            adv["thick_vessel_periphery_ratio"] = 0.0

        # Trunk vessel extraction and metrics
        if thick_map is not None:
            trunk_coords = self.extract_trunk_skeleton(
                thick_map, estimated_radius=estimated_radius
            )
        else:
            trunk_coords = None

        if trunk_coords is None:
            adv["trunk_eccentricity"] = -1.0
            adv["angular_distribution_cv"] = -1.0
            adv["radial_uniformity"] = 0.0
        else:
            trunk_ecc = self.compute_trunk_eccentricity(
                trunk_coords, center, estimated_radius
            )
            sector_counts, angular_cv, radial_uniformity = (
                self.compute_angular_distribution(trunk_coords, center)
            )
            adv["trunk_eccentricity"] = trunk_ecc
            adv["angular_distribution_cv"] = angular_cv
            adv["radial_uniformity"] = radial_uniformity

        # Branch aggregation
        if (
            branch_data is not None
            and "endpoints" in branch_data
            and "lengths" in branch_data
        ):
            # choose a skeleton diameter (µm) estimate for tortuosity threshold
            skel_diam_um = 0.0
            if adv.get("diameter_center_mean", 0.0) > 0:
                skel_diam_um = adv.get("diameter_center_mean", 0.0)
            elif adv.get("diameter_periphery_mean", 0.0) > 0:
                skel_diam_um = adv.get("diameter_periphery_mean", 0.0)

            agg = self.aggregate_branch_info_by_region(
                skeleton=skeleton_analyzer.analyze(binary_image, roi_mask=lesion_mask)[
                    "skeleton"
                ],
                center_mask=center_mask,
                periphery_mask=periphery_mask,
                branch_data=branch_data,
                mm_per_pixel=self.pixel_size_mm,
                skeleton_diameter_um=skel_diam_um,
            )
            # include explicit loop counts for later complexity calc
            adv.update(
                {
                    "center_branch_count": agg["center"]["count"],
                    "periphery_branch_count": agg["periphery"]["count"],
                    "vessel_length_center": agg["center"]["total_length_mm"],
                    "vessel_length_periphery": agg["periphery"]["total_length_mm"],
                    "tortuosity_center": agg["center"]["avg_tortuosity"],
                    "tortuosity_periphery": agg["periphery"]["avg_tortuosity"],
                    "FD_center": agg["center"]["fractal_dimension"],
                    "FD_periphery": agg["periphery"]["fractal_dimension"],
                    "euler_center": agg["center"]["euler_number"],
                    "euler_periphery": agg["periphery"]["euler_number"],
                    "center_n_loops": agg["center"].get("n_loops", 0),
                    "periphery_n_loops": agg["periphery"].get("n_loops", 0),
                }
            )
        else:
            adv.update(
                {
                    "center_branch_count": 0,
                    "periphery_branch_count": 0,
                    "vessel_length_center": 0.0,
                    "vessel_length_periphery": 0.0,
                    "tortuosity_center": 0.0,
                    "tortuosity_periphery": 0.0,
                    "FD_center": 0.0,
                    "FD_periphery": 0.0,
                    "euler_center": 0,
                    "euler_periphery": 0,
                    "center_n_loops": 0,
                    "periphery_n_loops": 0,
                }
            )

        # Pattern classification
        adv["pattern_classification"], adv["pattern_score"] = (
            self.classify_vessel_pattern(
                adv.get("trunk_eccentricity", -1.0),
                adv.get("radial_uniformity", 0.0),
                adv.get("thick_vessel_center_ratio", 0.0),
                adv.get("diameter_center_periphery_ratio", 1.0),
            )
        )

        # Complexity
        center_m = {
            "n_loops": adv.get("center_n_loops", 0),
            "count": adv.get("center_branch_count", 0),
            "total_length_mm": adv.get("vessel_length_center", 0.0),
            "euler_number": adv.get("euler_center", 0),
            "thick_center_ratio": adv.get("thick_vessel_center_ratio", 0.0),
            "diameter_ratio": adv.get("diameter_center_periphery_ratio", 1.0),
        }
        periphery_m = {
            "n_loops": adv.get("periphery_n_loops", 0),
            "count": adv.get("periphery_branch_count", 0),
            "total_length_mm": adv.get("vessel_length_periphery", 0.0),
            "euler_number": adv.get("euler_periphery", 0),
        }
        adv["complexity_score"] = self.calculate_complexity_score(
            center_m,
            periphery_m,
            adv.get("trunk_eccentricity", -1.0),
            adv.get("angular_distribution_cv", -1.0),
        )

        return adv

    def _compute_complexity(self, skeleton_results: Dict) -> float:
        """
        複雑性スコアを計算

        Parameters
        ----------
        skeleton_results : dict
            スケルトン解析結果

        Returns
        -------
        float
            複雑性スコア（正規化）
        """
        # 複雑性 = 分岐数 + ループ数 + (トルトゥオシティ - 1) * 10
        # フラクタル次元も考慮

        num_junctions = skeleton_results["num_junctions"]
        num_loops = skeleton_results["num_loops"]
        tortuosity = skeleton_results["tortuosity_mean"]
        fractal_dim = skeleton_results["fractal_dimension"]

        complexity = (
            num_junctions * 2.0
            + num_loops * 3.0
            + (tortuosity - 1.0) * 10.0
            + (fractal_dim - 1.0) * 5.0
        )

        # 正規化（0-100スケール）
        complexity = max(0.0, min(100.0, complexity))

        return complexity


def create_analyzer(
    center_radius_mm: float = 0.5, pixel_size_mm: float = 0.003
) -> RegionalAnalyzer:
    """
    デフォルトパラメータで解析器を作成

    Parameters
    ----------
    center_radius_mm : float
        Center領域の半径 (mm)
    pixel_size_mm : float
        ピクセルサイズ (mm)

    Returns
    -------
    RegionalAnalyzer
        領域別解析器
    """
    return RegionalAnalyzer(
        center_radius_mm=center_radius_mm, pixel_size_mm=pixel_size_mm
    )
