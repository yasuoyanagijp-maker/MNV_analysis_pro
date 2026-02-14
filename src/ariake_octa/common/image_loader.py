"""
Common utilities for image loading

Supports TIFF, JPEG, PNG formats with automatic bit depth conversion
"""

from pathlib import Path

import numpy as np
import tifffile
from PIL import Image


class ImageLoader:
    """
    画像読み込みユーティリティ

    対応形式: TIFF, JPEG, PNG
    自動変換: 16-bit → 8-bit
    """

    @staticmethod
    def load(image_path: str) -> np.ndarray:
        """
        画像を読み込み、8-bit グレースケールに変換

        Args:
            image_path: 画像ファイルパス

        Returns:
            image: (H×W) numpy array, dtype=uint8

        Raises:
            FileNotFoundError: ファイルが存在しない
            ValueError: サポートされていない形式
        """
        path = Path(image_path)

        if not path.exists():
            raise FileNotFoundError(f"画像ファイルが見つかりません: {image_path}")

        suffix = path.suffix.lower()

        # TIFF形式
        if suffix in [".tif", ".tiff"]:
            image = tifffile.imread(str(path))
        # JPEG/PNG形式
        elif suffix in [".jpg", ".jpeg", ".png"]:
            image = np.array(Image.open(str(path)))
        else:
            raise ValueError(f"サポートされていない画像形式: {suffix}")

        # グレースケール変換
        if image.ndim == 3:
            # RGB → Grayscale (luminosity method)
            image = np.dot(image[..., :3], [0.299, 0.587, 0.114]).astype(np.uint8)

        # 16-bit → 8-bit変換
        if image.dtype == np.uint16:
            image = (image / 256).astype(np.uint8)

        return image.astype(np.uint8)

    @staticmethod
    def load_multiple(image_paths: list) -> list:
        """
        複数画像を読み込み

        Args:
            image_paths: 画像ファイルパスのリスト

        Returns:
            images: numpy配列のリスト
        """
        return [ImageLoader.load(path) for path in image_paths]

    @staticmethod
    def get_pixel_size_from_metadata(image_path: str) -> float:
        """
        TIFFメタデータからピクセルサイズを取得

        Args:
            image_path: TIFF画像パス

        Returns:
            pixel_size_um: ピクセルサイズ (μm/pixel)

        Note:
            メタデータがない場合は標準値0.744 μm/pixelを返す
        """
        path = Path(image_path)

        if path.suffix.lower() not in [".tif", ".tiff"]:
            return 0.744  # デフォルト値

        try:
            with tifffile.TiffFile(str(path)) as tif:
                # ImageDescriptionからピクセルサイズを抽出
                if hasattr(tif.pages[0], "tags"):
                    tags = tif.pages[0].tags
                    if "XResolution" in tags:
                        x_res = tags["XResolution"].value
                        if isinstance(x_res, tuple):
                            # ピクセル/mm から μm/pixel へ変換
                            pixel_size_um = (x_res[1] / x_res[0]) * 1000
                            return pixel_size_um
        except Exception:
            pass

        return 0.744  # デフォルト値
