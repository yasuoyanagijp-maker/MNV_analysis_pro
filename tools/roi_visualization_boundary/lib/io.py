"""Shared I/O and ColorMask preview helpers for visualization-boundary pilots."""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import cv2
import numpy as np

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
    sys.path.insert(0, str(_REPO / "src"))

from ariake_octa.mnv.visualization_rgb import VisualizationRGB  # noqa: E402
from core.mnv_pipeline import FILTER_PARAMS_SMALL  # noqa: E402
from core.vessel_detection import MNVPreprocessor  # noqa: E402
from tools.roi_visualization_boundary.lib.cases import CASE_LABELS, SCALE_MM  # noqa: E402
from utils.dual_grader_merge import match_stem  # noqa: E402
from utils.image_utils import ImageProcessor  # noqa: E402


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def index_by_stem(rows: List[Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    return {match_stem(r.get("File", "") or r.get("ID", "")): r for r in rows}


def case_id(filename: str) -> str:
    for token, label in CASE_LABELS.items():
        if token in filename:
            return label
    return match_stem(filename)


def find_mask(export_root: Path, stem: str) -> Path:
    masks = list((export_root / "masks").rglob("*.png"))
    for p in masks:
        if match_stem(p.name) == stem:
            return p
    raise FileNotFoundError(f"ROI mask not found for {stem} under {export_root}")


def find_image(export_root: Path, stem: str) -> Path:
    images = list((export_root / "images").rglob("*.png"))
    for p in images:
        if match_stem(p.name) == stem:
            return p
    raise FileNotFoundError(f"Export image not found for {stem} under {export_root}")


def load_gray(path: Path) -> np.ndarray:
    img = ImageProcessor.load_image(str(path), as_gray=True)
    return ImageProcessor.ensure_8bit(img)


def load_roi(path: Path, shape: Tuple[int, int]) -> np.ndarray:
    mask = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        raise RuntimeError(f"Failed to read mask: {path}")
    if mask.shape[:2] != shape:
        mask = cv2.resize(
            mask, (shape[1], shape[0]), interpolation=cv2.INTER_NEAREST
        )
    return ((mask > 0).astype(np.uint8)) * 255


def detect_vessels(image: np.ndarray) -> np.ndarray:
    preprocessor = MNVPreprocessor(
        mexican_hat_sigma=1.0,
        tubeness_sigma=2.5,
        filter_params=dict(FILTER_PARAMS_SMALL),
    )
    out = preprocessor.preprocess_mnv(image, roi_mask=np.ones_like(image) * 255)
    binary = out["binary"]
    return ((binary > 0).astype(np.uint8)) * 255


def make_rgb(image: np.ndarray, binary: np.ndarray, roi: np.ndarray) -> np.ndarray:
    vis = VisualizationRGB(pixel_size_mm=SCALE_MM / image.shape[1])
    return vis.create_rgb_visualization(
        original_image=image,
        binary_vessel=binary,
        lesion_mask=roi,
        metrics=None,
        highskew_mask=None,
        add_overlays=False,
    )
