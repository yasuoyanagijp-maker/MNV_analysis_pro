"""
LoG (Laplacian of Gaussian) Filter

FeatureJ Laplacian compatible implementation
"""

import numpy as np
from scipy import ndimage


class LoGFilter:
    """
    LoG (Laplacian of Gaussian) フィルタ

    ImageJマクロの対応箇所:
    - FeatureJ Laplacian (sigma=1)
    - processMexicanHatImproved() 関数

    Note:
    - ImageJの"Mexican Hat"は実際にはLoG（Laplacian of Gaussian）
    - FeatureJ Laplacianと互換性あり
    """

    def __init__(self, sigma: float = 1.0):
        """
        Args:
            sigma: ガウシアンσ（標準値: 1.0）
        """
        self.sigma = sigma

    def apply(self, image: np.ndarray, sigma: float = None) -> np.ndarray:
        """
        LoGフィルタを適用

        Args:
            image: 入力画像 (H×W uint8)
            sigma: ガウシアンσ（Noneの場合はデフォルト値を使用）

        Returns:
            filtered: フィルタ済み画像 (H×W uint8)

        アルゴリズム:
            1. ガウシアンブラー
            2. Laplacian演算（2次微分）
            3. 絶対値化（血管は暗→明になる）
            4. 正規化（0-255）
        """
        if sigma is None:
            sigma = self.sigma

        if image.dtype != np.uint8:
            image = image.astype(np.uint8)

        # 浮動小数点に変換
        img_float = image.astype(np.float64)

        # Step 1: ガウシアンブラー
        blurred = ndimage.gaussian_filter(img_float, sigma=sigma)

        # Step 2: Laplacian演算（2次微分）
        # ndimage.laplace は ∇²f を計算
        laplacian = ndimage.laplace(blurred)

        # Step 3: 絶対値化
        # 血管（暗い領域）は負の2次微分を持つので、絶対値で反転
        abs_laplacian = np.abs(laplacian)

        # Step 4: 正規化（0-255）
        if abs_laplacian.max() > abs_laplacian.min():
            normalized = (abs_laplacian - abs_laplacian.min()) / (
                abs_laplacian.max() - abs_laplacian.min()
            )
            filtered = (normalized * 255).astype(np.uint8)
        else:
            filtered = np.zeros_like(image, dtype=np.uint8)

        return filtered

    def apply_multi_scale(
        self, image: np.ndarray, sigmas: list = [0.5, 1.0, 2.0]
    ) -> np.ndarray:
        """
        マルチスケールLoGフィルタ（最大値投影）

        Args:
            image: 入力画像
            sigmas: σのリスト

        Returns:
            filtered: 最大値投影後の画像
        """
        results = []

        for sigma in sigmas:
            filtered = self.apply(image, sigma=sigma)
            results.append(filtered)

        # 最大値投影
        max_projection = np.maximum.reduce(results)

        return max_projection

    def get_raw_laplacian(self, image: np.ndarray, sigma: float = None) -> np.ndarray:
        """
        生のLaplacian値を取得（デバッグ用）

        Args:
            image: 入力画像
            sigma: ガウシアンσ

        Returns:
            laplacian: Laplacian画像（正負の値を含む）
        """
        if sigma is None:
            sigma = self.sigma

        img_float = image.astype(np.float64)
        blurred = ndimage.gaussian_filter(img_float, sigma=sigma)
        laplacian = ndimage.laplace(blurred)

        return laplacian
