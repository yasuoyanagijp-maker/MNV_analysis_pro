"""
Phansalkar adaptive binarization filter

ImageJ equivalent: AUTO_LOCAL_THRESHOLD (Phansalkar method)
"""

import numpy as np
from scipy import ndimage


class PhansalkarBinarizer:
    """
    Phansalkar適応二値化（VD解析専用）

    ImageJマクロの対応箇所:
    - binarizeAdaptive() 関数
    - AUTO_LOCAL_THRESHOLD (Phansalkar method)

    Reference:
    Phansalkar et al. (2011) "Adaptive local thresholding for detection
    of nuclei in diversity stained cytology images"
    """

    def __init__(self, window_radius: int = 15, k: float = 0.25, r: float = 0.5):
        """
        Args:
            window_radius: 適応ウィンドウ半径（ピクセル）
            k: Phansalkar k パラメータ（標準偏差の重み）
            r: Phansalkar R パラメータ（動的範囲）
               - uint8画像の場合: 128.0 (= 0.5 * 256)
               - 正規化画像(0-1)の場合: 0.5
        """
        self.window_radius = window_radius
        self.k = k
        self.r = r

    def binarize(self, image: np.ndarray) -> np.ndarray:
        """
        Phansalkar適応二値化を実行

        Args:
            image: グレースケール画像 (H×W uint8)

        Returns:
            binary: 二値画像 (H×W bool)

        アルゴリズム:
            threshold = mean * (1 + k * ((std / r) - 1))
            binary = image > threshold
        """
        if image.dtype != np.uint8:
            image = image.astype(np.uint8)

        # 浮動小数点に変換
        img_float = image.astype(np.float64)

        # カーネルサイズ
        kernel_size = 2 * self.window_radius + 1

        # 局所平均の計算（Box Filter）
        mean = ndimage.uniform_filter(img_float, size=kernel_size, mode="reflect")

        # 局所標準偏差の計算
        mean_sq = ndimage.uniform_filter(img_float**2, size=kernel_size, mode="reflect")
        variance = np.maximum(mean_sq - mean**2, 0)
        std = np.sqrt(variance)

        # Phansalkar閾値計算
        # threshold = mean * (1 + k * ((std / r) - 1))
        threshold = mean * (1.0 + self.k * ((std / self.r) - 1.0))

        # 二値化
        binary = img_float > threshold

        return binary.astype(bool)

    def get_threshold_map(self, image: np.ndarray) -> np.ndarray:
        """
        閾値マップを取得（デバッグ用）

        Args:
            image: グレースケール画像

        Returns:
            threshold_map: 各ピクセルの閾値 (H×W float)
        """
        img_float = image.astype(np.float64)
        kernel_size = 2 * self.window_radius + 1

        mean = ndimage.uniform_filter(img_float, size=kernel_size, mode="reflect")
        mean_sq = ndimage.uniform_filter(img_float**2, size=kernel_size, mode="reflect")
        variance = np.maximum(mean_sq - mean**2, 0)
        std = np.sqrt(variance)

        threshold_map = mean * (1.0 + self.k * ((std / self.r) - 1.0))

        return threshold_map
