"""
Filter Fusion

Combine LoG and Tubeness filter results
"""

from typing import List

import numpy as np


class FilterFusion:
    """
    2フィルタ融合（LoG + Tubeness）

    ImageJマクロの対応箇所:
    - Mexican Hat + Tubeness の融合
    - 論理和（OR）または加重和
    """

    def __init__(self, method: str = "weighted_sum", weights: List[float] = [0.5, 0.5]):
        """
        Args:
            method: 融合方法 ('weighted_sum', 'max', 'logical_or')
            weights: 加重和の重み [LoG, Tubeness]
        """
        self.method = method
        self.weights = weights

        # 重みの正規化
        if method == "weighted_sum":
            total = sum(weights)
            self.weights = [w / total for w in weights]

    def fuse(
        self,
        log_result: np.ndarray,
        tubeness_result: np.ndarray,
        weights: List[float] = None,
    ) -> np.ndarray:
        """
        2つのフィルタ結果を融合

        Args:
            log_result: LoGフィルタ結果 (H×W uint8)
            tubeness_result: Tubenessフィルタ結果 (H×W uint8)
            weights: 加重和の重み（Noneの場合はデフォルト値）

        Returns:
            fused: 融合結果 (H×W uint8)
        """
        if log_result.shape != tubeness_result.shape:
            raise ValueError(
                f"画像サイズが一致しません: "
                f"LoG {log_result.shape} vs Tubeness {tubeness_result.shape}"
            )

        if weights is None:
            weights = self.weights

        # 融合方法に応じて処理
        if self.method == "weighted_sum":
            fused = self._weighted_sum(log_result, tubeness_result, weights)
        elif self.method == "max":
            fused = self._max_fusion(log_result, tubeness_result)
        elif self.method == "logical_or":
            fused = self._logical_or(log_result, tubeness_result)
        else:
            raise ValueError(f"Unknown fusion method: {self.method}")

        return fused

    def _weighted_sum(
        self, img1: np.ndarray, img2: np.ndarray, weights: List[float]
    ) -> np.ndarray:
        """
        加重和による融合

        fused = w1 × img1 + w2 × img2
        """
        img1_float = img1.astype(np.float64)
        img2_float = img2.astype(np.float64)

        fused_float = weights[0] * img1_float + weights[1] * img2_float
        fused = np.clip(fused_float, 0, 255).astype(np.uint8)

        return fused

    def _max_fusion(self, img1: np.ndarray, img2: np.ndarray) -> np.ndarray:
        """
        最大値による融合

        fused = max(img1, img2)
        """
        fused = np.maximum(img1, img2)
        return fused

    def _logical_or(self, img1: np.ndarray, img2: np.ndarray) -> np.ndarray:
        """
        論理和による融合（二値画像用）

        fused = img1 OR img2
        """
        # 閾値処理（128以上を血管とみなす）
        binary1 = img1 > 127
        binary2 = img2 > 127

        # 論理和
        fused_binary = binary1 | binary2

        # uint8に戻す
        fused = (fused_binary.astype(np.uint8)) * 255

        return fused

    def get_contribution_map(
        self, log_result: np.ndarray, tubeness_result: np.ndarray
    ) -> np.ndarray:
        """
        各フィルタの寄与度マップを取得（デバッグ用）

        Returns:
            contribution: (H×W) 0=LoG優勢, 1=Tubeness優勢
        """
        log_float = log_result.astype(np.float64)
        tubeness_float = tubeness_result.astype(np.float64)

        # Tubenessの寄与度（0-1）
        total = log_float + tubeness_float + 1e-10
        contribution = tubeness_float / total

        return contribution
