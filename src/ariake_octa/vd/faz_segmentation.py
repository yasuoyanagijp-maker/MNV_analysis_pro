"""
Enhanced FAZ (Foveal Avascular Zone) Segmentation Module

Multiple segmentation approaches inspired by:
- SAM-OCTA: Segment Anything Model adaptation
- S²A-Net: CNN+Transformer framework
- FAZ_Extraction: Traditional image processing
- MultitaskOCTA: Multi-task learning approach

This module provides a unified interface with multiple fallback methods.
"""

from typing import Dict, List, Optional, Tuple

import numpy as np
from skimage import measure, morphology, filters, segmentation, feature, transform
from scipy import ndimage
from skimage import feature, filters, measure, morphology, segmentation


class EnhancedFAZSegmentation:
    """
    Enhanced FAZ segmentation with multiple methods

    Supports:
    1. Morphological method (default, fast)
    2. Edge-based method (traditional)
    3. Region growing method (precise)
    4. Hybrid method (combines multiple approaches)
    """

    def __init__(
        self,
        method: str = "morphological",
        min_area_mm2: float = 0.1,
        max_area_mm2: float = 1.5,
        min_circularity: float = 0.5,
        pixel_size_mm: float = 0.00744,
    ):
        """
        Args:
            method: Segmentation method ('morphological', 'edge', 'region_growing', 'hybrid')
            min_area_mm2: Minimum FAZ area (mm²)
            max_area_mm2: Maximum FAZ area (mm²)
            min_circularity: Minimum circularity (0-1)
            pixel_size_mm: Pixel size (mm/pixel)
        """
        valid_methods = ["morphological", "edge", "region_growing", "hybrid"]
        if method not in valid_methods:
            raise ValueError(f"Method must be one of {valid_methods}")

        self.method = method
        self.min_area_mm2 = min_area_mm2
        self.max_area_mm2 = max_area_mm2
        self.min_circularity = min_circularity
        self.pixel_size_mm = pixel_size_mm

    def segment(
        self, vessel_image: np.ndarray, binary_mask: Optional[np.ndarray] = None
    ) -> Tuple[Optional[np.ndarray], Dict]:
        """
        Segment FAZ from vessel image

        Args:
            vessel_image: Grayscale vessel image (H×W)
            binary_mask: Pre-computed binary vessel mask (optional)

        Returns:
            faz_mask: FAZ region mask (H×W bool) or None if detection failed
            metrics: Dictionary of FAZ metrics
        """
        # Apply selected method
        if self.method == "morphological":
            faz_mask = self._morphological_method(vessel_image, binary_mask)
        elif self.method == "edge":
            faz_mask = self._edge_based_method(vessel_image)
        elif self.method == "region_growing":
            faz_mask = self._region_growing_method(vessel_image, binary_mask)
        elif self.method == "hybrid":
            faz_mask = self._hybrid_method(vessel_image, binary_mask)
        else:
            raise ValueError(f"Unknown method: {self.method}")

        # Validate and compute metrics
        if faz_mask is None:
            return None, self._empty_metrics()

        # Validate FAZ region
        is_valid, metrics = self._validate_and_measure(faz_mask)

        if not is_valid:
            return None, self._empty_metrics()

        return faz_mask, metrics

    def _morphological_method(
        self, vessel_image: np.ndarray, binary_mask: Optional[np.ndarray] = None
    ) -> Optional[np.ndarray]:
        """
        Morphological FAZ detection (fastest method)

        Based on traditional image processing approach
        """
        if binary_mask is None:
            # Binarize using Otsu if not provided
            threshold = filters.threshold_otsu(vessel_image)
            binary_mask = vessel_image > threshold

        # Invert to get avascular regions
        inverted = ~binary_mask

        # Find center seed point
        h, w = inverted.shape
        center_y, center_x = h // 2, w // 2

        # Search for avascular region near center
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

        # Connected component analysis
        labeled = measure.label(inverted, connectivity=2)
        seed_label = labeled[seed_y, seed_x]

        if seed_label == 0:
            return None

        faz_mask = labeled == seed_label

        # Post-processing: fill holes and smooth
        faz_mask = morphology.remove_small_holes(faz_mask, max_size=50)
        faz_mask = morphology.closing(faz_mask, morphology.disk(2))
        faz_mask = morphology.opening(faz_mask, morphology.disk(1))

        return faz_mask

    def _edge_based_method(self, vessel_image: np.ndarray) -> Optional[np.ndarray]:
        """
        Edge-based FAZ detection using Canny edge detection

        Inspired by FAZ_Extraction traditional approach
        """
        # Preprocessing
        smoothed = filters.gaussian(vessel_image, sigma=2.0)

        # Edge detection
        edges = feature.canny(
            smoothed, sigma=1.5, low_threshold=0.05, high_threshold=0.15
        )

        # Fill regions
        filled = ndimage.binary_fill_holes(edges)

        # Remove edge pixels
        filled[edges] = False

        # Find largest central region
        h, w = filled.shape
        center_y, center_x = h // 2, w // 2

        labeled = measure.label(filled, connectivity=2)

        if labeled[center_y, center_x] == 0:
            # No region at center, find nearest
            regions = measure.regionprops(labeled)
            if not regions:
                return None

            # Find region closest to center
            min_dist = float("inf")
            best_label = 0
            for region in regions:
                cy, cx = region.centroid
                dist = np.sqrt((cy - center_y) ** 2 + (cx - center_x) ** 2)
                if dist < min_dist:
                    min_dist = dist
                    best_label = region.label

            faz_mask = labeled == best_label
        else:
            faz_mask = labeled == labeled[center_y, center_x]

        # Morphological refinement
        faz_mask = morphology.closing(faz_mask, morphology.disk(3))

        return faz_mask

    def _region_growing_method(
        self, vessel_image: np.ndarray, binary_mask: Optional[np.ndarray] = None
    ) -> Optional[np.ndarray]:
        """
        Region growing FAZ detection (most precise)

        Inspired by region-based segmentation approaches
        """
        if binary_mask is None:
            threshold = filters.threshold_otsu(vessel_image)
            binary_mask = vessel_image > threshold

        # Invert to get avascular regions
        inverted = ~binary_mask

        # Find center seed
        h, w = inverted.shape
        center_y, center_x = h // 2, w // 2

        # Create seed point at center of avascular region
        if not inverted[center_y, center_x]:
            # Find nearest avascular pixel
            y_coords, x_coords = np.where(inverted)
            if len(y_coords) == 0:
                return None

            distances = (y_coords - center_y) ** 2 + (x_coords - center_x) ** 2
            nearest_idx = np.argmin(distances)
            seed_y, seed_x = y_coords[nearest_idx], x_coords[nearest_idx]
        else:
            seed_y, seed_x = center_y, center_x

        # Region growing using flood fill
        filled = segmentation.flood_fill(
            inverted.astype(np.uint8),
            (seed_y, seed_x),
            1,
            in_place=False,
            connectivity=2,
        )

        # Use watershed segmentation for better boundary
        distance = ndimage.distance_transform_edt(inverted)

        # Create markers
        markers = np.zeros_like(inverted, dtype=int)
        markers[seed_y, seed_x] = 1
        markers[binary_mask] = 2  # Vessel regions

        # Watershed
        labels = segmentation.watershed(-distance, markers, mask=np.ones_like(inverted))
        faz_mask = labels == 1

        # Post-processing
        faz_mask = morphology.opening(faz_mask, morphology.disk(2))
        faz_mask = morphology.remove_small_holes(faz_mask, max_size=100)

        return faz_mask

    def _hybrid_method(
        self, vessel_image: np.ndarray, binary_mask: Optional[np.ndarray] = None
    ) -> Optional[np.ndarray]:
        """
        Hybrid FAZ detection combining multiple methods

        Combines morphological, edge-based, and region growing for robustness
        """
        results = []

        # Try each method
        try:
            mask1 = self._morphological_method(vessel_image, binary_mask)
            if mask1 is not None:
                results.append(mask1)
        except Exception:
            pass

        try:
            mask2 = self._edge_based_method(vessel_image)
            if mask2 is not None:
                results.append(mask2)
        except Exception:
            pass

        try:
            mask3 = self._region_growing_method(vessel_image, binary_mask)
            if mask3 is not None:
                results.append(mask3)
        except Exception:
            pass

        if not results:
            return None

        # Combine results using majority voting
        if len(results) == 1:
            return results[0]

        # Stack and take majority
        stacked = np.stack(results, axis=-1)
        combined = np.sum(stacked, axis=-1) > (len(results) // 2)

        # Refine combined result
        combined = morphology.closing(combined, morphology.disk(2))
        combined = morphology.remove_small_holes(combined, max_size=50)

        return combined

    def _validate_and_measure(self, faz_mask: np.ndarray) -> Tuple[bool, Dict]:
        """
        Validate FAZ region and compute metrics

        Returns:
            is_valid: Whether FAZ is valid
            metrics: Dictionary of measurements
        """
        # Label the mask properly for region properties
        labeled_mask = measure.label(faz_mask.astype(int), connectivity=2)
        regions = measure.regionprops(labeled_mask)

        if not regions:
            return False, self._empty_metrics()

        props = regions[0]

        # Calculate metrics in pixels
        area_px = props.area
        perimeter_px = props.perimeter

        # Convert to mm
        area_mm2 = area_px * (self.pixel_size_mm**2)
        perimeter_mm = perimeter_px * self.pixel_size_mm

        # Circularity
        if perimeter_px > 0:
            circularity = 4 * np.pi * area_px / (perimeter_px**2)
        else:
            circularity = 0.0

        # Validate constraints
        if area_mm2 < self.min_area_mm2:
            return False, self._empty_metrics()

        if area_mm2 > self.max_area_mm2:
            return False, self._empty_metrics()

        if circularity < self.min_circularity:
            return False, self._empty_metrics()

        # Compute all metrics
        equivalent_diameter_mm = np.sqrt(4 * area_mm2 / np.pi)
        centroid = props.centroid
        center_y_mm = centroid[0] * self.pixel_size_mm
        center_x_mm = centroid[1] * self.pixel_size_mm

        # Additional metrics
        major_axis_mm = props.axis_major_length * self.pixel_size_mm
        minor_axis_mm = props.axis_minor_length * self.pixel_size_mm
        eccentricity = props.eccentricity
        solidity = props.solidity

        metrics = {
            "faz_area_mm2": float(area_mm2),
            "faz_perimeter_mm": float(perimeter_mm),
            "faz_circularity": float(circularity),
            "faz_equivalent_diameter_mm": float(equivalent_diameter_mm),
            "faz_center_y_mm": float(center_y_mm),
            "faz_center_x_mm": float(center_x_mm),
            "faz_major_axis_mm": float(major_axis_mm),
            "faz_minor_axis_mm": float(minor_axis_mm),
            "faz_eccentricity": float(eccentricity),
            "faz_solidity": float(solidity),
            "faz_aspect_ratio": (
                float(major_axis_mm / minor_axis_mm) if minor_axis_mm > 1e-10 else 0.0
            ),
            "segmentation_method": self.method,
        }

        return True, metrics

    def _empty_metrics(self) -> Dict:
        """Return empty metrics dictionary"""
        return {
            "faz_area_mm2": 0.0,
            "faz_perimeter_mm": 0.0,
            "faz_circularity": 0.0,
            "faz_equivalent_diameter_mm": 0.0,
            "faz_center_y_mm": 0.0,
            "faz_center_x_mm": 0.0,
            "faz_major_axis_mm": 0.0,
            "faz_minor_axis_mm": 0.0,
            "faz_eccentricity": 0.0,
            "faz_solidity": 0.0,
            "faz_aspect_ratio": 0.0,
            "segmentation_method": self.method,
        }


class FAZVisualization:
    """
    FAZ visualization utilities

    Provides methods to visualize FAZ segmentation results
    """

    @staticmethod
    def overlay_faz(
        image: np.ndarray,
        faz_mask: np.ndarray,
        alpha: float = 0.5,
        color: Tuple[int, int, int] = (255, 0, 0),
    ) -> np.ndarray:
        """
        Overlay FAZ mask on image

        Args:
            image: Grayscale or RGB image
            faz_mask: FAZ mask (bool)
            alpha: Transparency (0-1)
            color: RGB color tuple

        Returns:
            overlaid: RGB image with FAZ overlay
        """
        # Convert to RGB if grayscale
        if image.ndim == 2:
            rgb_image = np.stack([image] * 3, axis=-1)
        else:
            rgb_image = image.copy()

        # Normalize to 0-255 if needed
        if rgb_image.max() <= 1.0:
            rgb_image = (rgb_image * 255).astype(np.uint8)

        # Create colored overlay
        overlay = rgb_image.copy()
        overlay[faz_mask] = color

        # Blend
        result = ((1 - alpha) * rgb_image + alpha * overlay).astype(np.uint8)

        return result

    @staticmethod
    def draw_faz_contour(
        image: np.ndarray,
        faz_mask: np.ndarray,
        color: Tuple[int, int, int] = (0, 255, 0),
        thickness: int = 2,
    ) -> np.ndarray:
        """
        Draw FAZ contour on image

        Args:
            image: Grayscale or RGB image
            faz_mask: FAZ mask (bool)
            color: RGB color tuple
            thickness: Line thickness

        Returns:
            result: Image with FAZ contour
        """
        # Convert to RGB if needed
        if image.ndim == 2:
            result = np.stack([image] * 3, axis=-1)
        else:
            result = image.copy()

        # Normalize
        if result.max() <= 1.0:
            result = (result * 255).astype(np.uint8)

        # Find contours
        contours = measure.find_contours(faz_mask.astype(float), 0.5)

        # Draw contours
        for contour in contours:
            # Convert to integer coordinates
            coords = contour.astype(int)
            for i in range(len(coords) - 1):
                y1, x1 = coords[i]
                y2, x2 = coords[i + 1]
                # Simple line drawing
                if 0 <= y1 < result.shape[0] and 0 <= x1 < result.shape[1]:
                    result[y1, x1] = color

        return result

    @staticmethod
    def create_comparison_view(
        image: np.ndarray,
        faz_masks: Dict[str, np.ndarray],
        titles: Optional[List[str]] = None,
    ) -> np.ndarray:
        """
        Create comparison view of multiple FAZ segmentations

        Args:
            image: Original image
            faz_masks: Dictionary of {method_name: mask}
            titles: Optional list of titles

        Returns:
            comparison: Grid of images
        """
        n_methods = len(faz_masks)

        if n_methods == 0:
            return image

        # Create grid
        results = []
        for method_name, mask in faz_masks.items():
            overlay = FAZVisualization.overlay_faz(image, mask)
            results.append(overlay)

        # Stack horizontally
        comparison = np.concatenate(results, axis=1)

        return comparison
