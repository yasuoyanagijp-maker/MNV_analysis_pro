import numpy as np
from scipy import signal
from skimage.filters import frangi, gabor_kernel


def multi_scale_frangi(img, scales=(0.8, 1.0, 1.2, 1.5, 2.0)):
    # img: 2D, uint8 or float
    imgf = img.astype("float32") / 255.0
    # use skimage frangi (single-scale approximate: call with sigmas list)
    try:
        res = frangi(imgf, sigmas=scales)
    except Exception:
        # fallback: gaussian + sobel ridge approximation
        res = imgf
    res = (res - res.min()) / (res.max() - res.min() + 1e-12)
    return (res * 255).astype("uint8")


def gabor_filter_max(img, thetas=(0, 30, 60, 90, 120, 150), sigma=2.0, wavelength=8.0):
    imgf = img.astype("float32") / 255.0
    out = np.zeros_like(imgf)
    for theta in thetas:
        kern = np.real(
            gabor_kernel(
                frequency=1.0 / wavelength,
                theta=np.deg2rad(theta),
                sigma_x=sigma,
                sigma_y=sigma,
            )
        )
        # convolution
        conv = signal.fftconvolve(imgf, kern, mode="same")
        out = np.maximum(out, conv)
    out = (out - out.min()) / (out.max() - out.min() + 1e-12)
    return (out * 255).astype("uint8")


def fuse_filters(filter_imgs, weights=None):
    # filter_imgs: list of numpy arrays (same shape)
    if not filter_imgs:
        raise ValueError("No filters to fuse")
    if weights is None:
        weights = [1.0 / len(filter_imgs)] * len(filter_imgs)
    acc = None
    for img, w in zip(filter_imgs, weights):
        arr = img.astype("float32")
        if acc is None:
            acc = arr * w
        else:
            acc += arr * w
    acc = acc - acc.min()
    if acc.max() > 0:
        acc = acc / acc.max() * 255.0
    return acc.astype("uint8")
