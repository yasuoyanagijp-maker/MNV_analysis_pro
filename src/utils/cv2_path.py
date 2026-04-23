"""
OpenCV 画像読み込み (Unicode / 非ASCII パス対応).

cv2.imread() は多くの環境で非ASCIIを含むパスを扱えず None を返す。
Path.read_bytes() + imdecode を使う。
"""

import cv2
import numpy as np
from pathlib import Path
from typing import Optional


def imread_bgr(path: str) -> Optional[np.ndarray]:
    """BGR 8bit、失敗時 None."""
    p = Path(path)
    if not p.is_file():
        return None
    try:
        data = p.read_bytes()
    except OSError:
        return None
    if len(data) < 8:
        return None
    arr = np.frombuffer(data, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def imread_grayscale(path: str) -> Optional[np.ndarray]:
    """グレースケール 8bit、失敗時 None."""
    p = Path(path)
    if not p.is_file():
        return None
    try:
        data = p.read_bytes()
    except OSError:
        return None
    if len(data) < 8:
        return None
    arr = np.frombuffer(data, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
