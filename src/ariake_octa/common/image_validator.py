"""
Image quality validation utilities
"""

from typing import Dict

import numpy as np


class ImageQualityValidator:
    """
    入力画像の品質を検証

    検証項目:
    - ピクセルサイズの妥当性（0.5-1.5 μm/pixel）
    - SNR（Signal-to-Noise Ratio）
    - コントラスト
    """

    def __init__(
        self,
        min_pixel_size_um: float = 0.5,
        max_pixel_size_um: float = 1.5,
        min_snr_db: float = 20.0,
        min_contrast: float = 0.3,
    ):
        """
        Args:
            min_pixel_size_um: 最小ピクセルサイズ
            max_pixel_size_um: 最大ピクセルサイズ
            min_snr_db: 最小SNR（dB）
            min_contrast: 最小コントラスト
        """
        self.min_pixel_size_um = min_pixel_size_um
        self.max_pixel_size_um = max_pixel_size_um
        self.min_snr_db = min_snr_db
        self.min_contrast = min_contrast

    def validate(
        self, image: np.ndarray, pixel_size_um: float, analysis_type: str = "VD"
    ) -> Dict:
        """
        画像品質を検証

        Args:
            image: 入力画像 (H×W uint8)
            pixel_size_um: ピクセルサイズ (μm/pixel)
            analysis_type: 'VD' または 'MNV'

        Returns:
            {
                'is_valid': bool,
                'snr_db': float,
                'contrast': float,
                'warnings': list[str]
            }
        """
        warnings = []

        # 画像サイズチェック
        h, w = image.shape
        if h < 512 or w < 512:
            warnings.append(f"画像サイズが小さい: {w}×{h} px < 512×512 px")

        # ピクセルサイズチェック
        if not (self.min_pixel_size_um <= pixel_size_um <= self.max_pixel_size_um):
            warnings.append(
                f"ピクセルサイズが範囲外: {pixel_size_um:.3f} μm/pixel "
                f"(推奨: {self.min_pixel_size_um}-{self.max_pixel_size_um})"
            )

        # SNR計算
        signal = image.mean()
        noise = image.std()
        snr_db = 20 * np.log10(signal / (noise + 1e-10)) if noise > 0 else 0

        min_snr = 25.0 if analysis_type == "MNV" else 20.0
        if snr_db < min_snr:
            warnings.append(f"SNRが低い: {snr_db:.1f} dB < {min_snr} dB")

        # コントラスト計算
        contrast = (image.max() - image.min()) / (image.max() + image.min() + 1e-10)

        if contrast < self.min_contrast:
            warnings.append(f"コントラストが低い: {contrast:.3f} < {self.min_contrast}")

        # ダイナミックレンジチェック
        unique_values = len(np.unique(image))
        if unique_values < 50:
            warnings.append(f"ダイナミックレンジが狭い: {unique_values} unique values")

        return {
            "is_valid": len(warnings) == 0,
            "snr_db": snr_db,
            "contrast": contrast,
            "dynamic_range": unique_values,
            "warnings": warnings,
        }

    def validate_pair(self, superficial: np.ndarray, deep: np.ndarray) -> Dict:
        """
        ペア画像（VD用）の検証

        Args:
            superficial: 表層画像
            deep: 深層画像

        Returns:
            検証結果辞書
        """
        warnings = []

        # サイズ一致チェック
        if superficial.shape != deep.shape:
            warnings.append(
                f"画像ペアのサイズ不一致: "
                f"Superficial {superficial.shape} vs Deep {deep.shape}"
            )

        # 各画像の品質チェックは省略（呼び出し側で実施）

        return {"is_valid": len(warnings) == 0, "warnings": warnings}
