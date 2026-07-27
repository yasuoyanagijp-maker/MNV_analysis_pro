#!/usr/bin/env python3
"""Assemble Figure 3 processing-step montage from MNV debug panels.

Accepts either:
  --from-dir <uuid output/mnv/...>  (uses debug_*.png + visualization_rgb.png)
  --panels with explicit image paths
  --run-headless <image_path>       (optional: CoreMNVPipeline with auto ROI)

Draft panels (labeled A–D by default):
  A original / ROI overlay
  B vessel enhancement (mex_hat or tubeness)
  C binary vessel map
  D color overlay / visualization_rgb

Note: Existing output/mnv/*/ folders usually lack case metadata, so prefer
--run-headless on 1–3 representative cohort images, or run the same cases in
Flet and pass --from-dir. Auto-ROI headless frames are draft-quality; freehand
ROI in Flet is preferred for the final figure.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parents[2]
FIG_DIR = REPO_ROOT / "documentation" / "graefe_revision" / "figures"
DEFAULT_OUT_STEM = FIG_DIR / "Figure3_processing_steps"


def _to_rgb(arr: np.ndarray) -> np.ndarray:
    if arr is None:
        raise ValueError("image is None")
    if arr.ndim == 2:
        return cv2.cvtColor(arr, cv2.COLOR_GRAY2RGB)
    if arr.shape[2] == 4:
        return cv2.cvtColor(arr, cv2.COLOR_BGRA2RGB)
    return cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)


def _load_rgb(path: Path) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise FileNotFoundError(path)
    return _to_rgb(img)


def _resize_max(img: np.ndarray, max_side: int) -> np.ndarray:
    h, w = img.shape[:2]
    scale = min(1.0, max_side / max(h, w))
    if scale >= 0.999:
        return img
    return cv2.resize(
        img,
        (int(round(w * scale)), int(round(h * scale))),
        interpolation=cv2.INTER_AREA,
    )


def _fit_canvas(img: np.ndarray, size: tuple[int, int], bg=(245, 245, 245)) -> np.ndarray:
    th, tw = size
    h, w = img.shape[:2]
    scale = min(tw / w, th / h)
    nw, nh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
    canvas = np.full((th, tw, 3), bg, dtype=np.uint8)
    y0 = (th - nh) // 2
    x0 = (tw - nw) // 2
    canvas[y0 : y0 + nh, x0 : x0 + nw] = resized
    return canvas


def make_roi_overlay(original: np.ndarray, roi_mask: np.ndarray) -> np.ndarray:
    base = original.copy()
    if roi_mask.shape[:2] != base.shape[:2]:
        roi_mask = cv2.resize(
            roi_mask, (base.shape[1], base.shape[0]), interpolation=cv2.INTER_NEAREST
        )
    if roi_mask.ndim == 3:
        roi_mask = cv2.cvtColor(roi_mask, cv2.COLOR_RGB2GRAY)
    overlay = base.copy()
    # tint ROI green
    green = np.zeros_like(base)
    green[:, :, 1] = 180
    m = roi_mask > 0
    overlay[m] = (0.65 * base[m] + 0.35 * green[m]).astype(np.uint8)
    contours, _ = cv2.findContours(
        (roi_mask > 0).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    cv2.drawContours(overlay, contours, -1, (0, 220, 80), 2)
    return overlay


def _roi_bbox(roi_mask: np.ndarray, pad: float = 0.08) -> tuple[int, int, int, int]:
    ys, xs = np.where(roi_mask > 0)
    if ys.size == 0:
        h, w = roi_mask.shape[:2]
        return 0, 0, h, w
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    h, w = roi_mask.shape[:2]
    bh, bw = y1 - y0, x1 - x0
    py, px = int(round(bh * pad)), int(round(bw * pad))
    y0 = max(0, y0 - py)
    x0 = max(0, x0 - px)
    y1 = min(h, y1 + py)
    x1 = min(w, x1 + px)
    return y0, y1, x0, x1


def _crop_to_roi(img: np.ndarray, roi_mask: np.ndarray, apply_mask: bool = True) -> np.ndarray:
    if roi_mask.shape[:2] != img.shape[:2]:
        roi_mask = cv2.resize(
            roi_mask, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST
        )
    y0, y1, x0, x1 = _roi_bbox(roi_mask)
    out = img[y0:y1, x0:x1].copy()
    if apply_mask:
        m = roi_mask[y0:y1, x0:x1] > 0
        if out.ndim == 2:
            out = out.copy()
            out[~m] = 0
        else:
            out[~m] = 0
    return out


def collect_from_dir(
    run_dir: Path, original_path: Path | None = None
) -> dict[str, np.ndarray]:
    run_dir = Path(run_dir)
    mex = run_dir / "debug_mex_hat.png"
    tube = run_dir / "debug_tubeness.png"
    binary = run_dir / "debug_binary_combined.png"
    roi = run_dir / "debug_roi_mask.png"
    vis = run_dir / "visualization_rgb.png"

    roi_img = None
    if roi.is_file():
        roi_img = cv2.imread(str(roi), cv2.IMREAD_GRAYSCALE)

    panels: dict[str, np.ndarray] = {}
    if original_path and Path(original_path).is_file() and roi_img is not None:
        orig = _load_rgb(Path(original_path))
        panels["A"] = make_roi_overlay(orig, roi_img)
    elif roi_img is not None:
        # ROI alone as stand-in
        panels["A"] = _load_rgb(roi)
    else:
        raise FileNotFoundError(f"Need original+ROI or debug_roi_mask in {run_dir}")

    if mex.is_file():
        enh = _load_rgb(mex)
    elif tube.is_file():
        enh = _load_rgb(tube)
    else:
        raise FileNotFoundError(f"Need debug_mex_hat or debug_tubeness in {run_dir}")
    panels["B"] = _crop_to_roi(enh, roi_img) if roi_img is not None else enh

    if not binary.is_file():
        raise FileNotFoundError(f"Need debug_binary_combined in {run_dir}")
    bin_img = _load_rgb(binary)
    panels["C"] = _crop_to_roi(bin_img, roi_img) if roi_img is not None else bin_img

    if not vis.is_file():
        raise FileNotFoundError(f"Need visualization_rgb in {run_dir}")
    panels["D"] = _load_rgb(vis)
    return panels


def run_headless(
    image_path: Path, scale_mm: float, out_dir: Path
) -> Path:
    """Run CoreMNVPipeline with automatic ROI; return output dir."""
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from core.mnv_pipeline import MNVPipeline

    out_dir.mkdir(parents=True, exist_ok=True)
    pipe = MNVPipeline(
        scale_mm=scale_mm,
        save_stages=True,
        verbose=True,
        debug=True,
        enable_roi_refinement=True,
    )
    print(f"Headless analyze: {image_path} scale={scale_mm} -> {out_dir}")
    pipe.analyze(str(image_path), output_dir=str(out_dir), roi_mask=None)
    return out_dir


def assemble_montage(
    panels: dict[str, np.ndarray],
    labels: dict[str, str],
    order: list[str] = ("A", "B", "C", "D"),
    panel_size: tuple[int, int] = (720, 720),
    label_h: int = 56,
) -> Image.Image:
    n = len(order)
    cols = 2
    rows = int(np.ceil(n / cols))
    pad = 18
    title_gap = 8
    W = cols * panel_size[0] + (cols + 1) * pad
    H = rows * (panel_size[1] + label_h + title_gap) + (rows + 1) * pad
    canvas = Image.new("RGB", (W, H), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 28)
        font_sm = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 22)
    except OSError:
        font = ImageFont.load_default()
        font_sm = font

    for i, key in enumerate(order):
        r, c = divmod(i, cols)
        x0 = pad + c * (panel_size[0] + pad)
        y0 = pad + r * (panel_size[1] + label_h + title_gap + pad)
        fitted = _fit_canvas(panels[key], panel_size)
        canvas.paste(Image.fromarray(fitted), (x0, y0 + label_h))
        title = labels.get(key, key)
        draw.text((x0 + 4, y0 + 8), f"{key}. {title}", fill=(20, 20, 20), font=font)
    return canvas


def write_caption(path: Path, source_note: str) -> None:
    text = f"""# Figure 3 — Processing steps (draft caption)

**Figure 3.** Representative OCTA en-face image of macular neovascularization illustrating the semi-automated processing pipeline. **(A)** Input angiogram with freehand / refined region of interest (ROI; green outline and tint). **(B)** Hybrid multiscale vessel enhancement (Mexican-hat / Laplacian-of-Gaussian component shown; Frangi/tubeness is combined in the full pipeline). **(C)** Adaptive Phansalkar binarization within the ROI after morphological refinement. **(D)** Color-coded vessel visualization used for qualitative review alongside quantitative skeleton-derived metrics (Network Complexity Score, Caliber Uniformity Score, Maturity Index).

*Draft assembly note:* {source_note}

Final panels for submission should preferably come from 1–3 cohort cases processed in Flet with the same freehand ROI workflow used clinically (see `scripts/graefe_revision/assemble_figure3.py --from-dir`). Auto-ROI headless frames are acceptable only as interim drafts.
"""
    path.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-dir", type=Path, help="output/mnv/<uuid> with debug_*.png")
    parser.add_argument("--original", type=Path, help="Original OCTA image for panel A")
    parser.add_argument("--run-headless", type=Path, help="Image path to process headless")
    parser.add_argument("--scale-mm", type=float, default=6.0)
    parser.add_argument(
        "--out-stem",
        type=Path,
        default=DEFAULT_OUT_STEM,
        help="Output path without extension",
    )
    parser.add_argument("--tiff", action="store_true", default=True)
    parser.add_argument("--no-tiff", action="store_true")
    parser.add_argument(
        "--pick-existing",
        action="store_true",
        help="Auto-pick a recent full-panel debug dir if --from-dir omitted",
    )
    args = parser.parse_args()

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    source_note = ""

    if args.run_headless:
        image_path = Path(args.run_headless)
        out_dir = (
            REPO_ROOT
            / "documentation"
            / "graefe_revision"
            / "figures"
            / "_fig3_runs"
            / str(uuid.uuid4())
        )
        run_headless(image_path, args.scale_mm, out_dir)
        panels = collect_from_dir(out_dir, original_path=image_path)
        source_note = (
            f"Headless CoreMNVPipeline auto-ROI on `{image_path.name}` "
            f"(scale_mm={args.scale_mm}); draft quality."
        )
    else:
        run_dir = args.from_dir
        if run_dir is None and args.pick_existing:
            root = REPO_ROOT / "output" / "mnv"
            need = [
                "debug_mex_hat.png",
                "debug_binary_combined.png",
                "debug_roi_mask.png",
                "visualization_rgb.png",
            ]
            cands = []
            for d in root.iterdir():
                if d.is_dir() and all((d / n).exists() for n in need):
                    cands.append((d.stat().st_mtime, d))
            if not cands:
                raise SystemExit("No full-panel debug dirs found under output/mnv")
            cands.sort(reverse=True)
            run_dir = cands[0][1]
            print(f"Picked existing debug dir: {run_dir}")
        if run_dir is None:
            raise SystemExit("Provide --from-dir, --run-headless, or --pick-existing")
        panels = collect_from_dir(run_dir, original_path=args.original)
        source_note = f"Panels from `{run_dir}`" + (
            f" with original `{args.original}`" if args.original else " (ROI mask as panel A stand-in)"
        )

    labels = {
        "A": "Original OCTA with ROI",
        "B": "Vessel enhancement",
        "C": "Binary vessel map",
        "D": "Color visualization",
    }
    # Upscale tiny panels for print readability
    for k, v in list(panels.items()):
        panels[k] = _resize_max(v, 1200)

    montage = assemble_montage(panels, labels)
    out_stem = Path(args.out_stem)
    out_stem.parent.mkdir(parents=True, exist_ok=True)
    png_path = out_stem.with_suffix(".png")
    montage.save(png_path, optimize=True)
    print(f"Wrote {png_path} ({montage.size[0]}x{montage.size[1]})")

    if args.tiff and not args.no_tiff:
        tiff_path = out_stem.with_suffix(".tiff")
        # Flatten for broader compatibility
        montage_rgb = montage.convert("RGB")
        montage_rgb.save(tiff_path, compression="tiff_lzw")
        print(f"Wrote {tiff_path}")

    caption_path = out_stem.with_name(out_stem.name + "_caption.md")
    write_caption(caption_path, source_note)
    print(f"Wrote {caption_path}")


if __name__ == "__main__":
    main()
