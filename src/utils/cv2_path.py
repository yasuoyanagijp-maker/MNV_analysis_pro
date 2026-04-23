"""
OpenCV 画像読み込み (Unicode / 非ASCII パス対応).

- cv2.imread: 非ASCII パスで失敗しやすい。
- imdecode(バイト列): 多くのケースで有効。一部 PNG / 解像度で失敗する場合あり。
- Pillow Image.open(path): プロジェクト内 ImageLoader と同じく、パス上の非ASCIIに強い。

is_file() の事前チェックは、OneDrive や NFD 正規化の違いで誤爆するため使わない。
"""

import cv2
import numpy as np
from pathlib import Path
from typing import Optional


def imread_bgr(path: str) -> Optional[np.ndarray]:
    """BGR uint8 3ch、失敗時 None."""
    p = Path(path)
    if not p.exists():
        return None
    try:
        data = p.read_bytes()
    except OSError as e:
        print(f"cv2_path.imread_bgr: read_bytes OSError: {e!r} path={path!r}", flush=True)
        return None
    if len(data) < 8:
        return None
    arr = np.frombuffer(data, dtype=np.uint8)
    bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if bgr is not None and bgr.size > 0:
        return bgr
    # Pillow フォールバック (image_loader 系と同様、Main Report2.png 等で imdecode が失敗しうる)
    try:
        from PIL import Image

        with Image.open(p) as pil:
            if pil.mode in ("RGBA", "LA", "P", "PA"):
                pil = pil.convert("RGB")
            elif pil.mode != "RGB":
                pil = pil.convert("RGB")
            rgb = np.asarray(pil)
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    except Exception as e:
        print(f"cv2_path.imread_bgr: Pillow fallback failed: {e!r} path={path!r}", flush=True)
        return None


def imread_grayscale(path: str) -> Optional[np.ndarray]:
    """グレースケール 8bit、失敗時 None。"""
    p = Path(path)
    if not p.exists():
        return None
    try:
        data = p.read_bytes()
    except OSError as e:
        print(f"cv2_path.imread_grayscale: read_bytes OSError: {e!r} path={path!r}", flush=True)
        return None
    if len(data) < 8:
        return None
    arr = np.frombuffer(data, dtype=np.uint8)
    g = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if g is not None and g.size > 0:
        return g
    try:
        from PIL import Image

        with Image.open(p) as pil:
            g2 = np.asarray(pil.convert("L"))
        return g2.astype(np.uint8)
    except Exception as e:
        print(f"cv2_path.imread_grayscale: Pillow fallback failed: {e!r} path={path!r}", flush=True)
        return None
