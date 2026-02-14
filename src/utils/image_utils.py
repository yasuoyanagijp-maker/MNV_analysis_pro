"""画像処理の基本ユーティリティ"""

import numpy as np
from skimage import img_as_float, img_as_ubyte, io


class ImageProcessor:
    """画像処理の基本機能"""

    @staticmethod
    def load_image(path: str, as_gray: bool = True) -> np.ndarray:
        """画像を読み込む"""
        if as_gray:
            img = io.imread(path, as_gray=True)
            if img.dtype != np.uint8:
                img = img_as_ubyte(img)
        else:
            img = io.imread(path)
        return img

    @staticmethod
    def ensure_8bit(image: np.ndarray) -> np.ndarray:
        """8bit画像に変換"""
        if image.dtype == np.uint8:
            return image
        return img_as_ubyte(img_as_float(image))

    @staticmethod
    def ensure_binary(image: np.ndarray) -> np.ndarray:
        """二値画像に変換"""
        if image.dtype == bool:
            return image.astype(np.uint8) * 255
        if len(np.unique(image)) == 2:
            return (image > 0).astype(np.uint8) * 255
        return image

    @staticmethod
    def normalize(image: np.ndarray) -> np.ndarray:
        """正規化 (0-255)"""
        img_min = image.min()
        img_max = image.max()
        if img_max - img_min == 0:
            return np.zeros_like(image)
        normalized = 255 * (image - img_min) / (img_max - img_min)
        return normalized.astype(np.uint8)


class ScaleManager:
    """スケール管理クラス"""

    def __init__(self, image_width: int, scale_mm: float):
        """
        Parameters:
        -----------
        image_width : int
            画像の幅（ピクセル）
        scale_mm : float
            画像の実寸法（mm）
        """
        self.image_width = image_width
        self.scale_mm = scale_mm
        self.mm_per_pixel = scale_mm / image_width
        self.pixel_size_um = (scale_mm * 1000) / image_width

    def pixels_to_mm(self, pixels: float) -> float:
        """ピクセルをmmに変換"""
        return pixels * self.mm_per_pixel

    def mm_to_pixels(self, mm: float) -> int:
        """mmをピクセルに変換"""
        return int(mm / self.mm_per_pixel)

    def pixels_to_um(self, pixels: float) -> float:
        """ピクセルをμmに変換"""
        return pixels * self.pixel_size_um
