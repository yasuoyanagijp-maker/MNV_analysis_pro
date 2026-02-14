from shapely.geometry import Polygon
from skimage import measure
from skimage.draw import polygon2mask



def polygon_to_mask(poly_coords, shape):
    poly = Polygon(poly_coords)
    mask = polygon2mask(shape, poly.exterior.coords)
    return mask


def flow_deficit_analysis(
    fd_img, roi_coords, pixel_size_um, num_rings=3, enlarge_step_mm=0.2
):
    """
    fd_img: 2D array (uint8) - binary image where vessels=1, background=0 or inverted.
    roi_coords: list of (x,y) coordinates (pixel coords) for MNV ROI (freehand polygon)
    pixel_size_um: µm per pixel
    returns dict with FD_percent_R1..R3, FD_average_area_R*, FD_number_R* etc.
    """
    h, w = fd_img.shape
    shape = (h, w)
    results = {}
    # base polygon
    poly = Polygon(roi_coords)
    if not poly.is_valid or poly.area == 0:
        # default zeros
        for r in range(1, num_rings + 1):
            results[f"FD_percent_R{r}"] = 0
            results[f"FD_avg_area_R{r}"] = 0
            results[f"FD_number_R{r}"] = 0
            results[f"FD_density_R{r}"] = 0
        return results
    # pixel buffer per ring in pixels
    pixels_per_mm = 1000.0 / pixel_size_um
    step_px = enlarge_step_mm * pixels_per_mm
    # create rings
    ring_polys = []
    for ring in range(1, num_rings + 1):
        buff = ring * step_px
        outer = poly.buffer(buff)
        inner = poly.buffer((ring - 1) * step_px)
        ring_poly = outer.difference(inner)
        ring_polys.append(ring_poly)
    # fd mask: treat zero pixels as FD (holes); create boolean array where FD=True
    if fd_img.dtype != bool:
        fd_bool = fd_img == 0
    else:
        fd_bool = fd_img
    for idx, ring_poly in enumerate(ring_polys):
        if ring_poly.is_empty:
            results[f"FD_percent_R{idx+1}"] = 0
            results[f"FD_avg_area_R{idx+1}"] = 0
            results[f"FD_number_R{idx+1}"] = 0
            results[f"FD_density_R{idx+1}"] = 0
            continue
        mask = polygon2mask(shape, ring_poly.exterior.coords)
        mask = mask.astype(bool)
        # count fd pixels inside mask
        fd_region = fd_bool & mask
        total_pixels = mask.sum()
        fd_pixels = fd_region.sum()
        # label connected components of FD region for particle stats
        if fd_pixels == 0 or total_pixels == 0:
            results[f"FD_percent_R{idx+1}"] = 0
            results[f"FD_avg_area_R{idx+1}"] = 0
            results[f"FD_number_R{idx+1}"] = 0
            results[f"FD_density_R{idx+1}"] = 0
            continue
        lbl = measure.label(fd_region)
        props = measure.regionprops(lbl)
        n_particles = len(props)
        pixel_area_mm2 = (pixel_size_um / 1000.0) ** 2
        total_fd_area_um2 = sum([p.area * (pixel_size_um**2) for p in props])
        if total_pixels > 0:
            roi_area_mm2 = total_pixels * pixel_area_mm2
            fd_percent = (total_fd_area_um2 / (roi_area_mm2 * 1e6)) * 100.0
        else:
            fd_percent = 0
        avg_area = (total_fd_area_um2 / n_particles) if n_particles > 0 else 0
        density = n_particles / (roi_area_mm2) if roi_area_mm2 > 0 else 0
        results[f"FD_percent_R{idx+1}"] = fd_percent
        results[f"FD_avg_area_R{idx+1}"] = avg_area
        results[f"FD_number_R{idx+1}"] = n_particles
        results[f"FD_density_R{idx+1}"] = density
    return results
