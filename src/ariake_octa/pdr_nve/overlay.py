"""QA montage, ARIAKE-style RGB viz, and analysis binary masks."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import cv2
import numpy as np
from PIL import Image

from ._paths import ensure_import_paths
from .scale import PixelScale
from .vessels import VesselMaps

ensure_import_paths()


def _u8(mask: np.ndarray) -> np.ndarray:
    return ((mask > 0).astype(np.uint8)) * 255


def save_gray_png(path: Path, image: np.ndarray) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(_u8(image) if image.dtype == bool else image.astype(np.uint8)).save(
        path
    )
    return path


def save_rgb_png(path: Path, rgb: np.ndarray) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), mode="RGB").save(path)
    return path


def _highskew_from_large(maps: VesselMaps) -> np.ndarray:
    """Distance-weighted large-vessel map so ARIAKE subtractive RGB shows red trunks."""
    if not np.any(maps.large_mask):
        return np.zeros(maps.binary.shape, dtype=np.float32)
    hsk = maps.distance_px.astype(np.float32)
    hsk = np.where(maps.large_mask, hsk, 0.0)
    if float(hsk.max()) > 0:
        hsk = hsk * (255.0 / float(hsk.max()))
    hsk = cv2.GaussianBlur(hsk, (0, 0), 1.2)
    return hsk


def create_ariake_rgb(
    image_u8: np.ndarray,
    maps: VesselMaps,
    roi: np.ndarray,
    scale: PixelScale,
    metrics: Optional[Dict] = None,
    add_overlays: bool = True,
) -> np.ndarray:
    """
    Same subtractive RGB as the MNV app (VisualizationRGB):

    * yellow = vessels in ROI
    * red = large-caliber / trunk vessels (used in place of high-skew)
    * gray = background
    """
    from ariake_octa.mnv.visualization_rgb import VisualizationRGB

    bar_mm = 1.0 if scale.scan_size_mm >= 10 else 0.5
    vis = VisualizationRGB(
        pixel_size_mm=scale.mm_per_px,
        scale_bar_length_mm=bar_mm,
        font_scale=0.55,
        font_thickness=1,
    )
    overlay_metrics = None
    if metrics:
        overlay_metrics = {
            "lesion_area_mm2": metrics.get("roi_area_mm2"),
            "vessel_density": metrics.get("vessel_area_density"),
        }
    return vis.create_rgb_visualization(
        original_image=image_u8,
        binary_vessel=_u8(maps.binary),
        lesion_mask=_u8(roi),
        metrics=overlay_metrics,
        highskew_mask=_highskew_from_large(maps),
        add_overlays=add_overlays,
    )


def _draw_contour(rgb: np.ndarray, mask: np.ndarray, color, thickness: int = 2) -> None:
    contours, _ = cv2.findContours(_u8(mask), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(rgb, contours, -1, color, thickness)


def _to_rgb(gray: np.ndarray) -> np.ndarray:
    g = gray if gray.ndim == 2 else gray[..., 0]
    return np.stack([g, g, g], axis=-1)


def _label(rgb: np.ndarray, text: str) -> np.ndarray:
    out = rgb.copy()
    cv2.rectangle(out, (0, 0), (min(out.shape[1], 8 * len(text) + 16), 22), (0, 0, 0), -1)
    cv2.putText(
        out, text, (6, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 0), 1, cv2.LINE_AA
    )
    return out


def _resize_to(img: np.ndarray, hw: tuple) -> np.ndarray:
    h, w = hw
    if img.shape[0] == h and img.shape[1] == w:
        return img
    interp = cv2.INTER_NEAREST if img.ndim == 2 else cv2.INTER_LINEAR
    return cv2.resize(img, (w, h), interpolation=interp)


def create_qa_montage(
    before: np.ndarray,
    after_reg: np.ndarray,
    before_maps: VesselMaps,
    after_maps: VesselMaps,
    roi: np.ndarray,
    before_rgb: np.ndarray,
    after_rgb: np.ndarray,
) -> np.ndarray:
    """Side-by-side visual QA: raw, ARIAKE RGB, masks, registration checker."""
    h, w = before.shape[:2]
    after_reg = _resize_to(after_reg, (h, w))
    roi = _resize_to(_u8(roi), (h, w))

    raw_b = _to_rgb(before)
    raw_a = _to_rgb(after_reg)
    _draw_contour(raw_b, roi, (0, 255, 0), 2)
    _draw_contour(raw_a, roi, (0, 255, 0), 2)

    checker = np.zeros((h, w, 3), dtype=np.uint8)
    checker[..., 1] = before
    checker[..., 0] = after_reg
    checker[..., 2] = ((before.astype(np.uint16) + after_reg.astype(np.uint16)) // 2).astype(
        np.uint8
    )

    def mask_panel(vessel, large, title):
        panel = _to_rgb(before if title.startswith("before") else after_reg)
        panel = (panel.astype(np.float32) * 0.35).astype(np.uint8)
        keep = vessel & np.logical_not(large)
        panel[keep] = (255, 220, 40)
        panel[large] = (255, 40, 40)
        _draw_contour(panel, roi, (0, 255, 80), 1)
        return _label(panel, title)

    row1 = np.concatenate(
        [
            _label(raw_b, "before + ROI"),
            _label(raw_a, "after (registered) + ROI"),
            _label(checker, "register overlay (R=after G=before)"),
        ],
        axis=1,
    )
    row2 = np.concatenate(
        [
            _label(before_rgb, "before ARIAKE RGB"),
            _label(after_rgb, "after ARIAKE RGB"),
            mask_panel(after_maps.binary, after_maps.large_mask, "after masks Y=keep R=large"),
        ],
        axis=1,
    )
    row3 = np.concatenate(
        [
            mask_panel(before_maps.binary, before_maps.large_mask, "before masks Y=keep R=large"),
            _label(_to_rgb(roi), "shared ROI mask"),
            _label(
                _to_rgb(
                    np.clip(
                        (
                            before_maps.binary.astype(np.int16)
                            - after_maps.binary.astype(np.int16)
                        )
                        * 127
                        + 128,
                        0,
                        255,
                    ).astype(np.uint8)
                ),
                "vessel difference (before-after)",
            ),
        ],
        axis=1,
    )
    return np.concatenate([row1, row2, row3], axis=0)


def save_analysis_images(
    output_dir: Path,
    case_id: str,
    before: np.ndarray,
    after_reg: np.ndarray,
    before_maps: VesselMaps,
    after_maps: VesselMaps,
    roi: np.ndarray,
    scale: PixelScale,
    before_metrics: Dict,
    after_metrics: Dict,
) -> Dict[str, str]:
    """
    Write per-frame ARIAKE RGB + binary masks and a QA montage.

    Names are ``{case}_{phase}_{kind}.png`` so they can be opened without a
    sidecar. ``after_*`` frames are in the registered (before) coordinate frame.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: Dict[str, str] = {}

    before_rgb = create_ariake_rgb(before, before_maps, roi, scale, before_metrics)
    after_rgb = create_ariake_rgb(after_reg, after_maps, roi, scale, after_metrics)
    paths["before_rgb"] = str(
        save_rgb_png(output_dir / f"{case_id}_before_rgb.png", before_rgb)
    )
    paths["after_rgb"] = str(
        save_rgb_png(output_dir / f"{case_id}_after_rgb.png", after_rgb)
    )

    for phase, maps in (("before", before_maps), ("after", after_maps)):
        paths[f"{phase}_vessel_mask"] = str(
            save_gray_png(
                output_dir / f"{case_id}_{phase}_vessel_mask.png", maps.binary
            )
        )
        paths[f"{phase}_roi_mask"] = str(
            save_gray_png(output_dir / f"{case_id}_{phase}_roi_mask.png", roi)
        )
        paths[f"{phase}_vessel_mask_no_large"] = str(
            save_gray_png(
                output_dir / f"{case_id}_{phase}_vessel_mask_no_large.png",
                maps.binary_no_large,
            )
        )
        paths[f"{phase}_large_vessel_mask"] = str(
            save_gray_png(
                output_dir / f"{case_id}_{phase}_large_vessel_mask.png", maps.large_mask
            )
        )

    montage = create_qa_montage(
        before, after_reg, before_maps, after_maps, roi, before_rgb, after_rgb
    )
    paths["overlay_qa"] = str(
        save_rgb_png(output_dir / f"{case_id}_overlay_qa.png", montage)
    )
    paths["shared_roi_mask"] = str(
        save_gray_png(output_dir / f"{case_id}_shared_roi_mask.png", roi)
    )
    return paths


def _checkerboard(a: np.ndarray, b: np.ndarray, block: int = 32) -> np.ndarray:
    h, w = a.shape[:2]
    yy, xx = np.indices((h, w))
    sel = ((yy // block) + (xx // block)) % 2 == 0
    out = a.copy()
    out[sel] = b[sel]
    return out


def create_register_qa(
    ref_before: np.ndarray,
    ref_after_warped: np.ndarray,
    analysis_before: np.ndarray,
    analysis_after_warped: np.ndarray,
    *,
    cc_ref: float,
    cc_ref_persistent: float,
    cc_analysis: float,
    tx: float,
    ty: float,
    method: str,
    reference_kind: str,
) -> np.ndarray:
    """Two-row registration QA: Global (or other ref) vs analysis slab."""
    h, w = ref_before.shape[:2]
    ref_after_warped = _resize_to(ref_after_warped, (h, w))
    analysis_before = _resize_to(analysis_before, (h, w))
    analysis_after_warped = _resize_to(analysis_after_warped, (h, w))

    def color_overlay(g_before, g_after):
        panel = np.zeros((h, w, 3), dtype=np.uint8)
        panel[..., 1] = g_before
        panel[..., 0] = g_after
        panel[..., 2] = ((g_before.astype(np.uint16) + g_after.astype(np.uint16)) // 2).astype(
            np.uint8
        )
        return panel

    def board(g_before, g_after):
        return _to_rgb(_checkerboard(g_before, g_after, block=32))

    header = (
        f"ref={reference_kind}  method={method}  "
        f"cc_ref={cc_ref:.3f}  cc_persist={cc_ref_persistent:.3f}  "
        f"cc_analysis={cc_analysis:.3f}  tx={tx:.1f}  ty={ty:.1f} px"
    )
    row1 = np.concatenate(
        [
            _label(color_overlay(ref_before, ref_after_warped), "ref overlay R=after G=before"),
            _label(board(ref_before, ref_after_warped), "ref checkerboard 32px"),
        ],
        axis=1,
    )
    row2 = np.concatenate(
        [
            _label(
                color_overlay(analysis_before, analysis_after_warped),
                "analysis overlay R=after G=before",
            ),
            _label(board(analysis_before, analysis_after_warped), "analysis checkerboard 32px"),
        ],
        axis=1,
    )
    canvas = np.concatenate([row1, row2], axis=0)
    bar = np.zeros((28, canvas.shape[1], 3), dtype=np.uint8)
    cv2.putText(
        bar, header, (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 0), 1, cv2.LINE_AA
    )
    return np.concatenate([bar, canvas], axis=0)
