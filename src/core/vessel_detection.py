"""
血管検出モジュール
MNV画像から血管を検出・抽出
"""

import logging
import time
from typing import Dict, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

from .preprocessing import AdaptiveThresholder, BinaryPostProcessor, FilterBank


class MNVPreprocessor:
    """
    MNV画像の前処理クラス
    ImageJマクロの performImagePreprocessing に対応
    """

    def __init__(
        self,
        mexican_hat_sigma: float = 1.0,
        tubeness_sigma: float = 1.0,
        use_multiscale_mexican_hat: bool = True,  # 太い血管ロス防止（sigma 1,1.5,2 の max）
        use_multiscale_tubeness: bool = False,  # ImageJ準拠：シングルスケール
        tubeness_sigmas: Tuple[float, ...] = (
            0.8,
            1.2,
            2.0,
        ),  # マルチスケール時のみ使用
        gaussian_blur: bool = False,
        gaussian_sigma: float = 1.0,
        use_parallel: bool = True,
        filter_params: Optional[Dict] = None,
    ):  # 並列処理をデフォルトで有効化
        """
        Parameters:
        -----------
        mexican_hat_sigma : float
            Mexican Hat filterのsigma値（シングルスケール時）
        use_multiscale_mexican_hat : bool
            マルチスケールMexican Hatを使用するか（太い血管のロス防止、デフォルトTrue）
        tubeness_sigma : float
            Tubeness filterのsigma値（マルチスケール不使用時）
        use_multiscale_tubeness : bool
            マルチスケールTubenessを使用するか
        tubeness_sigmas : tuple
            マルチスケールTubenessのsigmaリスト（デフォルト: 3スケール）
        gaussian_blur : bool
            ガウシアンブラーを適用するか
        gaussian_sigma : float
            ガウシアンブラーのsigma値
        use_parallel : bool
            並列処理を使用するか（デフォルト: True）
        filter_params : dict, optional
            FilterBank用オプション: percentile_low, percentile_high,
            otsu_scale, sauvola_k
        """
        self.mexican_hat_sigma = mexican_hat_sigma
        self.tubeness_sigma = tubeness_sigma
        self.use_multiscale_mexican_hat = use_multiscale_mexican_hat
        self.use_multiscale_tubeness = use_multiscale_tubeness
        self.tubeness_sigmas = tubeness_sigmas
        self.gaussian_blur = gaussian_blur
        self.gaussian_sigma = gaussian_sigma
        self.use_parallel = use_parallel
        self.filter_params = filter_params or {}

        self.filter_bank = FilterBank()
        self.thresholder = AdaptiveThresholder()
        self.postprocessor = BinaryPostProcessor()

    def preprocess_mnv(
        self, image: np.ndarray, roi_mask: np.ndarray
    ) -> Dict[str, np.ndarray]:
        """
        MNV画像の完全前処理パイプライン

        Parameters:
        -----------
        image : np.ndarray
            入力画像（8-bit グレースケール）
        roi_mask : np.ndarray
            ROIマスク

        Returns:
        --------
        results : dict
            'mex_hat': Mexican Hat フィルタ結果（二値）
            'tubeness': Tubeness フィルタ結果（二値）
            'binary': 最終二値画像
        """
        print("  Preprocessing MNV image...")

        # 1. Mexican Hat Filter（ImageJ processMexicanHatImproved 互換）
        # ImageJ preproc(): Despeckle（入力へのノイズ除去）を LoG の前に適用
        image_for_mex = cv2.medianBlur(image, 3)
        # マルチスケール時: sigma 1,1.5,2 の max で太い血管ロス防止
        filter_start = time.time()
        print("    - Applying Mexican Hat filter...", end=" ", flush=True)
        _mh_params = {
            k: v
            for k, v in self.filter_params.items()
            if k in ("percentile_low", "percentile_high", "otsu_scale",
                      "normalization")
        }
        if self.use_multiscale_mexican_hat:
            mex_hat_binary = self.filter_bank.mexican_hat_multiscale(
                image_for_mex, sigmas=(1.0, 1.5, 2.0), **_mh_params
            )
        else:
            mex_hat_binary = self.filter_bank.mexican_hat(
                image_for_mex, sigma=self.mexican_hat_sigma, **_mh_params
            )
        mex_hat_binary = self.postprocessor.denoise_improved(
            mex_hat_binary, max_iterations=15, remove_small_particles=True
        )
        print(f"[{time.time() - filter_start:.2f}s]")

        # 2. Tubeness Filter（ImageJ processTubenessImproved 互換）
        # ImageJ: Tubeness -> Sauvola(k=0.5) -> denoiseImproved(1)
        # tubeness_filter_accurate が Sauvola 適用済み二値を返す
        filter_start = time.time()
        print("    - Applying Tubeness filter...", end=" ", flush=True)
        _tub_params = {
            k: v
            for k, v in self.filter_params.items()
            if k
            in (
                "percentile_low",
                "percentile_high",
                "sauvola_k",
                "sigma",
                "beta",
                "c",
                "normalization",
            )
        }
        _tub_params.setdefault("sigma", self.tubeness_sigma)
        tubeness_binary = self.filter_bank.tubeness_filter_accurate(
            image, **_tub_params
        )
        # Tubeness後denoise: filter_paramsで強度を制御可能
        denoise_mode = self.filter_params.get("tubeness_denoise", "full")
        if denoise_mode == "none":
            pass
        elif denoise_mode == "weak":
            tubeness_binary = self.postprocessor.denoise_improved(
                tubeness_binary, max_iterations=3, remove_small_particles=False
            )
        else:
            tubeness_binary = self.postprocessor.denoise_improved(
                tubeness_binary, max_iterations=15, remove_small_particles=True
            )
        print(f"[{time.time() - filter_start:.2f}s]")

        # 3. 結合（ImageJ createBinaryImageImproved 互換）
        # ImageJ: OR -> denoiseImproved(0) = Despeckle のみ
        filter_start = time.time()
        print("    - Combining filters...", end=" ", flush=True)
        binary = self._combine_filters(mex_hat_binary, tubeness_binary)
        print(f"[{time.time() - filter_start:.2f}s]")

        # 4. ROIマスク適用は行わない（バイナリ画像はROIクロップせず出力）
        # 注意: ImageJではOR結合後にdenoiseをかけない
        print("  Preprocessing completed.")
        return {
            "mex_hat": mex_hat_binary,
            "tubeness": tubeness_binary,
            "binary": binary,
            "mex_hat_gray": mex_hat_binary,  # compatibility
            "tubeness_gray": tubeness_binary,  # compatibility (same as tubeness)
        }

    def _process_mexican_hat_with_gray(self, image: np.ndarray):
        # ガウシアンブラー（オプション）
        if self.gaussian_blur:
            image_blur = cv2.GaussianBlur(image, (0, 0), sigmaX=self.gaussian_sigma)
        else:
            image_blur = image.copy()
        # Mexican Hat Filter適用
        mex_hat = self.filter_bank.mexican_hat(image_blur, sigma=self.mexican_hat_sigma)
        # 二値化（大津の方法）
        _, binary = cv2.threshold(mex_hat, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        # Denoise Improved
        binary = self.postprocessor.denoise_improved(
            binary, max_iterations=15, remove_small_particles=True
        )
        return mex_hat, binary

    def _process_tubeness_single_with_gray(self, image: np.ndarray):
        tubeness = self.filter_bank.tubeness_filter_accurate(
            image, sigma=self.tubeness_sigma, beta=0.5, c=15
        )
        binary = self.thresholder.sauvola(
            tubeness, radius=15, k=0.0, white_objects=True
        )
        binary = self.postprocessor.denoise_improved(
            binary, max_iterations=15, remove_small_particles=True
        )
        return tubeness, binary

    def _process_tubeness_multiscale_with_gray(self, image: np.ndarray):
        tubeness = self.filter_bank.multiscale_tubeness(
            image,
            sigmas=self.tubeness_sigmas,
            beta=0.5,
            c=15,
            use_parallel=self.use_parallel,
        )
        binary = self.thresholder.sauvola(
            tubeness, radius=15, k=0.0, white_objects=True
        )
        binary = self.postprocessor.denoise_improved(
            binary, max_iterations=15, remove_small_particles=True
        )
        return tubeness, binary

    def _process_mexican_hat(self, image: np.ndarray) -> np.ndarray:
        """
        Mexican Hat Filter処理
        ImageJの processMexicanHatImproved に対応
        """
        # ガウシアンブラー（オプション）
        if self.gaussian_blur:
            image_blur = cv2.GaussianBlur(image, (0, 0), sigmaX=self.gaussian_sigma)
        else:
            image_blur = image.copy()

        # Mexican Hat Filter適用
        mex_hat = self.filter_bank.mexican_hat(image_blur, sigma=self.mexican_hat_sigma)

        # 二値化（大津の方法）
        _, binary = cv2.threshold(mex_hat, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # Denoise Improved（Blurの後に適用）
        # ImageJ: denoiseImproved(removeSmallParticles=1)
        # max_iterations=15（ImageJのMAX_DESPECKLE_ITERATIONS）
        binary = self.postprocessor.denoise_improved(
            binary, max_iterations=15, remove_small_particles=True
        )

        return binary

    def _process_tubeness_single(self, image: np.ndarray) -> np.ndarray:
        """
        Tubeness Filter処理（シングルスケール）
        ImageJの processTubenessImproved に対応
        """
        # 正確なTubeness Filter適用
        tubeness = self.filter_bank.tubeness_filter_accurate(
            image, sigma=self.tubeness_sigma, beta=0.5, c=15
        )

        # Sauvola二値化
        binary = self.thresholder.sauvola(
            tubeness,
            radius=15,
            k=0.0,  # ImageJのparameter_1=0に対応（内部で0.5に変換される）
            white_objects=True,
        )

        # Denoise Improved（Blurの後に適用）
        # ImageJ: denoiseImproved(removeSmallParticles=1)
        # max_iterations=15（ImageJのMAX_DESPECKLE_ITERATIONS）
        binary = self.postprocessor.denoise_improved(
            binary, max_iterations=15, remove_small_particles=True
        )

        return binary

    def _process_tubeness_multiscale(self, image: np.ndarray) -> np.ndarray:
        """
        Tubeness Filter処理（マルチスケール）
        様々な太さの血管に対応
        """
        # マルチスケールTubeness Filter適用
        tubeness = self.filter_bank.multiscale_tubeness(
            image,
            sigmas=self.tubeness_sigmas,
            beta=0.5,
            c=15,
            use_parallel=self.use_parallel,
        )

        # Sauvola二値化
        binary = self.thresholder.sauvola(
            tubeness, radius=15, k=0.0, white_objects=True
        )

        # Denoise Improved（Blurの後に適用）
        # ImageJ: denoiseImproved(removeSmallParticles=1)
        # max_iterations=15（ImageJのMAX_DESPECKLE_ITERATIONS）
        binary = self.postprocessor.denoise_improved(
            binary, max_iterations=15, remove_small_particles=True
        )

        return binary

    def _combine_filters(
        self, mex_hat_binary: np.ndarray, tubeness_binary: np.ndarray
    ) -> np.ndarray:
        """
        2つのフィルタ結果を結合
        ImageJの createBinaryImageImproved に対応

        注意: ImageJではOR結合後にdenoiseImproved(removeSmallParticles=0)を実行
        - Despeckleのみ実行（最大15回反復）
        - removeSmallParticlesは実行しない
        """
        # OR結合
        combined = cv2.bitwise_or(mex_hat_binary, tubeness_binary)

        # ImageJ: denoiseImproved(removeSmallParticles=0)
        # Despeckleのみ、removeSmallParticlesは実行しない
        combined = self.postprocessor.denoise_improved(
            combined, max_iterations=15, remove_small_particles=False
        )

        return combined


class VesselEnhancer:
    """
    血管強調クラス
    より高度な血管検出のための追加メソッド
    """

    @staticmethod
    def enhance_vessels_custom_hessian(
        image: np.ndarray,
        sigmas: Tuple[float, ...] = (0.5, 1.0, 1.5, 2.0, 2.5),
        spacing: float = 1.0,
        tau: float = 2.0,
    ) -> np.ndarray:
        """
        Custom Hessian Vesselness Filter（FAZSEG方式）による血管強調

        Parameters:
        -----------
        image : np.ndarray
            入力画像
        sigmas : tuple
            スケールパラメータ（デフォルト: 0.5-2.5）
        spacing : float
            ピクセルスペーシング
        tau : float
            tau正規化パラメータ

        Returns:
        --------
        enhanced : np.ndarray
            強調画像（0-255）
        """
        # 前処理（FAZSEG方式）
        if image.dtype == np.float32:
            image = (image * 255).astype(np.uint8)

        # 画像反転（FAZを明るく）
        image_inverted = 255 - image

        # 1%タイル閾値でノイズ除去
        thr = np.percentile(image_inverted[image_inverted > 0], 1) * 0.9
        image_inverted[image_inverted <= thr] = thr

        # 0-1正規化
        image_norm = image_inverted - np.min(image_inverted)
        image_norm = image_norm / np.max(image_norm)

        # Vesselness計算
        vesselness = None
        for sigma in sigmas:
            # Hessian行列計算
            lambda1, lambda2 = VesselEnhancer._compute_hessian_eigenvalues(
                image_norm, sigma, spacing
            )

            # tau正規化
            lambda3 = lambda2.copy()
            new_tau = tau * np.min(lambda3)
            lambda3[(lambda3 < 0) & (lambda3 >= new_tau)] = new_tau
            different = lambda3 - lambda2

            # Vesselness応答（FAZSEG式）
            response = (
                ((np.absolute(lambda2) ** 2) * np.absolute(different))
                * 27
                / ((2 * np.absolute(lambda2) + np.absolute(different)) ** 3 + 1e-10)
            )

            # 2段階閾値
            response[(lambda2 < lambda3 / 2)] = 1  # 強い血管
            response[(lambda2 >= 0)] = 0  # 明るい構造除外
            response[np.isinf(response)] = 0

            # マルチスケール最大値
            if vesselness is None:
                vesselness = response
            else:
                vesselness = np.maximum(vesselness, response)

        # ノイズ除去
        vesselness[vesselness < 1e-2] = 0

        # 0-255に正規化
        enhanced = cv2.normalize(vesselness, None, 0, 255, cv2.NORM_MINMAX).astype(
            np.uint8
        )

        return enhanced

    @staticmethod
    def _compute_hessian_eigenvalues(
        image: np.ndarray, sigma: float, spacing: float = 1.0
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Hessian行列の固有値を計算（FAZSEG方式）

        Parameters:
        -----------
        image : np.ndarray
            正規化済み画像（0-1）
        sigma : float
            ガウシアンスケール
        spacing : float
            ピクセルスペーシング

        Returns:
        --------
        lambda1, lambda2 : tuple of np.ndarray
            固有値（|lambda1| < |lambda2|にソート済み）
        """

        # ガウシアン平滑化
        image_smooth = VesselEnhancer._gaussian_smooth(image, sigma, spacing)

        # 勾配計算
        h, w = image.shape

        # Y方向
        Dy = np.zeros_like(image_smooth)
        Dy[0, :] = image_smooth[1, :] - image_smooth[0, :]
        Dy[h - 1, :] = image_smooth[h - 1, :] - image_smooth[h - 2, :]
        Dy[1 : h - 1, :] = (image_smooth[2:h, :] - image_smooth[0 : h - 2, :]) / 2

        Dyy = np.zeros_like(Dy)
        Dyy[0, :] = Dy[1, :] - Dy[0, :]
        Dyy[h - 1, :] = Dy[h - 1, :] - Dy[h - 2, :]
        Dyy[1 : h - 1, :] = (Dy[2:h, :] - Dy[0 : h - 2, :]) / 2

        # X方向
        Dx = np.zeros_like(image_smooth)
        Dx[:, 0] = image_smooth[:, 1] - image_smooth[:, 0]
        Dx[:, w - 1] = image_smooth[:, w - 1] - image_smooth[:, w - 2]
        Dx[:, 1 : w - 1] = (image_smooth[:, 2:w] - image_smooth[:, 0 : w - 2]) / 2

        Dxx = np.zeros_like(Dx)
        Dxx[:, 0] = Dx[:, 1] - Dx[:, 0]
        Dxx[:, w - 1] = Dx[:, w - 1] - Dx[:, w - 2]
        Dxx[:, 1 : w - 1] = (Dx[:, 2:w] - Dx[:, 0 : w - 2]) / 2

        # XY交差項
        Dxy = np.zeros_like(Dx)
        Dxy[0, :] = Dx[1, :] - Dx[0, :]
        Dxy[h - 1, :] = Dx[h - 1, :] - Dx[h - 2, :]
        Dxy[1 : h - 1, :] = (Dx[2:h, :] - Dx[0 : h - 2, :]) / 2

        # スケール正規化
        c = sigma**2
        hxx = -c * Dxx
        hyy = -c * Dyy
        hxy = -c * Dxy

        # 固有値計算の最適化（計算が必要な領域のみ）
        B1 = -(hxx + hyy)
        B2 = hxx * hyy - hxy**2
        valid_mask = (B1 < 0) | ((B1 != 0) | (B2 != 0))

        # 固有値計算
        lambda1 = np.zeros_like(image)
        lambda2 = np.zeros_like(image)

        if np.any(valid_mask):
            hxx_flat = hxx[valid_mask]
            hyy_flat = hyy[valid_mask]
            hxy_flat = hxy[valid_mask]

            tmp = np.sqrt((hxx_flat - hyy_flat) ** 2 + 4 * (hxy_flat**2))
            mu1 = 0.5 * (hxx_flat + hyy_flat + tmp)
            mu2 = 0.5 * (hxx_flat + hyy_flat - tmp)

            # 絶対値でソート: |lambda1| < |lambda2|
            swap_mask = np.absolute(mu1) > np.absolute(mu2)
            lambda1_flat = mu1.copy()
            lambda2_flat = mu2.copy()
            lambda1_flat[swap_mask] = mu2[swap_mask]
            lambda2_flat[swap_mask] = mu1[swap_mask]

            lambda1[valid_mask] = lambda1_flat
            lambda2[valid_mask] = lambda2_flat

        # ノイズ除去
        lambda1[np.isinf(lambda1)] = 0
        lambda2[np.isinf(lambda2)] = 0
        lambda1[np.absolute(lambda1) < 1e-4] = 0
        lambda2[np.absolute(lambda2) < 1e-4] = 0

        return lambda1, lambda2

    @staticmethod
    def _gaussian_smooth(
        image: np.ndarray, sigma: float, spacing: float = 1.0
    ) -> np.ndarray:
        """
        分離可能ガウシアンフィルタ（FAZSEG方式）

        Parameters:
        -----------
        image : np.ndarray
            入力画像
        sigma : float
            ガウシアンスケール
        spacing : float
            ピクセルスペーシング

        Returns:
        --------
        smoothed : np.ndarray
            平滑化画像
        """
        from scipy import ndimage

        siz = sigma * 6
        temp = int(round(siz / spacing / 2))

        # X方向
        x = np.arange(-temp, temp + 1)
        H = np.exp(-(x**2 / (2 * ((sigma / spacing) ** 2))))
        H = H / np.sum(H)
        Hx = H.reshape(len(H), 1)
        result = ndimage.convolve(image, Hx, mode="nearest")

        # Y方向
        Hy = H.reshape(1, len(H))
        result = ndimage.convolve(result, Hy, mode="nearest")

        return result

    @staticmethod
    def enhance_vessels_frangi(
        image: np.ndarray,
        sigmas: Tuple[float, ...] = (0.8, 1.0, 1.2, 1.5, 2.0),
        alpha: float = 0.5,
        beta: float = 0.5,
        gamma: float = 15,
    ) -> np.ndarray:
        """
        Frangi Vesselness Filterによる血管強調（後方互換性のため残す）

        Parameters:
        -----------
        image : np.ndarray
            入力画像
        sigmas : tuple
            スケールパラメータ
        alpha : float
            形状比の重み
        beta : float
            構造強度の重み
        gamma : float
            ノイズ抑制の重み

        Returns:
        --------
        enhanced : np.ndarray
            強調画像（0-255）
        """
        filter_bank = FilterBank()
        return filter_bank.frangi_filter(
            image, sigmas=sigmas, alpha=alpha, beta=beta, gamma=gamma
        )

    @staticmethod
    def enhance_vessels_clahe(
        image: np.ndarray,
        clip_limit: float = 3.0,
        tile_grid_size: Tuple[int, int] = (8, 8),
    ) -> np.ndarray:
        """
        CLAHEによるコントラスト強調

        Parameters:
        -----------
        image : np.ndarray
            入力画像
        clip_limit : float
            クリップリミット
        tile_grid_size : tuple
            タイルグリッドサイズ

        Returns:
        --------
        enhanced : np.ndarray
            強調画像
        """
        clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid_size)
        return clahe.apply(image)

    @staticmethod
    def enhance_vessels(
        image: np.ndarray, method: str = "custom_hessian", **kwargs
    ) -> np.ndarray:
        """
        血管強調（統合メソッド）

        Parameters:
        -----------
        image : np.ndarray
            入力画像
        method : str
            使用するフィルター: "custom_hessian" (デフォルト), "frangi", "clahe"
        **kwargs : dict
            各メソッドのパラメータ

        Returns:
        --------
        enhanced : np.ndarray
            強調画像（0-255）
        """
        if method == "custom_hessian":
            return VesselEnhancer.enhance_vessels_custom_hessian(image, **kwargs)
        elif method == "frangi":
            return VesselEnhancer.enhance_vessels_frangi(image, **kwargs)
        elif method == "clahe":
            return VesselEnhancer.enhance_vessels_clahe(image, **kwargs)
        else:
            raise ValueError(
                f"Unknown method: {method}. Choose from 'custom_hessian', 'frangi', 'clahe'"
            )


class VesselQualityChecker:
    """
    血管検出品質チェッカー
    検出結果の品質を評価
    """

    @staticmethod
    def check_detection_quality(
        binary: np.ndarray, roi_mask: np.ndarray
    ) -> Dict[str, any]:
        """
        検出品質をチェック

        Parameters:
        -----------
        binary : np.ndarray
            二値化画像
        roi_mask : np.ndarray
            ROIマスク

        Returns:
        --------
        quality : dict
            品質指標
        """
        # 血管領域の割合
        roi_pixels = np.sum(roi_mask > 0)
        vessel_pixels = np.sum((binary > 0) & (roi_mask > 0))
        vessel_ratio = vessel_pixels / roi_pixels if roi_pixels > 0 else 0

        # 連結成分数
        from skimage import measure

        labels = measure.label(binary > 0, connectivity=2)
        num_components = labels.max()

        # 最大連結成分のサイズ
        if num_components > 0:
            component_sizes = [
                np.sum(labels == i) for i in range(1, num_components + 1)
            ]
            max_component_size = max(component_sizes)
            max_component_ratio = (
                max_component_size / vessel_pixels if vessel_pixels > 0 else 0
            )
        else:
            max_component_size = 0
            max_component_ratio = 0

        # 品質判定
        is_good_quality = (
            0.05 <= vessel_ratio <= 0.70  # 血管密度が適切
            and num_components >= 3  # 複数の血管が検出
            and max_component_ratio < 0.95  # 1つの巨大連結成分ではない
        )

        return {
            "vessel_ratio": vessel_ratio,
            "num_components": num_components,
            "max_component_size": max_component_size,
            "max_component_ratio": max_component_ratio,
            "is_good_quality": is_good_quality,
            "quality_issues": VesselQualityChecker._identify_issues(
                vessel_ratio, num_components, max_component_ratio
            ),
        }

    @staticmethod
    def _identify_issues(
        vessel_ratio: float, num_components: int, max_component_ratio: float
    ) -> list:
        """品質問題を特定"""
        issues = []

        if vessel_ratio < 0.05:
            issues.append("Very low vessel density - possible detection failure")
        elif vessel_ratio > 0.70:
            issues.append("Very high vessel density - possible over-detection")

        if num_components < 3:
            issues.append("Too few vessel components detected")

        if max_component_ratio > 0.95:
            issues.append("Detection dominated by single large component")

        return issues if issues else ["No issues detected"]


class VDProcessor:
    """
    VDè§£æžç”¨ã®å‡¦ç†ã‚¯ãƒ©ã‚¹
    VDè§£æžã®img_process_measurement ã«å¯¾å¿œ
    """

    def __init__(self, pipeline_type: str = "High Precision"):
        """
        Parameters:
        -----------
        pipeline_type : str
            血管強調パイプラインのタイプ
        """
        self.pipeline_type = pipeline_type
        self.post_processor = BinaryPostProcessor()

    def process_for_vd(
        self,
        image: np.ndarray,
        faz_mask: np.ndarray,
        phansalkar_radius: Optional[int] = None,
        enhancement_method: str = "custom_hessian",
    ) -> np.ndarray:
        """
        VDè§£æžç”¨ã®ç”»åƒå‡¦ç†

        Parameters:
        -----------
        image : np.ndarray
            å…¥åŠ›ç”»åƒï¼ˆSuperficial or Deepï¼‰
        faz_mask : np.ndarray
            FAZãƒžã‚¹ã‚¯ï¼ˆ255=FAZé ˜åŸŸã€0=æœ‰åŠ¹é ˜åŸŸï¼‰
        phansalkar_radius : int, optional
            PhansalkaråŠå¾„

        Returns:
        --------
        binary : np.ndarray
            血管二値画像（FAZ領域がマスクされている）
        """
        # 血管強調（Custom Hessian or Frangi filter）
        if enhancement_method == "custom_hessian":
            enhanced = VesselEnhancer.enhance_vessels_custom_hessian(
                image, sigmas=(0.5, 1.0, 1.5, 2.0, 2.5)
            )
        elif enhancement_method == "frangi":
            enhanced = VesselEnhancer.enhance_vessels_frangi(
                image, sigmas=(0.8, 1.0, 1.2, 1.5, 2.0)
            )
        else:
            raise ValueError(f"Unknown enhancement method: {enhancement_method}")

        # 二値化
        thresholder = AdaptiveThresholder()
        if phansalkar_radius is not None:
            binary = thresholder.phansalkar(enhanced, radius=phansalkar_radius)
        else:
            binary = thresholder.adaptive_threshold(enhanced, method="phansalkar")

        # FAZ領域をマスク（FAZは黒=0になる）
        faz_inverse = 255 - faz_mask
        binary = cv2.bitwise_and(binary, binary, mask=faz_inverse)

        return binary

    @staticmethod
    def li_threshold_imagej_style(image: np.ndarray) -> float:
        """
        ImageJ互換のLi法閾値計算

        ImageJのAutoThresholder.Liメソッドの実装に基づく
        反復的平均ベース

        Parameters:
        -----------
        image : np.ndarray
            入力画像（グレースケール）

        Returns:
        --------
        threshold : float
            閾値
        """
        # ヒストグラム作成
        hist, _ = np.histogram(image.ravel(), bins=256, range=(0, 256))

        total_pixels = hist.sum()
        if total_pixels == 0:
            return 0

        # 平均値を初期閾値とする
        mean = np.sum(np.arange(256) * hist) / total_pixels
        threshold = int(mean)

        # 反復計算
        tolerance = 0.5
        max_iterations = 10000

        for _ in range(max_iterations):
            # 前景と背景の平均を計算
            sum_back = 0.0
            sum_obj = 0.0
            num_back = 0
            num_obj = 0

            for i in range(256):
                if i <= threshold:
                    sum_back += i * hist[i]
                    num_back += hist[i]
                else:
                    sum_obj += i * hist[i]
                    num_obj += hist[i]

            mean_back = sum_back / num_back if num_back > 0 else 0
            mean_obj = sum_obj / num_obj if num_obj > 0 else 0

            # 新しい閾値
            new_threshold = (mean_back + mean_obj) / 2.0

            # 収束チェック
            if abs(new_threshold - threshold) < tolerance:
                break

            threshold = int(new_threshold + 0.5)

        return threshold

    @staticmethod
    def _bandpass_for_faz_fast(
        img: np.ndarray,
        sigma_large: float = 1024 / 3.0,
        sigma_small: float = 3.5,
        downsample_size: int = 200,
    ) -> np.ndarray:
        """
        FAZ用バンドパス（大sigmaをダウンサンプル上で実行して高速化）。
        高域＝元画像－低域。低域は縮小→大sigmaブラー→拡大で近似。

        Parameters
        ----------
        img : np.ndarray
            800x800 等のグレースケール画像
        sigma_large : float
            低域用ガウシアン sigma（元解像度換算）
        sigma_small : float
            正規化後の軽いブラー用 sigma
        downsample_size : int
            低域計算用の短辺サイズ（小さいほど速いが粗い）

        Returns
        -------
        bandpass : np.ndarray
            img と同じ shape のバンドパス画像
        """
        h, w = img.shape
        small = cv2.resize(
            img, (downsample_size, downsample_size), interpolation=cv2.INTER_LINEAR
        )
        sigma_s = sigma_large * (downsample_size / max(w, h))
        blurred_small = cv2.GaussianBlur(small, (0, 0), sigma_s)
        high_pass_small = cv2.subtract(small, blurred_small)
        high_pass = cv2.resize(
            high_pass_small, (w, h), interpolation=cv2.INTER_LINEAR
        )
        high_pass_normalized = cv2.normalize(
            high_pass, None, 0, 255, cv2.NORM_MINMAX
        )
        bandpass = cv2.GaussianBlur(
            high_pass_normalized, (0, 0), sigma_small
        )
        return bandpass

    def process_combined_for_faz_optimized(
        self,
        superficial: np.ndarray,
        deep: np.ndarray,
        li_threshold_scale: float = 1.0,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Optimized combined processing for FAZ detection
        - Hessian vessel enhancement (FAZSEG method) before combine
        - Weighted blend (0.7:0.3)
        - Bandpass filter with normalization
        - CLAHE
        - Li method binarization
        - Skeletonization
        - Close operation (8 iterations)

        Parameters:
        -----------
        superficial : np.ndarray
            Superficial layer image
        deep : np.ndarray
            Deep layer image

        Returns:
        --------
        binary_resized : np.ndarray
            Binary image for FAZ detection
        combined : np.ndarray
            Combined image
        """
        h, w = superficial.shape

        # Apply Hessian vessel enhancement to each layer (FAZSEG method)
        t0 = time.perf_counter()
        print("  Hessianフィルター適用中...")
        superficial_enhanced = VesselEnhancer.enhance_vessels_custom_hessian(
            superficial, sigmas=(0.5, 1.0, 1.5, 2.0, 2.5)
        )
        deep_enhanced = VesselEnhancer.enhance_vessels_custom_hessian(
            deep, sigmas=(0.5, 1.0, 1.5, 2.0, 2.5)
        )
        logger.info(
            "[VD timing]       faz_skel_hessian: %.3f s",
            time.perf_counter() - t0,
        )

        t0 = time.perf_counter()
        superficial_resized = cv2.resize(
            superficial_enhanced, (800, 800), interpolation=cv2.INTER_LINEAR
        )
        deep_resized = cv2.resize(
            deep_enhanced, (800, 800), interpolation=cv2.INTER_LINEAR
        )
        combined = cv2.addWeighted(
            superficial_resized, 0.7, deep_resized, 0.3, 0
        )
        logger.info(
            "[VD timing]       faz_skel_resize_blend: %.3f s",
            time.perf_counter() - t0,
        )

        # Bandpass Filter (downsample large blur for speed)
        t0 = time.perf_counter()
        bandpass = VDProcessor._bandpass_for_faz_fast(combined)
        logger.info(
            "[VD timing]       faz_skel_bandpass: %.3f s",
            time.perf_counter() - t0,
        )

        t0 = time.perf_counter()
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        bandpass = clahe.apply(bandpass)
        logger.info(
            "[VD timing]       faz_skel_clahe: %.3f s",
            time.perf_counter() - t0,
        )

        # Li method binarization
        t0 = time.perf_counter()
        try:
            threshold_value = VDProcessor.li_threshold_imagej_style(bandpass)
            if li_threshold_scale != 1.0:
                threshold_value = min(
                    255.0, float(threshold_value) * li_threshold_scale
                )
            binary = (bandpass > threshold_value).astype(np.uint8) * 255
        except Exception:
            _, binary = cv2.threshold(
                bandpass, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
            )
        logger.info(
            "[VD timing]       faz_skel_li_binary: %.3f s",
            time.perf_counter() - t0,
        )

        # Skeletonize
        t0 = time.perf_counter()
        from skimage.morphology import skeletonize

        skeleton_bool = skeletonize(binary > 0)
        skeleton = (skeleton_bool * 255).astype(np.uint8)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        skeleton = cv2.morphologyEx(
            skeleton, cv2.MORPH_CLOSE, kernel, iterations=8
        )
        skeleton_resized = cv2.resize(
            skeleton, (w, h), interpolation=cv2.INTER_LINEAR
        )
        _, skeleton_resized = cv2.threshold(
            skeleton_resized, 50, 255, cv2.THRESH_BINARY
        )
        logger.info(
            "[VD timing]       faz_skel_skeletonize_close: %.3f s",
            time.perf_counter() - t0,
        )

        combined_resized = cv2.resize(
            combined, (w, h), interpolation=cv2.INTER_LINEAR
        )

        return skeleton_resized, combined_resized

    def process_combined_for_faz(
        self,
        superficial: np.ndarray,
        deep: np.ndarray,
        li_threshold_scale: float = 1.0,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Superficial + Deep ã‚’çµ±åˆã—ã¦FAZæ¤œå‡ºç”¨ã®ã‚¹ã‚±ãƒ«ãƒˆãƒ³ã‚’ä½œæˆ
        VDè§£æžã®processVDFileå†…ã®å‡¦ç†ã«å¯¾å¿œ

        Parameters:
        -----------
        superficial : np.ndarray
            Superficialå±¤ã®äºŒå€¤ç”»åƒ
        deep : np.ndarray
            Deepå±¤ã®äºŒå€¤ç”»åƒ

        Returns:
        --------
        skeleton : np.ndarray
            Skeleton image
        combined : np.ndarray
            Combined image
        """
        h, w = superficial.shape
        t0 = time.perf_counter()
        superficial_resized = cv2.resize(
            superficial, (800, 800), interpolation=cv2.INTER_LINEAR
        )
        deep_resized = cv2.resize(
            deep, (800, 800), interpolation=cv2.INTER_LINEAR
        )
        combined = cv2.addWeighted(
            superficial_resized, 0.7, deep_resized, 0.3, 0
        )
        logger.info(
            "[VD timing]       faz_skel_resize_blend: %.3f s",
            time.perf_counter() - t0,
        )

        t0 = time.perf_counter()
        bandpass = VDProcessor._bandpass_for_faz_fast(combined)
        logger.info(
            "[VD timing]       faz_skel_bandpass: %.3f s",
            time.perf_counter() - t0,
        )

        t0 = time.perf_counter()
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        bandpass = clahe.apply(bandpass)
        logger.info(
            "[VD timing]       faz_skel_clahe: %.3f s",
            time.perf_counter() - t0,
        )

        t0 = time.perf_counter()
        from skimage.filters import threshold_li

        try:
            threshold_value = threshold_li(bandpass)
            if li_threshold_scale != 1.0:
                threshold_value = min(
                    255.0, float(threshold_value) * li_threshold_scale
                )
            binary = (bandpass > threshold_value).astype(np.uint8) * 255
        except Exception:
            _, binary = cv2.threshold(
                bandpass, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
            )
        logger.info(
            "[VD timing]       faz_skel_li_binary: %.3f s",
            time.perf_counter() - t0,
        )

        t0 = time.perf_counter()
        from skimage.morphology import skeletonize

        skeleton_bool = skeletonize(binary > 0)
        skeleton = (skeleton_bool * 255).astype(np.uint8)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        skeleton = cv2.morphologyEx(
            skeleton, cv2.MORPH_CLOSE, kernel, iterations=8
        )
        skeleton = cv2.resize(skeleton, (w, h), interpolation=cv2.INTER_LINEAR)
        _, skeleton = cv2.threshold(skeleton, 50, 255, cv2.THRESH_BINARY)
        logger.info(
            "[VD timing]       faz_skel_skeletonize_close: %.3f s",
            time.perf_counter() - t0,
        )

        t0 = time.perf_counter()
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
            skeleton, connectivity=8
        )
        cleaned = np.zeros_like(skeleton)
        for i in range(1, num_labels):
            area = stats[i, cv2.CC_STAT_AREA]
            if area <= 1000:
                cleaned[labels == i] = 0
            else:
                cleaned[labels == i] = 255
        logger.info(
            "[VD timing]       faz_skel_small_particle_removal: %.3f s",
            time.perf_counter() - t0,
        )

        combined_resized = cv2.resize(
            combined, (w, h), interpolation=cv2.INTER_LINEAR
        )

        return cleaned, combined_resized

    def process_single_for_faz(
        self,
        image: np.ndarray,
        li_threshold_scale: float = 1.0,
        use_optimized: bool = True,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Single image processing for FAZ detection (File Upload mode).
        Uses the same pipeline as process_combined_for_faz but with one image.
        No superficial/deep blend - the image is used directly.

        Parameters:
        -----------
        image : np.ndarray
            Input OCTA image (grayscale)
        li_threshold_scale : float
            Li threshold scale (same as pair mode)
        use_optimized : bool
            True: Hessian enhancement before processing (recommended)

        Returns:
        --------
        skeleton : np.ndarray
            Skeleton image for FAZ detection
        combined : np.ndarray
            Processed image (for intensity refinement if used)
        """
        h, w = image.shape
        t0 = time.perf_counter()
        if use_optimized:
            img_enhanced = VesselEnhancer.enhance_vessels_custom_hessian(
                image, sigmas=(0.5, 1.0, 1.5, 2.0, 2.5)
            )
        else:
            img_enhanced = image.copy()
        logger.info(
            "[VD timing]       faz_skel_hessian: %.3f s",
            time.perf_counter() - t0,
        )

        t0 = time.perf_counter()
        img_resized = cv2.resize(
            img_enhanced, (800, 800), interpolation=cv2.INTER_LINEAR
        )
        logger.info(
            "[VD timing]       faz_skel_resize: %.3f s",
            time.perf_counter() - t0,
        )

        # Bandpass Filter (downsample large blur for speed)
        t0 = time.perf_counter()
        bandpass = VDProcessor._bandpass_for_faz_fast(img_resized)
        logger.info(
            "[VD timing]       faz_skel_bandpass: %.3f s",
            time.perf_counter() - t0,
        )

        t0 = time.perf_counter()
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        bandpass = clahe.apply(bandpass)
        logger.info(
            "[VD timing]       faz_skel_clahe: %.3f s",
            time.perf_counter() - t0,
        )

        # Li method binarization
        t0 = time.perf_counter()
        try:
            threshold_value = VDProcessor.li_threshold_imagej_style(bandpass)
            if li_threshold_scale != 1.0:
                threshold_value = min(
                    255.0, float(threshold_value) * li_threshold_scale
                )
            binary = (bandpass > threshold_value).astype(np.uint8) * 255
        except Exception:
            _, binary = cv2.threshold(
                bandpass, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
            )
        logger.info(
            "[VD timing]       faz_skel_li_binary: %.3f s",
            time.perf_counter() - t0,
        )

        # Skeletonize
        t0 = time.perf_counter()
        from skimage.morphology import skeletonize

        skeleton_bool = skeletonize(binary > 0)
        skeleton = (skeleton_bool * 255).astype(np.uint8)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        skeleton = cv2.morphologyEx(skeleton, cv2.MORPH_CLOSE, kernel, iterations=8)

        skeleton_resized = cv2.resize(
            skeleton, (w, h), interpolation=cv2.INTER_LINEAR
        )
        _, skeleton_resized = cv2.threshold(
            skeleton_resized, 50, 255, cv2.THRESH_BINARY
        )
        logger.info(
            "[VD timing]       faz_skel_skeletonize_close: %.3f s",
            time.perf_counter() - t0,
        )

        combined_resized = cv2.resize(
            bandpass, (w, h), interpolation=cv2.INTER_LINEAR
        )

        return skeleton_resized, combined_resized

    @staticmethod
    def refine_vessel_mask_by_intensity(
        skeleton: np.ndarray,
        combined: np.ndarray,
        center_roi_ratio: float = 0.5,
        intensity_percentile: float = 30.0,
    ) -> np.ndarray:
        """
        中心ROI内で「血管の色の薄い」ピクセルを無血管として扱い、FAZ候補を広げる。
        スケルトン化以降の改善: 血管マスク（skeleton>0）のうち、
        統合画像の強度が中心域の下位 percentile 以下の点を血管から外す。

        Parameters:
        -----------
        skeleton : np.ndarray
            スケルトン画像 (H,W), 0=無血管, 255=血管
        combined : np.ndarray
            統合画像（800x800でも可。skeletonと同じサイズにリサイズされる）
        center_roi_ratio : float
            中心ROIの幅・高さの割合（0.5 = 画像の50%を中心とする）
        intensity_percentile : float
            中心ROI内の強度のこのパーセンタイル以下を「薄い」とみなす (0-100)

        Returns:
        --------
        refined : np.ndarray
            精査後のスケルトン (0/255), 薄い血管を0にしたもの
        """
        h, w = skeleton.shape
        if combined.shape != (h, w):
            combined = cv2.resize(
                combined, (w, h), interpolation=cv2.INTER_LINEAR
            )
        refined = skeleton.copy()
        cy, cx = h // 2, w // 2
        half = min(w, h) * center_roi_ratio / 2.0
        y0 = max(0, int(cy - half))
        y1 = min(h, int(cy + half))
        x0 = max(0, int(cx - half))
        x1 = min(w, int(cx + half))
        center_roi = combined[y0:y1, x0:x1]
        thresh = np.percentile(center_roi.ravel(), intensity_percentile)
        in_center = np.zeros_like(refined, dtype=bool)
        in_center[y0:y1, x0:x1] = True
        vessel_faint = (refined > 0) & in_center & (combined < thresh)
        refined[vessel_faint] = 0
        return refined


class QualityChecker:
    """ç”»åƒå“è³ªãƒã‚§ãƒƒã‚¯ã‚¯ãƒ©ã‚¹"""

    @staticmethod
    def check_image_quality(
        image: np.ndarray, binary: Optional[np.ndarray] = None
    ) -> Dict[str, float]:
        """
        ç”»åƒå“è³ªã‚’ãƒã‚§ãƒƒã‚¯
        checkImageQuality ã«å¯¾å¿œ

        Parameters:
        -----------
        image : np.ndarray
            å…ƒç”»åƒ
        binary : np.ndarray, optional
            äºŒå€¤ç”»åƒ

        Returns:
        --------
        metrics : dict
            å“è³ªãƒ¡ãƒˆãƒªã‚¯ã‚¹
        """
        metrics = {}

        # è¼åº¦çµ±è¨ˆ
        mean_val = image.mean()
        std_val = image.std()

        metrics["mean_intensity"] = mean_val
        metrics["std_intensity"] = std_val

        # è­¦å‘Šãƒã‚§ãƒƒã‚¯
        if mean_val < 5:
            metrics["warning"] = "Image is too dark"
        elif std_val < 10:
            metrics["warning"] = "Low contrast"
        else:
            metrics["warning"] = None

        # è¡€ç®¡å¯†åº¦ãƒã‚§ãƒƒã‚¯ï¼ˆäºŒå€¤ç”»åƒãŒã‚ã‚‹å ´åˆï¼‰
        if binary is not None:
            vessel_density = (binary > 0).sum() / binary.size * 100
            metrics["vessel_density"] = vessel_density

            if vessel_density < 5 or vessel_density > 80:
                metrics["density_warning"] = (
                    f"Abnormal vessel density: {vessel_density:.1f}%"
                )

        return metrics
