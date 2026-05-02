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
import logging

logger = logging.getLogger(__name__)

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
        self, image: np.ndarray, vessel_mask: np.ndarray, mm_per_pixel: float = 1.0, layer_type: str = "DCP"
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
        layer_type : str
            Layer type ("SCP", "DCP", or "INTEGRATED")
        """
        print(f"\n!!! ImprovedFAZDetector: detect() started [{layer_type}]. mm_per_pixel={mm_per_pixel:.6f}")
        logger.info("ImprovedFAZDetector: detect() called [%s]. mm_per_pixel=%.6f", layer_type, mm_per_pixel)
        # Adaptive preprocessing
        processed = self._adaptive_preprocessing(image, vessel_mask)

        # Multi-candidate detection
        candidates = self._detect_candidates(processed, vessel_mask, mm_per_pixel, layer_type)

        # Score and select best candidate
        best_mask = self._score_and_select(candidates, processed, vessel_mask, mm_per_pixel)

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
        self, processed: np.ndarray, vessel_mask: np.ndarray, mm_per_pixel: float, layer_type: str = "DCP"
    ) -> list:
        """Detect multiple FAZ candidates using different methods."""
        candidates = [] # list of (mask, method_name) tuples
        avascular = ~vessel_mask
        center_y, center_x = avascular.shape[0] // 2, avascular.shape[1] // 2
        distance = ndimage.distance_transform_edt(avascular)

        # --- Define stable seed coordinates for all methods ---
        max_dist_px = int(1.0 / mm_per_pixel) if mm_per_pixel > 0 else avascular.shape[0] // 3
        y, x = np.ogrid[:avascular.shape[0], :avascular.shape[1]]
        dist_to_center = np.sqrt((x - center_x)**2 + (y - center_y)**2)
        center_region = dist_to_center < max_dist_px
        masked_dist = distance.copy()
        masked_dist[~center_region] = 0
        if np.any(masked_dist > 0):
            seed_y, seed_x = np.unravel_index(np.argmax(masked_dist), masked_dist.shape)
            seed_y, seed_x = int(seed_y), int(seed_x)
        else:
            seed_y, seed_x = center_y, center_x

        # --- Method 1: Region Growing [NEW] ---
        # Grows from center until hits a vessel wall
        try:
            li_thresh = filters.threshold_li(processed)
            walls = processed > li_thresh
            if layer_type in ["SCP", "INTEGRATED"]:
                walls = morphology.binary_dilation(walls, morphology.disk(2))
            
            # Simple region grow
            seed_mask = np.zeros_like(avascular, dtype=bool)
            seed_mask[seed_y, seed_x] = True
            grown = seed_mask.copy()
            # Grow up to 1.5mm radius
            for _ in range(int(1.5 / mm_per_pixel)):
                next_grown = morphology.binary_dilation(grown) & (~walls)
                if np.array_equal(next_grown, grown): break
                grown = next_grown
            candidates.append((grown, "Region Growing"))
        except Exception:
            pass

        # Method 2: Distance transform based
        try:
            thresh_dist = filters.threshold_otsu(distance)
            dist_mask = distance > thresh_dist
            candidates.append((dist_mask, "Distance Transform"))
        except Exception:
            pass

        # Method 3: Adaptive Watershed
        try:
            if np.any(avascular):
                markers = np.zeros_like(avascular, dtype=int)
                markers[seed_y, seed_x] = 1
                markers[vessel_mask] = 2
                markers[0, :] = 2; markers[-1, :] = 2; markers[:, 0] = 2; markers[:, -1] = 2
                labels = segmentation.watershed(processed, markers, mask=avascular)
                candidates.append(((labels == 1), "Adaptive Watershed"))
        except Exception:
            pass
            

        # --- Method 5: Radial-Spline with Li and Noise Filter [IMPROVED] ---
        try:
            from scipy.interpolate import splprep, splev
            
            # Use layer-specific thresholding
            if layer_type in ["SCP", "INTEGRATED"]:
                # For SCP, the FAZ should be smaller/tighter. Increase sensitivity to catch inward boundaries.
                li_thresh = filters.threshold_li(processed)
                # Lower threshold to catch even faint inward vessel ends
                clean_vessels = processed > (li_thresh * 0.7) 
                # Dilate vessels to ensure rays hit the innermost boundary
                clean_vessels = morphology.binary_dilation(clean_vessels, morphology.disk(2))
                start_r = int(0.02 / mm_per_pixel) if mm_per_pixel > 0 else 2 
            else:
                # For DCP (KEEP CURRENT PERFECT LOGIC)
                li_thresh = filters.threshold_li(processed)
                clean_vessels = processed > li_thresh
                clean_vessels = morphology.binary_dilation(clean_vessels, morphology.disk(1))
                start_r = int(0.05 / mm_per_pixel) if mm_per_pixel > 0 else 5
            
            num_rays = 120
            angles = np.linspace(0, 2*np.pi, num_rays, endpoint=False)
            max_r_px = int(1.5 / mm_per_pixel) if mm_per_pixel > 0 else 150
            
            points = []
            distances = []
            for ang in angles:
                dx, dy = np.cos(ang), np.sin(ang)
                found = False
                for r in range(start_r, max_r_px):
                    px, py = int(seed_x + r * dx), int(seed_y + r * dy)
                    if px < 0 or px >= avascular.shape[1] or py < 0 or py >= avascular.shape[0]:
                        break
                    if clean_vessels[py, px]:
                        distances.append(r)
                        found = True
                        break
                if not found:
                    distances.append(np.nan)
            
            # Radial Outlier Filter: Use median filter to remove noise-induced inward jumps
            dist_arr = np.array(distances)
            # Fill NaNs by interpolation
            nan_mask = np.isnan(dist_arr)
            if np.all(nan_mask): raise ValueError("No vessel hits")
            
            indices = np.arange(num_rays)
            dist_arr[nan_mask] = np.interp(indices[nan_mask], indices[~nan_mask], dist_arr[~nan_mask], period=num_rays)
            
            # Apply median filter to radial distances to remove jaggedness from noise
            from scipy.signal import medfilt
            dist_filtered = medfilt(dist_arr, kernel_size=15) # Smooth jumps
            
            pts = []
            for i, ang in enumerate(angles):
                pts.append((seed_y + dist_filtered[i] * np.sin(ang), seed_x + dist_filtered[i] * np.cos(ang)))
            pts = np.array(pts)
            
            # Spline fit
            _, idx = np.unique(pts, axis=0, return_index=True)
            pts = pts[np.sort(idx)]
            if len(pts) >= 5:
                smoothing = len(pts) * 3.0 # Stronger smoothing
                tck, u = splprep([pts[:, 1], pts[:, 0]], s=smoothing, per=True)
                unew = np.linspace(0, 1, 200)
                out = splev(unew, tck)
                poly_pts = np.array(out).T.astype(np.int32)
                radial_mask = np.zeros_like(avascular, dtype=np.uint8)
                if HAS_CV2:
                    cv2.fillPoly(radial_mask, [poly_pts], 1)
                else:
                    from skimage.draw import polygon
                    rr, cc = polygon(poly_pts[:, 1], poly_pts[:, 0], avascular.shape)
                    radial_mask[rr, cc] = 1
                candidates.append(((radial_mask > 0) & avascular, "Radial-Spline"))
        except Exception as e:
            logger.warning(f"Radial-Spline failed: {e}")

        return candidates

    def _score_and_select(
        self, candidates: list, processed: np.ndarray, vessel_mask: np.ndarray, mm_per_pixel: float
    ) -> np.ndarray:
        """Score candidates and select the best one."""
        best_score = -1e9
        best_mask = np.zeros_like(vessel_mask)

        print("-" * 50)
        print(" FAZ Candidate Scoring Detail")
        print("-" * 50)
        for i, (candidate, method_name) in enumerate(candidates):
            if not np.any(candidate):
                print(f"[{i+1}] {method_name:25s}: Empty mask")
                continue

            score, details = self._score_candidate_with_details(candidate, processed, vessel_mask, mm_per_pixel)
            
            print(f"[{i+1}] {method_name:25s}: Total={score:6.3f} | Area={details['area_mm2']:4.2f}mm2 | Circ={details['circ']:4.2f} | Cent={details['cent']:4.2f}")
            
            if score > best_score:
                best_score = score
                best_mask = candidate
        print("-" * 50)

        return best_mask

    def _score_candidate_with_details(
        self, mask: np.ndarray, processed: np.ndarray, vessel_mask: np.ndarray, mm_per_pixel: float
    ) -> Tuple[float, Dict]:
        """Score a candidate FAZ mask and return component details."""
        if not np.any(mask):
            return -1.0, {"area_mm2": 0.0, "circ": 0.0, "cent": 0.0}

        area_px = np.sum(mask)
        area_mm2 = area_px * (mm_per_pixel ** 2) if mm_per_pixel > 0 else area_px / 10000.0

        if area_mm2 > 3.0:
            return -10.0, {"area_mm2": area_mm2, "circ": 0.0, "cent": 0.0}
        elif area_mm2 < 0.01:
            return -1.0, {"area_mm2": area_mm2, "circ": 0.0, "cent": 0.0}
            
        if area_mm2 <= 0.4:
            size_score = area_mm2 / 0.4
        else:
            size_score = max(0.0, 1.0 - (area_mm2 - 0.4) / 2.6)

        # Circularity
        regions = measure.regionprops(measure.label(mask))
        if regions:
            region = max(regions, key=lambda r: r.area)
            perimeter = region.perimeter
            circularity = (4 * np.pi * region.area / (perimeter**2)) if perimeter > 0 else 0.0
        else:
            circularity = 0.0
        circ_score = circularity

        # Centrality
        centroid = ndimage.center_of_mass(mask)
        center_y, center_x = mask.shape[0] / 2, mask.shape[1] / 2
        dist_px = np.sqrt((centroid[0] - center_y) ** 2 + (centroid[1] - center_x) ** 2)
        dist_mm = dist_px * mm_per_pixel if mm_per_pixel > 0 else dist_px / (mask.shape[0] / 3.0)
        
        if dist_mm > 1.8:
            return -5.0, {"area_mm2": area_mm2, "circ": circ_score, "cent": 0.0}
        centrality_score = max(0.0, 1.0 - (dist_mm / 1.5))

        # Intensity homogeneity
        intensities = processed[mask]
        homogeneity_score = 1 / (1 + np.std(intensities)) if np.any(mask) else 0.0

        total_score = (
            size_score * 0.40
            + circ_score * 0.20
            + centrality_score * 0.30
            + homogeneity_score * 0.10
        )
        
        details = {
            "area_mm2": area_mm2,
            "circ": circ_score,
            "cent": centrality_score
        }

        return total_score, details

    def _score_candidate(
        self, mask: np.ndarray, processed: np.ndarray, vessel_mask: np.ndarray, mm_per_pixel: float
    ) -> float:
        """Legacy wrapper for _score_candidate_with_details."""
        score, _ = self._score_candidate_with_details(mask, processed, vessel_mask, mm_per_pixel)
        return score

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
            print(f"!!! ImprovedFAZDetector: Validation Failed: Area={area_mm2:.4f} (min={self.min_area_mm2}), Circ={circularity:.4f} (min={self.min_circularity})")
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
