"""
MNV image preprocessing

CLAHE (Contrast Limited Adaptive Histogram Equalization) + Background Subtraction
"""

import numpy as np
from scipy import ndimage
from skimage import exposure


class MNVPreprocessor:
    """
    MNV画像前処理（CLAHE + 背景除去）

    ImageJマクロの対応箇所:
    - preprocessImage() 関数
    - CLAHE: blocksize=127, clip_limit=3
    - Background Subtraction: Gaussian blur sigma=5.0
    """

    def __init__(
        self,
        clahe_clip_limit: float = 3.0,
        clahe_blocksize: int = 127,
        background_sigma: float = 5.0,
    ):
        """
        Args:
            clahe_clip_limit: CLAHEクリップリミット（0-100、ImageJ互換）
            clahe_blocksize: CLAHEブロックサイズ（ピクセル）
            background_sigma: 背景推定用ガウシアンブラーのσ
        """
        self.clahe_clip_limit = clahe_clip_limit
        self.clahe_blocksize = clahe_blocksize
        self.background_sigma = background_sigma

    def preprocess(self, image: np.ndarray) -> np.ndarray:
        """
        前処理を実行

        Args:
            image: 入力画像 (H×W uint8)

        Returns:
            preprocessed: 前処理済み画像 (H×W uint8)

        処理順序:
            1. CLAHE（コントラスト強調）
            2. ガウシアンブラーで背景推定
            3. 背景除去（元画像 - 背景）
            4. 正規化（0-255）
        """
        if image.dtype != np.uint8:
            image = image.astype(np.uint8)

        # Step 1: CLAHE
        # scikit-imageのCLAHEはclip_limitが0-1の範囲なので変換
        clip_limit_normalized = self.clahe_clip_limit / 100.0

        clahe_image = exposure.equalize_adapthist(
            image / 255.0,
            kernel_size=self.clahe_blocksize,
            clip_limit=clip_limit_normalized,
        )
        clahe_image = (clahe_image * 255).astype(np.uint8)

        # Step 2: 背景推定（ガウシアンブラー）
        background = ndimage.gaussian_filter(
            clahe_image.astype(float), sigma=self.background_sigma
        )

        # Step 3: 背景除去
        subtracted = np.clip(clahe_image.astype(float) - background, 0, 255)

        # Step 4: 正規化（0-255にリスケール）
        if subtracted.max() > subtracted.min():
            subtracted = (subtracted - subtracted.min()) / (
                subtracted.max() - subtracted.min()
            )
            preprocessed = (subtracted * 255).astype(np.uint8)
        else:
            preprocessed = subtracted.astype(np.uint8)

        return preprocessed

    def get_clahe_only(self, image: np.ndarray) -> np.ndarray:
        """
        CLAHEのみを適用（デバッグ用）

        Args:
            image: 入力画像

        Returns:
            clahe_image: CLAHE適用後の画像
        """
        clip_limit_normalized = self.clahe_clip_limit / 100.0

        clahe_image = exposure.equalize_adapthist(
            image / 255.0,
            kernel_size=self.clahe_blocksize,
            clip_limit=clip_limit_normalized,
        )

        return (clahe_image * 255).astype(np.uint8)

    def get_background(self, image: np.ndarray) -> np.ndarray:
        """
        背景画像を取得（デバッグ用）

        Args:
            image: CLAHE適用済み画像

        Returns:
            background: 背景推定画像
        """
        background = ndimage.gaussian_filter(
            image.astype(float), sigma=self.background_sigma
        )

        return background.astype(np.uint8)
