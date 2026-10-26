"""
Pair registration: after → before.

Approach follows ARIAKE OCTA Stack Registration (yasuoyanagijp-maker/stack_reg)
without importing that repo:

* CLAHE pretreat
* coarse translation seed (phase correlation; stack_reg uses matchTemplate,
  which is a no-op when the two frames are the same size)
* Gaussian-pyramid ``cv2.findTransformECC`` (MOTION_AFFINE)
* if confidence is low, ORB + RANSAC partial-affine refine
* warp with ``WARP_INVERSE_MAP`` (matrix maps reference coords → source coords)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

import cv2
import numpy as np

DEFAULT_CONFIDENCE_THRESHOLD = 0.80
REFINE_MIN_IMPROVEMENT = 0.02


@dataclass
class RegistrationResult:
    warped_after: np.ndarray
    matrix: np.ndarray
    score: float
    persistent_score: float
    method: str
    translation_xy: Tuple[float, float]
    failed: bool
    valid_overlap_frac: float
    reference_kind: str = "analysis_slab"
    n_register_slabs: int = 1
    combine_mode: str = "none"

    def to_record(self) -> dict:
        return {
            "registration_cc": self.score,
            "registration_cc_persistent": self.persistent_score,
            "registration_method": self.method,
            "registration_failed": self.failed,
            "registration_tx_px": self.translation_xy[0],
            "registration_ty_px": self.translation_xy[1],
            "registration_overlap_frac": self.valid_overlap_frac,
            "registration_reference": self.reference_kind,
            "registration_n_slabs": int(self.n_register_slabs),
            "registration_combine": self.combine_mode,
        }


def _clahe(image: np.ndarray) -> np.ndarray:
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(image.astype(np.uint8))


def build_gaussian_pyramid(img: np.ndarray, min_size: int = 64):
    pyramid = [img]
    while True:
        h, w = pyramid[-1].shape[:2]
        if h <= min_size * 2 or w <= min_size * 2:
            break
        pyramid.append(cv2.pyrDown(pyramid[-1]))
    return pyramid


def compute_alignment_cc(
    reference: np.ndarray,
    source: np.ndarray,
    matrix: np.ndarray,
) -> float:
    h, w = reference.shape[:2]
    warped = cv2.warpAffine(
        source.astype(np.float32),
        matrix.astype(np.float32),
        (w, h),
        flags=cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )
    mask = warped > 0
    if int(mask.sum()) < 16:
        return 0.0
    a = reference.astype(np.float32)[mask]
    b = warped[mask]
    a = a - a.mean()
    b = b - b.mean()
    denom = float(np.sqrt((a * a).sum() * (b * b).sum()))
    if denom <= 1e-9:
        return 0.0
    return float(np.clip((a * b).sum() / denom, -1.0, 1.0))


def _phase_corr_translation(reference: np.ndarray, source: np.ndarray) -> Tuple[float, float, float]:
    ref = reference.astype(np.float32)
    src = source.astype(np.float32)
    ref = (ref - ref.mean()) / (ref.std() + 1e-6)
    src = (src - src.mean()) / (src.std() + 1e-6)
    window = cv2.createHanningWindow((ref.shape[1], ref.shape[0]), cv2.CV_32F)
    shift, response = cv2.phaseCorrelate(ref, src, window)
    # phaseCorrelate: shift such that source shifted by (dx, dy) matches reference
    return float(shift[0]), float(shift[1]), float(response)


def _ecc_pyramid_affine(
    reference: np.ndarray,
    source: np.ndarray,
    seed_matrix: np.ndarray,
) -> Tuple[np.ndarray, float]:
    ref_f = reference.astype(np.float32)
    src_f = source.astype(np.float32)
    ref_pyr = build_gaussian_pyramid(ref_f, min_size=64)
    src_pyr = build_gaussian_pyramid(src_f, min_size=64)
    levels = min(len(ref_pyr), len(src_pyr))
    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-5)

    # Scale seed (full-res) down to the coarsest level.
    warp = seed_matrix.astype(np.float64).copy()
    scale = 0.5 ** (levels - 1)
    warp[:, 2] *= scale
    warp[0, 0] = 1.0
    warp[0, 1] = 0.0
    warp[1, 0] = 0.0
    warp[1, 1] = 1.0
    warp = warp.astype(np.float32)

    s_up = np.array(
        [[2.0, 0.0, 0.0], [0.0, 2.0, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64
    )
    s_down = np.array(
        [[0.5, 0.0, 0.0], [0.0, 0.5, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64
    )

    finest_cc = 0.0
    for level_idx, level_res in enumerate(reversed(range(levels))):
        try:
            cc, new_warp = cv2.findTransformECC(
                ref_pyr[level_res],
                src_pyr[level_res],
                warp,
                cv2.MOTION_AFFINE,
                criteria,
            )
            warp = new_warp
            if level_res == 0:
                finest_cc = float(cc)
        except cv2.error:
            pass
        if level_res > 0:
            m3 = np.vstack([warp.astype(np.float64), [0.0, 0.0, 1.0]])
            warp = (s_up @ m3 @ s_down)[:2, :].astype(np.float32)
    return warp.astype(np.float32), finest_cc


def _orb_refine(
    reference: np.ndarray, source: np.ndarray
) -> Optional[Tuple[np.ndarray, float]]:
    orb = cv2.ORB_create(nfeatures=2000)
    kp_ref, des_ref = orb.detectAndCompute(reference.astype(np.uint8), None)
    kp_src, des_src = orb.detectAndCompute(source.astype(np.uint8), None)
    if des_ref is None or des_src is None or len(kp_ref) < 8 or len(kp_src) < 8:
        return None
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    knn = matcher.knnMatch(des_ref, des_src, k=2)
    good = [
        pair[0]
        for pair in knn
        if len(pair) == 2 and pair[0].distance < 0.75 * pair[1].distance
    ]
    if len(good) < 6:
        return None
    ref_pts = np.float32([kp_ref[m.queryIdx].pt for m in good])
    src_pts = np.float32([kp_src[m.trainIdx].pt for m in good])
    matrix, _ = cv2.estimateAffinePartial2D(
        ref_pts, src_pts, method=cv2.RANSAC, ransacReprojThreshold=5.0
    )
    if matrix is None:
        return None
    matrix = matrix.astype(np.float32)
    return matrix, compute_alignment_cc(reference, source, matrix)


def _persistent_cc(reference: np.ndarray, warped: np.ndarray) -> float:
    """
    Correlation on the brightest 15% of *either* frame.

    Full-image CC collapses after NVE pruning (the lesion signal disappears).
    Persistent bright ridges (trunks, disc star) are the structures used to
    judge whether the pair is still in the same coordinate frame.
    """
    ref = reference.astype(np.float32)
    src = warped.astype(np.float32)
    thr = float(np.percentile(np.concatenate([ref.ravel(), src.ravel()]), 85))
    mask = (ref >= thr) | (src >= thr)
    if int(mask.sum()) < 32:
        return 0.0
    a = ref[mask] - ref[mask].mean()
    b = src[mask] - src[mask].mean()
    denom = float(np.sqrt((a * a).sum() * (b * b).sum()))
    if denom <= 1e-9:
        return 0.0
    return float(np.clip((a * b).sum() / denom, -1.0, 1.0))


def combine_slabs(
    images: Sequence[np.ndarray],
    mode: str = "mean",
    target_shape: Optional[Tuple[int, int]] = None,
) -> np.ndarray:
    """
    Build one registration reference from several en-face slabs.

    Same idea as stack_reg / ImageJ ``Z Project`` (Image 5 = average intensity)
    and device exports such as VRI+Retina Global. ``mode='sum'`` adds the
    slabs then rescales to 8-bit so the result does not clip.
    """
    if not images:
        raise ValueError("combine_slabs requires at least one image")
    mode = (mode or "mean").strip().lower()
    if mode not in {"mean", "sum", "max"}:
        raise ValueError(f"Unknown combine mode: {mode}")
    resized = []
    for img in images:
        arr = np.asarray(img)
        if arr.ndim != 2:
            raise ValueError(f"Slabs must be 2-D grayscale, got {arr.shape}")
        if target_shape is not None and arr.shape[:2] != target_shape:
            arr = cv2.resize(
                arr.astype(np.uint8),
                (target_shape[1], target_shape[0]),
                interpolation=cv2.INTER_LINEAR,
            )
        resized.append(arr.astype(np.float32))
    stack = np.stack(resized, axis=0)
    if mode == "sum":
        combined = stack.sum(axis=0)
        mx = float(combined.max())
        if mx > 0:
            combined = combined * (255.0 / mx)
    elif mode == "max":
        combined = stack.max(axis=0)
    else:
        combined = stack.mean(axis=0)
    return np.clip(np.rint(combined), 0, 255).astype(np.uint8)


def warp_gray(image: np.ndarray, matrix: np.ndarray, shape: tuple) -> np.ndarray:
    h, w = shape[:2]
    return cv2.warpAffine(
        image.astype(np.uint8),
        matrix.astype(np.float32),
        (w, h),
        flags=cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )


def identity_result(after: np.ndarray) -> RegistrationResult:
    return RegistrationResult(
        warped_after=after.copy(),
        matrix=np.eye(2, 3, dtype=np.float32),
        score=1.0,
        persistent_score=1.0,
        method="identity",
        translation_xy=(0.0, 0.0),
        failed=False,
        valid_overlap_frac=1.0,
        reference_kind="identity",
        n_register_slabs=0,
        combine_mode="none",
    )


def register_after_to_before(
    before: np.ndarray,
    after: np.ndarray,
    enabled: bool = True,
) -> RegistrationResult:
    """Warp ``after`` into ``before`` coordinates."""
    if not enabled:
        return identity_result(after)
    if before.shape[:2] != after.shape[:2]:
        after = cv2.resize(
            after, (before.shape[1], before.shape[0]), interpolation=cv2.INTER_LINEAR
        )

    ref = _clahe(before)
    src = _clahe(after)
    dx, dy, _resp = _phase_corr_translation(ref, src)
    # phaseCorrelate shift of source toward reference; ECC matrix maps ref→src,
    # so translation of src relative to ref is the opposite of the displayed warp.
    seed = np.eye(2, 3, dtype=np.float32)
    seed[0, 2] = -dx
    seed[1, 2] = -dy

    matrix, ecc_cc = _ecc_pyramid_affine(ref, src, seed)
    score = compute_alignment_cc(ref, src, matrix)
    if ecc_cc > 0:
        score = max(score, float(ecc_cc))
    method = "ecc_pyramid"

    if score < DEFAULT_CONFIDENCE_THRESHOLD:
        refined = _orb_refine(ref, src)
        if refined is not None:
            cand_m, cand_cc = refined
            if cand_cc > score + REFINE_MIN_IMPROVEMENT:
                matrix = cand_m
                score = cand_cc
                method = "orb_ransac"

    h, w = before.shape[:2]
    warped = cv2.warpAffine(
        after,
        matrix.astype(np.float32),
        (w, h),
        flags=cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )
    overlap = float((warped > 0).mean())
    persistent = _persistent_cc(ref, _clahe(warped))
    shift = float(np.hypot(matrix[0, 2], matrix[1, 2]))
    huge_shift = shift > 0.35 * max(h, w)
    failed = overlap < 0.40 or huge_shift
    return RegistrationResult(
        warped_after=warped,
        matrix=matrix.astype(np.float32),
        score=float(score),
        persistent_score=float(persistent),
        method=method,
        translation_xy=(float(matrix[0, 2]), float(matrix[1, 2])),
        failed=failed,
        valid_overlap_frac=overlap,
        reference_kind="analysis_slab",
        n_register_slabs=1,
        combine_mode="none",
    )


def register_using_reference_slabs(
    analysis_before: np.ndarray,
    analysis_after: np.ndarray,
    ref_before: np.ndarray,
    ref_after: np.ndarray,
    *,
    enabled: bool = True,
    reference_kind: str = "combined_slabs",
    n_register_slabs: int = 1,
    combine_mode: str = "mean",
) -> RegistrationResult:
    """
    Estimate after→before on *reference* slabs (Retina / VRI+Retina Global /
    mean of all slabs), then warp the analysis slab with that matrix.

    ILM+49 NVE can vanish after anti-VEGF, so aligning on that slab alone
    is unreliable. Persistent inner-retina vasculature is what stack_reg
    uses as Image 5 (average projection).
    """
    if not enabled:
        return identity_result(analysis_after)
    shape = analysis_before.shape[:2]
    if ref_before.shape[:2] != shape:
        ref_before = cv2.resize(
            ref_before, (shape[1], shape[0]), interpolation=cv2.INTER_LINEAR
        )
    if ref_after.shape[:2] != shape:
        ref_after = cv2.resize(
            ref_after, (shape[1], shape[0]), interpolation=cv2.INTER_LINEAR
        )
    if analysis_after.shape[:2] != shape:
        analysis_after = cv2.resize(
            analysis_after, (shape[1], shape[0]), interpolation=cv2.INTER_LINEAR
        )
    est = register_after_to_before(ref_before, ref_after, enabled=True)
    warped = warp_gray(analysis_after, est.matrix, shape)
    est.warped_after = warped
    est.reference_kind = reference_kind
    est.n_register_slabs = int(n_register_slabs)
    est.combine_mode = combine_mode
    return est


def warp_mask(mask: np.ndarray, matrix: np.ndarray, shape: tuple) -> np.ndarray:
    h, w = shape[:2]
    warped = cv2.warpAffine(
        (mask > 0).astype(np.uint8) * 255,
        matrix.astype(np.float32),
        (w, h),
        flags=cv2.INTER_NEAREST + cv2.WARP_INVERSE_MAP,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )
    return warped
