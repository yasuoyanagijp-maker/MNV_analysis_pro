"""Load grayscale OCTA / ROI files and write the PDR NVE CSV."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Union

import numpy as np
from PIL import Image

from .scale import PixelScale

PathLike = Union[str, Path]


def load_gray_u8(path: PathLike) -> np.ndarray:
    """Load TIFF/JPEG/PNG/BMP as 8-bit grayscale (H×W)."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Image not found: {p}")
    image = np.array(Image.open(p))
    if image.ndim == 3:
        image = np.dot(image[..., :3], [0.299, 0.587, 0.114])
    if image.dtype == np.uint16:
        image = image / 256.0
    image = np.clip(np.rint(image), 0, 255).astype(np.uint8)
    if image.ndim != 2:
        raise ValueError(f"Expected 2D grayscale after conversion, got {image.shape}")
    return image


def load_mask_u8(path: PathLike, shape: Optional[tuple] = None) -> np.ndarray:
    """Load a binary mask (nonzero = ROI). Resizes with nearest-neighbor if needed."""
    import cv2

    mask = load_gray_u8(path)
    mask = ((mask > 0).astype(np.uint8)) * 255
    if shape is not None and mask.shape[:2] != shape[:2]:
        mask = cv2.resize(
            mask, (int(shape[1]), int(shape[0])), interpolation=cv2.INTER_NEAREST
        )
    return mask


def load_polygon(path: PathLike) -> List[tuple]:
    """
    Load polygon vertices as ``[(x, y), ...]``.

    Accepts JSON list of [x, y] or {\"polygon\": [[x, y], ...]} or a CSV with
    columns x,y (header optional).
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Polygon file not found: {p}")
    text = p.read_text(encoding="utf-8").strip()
    if p.suffix.lower() in {".json", ".geojson"}:
        data = json.loads(text)
        if isinstance(data, dict):
            if "polygon" in data:
                data = data["polygon"]
            elif "coordinates" in data:
                data = data["coordinates"]
                if isinstance(data, list) and data and isinstance(data[0], list):
                    if data and isinstance(data[0][0], (list, tuple)):
                        data = data[0]
        if not isinstance(data, list) or len(data) < 3:
            raise ValueError(f"Polygon JSON must be a list of ≥3 [x, y] points: {p}")
        return [(float(pt[0]), float(pt[1])) for pt in data]

    rows = []
    with p.open("r", encoding="utf-8", newline="") as fh:
        sample = text.splitlines()[0] if text else ""
        has_header = any(ch.isalpha() for ch in sample)
        reader = csv.reader(fh)
        for i, row in enumerate(reader):
            if not row or all(not c.strip() for c in row):
                continue
            if i == 0 and has_header:
                continue
            if len(row) < 2:
                raise ValueError(f"Polygon CSV rows need x,y: {p}")
            rows.append((float(row[0]), float(row[1])))
    if len(rows) < 3:
        raise ValueError(f"Polygon needs ≥3 vertices, got {len(rows)} in {p}")
    return rows


def polygon_to_mask(polygon: Sequence[tuple], shape: tuple) -> np.ndarray:
    """Rasterize an (x, y) polygon to a 0/255 mask."""
    from skimage.draw import polygon2mask

    coords = np.asarray(polygon, dtype=float)
    # skimage.draw.polygon2mask expects (row, col) = (y, x)
    rc = np.stack([coords[:, 1], coords[:, 0]], axis=1)
    mask = polygon2mask(shape[:2], rc)
    return (mask.astype(np.uint8)) * 255


def write_csv(path: PathLike, rows: Iterable[dict], fieldnames: Optional[Sequence[str]] = None) -> Path:
    rows = list(rows)
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError("No rows to write")
    names = list(fieldnames) if fieldnames else list(rows[0].keys())
    for row in rows:
        for key in row:
            if key not in names:
                names.append(key)
    with out.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=names, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: _csv_cell(row.get(k)) for k in names})
    return out


def _json_default(value):
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Not JSON serializable: {type(value)}")


def write_json(path: PathLike, payload: dict) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=_json_default) + "\n",
        encoding="utf-8",
    )
    return out


def _csv_cell(value):
    if value is None:
        return ""
    if isinstance(value, (bool, np.bool_)):
        return "true" if value else "false"
    if isinstance(value, (np.floating, float)):
        if np.isnan(value):
            return ""
        return f"{float(value):.8g}"
    if isinstance(value, (np.integer, int)):
        return str(int(value))
    if isinstance(value, (list, tuple)):
        return ";".join(str(v) for v in value)
    return str(value)


def scale_footer(scale: PixelScale) -> str:
    return (
        f"scan={scale.scan_size_mm:g} mm / {scale.pixel_width_px} px "
        f"= {scale.um_per_px:.4f} um/px"
    )
