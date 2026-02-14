"""
Quick example: LoG + Tubeness + adaptive binarize + small-particle removal + interactive ROI.
Save this at repository root and run after installing requirements.
"""

import tifffile as tiff
import numpy as np
from src.ariake_octa.tubeness import laplacian_of_gaussian, tubeness_sato
from src.ariake_octa.binarize import (
    adaptive_binarize_phansalkar,
    remove_small_particles,
)
from src.ariake_octa.roi import select_roi_interactive
import os


def main():
    infile = "input.tif"  # change to your file
    if not os.path.exists(infile):
        print("Place an input.tif in the repo root or change infile path")
        return
    img = tiff.imread(infile)
    # If RGB, use green channel like macro
    if img.ndim == 3 and img.shape[2] == 3:
        img_gray = img[:, :, 1]
    else:
        img_gray = img

    # interactive ROI (optional)
    roi = select_roi_interactive(img_gray)
    if roi is None:
        print("No ROI selected; proceeding on full image")

    # LoG (mexican-hat equivalent)
    log = laplacian_of_gaussian(img_gray, sigma=1.2)

    # Tubeness (Sato / Meijering)
    tube = tubeness_sato(img_gray, sigmas=(1.0, 2.0, 3.0), mode="sato")

    # Fuse and normalize
    fused = 0.6 * log.astype("float32") + 0.6 * tube.astype("float32")
    fused = (fused - fused.min()) / (fused.max() - fused.min() + 1e-12) * 255
    fused = fused.astype("uint8")

    # Adaptive binarize and clean
    binary = adaptive_binarize_phansalkar(fused, radius=15, k=0.1, R=128)
    cleaned = remove_small_particles(binary, min_size=50)

    # Save outputs
    tiff.imwrite("mex_hat.tif", log)
    tiff.imwrite("tubeness.tif", tube)
    tiff.imwrite("fused.tif", fused)
    tiff.imwrite("binary.tif", cleaned)
    print("Saved mex_hat.tif, tubeness.tif, fused.tif, binary.tif")


if __name__ == "__main__":
    main()
