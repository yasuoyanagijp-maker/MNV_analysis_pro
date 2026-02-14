"""
Utility helper functions: scale conversions, polygon buffer, image helpers.
"""

from shapely.geometry import Polygon
from skimage.draw import polygon2mask


def mm_per_pixel_from_scale(image_width_px, scale_mm):
    if image_width_px <= 0:
        return 0.0
    return float(scale_mm) / float(image_width_px)


def polygon_buffer_mm(polygon_coords, buffer_mm, mm_per_pixel):
    if mm_per_pixel <= 0:
        return polygon_coords
    buf_px = buffer_mm / mm_per_pixel
    poly = Polygon(polygon_coords)
    if poly.is_empty:
        return polygon_coords
    buffered = poly.buffer(buf_px)
    if buffered.is_empty:
        return polygon_coords
    return list(buffered.exterior.coords)


def polygon_mask(coords, shape):
    return polygon2mask(shape, coords)
