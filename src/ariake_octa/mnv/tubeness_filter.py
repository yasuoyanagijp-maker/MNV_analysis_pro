"""
Tubeness Filter (Frangi vesselness filter)

Multi-scale Hessian-based vessel enhancement
"""

import multiprocessing
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List

import numpy as np
from skimage.feature import hessian_matrix, hessian_matrix_eigvals


class TubenessFilter:
    """
    Tubenessフィルタ（Frangi vesselness filter）

    ImageJマクロの対応箇所:
    - Frangi Vesselness filter
    - マルチスケール処理（scales=[1, 2, 3]）

    Reference:
    Frangi et al. (1998) "Multiscale vessel enhancement filtering"
    """

    def __init__(
        self,
        scales: List[float] = [1.0, 2.0, 3.0],
        beta: float = 0.5,
        c: float = 15.0,
        use_parallel: bool = True,
        max_workers: int = None,
    ):
        """
        Args:
            scales: スケールのリスト（血管の太さに対応、ピクセル単位）
            beta: 形状比の重み（デフォルト: 0.5）
            c: 構造強度の重み（デフォルト: 15）
            use_parallel: 並列処理を使用するか（デフォルト: True）
            max_workers: 並列処理の最大ワーカー数（Noneの場合はCPUコア数）
        """
        self.scales = scales
        self.beta = beta
        self.c = c
        self.use_parallel = use_parallel
        self.max_workers = max_workers or min(len(scales), multiprocessing.cpu_count())

    def apply(self, image: np.ndarray, scales: List[float] = None) -> np.ndarray:
        """
        Tubenessフィルタを適用（マルチスケール）

        Args:
            image: 入力画像 (H×W uint8)
            scales: スケールのリスト（Noneの場合はデフォルト値）

        Returns:
            tubeness: Tubeness応答画像 (H×W uint8)

        アルゴリズム:
            1. 各スケールでHessian行列を計算
            2. 固有値から血管応答を計算
            3. 最大応答を選択（各ピクセル）
            4. 正規化（0-255）
        """
        if scales is None:
            scales = self.scales

        if image.dtype != np.uint8:
            image = image.astype(np.uint8)

        # 浮動小数点に変換
        img_float = image.astype(np.float64) / 255.0

        # 各スケールの応答を計算（並列処理対応）
        if self.use_parallel and len(scales) > 1:
            responses = self._compute_parallel(img_float, scales)
        else:
            responses = []
            for sigma in scales:
                response = self._single_scale_tubeness(img_float, sigma)
                responses.append(response)

        # 最大応答を選択（各ピクセルで最も強い応答）
        max_response = np.maximum.reduce(responses)

        # 正規化（0-255）
        if max_response.max() > 0:
            normalized = (max_response / max_response.max()) * 255
            tubeness = normalized.astype(np.uint8)
        else:
            tubeness = np.zeros_like(image, dtype=np.uint8)

        return tubeness

    def _single_scale_tubeness(self, image: np.ndarray, sigma: float) -> np.ndarray:
        """
        単一スケールでのTubeness計算

        Args:
            image: 正規化済み画像（0-1）
            sigma: ガウシアンスケール

        Returns:
            tubeness: Tubeness応答（0-1）
        """
        # Hessian行列を計算
        H_elems = hessian_matrix(image, sigma=sigma, order="rc")
        eigenvalues = hessian_matrix_eigvals(H_elems)

        # λ1, λ2を取得（|λ1| >= |λ2|）
        lambda1 = eigenvalues[0]
        lambda2 = eigenvalues[1]

        # 絶対値でソート
        abs_lambda1 = np.abs(lambda1)
        abs_lambda2 = np.abs(lambda2)

        # λ1とλ2を入れ替え（|λ1| >= |λ2|を保証）
        mask = abs_lambda1 < abs_lambda2
        lambda1_sorted = np.where(mask, lambda2, lambda1)
        lambda2_sorted = np.where(mask, lambda1, lambda2)

        # 形状比（管状構造の特異性）
        # R_B = |λ2| / |λ1|
        # R_B が小さい = 管状構造（λ2 << λ1）
        R_B = np.abs(lambda2_sorted) / (np.abs(lambda1_sorted) + 1e-10)

        # 構造強度（ノイズと区別）
        # S = sqrt(λ1² + λ2²)
        S = np.sqrt(lambda1_sorted**2 + lambda2_sorted**2)

        # Tubeness計算
        # V = exp(-R_B²/2β²) × (1 - exp(-S²/2c²))
        vesselness = np.exp(-(R_B**2) / (2 * self.beta**2)) * (
            1 - np.exp(-(S**2) / (2 * self.c**2))
        )

        # 暗い血管のみを検出（λ2 < 0）
        # λ2 > 0 は明るい管状構造（不要）
        vesselness[lambda2_sorted > 0] = 0

        return vesselness

    def _compute_parallel(
        self, image: np.ndarray, scales: List[float]
    ) -> List[np.ndarray]:
        """
        並列処理でマルチスケール応答を計算

        Args:
            image: 正規化済み画像（0-1）
            scales: スケールのリスト

        Returns:
            responses: 各スケールの応答リスト
        """
        responses = [None] * len(scales)

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 各スケールの処理を投入
            future_to_idx = {
                executor.submit(self._single_scale_tubeness, image, sigma): i
                for i, sigma in enumerate(scales)
            }

            # 結果を収集
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    responses[idx] = future.result()
                except Exception as e:
                    print(f"Error computing tubeness at scale {scales[idx]}: {e}")
                    # エラー時はゼロ配列を返す
                    responses[idx] = np.zeros_like(image)

        return responses

    def get_scale_specific_response(
        self, image: np.ndarray, scale_index: int = 0
    ) -> np.ndarray:
        """
        特定スケールの応答を取得（デバッグ用）

        Args:
            image: 入力画像
            scale_index: スケールのインデックス

        Returns:
            response: 指定スケールの応答画像
        """
        if scale_index >= len(self.scales):
            raise ValueError(f"Scale index {scale_index} out of range")

        img_float = image.astype(np.float64) / 255.0
        sigma = self.scales[scale_index]
        response = self._single_scale_tubeness(img_float, sigma)

        # 正規化
        if response.max() > 0:
            response = (response / response.max()) * 255

        return response.astype(np.uint8)
