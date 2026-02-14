"""
Enhanced FAZ Detection Module

This module provides improved FAZ detection using feature-based methods
without machine learning, incorporating adaptive preprocessing and
multi-candidate scoring.
"""

from typing import Dict, Tuple

import numpy as np
from scipy import ndimage
from skimage import filters, measure, morphology, segmentation

try:
    import cv2

    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False


class ImprovedFAZDetector:
    """
    Enhanced FAZ detector using multi-method approach with scoring and refinement.
    """

    def __init__(
        self,
        min_area_mm2: float = 0.001,
        min_circularity: float = 0.05,
        distance_trim_ratio: float = 0.14,
        distance_min_px: int = 1,
    ):
        self.min_area_mm2 = min_area_mm2
        self.min_circularity = min_circularity
        # Distance-transform based trim strength for boundary regularization.
        # Larger ratio trims protrusions more aggressively.
        self.distance_trim_ratio = float(max(0.05, min(distance_trim_ratio, 0.45)))
        self.distance_min_px = int(max(1, distance_min_px))

    def detect(
        self, image: np.ndarray, vessel_mask: np.ndarray, mm_per_pixel: float = 1.0
    ) -> Tuple[np.ndarray, Dict[str, float]]:
        """
        Detect FAZ using enhanced methods.

        Parameters
        ----------
        image : np.ndarray
            Preprocessed OCTA image
        vessel_mask : np.ndarray
            Binary vessel segmentation mask
        mm_per_pixel : float
            Pixel size in mm

        Returns
        -------
        faz_mask : np.ndarray
            Binary FAZ mask
        metrics : dict
            FAZ metrics
        """
        # Adaptive preprocessing
        processed = self._adaptive_preprocessing(image, vessel_mask)

        # Multi-candidate detection
        candidates = self._detect_candidates(processed, vessel_mask)

        # Score and select best candidate
        best_mask = self._score_and_select(candidates, processed, vessel_mask)

        # Refine boundary
        refined_mask = self._refine_boundary(best_mask, image)

        # Validate and measure
        final_mask, metrics = self._validate_and_measure(refined_mask, mm_per_pixel)

        return final_mask, metrics

    def _adaptive_preprocessing(
        self, image: np.ndarray, vessel_mask: np.ndarray
    ) -> np.ndarray:
        """Adaptive preprocessing based on image characteristics."""
        # Enhance contrast in avascular regions
        avascular = ~vessel_mask

        # Apply CLAHE-like enhancement to avascular regions
        if HAS_CV2 and image.dtype == np.uint8:
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            enhanced = clahe.apply(image)
        else:
            # Fallback to skimage
            enhanced = filters.rank.equalize(image.astype(np.uint8), morphology.disk(5))

        # Combine with original
        processed = np.where(avascular, enhanced, image)

        # Apply gaussian smoothing
        processed = filters.gaussian(processed, sigma=1.0)

        return processed

    def _detect_candidates(
        self, processed: np.ndarray, vessel_mask: np.ndarray
    ) -> list:
        """Detect multiple FAZ candidates using different methods."""
        candidates = []

        # Method 1: Morphological opening
        avascular = ~vessel_mask
        opened = morphology.opening(avascular, morphology.disk(3))
        candidates.append(opened)

        # Method 2: Distance transform based
        distance = ndimage.distance_transform_edt(avascular)
        thresh_dist = filters.threshold_otsu(distance)
        dist_mask = distance > thresh_dist
        candidates.append(dist_mask)

        # Method 3: Watershed from center
        if np.any(avascular):
            markers = np.zeros_like(avascular, dtype=int)
            center_y, center_x = (
                avascular.shape[0] // 2,
                avascular.shape[1] // 2,
            )
            markers[center_y, center_x] = 1
            markers[~avascular] = 2

            labels = segmentation.watershed(processed, markers, mask=avascular)
            watershed_mask = labels == 1
            candidates.append(watershed_mask)

        return candidates

    def _score_and_select(
        self, candidates: list, processed: np.ndarray, vessel_mask: np.ndarray
    ) -> np.ndarray:
        """Score candidates and select the best one."""
        best_score = -1
        best_mask = np.zeros_like(vessel_mask)

        for candidate in candidates:
            if not np.any(candidate):
                continue

            score = self._score_candidate(candidate, processed, vessel_mask)
            if score > best_score:
                best_score = score
                best_mask = candidate

        return best_mask

    def _score_candidate(
        self, mask: np.ndarray, processed: np.ndarray, vessel_mask: np.ndarray
    ) -> float:
        """Score a candidate FAZ mask."""
        if not np.any(mask):
            return 0.0

        # Size score (prefer medium sizes)
        area = np.sum(mask)
        size_score = min(area / 1000, 1.0) * (1 - min(area / 10000, 1.0))

        # Circularity score
        regions = measure.regionprops(measure.label(mask))
        if regions:
            region = max(regions, key=lambda r: r.area)
            perimeter = region.perimeter
            if perimeter > 0:
                circularity = 4 * np.pi * region.area / (perimeter**2)
            else:
                circularity = 0.0
        else:
            circularity = 0.0

        circ_score = circularity

        # Centrality score
        centroid = ndimage.center_of_mass(mask)
        center_y, center_x = mask.shape[0] / 2, mask.shape[1] / 2
        dist = np.sqrt((centroid[0] - center_y) ** 2 + (centroid[1] - center_x) ** 2)
        max_dist = np.sqrt(center_y**2 + center_x**2)
        centrality_score = 1 - (dist / max_dist)

        # Intensity homogeneity score
        if np.any(mask):
            intensities = processed[mask]
            homogeneity_score = 1 / (1 + np.std(intensities))
        else:
            homogeneity_score = 0.0

        # Combined score
        total_score = (
            size_score * 0.3
            + circ_score * 0.3
            + centrality_score * 0.2
            + homogeneity_score * 0.2
        )

        return total_score

    def _refine_boundary(self, mask: np.ndarray, image: np.ndarray) -> np.ndarray:
        """Refine FAZ boundary using morphological operations."""
        if not np.any(mask):
            return mask

        # Fill small holes
        filled = morphology.remove_small_holes(mask, area_threshold=50)

        # Remove small objects
        cleaned = morphology.remove_small_objects(filled, min_size=50)

        # Distance-transform based regularization:
        # remove outward protrusions while preserving the main central region.
        regularized = self._regularize_by_distance(cleaned)

        # Smooth boundary with closing
        smoothed = morphology.closing(regularized, morphology.disk(2))

        return smoothed

    def _regularize_by_distance(self, mask: np.ndarray) -> np.ndarray:
        """Trim protrusions using adaptive distance-transform threshold."""
        if not np.any(mask):
            return mask

        labeled = measure.label(mask)
        regions = measure.regionprops(labeled)
        if not regions:
            return mask

        largest_label = max(regions, key=lambda r: r.area).label
        largest = labeled == largest_label

        distance = ndimage.distance_transform_edt(largest)
        max_dist = float(distance.max())
        if max_dist <= 0:
            return largest

        trim_radius = max(self.distance_min_px, int(round(max_dist * self.distance_trim_ratio)))
        core = distance > float(trim_radius)
        if not np.any(core):
            return largest

        # Re-grow from stable core; thin protrusions are less likely to return.
        regrown = morphology.binary_dilation(core, morphology.disk(trim_radius))
        return regrown & largest

    def _validate_and_measure(
        self, mask: np.ndarray, mm_per_pixel: float
    ) -> Tuple[np.ndarray, Dict[str, float]]:
        """Validate final mask and compute metrics."""
        if not np.any(mask):
            return mask, {
                "faz_area_mm2": 0.0,
                "faz_perimeter_mm": 0.0,
                "faz_circularity": 0.0,
                "faz_equivalent_diameter_mm": 0.0,
                "faz_acircularity": 1.0,
                "faz_centroid_x_px": mask.shape[1] / 2,
                "faz_centroid_y_px": mask.shape[0] / 2,
            }

        # Get largest region
        labeled = measure.label(mask)
        regions = measure.regionprops(labeled)
        if not regions:
            return np.zeros_like(mask), {
                "faz_area_mm2": 0.0,
                "faz_perimeter_mm": 0.0,
                "faz_circularity": 0.0,
                "faz_equivalent_diameter_mm": 0.0,
                "faz_acircularity": 1.0,
                "faz_centroid_x_px": mask.shape[1] / 2,
                "faz_centroid_y_px": mask.shape[0] / 2,
            }

        region = max(regions, key=lambda r: r.area)

        # Basic measurements
        area_px = region.area
        perimeter_px = region.perimeter

        # Convert to mm
        area_mm2 = area_px * (mm_per_pixel**2)
        perimeter_mm = perimeter_px * mm_per_pixel

        # Circularity
        if perimeter_px > 0:
            circularity = 4 * np.pi * area_px / (perimeter_px**2)
        else:
            circularity = 0.0

        # Acircularity
        acircularity = 1.0 / circularity if circularity > 0 else float("inf")

        # Equivalent diameter
        equivalent_diameter_mm = 2 * np.sqrt(area_mm2 / np.pi)

        # Centroid
        cy, cx = region.centroid

        # Validate against thresholds
        if area_mm2 < self.min_area_mm2 or circularity < self.min_circularity:
            # Return empty mask if doesn't meet criteria
            return np.zeros_like(mask), {
                "faz_area_mm2": 0.0,
                "faz_perimeter_mm": 0.0,
                "faz_circularity": 0.0,
                "faz_equivalent_diameter_mm": 0.0,
                "faz_acircularity": 1.0,
                "faz_centroid_x_px": mask.shape[1] / 2,
                "faz_centroid_y_px": mask.shape[0] / 2,
            }

        # Create final mask with only the largest region
        final_mask = (labeled == region.label).astype(bool)

        metrics = {
            "faz_area_mm2": float(area_mm2),
            "faz_perimeter_mm": float(perimeter_mm),
            "faz_circularity": float(circularity),
            "faz_equivalent_diameter_mm": float(equivalent_diameter_mm),
            "faz_acircularity": float(acircularity),
            "faz_centroid_x_px": float(cx),
            "faz_centroid_y_px": float(cy),
        }

        return final_mask, metrics
