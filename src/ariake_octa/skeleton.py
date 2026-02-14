import numpy as np
from scipy.ndimage import distance_transform_edt
from skimage.morphology import skeletonize

try:
    import sknw
    import networkx as nx

    _SKNW_AVAILABLE = True
except Exception:
    _SKNW_AVAILABLE = False


def compute_skeleton_metrics(binary_mask, pixel_size_um=1.0):
    """
    Basic skeleton metrics: mean/std/max diameter on skeleton points.
    """
    bw = binary_mask > 0
    sk = skeletonize(bw).astype("uint8")
    dist = distance_transform_edt(bw)
    sk_points = sk.astype(bool)
    if sk_points.sum() == 0:
        return {"skeleton_mean_um": 0, "skeleton_std_um": 0, "skeleton_max_um": 0}
    values = dist[sk_points]
    mean = values.mean() * 2 * pixel_size_um
    std = values.std() * 2 * pixel_size_um
    mx = values.max() * 2 * pixel_size_um
    return {"skeleton_mean_um": mean, "skeleton_std_um": std, "skeleton_max_um": mx}


def compute_graph_metrics(binary_mask, pixel_size_um=1.0):
    """
    Build graph from skeleton and compute branches, junctions, endpoints, branch lengths, tortuosity.
    Requires sknw (preferred). Returns dict.
    """
    bw = binary_mask > 0
    sk = skeletonize(bw).astype("uint8")
    if not _SKNW_AVAILABLE:
        # fallback: estimate using simple labeling
        return {
            "n_branches": 0,
            "n_junctions": 0,
            "n_endpoints": 0,
            "total_branch_length_mm": 0.0,
            "tortuosity": 0.0,
            "branch_lengths": [],
        }
    G = sknw.build_sknw(sk, multi=True)
    n_branches = 0
    n_junctions = 0
    n_endpoints = 0
    total_branch_len_px = 0.0
    sumWeightedTortuosity = 0.0
    branch_count_for_tortuosity = 0
    branch_lengths = []
    for u, v, key in G.edges(keys=True):
        edge = G[u][v][key]
        pts = edge.get("pts", None)
        if pts is None:
            continue
        n_branches += 1
        # length in pixels (sum of distances between points)
        pts_arr = np.asarray(pts)
        if pts_arr.shape[0] < 2:
            continue
        diffs = np.diff(pts_arr, axis=0)
        seglens = np.sqrt((diffs**2).sum(axis=1))
        length_px = seglens.sum()
        total_branch_len_px += length_px
        branch_lengths.append(length_px * pixel_size_um / 1000.0)  # mm approx
        # euclidean dist between endpoints
        euclid = np.linalg.norm(pts_arr[0] - pts_arr[-1])
        if euclid > 0:
            t = length_px / euclid
            if not np.isnan(t) and 1.0 <= t < 10.0:
                sumWeightedTortuosity += length_px * t
                branch_count_for_tortuosity += length_px
    for n, data in G.nodes(data=True):
        degree = data.get("degree", G.degree(n))
        if degree >= 3:
            n_junctions += 1
        elif degree == 1:
            n_endpoints += 1
    total_branch_length_mm = total_branch_len_px * pixel_size_um / 1000.0
    tortuosity = (
        (sumWeightedTortuosity / branch_count_for_tortuosity)
        if branch_count_for_tortuosity > 0
        else 0.0
    )
    return {
        "n_branches": n_branches,
        "n_junctions": n_junctions,
        "n_endpoints": n_endpoints,
        "total_branch_length_mm": total_branch_length_mm,
        "tortuosity": tortuosity,
        "branch_lengths": branch_lengths,
    }
