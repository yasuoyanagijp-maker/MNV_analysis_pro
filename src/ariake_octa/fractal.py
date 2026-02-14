from math import log

from skimage import img_as_bool


def box_counting_fd(binary):
    """
    Compute fractal dimension by box-counting for a binary skeleton image.
    Returns FD (slope). If insufficient data, returns 0.
    """
    bw = img_as_bool(binary)
    h, w = bw.shape
    max_dim = max(w, h)
    min_box = 2
    # choose max_box as power of two <= max_dim/4
    max_box = 1
    while max_box * 2 <= max_dim // 4:
        max_box *= 2
    if max_box < min_box:
        max_box = min_box
    box_sizes = []
    box_counts = []
    box = min_box
    while box <= max_box:
        count = 0
        for y in range(0, h, box):
            for x in range(0, w, box):
                y2 = min(h, y + box)
                x2 = min(w, x + box)
                if bw[y:y2, x:x2].any():
                    count += 1
        if count > 0:
            box_sizes.append(box)
            box_counts.append(count)
        box *= 2
    if len(box_sizes) < 3:
        return 0.0
    n = len(box_sizes)
    sumLogS = sum([log(1.0 / bs) for bs in box_sizes])
    sumLogN = sum([log(nc) for nc in box_counts])
    sumLogSLogN = sum(
        [log(1.0 / bs) * log(nc) for bs, nc in zip(box_sizes, box_counts)]
    )
    sumLogS2 = sum([log(1.0 / bs) ** 2 for bs in box_sizes])
    denom = n * sumLogS2 - sumLogS * sumLogS
    if abs(denom) < 1e-12:
        return 0.0
    slope = (n * sumLogSLogN - sumLogS * sumLogN) / denom
    # sanity check
    if slope < 0.5 or slope > 2.5:
        return 0.0
    return slope
