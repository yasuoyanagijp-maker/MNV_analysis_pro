from math import atan2, degrees, floor, sqrt

import numpy as np
from skimage.draw import polygon2mask


def calculate_angular_cv(sector_counts):
    sectors = len(sector_counts)
    nonzero = [c for c in sector_counts if c > 0]
    nonZeroSectors = len(nonzero)
    minSectors = 3 if sectors >= 8 else 2
    if nonZeroSectors < minSectors:
        return -1
    meanCount = sum(nonzero) / nonZeroSectors
    variance = sum([(c - meanCount) ** 2 for c in nonzero]) / nonZeroSectors
    stdDev = sqrt(variance)
    cv = stdDev / meanCount if meanCount > 0 else -1
    if cv > 2.0:
        cv = 2.0
    return cv


def calculate_radial_uniformity(sector_counts):
    sectors = len(sector_counts)
    occupied = sum(1 for c in sector_counts if c > 0)
    if occupied < 3:
        return 0.0
    uniformity = occupied / sectors
    nonzero = [c for c in sector_counts if c > 0]
    meanCount = sum(nonzero) / len(nonzero)
    variance = sum([(c - meanCount) ** 2 for c in nonzero]) / len(nonzero)
    stdDev = sqrt(variance)
    cv = stdDev / meanCount if meanCount > 0 else 1.0
    if cv < 0.5:
        distributionUniformity = 1.0
    elif cv < 1.0:
        distributionUniformity = 0.7
    else:
        distributionUniformity = 0.4
    return uniformity * distributionUniformity


def analyze_spatial_distribution(
    distance_map, roi_coords, mm_per_pixel, num_sectors=8, num_radial_bins=10
):
    """
    distance_map: 2D array (distance transform)
    roi_coords: polygon coords list [(x,y),...]
    mm_per_pixel: mm per pixel
    Returns dict with trunk eccentricity, angular CV, radial profile, diameter_center/periphery etc.
    """
    h, w = distance_map.shape
    mask = polygon2mask((h, w), roi_coords)
    # get bounding box center
    xs = [p[0] for p in roi_coords]
    ys = [p[1] for p in roi_coords]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    centerX = (minx + maxx) / 2.0
    centerY = (miny + maxy) / 2.0
    # estimated radius in pixels
    roi_pixels = mask.sum()
    import math

    estimatedRadius = math.sqrt(roi_pixels / math.pi) if roi_pixels > 0 else 0
    centerRadius = estimatedRadius / 3.0
    # extract trunk pixels from distance_map thresholded (thick vessels)
    thick_mask = distance_map > 0  # caller may supply a thick map
    # get trunk pixel coordinates
    ys_idx, xs_idx = np.nonzero(thick_mask)
    nPixels = len(xs_idx)
    if nPixels == 0:
        return {
            "trunk_eccentricity": -1,
            "angular_distribution_cv": -1,
            "radial_profile": [],
        }
    trunkCenterX = xs_idx.mean()
    trunkCenterY = ys_idx.mean()
    eccentricityDistance = sqrt(
        (trunkCenterX - centerX) ** 2 + (trunkCenterY - centerY) ** 2
    )
    trunk_ecc = eccentricityDistance / (estimatedRadius if estimatedRadius > 0 else 1)
    if trunk_ecc > 1.0:
        trunk_ecc = 1.0
    # angular sectors
    sectors = num_sectors
    sectorCounts = [0] * sectors
    for x, y in zip(xs_idx, ys_idx):
        dx = x - centerX
        dy = y - centerY
        angle = atan2(dy, dx)
        a_deg = degrees(angle)
        if a_deg < 0:
            a_deg += 360
        sectorIdx = int(floor(a_deg / (360.0 / sectors)))
        if sectorIdx >= sectors:
            sectorIdx = sectors - 1
        sectorCounts[sectorIdx] += 1
    angular_cv = calculate_angular_cv(sectorCounts)
    radialMeans = []
    maxR = estimatedRadius
    if maxR <= 0:
        radialMeans = [0] * num_radial_bins
    else:
        binWidth = maxR / num_radial_bins
        for b in range(num_radial_bins):
            innerR = b * binWidth
            outerR = (b + 1) * binWidth
            # approximate by distance thresholds
            region_mask = (mask) & (distance_map >= innerR) & (distance_map < outerR)
            if region_mask.sum() > 0:
                mean = (
                    distance_map[region_mask].mean()
                    * 2
                    * mm_per_pixel
                    * 1000.0
                    / 1000.0
                )  # keep µm units approx
            else:
                mean = 0.0
            radialMeans.append(mean)
    radial_uniformity = calculate_radial_uniformity(sectorCounts)
    return {
        "trunk_eccentricity": trunk_ecc,
        "angular_distribution_cv": angular_cv,
        "radial_profile": radialMeans,
        "radial_uniformity": radial_uniformity,
        "estimated_radius_px": estimatedRadius,
    }
