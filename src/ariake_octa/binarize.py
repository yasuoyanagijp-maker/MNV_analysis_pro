import numpy as np
from scipy.ndimage import uniform_filter
from skimage.morphology import remove_small_holes, remove_small_objects



def adaptive_binarize_phansalkar(img, radius=15, k=0.1, R=128, p=2, q=10):
    # approximate Phansalkar using local mean and std
    imgf = img.astype("float32")
    size = 2 * radius + 1
    mean = uniform_filter(imgf, size)
    mean_sq = uniform_filter(imgf * imgf, size)
    variance = mean_sq - mean * mean
    std = np.sqrt(np.maximum(variance, 0))
    # Phansalkar formula approximation
    Rval = R if R > 0 else 128
    thresh = mean * (1 + p * np.exp(-q * mean / 255.0) + k * ((std / Rval) - 1))
    mask = imgf > thresh
    return mask.astype("uint8") * 255


from skimage.morphology import remove_small_holes, remove_small_objects


def remove_small_particles(mask, min_size=64, connectivity=1):
    """
    Remove small connected components from binary mask.
    mask: 2D numpy array (uint8 or bool) where foreground=255 or True
    min_size: minimum area in pixels to keep
    returns: cleaned mask (uint8 0/255)
    """
    bw = mask > 0
    # remove small objects
    cleaned = remove_small_objects(bw, min_size=min_size, connectivity=connectivity)
    # optionally remove small holes (fill small holes)
    cleaned = remove_small_holes(cleaned, area_threshold=min_size)
    return cleaned.astype("uint8") * 255
