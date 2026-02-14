"""
ROI auto-refinement adapted from macro's ROI_modify / ROI_semiauto_improved.
"""

import numpy as np
from shapely.geometry import Polygon
from skimage.draw import polygon2mask
from scipy.ndimage import gaussian_filter


def refine_roi_by_intensity(
    img, polygon_coords, iterations=5, search_radius=3, angle_threshold=0.5
):
    h, w = img.shape[:2]
    pts = np.array(polygon_coords, dtype=float)
    if len(pts) < 3:
        return polygon_coords
    for it in range(iterations):
        centroid = pts.mean(axis=0)
        new_pts = pts.copy()
        for i, (x, y) in enumerate(pts):
            x0 = int(round(x))
            y0 = int(round(y))
            if not (0 <= x0 < w and 0 <= y0 < h):
                continue
            best_val = img[y0, x0]
            best_pos = (x0, y0)
            dir_vec = np.array([x - centroid[0], y - centroid[1]])
            nrm = np.hypot(dir_vec[0], dir_vec[1])
            if nrm != 0:
                dir_vec = dir_vec / nrm
            else:
                dir_vec = np.array([1.0, 0.0])
            for dx in range(-search_radius, search_radius + 1):
                nx = x0 + dx
                if nx < 0 or nx >= w:
                    continue
                for dy in range(-search_radius, search_radius + 1):
                    ny = y0 + dy
                    if ny < 0 or ny >= h:
                        continue
                    cand_vec = np.array([nx - centroid[0], ny - centroid[1]])
                    cand_n = np.hypot(cand_vec[0], cand_vec[1])
                    if cand_n == 0:
                        continue
                    cand_vec = cand_vec / cand_n
                    dot = np.clip(np.dot(dir_vec, cand_vec), -1.0, 1.0)
                    angle = np.arccos(dot)
                    if abs(angle) > angle_threshold:
                        continue
                    val = img[ny, nx]
                    if val < best_val:
                        best_val = val
                        best_pos = (nx, ny)
            new_pts[i, 0] = best_pos[0]
            new_pts[i, 1] = best_pos[1]
        pts = (
            np.roll(new_pts, 1, axis=0) + new_pts + np.roll(new_pts, -1, axis=0)
        ) / 3.0
    return [(float(x), float(y)) for x, y in pts.tolist()]


def polygon_to_mask_coords(polygon_coords, shape):
    from skimage.draw import polygon2mask

    return polygon2mask(shape, polygon_coords)


def select_roi_interactive(image, title="Select ROI - close window when done"):
    """
    Show image and let user draw a polygon ROI interactively with matplotlib.
    Returns list of (x,y) coords (float) or None if cancelled.
    Requires matplotlib.
    """
    import matplotlib.pyplot as plt
    from matplotlib.widgets import PolygonSelector

    fig, ax = plt.subplots(figsize=(8, 8))
    if image.ndim == 3 and image.shape[2] == 3:
        ax.imshow(image)
    else:
        ax.imshow(image, cmap="gray")
    ax.set_title(title)
    coords = []

    def onselect(verts):
        nonlocal coords
        coords = verts
        # draw polygon
        ax.plot(
            [v[0] for v in verts + [verts[0]]], [v[1] for v in verts + [verts[0]]], "-r"
        )
        fig.canvas.draw_idle()

    _ = PolygonSelector(ax, onselect, useblit=True)
    plt.show()  # blocks until window closed

    if len(coords) == 0:
        return None
    # return as list of (x,y)
    return [(float(x), float(y)) for x, y in coords]
