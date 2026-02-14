"""
FAZ (Foveal Avascular Zone) Segmentation Module

This module provides automatic segmentation of the Foveal Avascular Zone (FAZ)
in OCTA images using traditional image processing techniques.

Based on approaches from:
- macarenadiaz/FAZ_Extraction: Traditional image processing (morphology, edge detection)
- ShellRedia/SAM-OCTA: Deep learning approach (for future enhancement)
- Humogjq/S2Anet: CNN+Transformer approach (for future enhancement)

Current implementation uses morphological operations and region growing.
"""

from typing import Dict, Optional, Tuple

import numpy as np
from skimage import filters, measure, morphology
from skimage.segmentation import active_contour


def detect_faz_region(
    vessel_mask: np.ndarray,
    image: Optional[np.ndarray] = None,
    min_area_px: int = 100,
    max_area_px: Optional[int] = None,
) -> Tuple[np.ndarray, Dict[str, float]]:
    """
    Detect FAZ region from vessel segmentation mask.

    The FAZ is the central avascular zone surrounded by vessels.
    This function finds the largest dark (vessel-free) region near the center.

    Parameters
    ----------
    vessel_mask : np.ndarray
        Binary mask where 1 = vessel, 0 = no vessel
    image : np.ndarray, optional
        Original grayscale image for refinement
    min_area_px : int
        Minimum FAZ area in pixels
    max_area_px : int, optional
        Maximum FAZ area in pixels (default: 1/4 of image area)

    Returns
    -------
    faz_mask : np.ndarray
        Binary mask of detected FAZ region
    metrics : dict
        Dictionary containing FAZ metrics (area, circularity, etc.)
    """
    h, w = vessel_mask.shape
    if max_area_px is None:
        max_area_px = (h * w) // 4

    # Invert vessel mask to find avascular regions
    avascular = ~vessel_mask.astype(bool)

    # Apply morphological closing to fill small gaps
    selem = morphology.disk(3)
    avascular_closed = morphology.closing(avascular, selem)

    # Remove small objects
    # Note: Suppress FutureWarning for scikit-image 0.26+ compatibility
    import warnings

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=FutureWarning)
        avascular_cleaned = morphology.remove_small_objects(
            avascular_closed, min_size=min_area_px
        )

    # Label connected components
    labeled = measure.label(avascular_cleaned)
    regions = measure.regionprops(labeled)

    if len(regions) == 0:
        # No FAZ detected, return empty mask with center coordinates
        # Note: Using (x, y) convention for consistency
        return np.zeros_like(vessel_mask, dtype=bool), {
            "faz_area_px": 0.0,
            "faz_perimeter_px": 0.0,
            "faz_circularity": 0.0,
            "faz_centroid_x": w / 2,  # x = column
            "faz_centroid_y": h / 2,  # y = row
        }

    # Find the region closest to image center within size constraints
    center_x, center_y = w / 2, h / 2
    best_region = None
    best_dist = float("inf")

    for region in regions:
        area = region.area
        if area < min_area_px or area > max_area_px:
            continue

        # Distance from region centroid to image center
        cy, cx = region.centroid
        dist = np.sqrt((cx - center_x) ** 2 + (cy - center_y) ** 2)

        if dist < best_dist:
            best_dist = dist
            best_region = region

    if best_region is None:
        # No suitable region found, use largest region
        best_region = max(regions, key=lambda r: r.area)

    # Create FAZ mask
    faz_mask = (labeled == best_region.label).astype(bool)

    # Calculate metrics
    area = best_region.area
    perimeter = best_region.perimeter

    # Circularity: 4π * area / perimeter^2 (1.0 = perfect circle)
    if perimeter > 0:
        circularity = 4 * np.pi * area / (perimeter**2)
    else:
        circularity = 0.0

    # Get centroid - region.centroid returns (row, col) = (y, x)
    cy, cx = best_region.centroid

    metrics = {
        "faz_area_px": float(area),
        "faz_perimeter_px": float(perimeter),
        "faz_circularity": float(circularity),
        "faz_centroid_x": float(cx),  # x = column
        "faz_centroid_y": float(cy),  # y = row
    }

    return faz_mask, metrics


def refine_faz_boundary(
    faz_mask: np.ndarray,
    image: np.ndarray,
    iterations: int = 100,
    alpha: float = 0.01,
    beta: float = 0.1,
) -> np.ndarray:
    """
    Refine FAZ boundary using active contour (snake) algorithm.

    Parameters
    ----------
    faz_mask : np.ndarray
        Initial FAZ mask
    image : np.ndarray
        Grayscale image for edge detection
    iterations : int
        Number of iterations for active contour
    alpha : float
        Snake length shape parameter
    beta : float
        Snake smoothness shape parameter

    Returns
    -------
    refined_mask : np.ndarray
        Refined FAZ mask
    """
    # Find contour of initial FAZ mask
    contours = measure.find_contours(faz_mask.astype(float), 0.5)

    if len(contours) == 0:
        return faz_mask

    # Use the longest contour
    init_contour = max(contours, key=len)

    # Smooth image for edge detection
    image_smooth = filters.gaussian(image, sigma=2.0)

    # Apply active contour
    try:
        refined_contour = active_contour(
            image_smooth,
            init_contour,
            alpha=alpha,
            beta=beta,
            gamma=0.01,
            max_iterations=iterations,
        )

        # Convert contour back to mask
        from skimage.draw import polygon2mask

        refined_mask = polygon2mask(faz_mask.shape, refined_contour)

        return refined_mask
    except Exception:
        # If active contour fails, return original mask
        return faz_mask


def compute_faz_metrics(
    faz_mask: np.ndarray,
    mm_per_pixel: float = 1.0,
) -> Dict[str, float]:
    """
    Compute comprehensive FAZ metrics.

    Parameters
    ----------
    faz_mask : np.ndarray
        Binary FAZ mask
    mm_per_pixel : float
        Pixel size in millimeters

    Returns
    -------
    metrics : dict
        Dictionary with FAZ metrics in mm units
    """
    if not np.any(faz_mask):
        return {
            "faz_area_mm2": 0.0,
            "faz_perimeter_mm": 0.0,
            "faz_circularity": 0.0,
            "faz_equivalent_diameter_mm": 0.0,
            "faz_acircularity": 1.0,
        }

    # Measure properties
    labeled = measure.label(faz_mask)
    regions = measure.regionprops(labeled)

    if len(regions) == 0:
        return {
            "faz_area_mm2": 0.0,
            "faz_perimeter_mm": 0.0,
            "faz_circularity": 0.0,
            "faz_equivalent_diameter_mm": 0.0,
            "faz_acircularity": 1.0,
        }

    # Use largest region
    region = max(regions, key=lambda r: r.area)

    # Convert to mm units
    area_px = region.area
    perimeter_px = region.perimeter

    area_mm2 = area_px * (mm_per_pixel**2)
    perimeter_mm = perimeter_px * mm_per_pixel

    # Circularity: 4π * area / perimeter^2
    if perimeter_px > 0:
        circularity = 4 * np.pi * area_px / (perimeter_px**2)
    else:
        circularity = 0.0

    # Acircularity (inverse of circularity, used in some papers)
    if circularity > 0:
        acircularity = 1.0 / circularity
    else:
        acircularity = float("inf")

    # Equivalent diameter
    equivalent_diameter_mm = 2 * np.sqrt(area_mm2 / np.pi)

    return {
        "faz_area_mm2": float(area_mm2),
        "faz_perimeter_mm": float(perimeter_mm),
        "faz_circularity": float(circularity),
        "faz_equivalent_diameter_mm": float(equivalent_diameter_mm),
        "faz_acircularity": float(acircularity),
    }


def segment_faz(
    image: np.ndarray,
    vessel_mask: np.ndarray,
    mm_per_pixel: float = 1.0,
    refine: bool = True,
    min_area_px: int = 100,
) -> Tuple[np.ndarray, Dict[str, float]]:
    """
    Complete FAZ segmentation pipeline.

    Parameters
    ----------
    image : np.ndarray
        Original grayscale OCTA image
    vessel_mask : np.ndarray
        Binary vessel segmentation mask
    mm_per_pixel : float
        Pixel size in millimeters
    refine : bool
        Whether to refine boundary with active contour
    min_area_px : int
        Minimum FAZ area in pixels

    Returns
    -------
    faz_mask : np.ndarray
        Binary FAZ mask
    metrics : dict
        Dictionary with FAZ metrics
    """
    # Detect initial FAZ region
    faz_mask, initial_metrics = detect_faz_region(
        vessel_mask, image, min_area_px=min_area_px
    )

    # Refine boundary if requested
    if refine and np.any(faz_mask):
        faz_mask = refine_faz_boundary(faz_mask, image)

    # Compute final metrics
    metrics = compute_faz_metrics(faz_mask, mm_per_pixel)

    # Add centroid information from initial detection
    metrics.update(
        {
            "faz_centroid_x_px": initial_metrics["faz_centroid_x"],
            "faz_centroid_y_px": initial_metrics["faz_centroid_y"],
        }
    )

    return faz_mask, metrics
