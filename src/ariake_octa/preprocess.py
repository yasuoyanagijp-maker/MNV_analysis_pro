import cv2
import numpy as np
from scipy.ndimage import gaussian_filter


def preprocess_image(img, clahe_clip=3.0, background_sigma=5.0):
    # img: numpy array (H,W[,C])
    if img.ndim == 3 and img.shape[2] == 3:
        # use green channel like macro
        img = img[:, :, 1]
    img = img.astype("float32")
    # CLAHE via OpenCV
    clahe = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=(8, 8))
    img8 = np.clip(img, 0, 255).astype("uint8")
    cl = clahe.apply(img8)
    # background subtraction
    bg = gaussian_filter(cl.astype("float32"), sigma=background_sigma)
    res = cl.astype("float32") - bg
    # normalize
    res = res - res.min()
    if res.max() > 0:
        res = res / res.max() * 255.0
    return res.astype("uint8")
