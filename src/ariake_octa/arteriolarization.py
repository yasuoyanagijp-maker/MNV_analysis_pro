"""
Arteriolarization / high-skewness segment analysis (approximate port).
"""

import numpy as np
from scipy.ndimage import binary_dilation
from skimage.measure import label, regionprops
from skimage.morphology import skeletonize


def analyze_arteriolarization(
    distance_map,
    skeleton_mask,
    roi_mask=None,
    mm_per_pixel=0.001,
    min_pixels_required=50,
):
    out = {}
    sk = skeleton_mask.astype(bool)
    if roi_mask is not None:
        sk = sk & (roi_mask.astype(bool))
    vals = distance_map[sk]
    if vals.size < 10:
        out["arteriolarization_segment_count"] = 0
        out["arteriolarization_total_length"] = 0.0
        out["arteriolarization_max_segment_length"] = 0.0
        out["arteriolarization_density"] = 0.0
        out["localized_diameter_variation"] = 0.0
        out["HighSkew_threshold"] = 0.0
        return out
    mean = float(vals.mean())
    std = float(vals.std())
    mx = float(vals.max())
    if std == 0.0:
        bins = np.floor(vals).astype(int)
        if bins.size > 0:
            mode = int(np.bincount(bins).argmax())
        else:
            mode = 0
        skew_threshold = mode + 1
    elif (std > 0 and std < 0.5) or (
        (mx - vals.min()) / (mean if mean > 0 else 1) < 0.5
    ):
        mode = int(np.bincount(np.floor(vals).astype(int)).argmax())
        skew_threshold = mode + 1
    else:
        skew_threshold = mean + 2.0 * std
    highskew = (distance_map - skew_threshold) > 0
    highskew_on_skeleton = highskew & skeleton_mask.astype(bool)
    radius_px = max(1, int(round(mean)))
    dilated = binary_dilation(
        highskew_on_skeleton, structure=np.ones((3, 3)), iterations=radius_px
    )
    skeletonized_highskew = skeletonize(dilated.astype(bool)).astype(np.uint8)
    labeled = label(skeletonized_highskew)
    props = regionprops(labeled)
    segment_count = len(props)
    total_length_px = sum([p.area for p in props]) if props else 0
    max_length_px = max([p.area for p in props]) if props else 0
    total_length_mm = total_length_px * mm_per_pixel
    max_length_mm = max_length_px * mm_per_pixel
    if roi_mask is not None:
        area_mm2 = roi_mask.sum() * (mm_per_pixel**2)
        density = segment_count / area_mm2 if area_mm2 > 0 else 0.0
    else:
        density = 0.0
    comp_lbl = label(dilated.astype(np.uint8))
    comp_props = regionprops(comp_lbl)
    lens = [p.equivalent_diameter for p in comp_props] if comp_props else [0]
    localized_cv = (
        (np.std(lens) / np.mean(lens)) * 100.0
        if len(lens) > 1 and np.mean(lens) > 0
        else 0.0
    )
    out.update(
        {
            "arteriolarization_segment_count": int(segment_count),
            "arteriolarization_total_length": float(total_length_mm),
            "arteriolarization_max_segment_length": float(max_length_mm),
            "arteriolarization_density": float(density),
            "localized_diameter_variation": float(localized_cv),
            "HighSkew_threshold": float(skew_threshold),
        }
    )
    return out
