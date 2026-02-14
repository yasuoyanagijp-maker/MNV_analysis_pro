import numpy as np
from scipy.ndimage import gaussian_laplace
from skimage.filters import meijering, sato



def laplacian_of_gaussian(img, sigma=1.0, rescale=True):
    """
    LoG (Laplacian of Gaussian) similar to ImageJ FeatureJ Laplacian.
    img: 2D numpy array (uint8/float)
    sigma: smoothing sigma in pixels
    returns: uint8 image (vessels enhanced bright)
    """
    imgf = img.astype("float32") / 255.0
    # gaussian_laplace returns negative for bright-on-dark blobs; take -result
    log = -gaussian_laplace(imgf, sigma=sigma)
    if rescale:
        log = (log - log.min()) / (log.max() - log.min() + 1e-12)
        log = (log * 255.0).astype("uint8")
    return (
        log
        if isinstance(log.dtype, np.dtype) and log.dtype == np.uint8
        else log.astype("uint8")
    )


def tubeness_sato(img, sigmas=(1.0, 2.0, 3.0), mode="sato", rescale=True):
    """
    Tubeness implementation approximating ImageJ Tubeness.
    mode: "sato" (skimage.filters.sato) or "meijering" (skimage.filters.meijering)
    sigmas: sequence of scales to evaluate
    returns: uint8 image (vesselness normalized to 0-255)
    """
    imgf = img.astype("float32") / 255.0
    if mode == "sato":
        out = sato(imgf, sigmas=tuple(sigmas))
    else:
        # meijering returns response for tubeness-like detection
        out = meijering(imgf, sigmas=tuple(sigmas))
    if rescale:
        out = (out - out.min()) / (out.max() - out.min() + 1e-12)
        out = (out * 255.0).astype("uint8")
    return out.astype("uint8")
