"""画像前処理モジュール"""

from typing import Tuple

import cv2
import numpy as np
from scipy import ndimage
from skimage import exposure
from skimage.morphology import reconstruction


class ImagePreprocessor:
    """画像前処理クラス"""

    def __init__(self, clahe_blocksize: int = 127, clahe_clip_limit: float = 3.0):
        self.clahe_blocksize = clahe_blocksize
        self.clahe_clip_limit = clahe_clip_limit

    def apply_clahe(self, image: np.ndarray) -> np.ndarray:
        """CLAHE (Contrast Limited Adaptive Histogram Equalization)を適用"""
        # OpenCVのCLAHEを使用
        clahe = cv2.createCLAHE(
            clipLimit=self.clahe_clip_limit,
            tileGridSize=(self.clahe_blocksize, self.clahe_blocksize),
        )
        return clahe.apply(image)

    def subtract_background(self, image: np.ndarray, sigma: float = 5.0) -> np.ndarray:
        """背景除去"""
        # ガウシアンブラーで背景推定
        background = ndimage.gaussian_filter(image.astype(float), sigma)

        # 減算
        foreground = image.astype(float) - background

        # 負の値をクリップ
        foreground = np.clip(foreground, 0, 255)

        return foreground.astype(np.uint8)

    def enhance_contrast(
        self, image: np.ndarray, saturated: float = 0.35
    ) -> np.ndarray:
        """コントラスト強調"""
        p2, p98 = np.percentile(image, (saturated, 100 - saturated))
        return exposure.rescale_intensity(image, in_range=(p2, p98))

    def preprocess_pipeline(
        self,
        image: np.ndarray,
        apply_clahe: bool = True,
        apply_background_sub: bool = True,
    ) -> np.ndarray:
        """前処理パイプライン"""
        result = image.copy()

        if apply_clahe:
            result = self.apply_clahe(result)

        if apply_background_sub:
            result = self.subtract_background(result)

        # 最終的な正規化
        result = self.enhance_contrast(result)

        return result


class FilterBank:
    """各種フィルタバンク"""

    @staticmethod
    def _normalize_to_8bit(
        data: np.ndarray,
        normalization: str = "percentile",
        percentile_low: float = 1.0,
        percentile_high: float = 99.0,
    ) -> np.ndarray:
        """
        Float画像を8-bitに正規化する共通ヘルパー。

        Parameters
        ----------
        data : np.ndarray
            正規化対象のfloat画像
        normalization : str
            "percentile"（外れ値耐性、1024px向け）または
            "minmax"（全値域を使用、小画像向け）
        percentile_low, percentile_high : float
            percentileモード時に使用するパーセンタイル範囲

        Returns
        -------
        np.ndarray (uint8)
        """
        if normalization == "minmax":
            vmin, vmax = data.min(), data.max()
            if vmax > vmin:
                normed = 255.0 * (data - vmin) / (vmax - vmin)
            else:
                normed = np.zeros_like(data)
        else:
            # percentile (default)
            p_lo, p_hi = np.percentile(data, [percentile_low, percentile_high])
            if p_hi > p_lo:
                normed = np.clip(255.0 * (data - p_lo) / (p_hi - p_lo), 0, 255)
            else:
                normed = np.zeros_like(data)
        return normed.astype(np.uint8)

    @staticmethod
    def mexican_hat(
        image: np.ndarray,
        sigma: float = 1.0,
        percentile_low: float = 1.0,
        percentile_high: float = 99.0,
        otsu_scale: float = 0.8,
        normalization: str = "percentile",
    ) -> np.ndarray:
        """
        Mexican Hat Filter (Laplacian of Gaussian)
        ImageJ FeatureJ Laplacian完全互換実装

        ImageJ処理:
        1. run("FeatureJ Laplacian", "sigma=" + mexican_hat_filter_radius)
        2. run("8-bit") - 正規化
        3. run("Make Binary") - Otsu threshold

        Parameters
        ----------
        normalization : str
            "percentile"（デフォルト、1024px向け）または
            "minmax"（小画像向け）
        """
        # FeatureJ Laplacianは -gaussian_laplace（符号が逆）
        log_filtered = -ndimage.gaussian_laplace(image.astype(float), sigma)

        # 8-bit変換
        log_8bit = FilterBank._normalize_to_8bit(
            log_filtered, normalization, percentile_low, percentile_high
        )

        # Make Binary: Otsu閾値 x otsu_scale で感度向上（薄い血管のロス抑制）
        otsu_thresh, _ = cv2.threshold(
            log_8bit, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )
        scaled_thresh = max(1, int(otsu_thresh * otsu_scale))
        _, binary = cv2.threshold(log_8bit, scaled_thresh, 255, cv2.THRESH_BINARY)

        return binary

    @staticmethod
    def mexican_hat_multiscale(
        image: np.ndarray,
        sigmas: Tuple[float, ...] = (1.0, 1.5, 2.0),
        percentile_low: float = 1.0,
        percentile_high: float = 99.0,
        otsu_scale: float = 0.8,
        normalization: str = "percentile",
    ) -> np.ndarray:
        """
        Multi-scale Mexican Hat (LoG) for capillary and thick vessel capture.
        Takes pixel-wise max across scales before Otsu.
        sigma 1.0-2.0 covers capillaries to moderately thick vessels.

        Parameters
        ----------
        normalization : str
            "percentile"（デフォルト、1024px向け）または
            "minmax"（小画像向け）
        """
        img_float = image.astype(float)
        log_stack = []
        for sigma in sigmas:
            log_filtered = -ndimage.gaussian_laplace(img_float, sigma)
            log_stack.append(log_filtered)
        log_max = np.maximum.reduce(log_stack)

        # 8-bit変換
        log_8bit = FilterBank._normalize_to_8bit(
            log_max, normalization, percentile_low, percentile_high
        )

        # Make Binary: Otsu閾値 x otsu_scale で感度向上
        otsu_thresh, _ = cv2.threshold(
            log_8bit, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )
        scaled_thresh = max(1, int(otsu_thresh * otsu_scale))
        _, binary = cv2.threshold(log_8bit, scaled_thresh, 255, cv2.THRESH_BINARY)
        return binary

    @staticmethod
    def frangi_filter(
        image: np.ndarray,
        sigmas: Tuple[float, ...] = (0.8, 1.0, 1.2, 1.5, 2.0),
        alpha: float = 0.5,
        beta: float = 0.5,
        gamma: float = 15,
    ) -> np.ndarray:
        """
        Frangi Vesselness Filter
        血管強調フィルタ
        """
        from skimage.filters import frangi

        # Frangiフィルタを適用
        filtered = frangi(
            image,
            sigmas=sigmas,
            alpha=alpha,
            beta=beta,
            gamma=gamma,
            black_ridges=False,
        )

        # 0-255に正規化
        filtered = (
            255
            * (filtered - filtered.min())
            / (filtered.max() - filtered.min() + 1e-10)
        )

        return filtered.astype(np.uint8)

    @staticmethod
    def tubeness_filter_accurate(
        image: np.ndarray,
        sigma: float = 1.0,
        beta: float = 0.5,
        c: float = 15,
        percentile_low: float = 1.0,
        percentile_high: float = 99.0,
        sauvola_k: float = 0.9,
        normalization: str = "percentile",
    ) -> np.ndarray:
        """
        ImageJ Tubeness Filter完全互換実装
        Hessian行列の最大絶対固有値 + Auto Local Threshold (Sauvola)

        ImageJ処理:
        1. run("Tubeness", "sigma=" + tubeness_filter_radius)  # Hessian-based
        2. run("8-bit") - 正規化
        3. run("Auto Local Threshold", "method=Sauvola radius=15 parameter_1=0 parameter_2=0 white")

        Parameters
        ----------
        image : np.ndarray
            入力画像（グレースケール）
        sigma : float
            ガウシアンスケール（血管太さ）
        beta : float
            （未使用、互換性のため残す）
        c : float
            （未使用、互換性のため残す）
        normalization : str
            "percentile"（デフォルト、1024px向け）または
            "minmax"（小画像向け）

        Returns
        -------
        binary : np.ndarray
            二値化Tubeness画像（0-255）
        """
        from skimage.feature import hessian_matrix, hessian_matrix_eigvals
        from skimage.filters import threshold_sauvola

        # Hessian行列計算（ImageJ FeatureJ Hessian互換）
        H_elems = hessian_matrix(image, sigma=sigma, mode="reflect", order="rc")
        eigen_vals = hessian_matrix_eigvals(H_elems)

        # 最大絶対固有値（largest absolute eigenvalue）
        # ImageJ Tubeness 2D: "If the largest eigenvalue is negative, the absolute value
        # is returned; otherwise returns 0." (dark vessels only)
        lambda_max = eigen_vals[0]  # 大きい方の固有値
        tubeness = np.abs(lambda_max).astype(np.float64)
        tubeness[lambda_max > 0] = 0  # bright tubes: zero out (ImageJ compatibility)

        # 8-bit変換: 正規化モードに応じて処理
        if tubeness.max() > 0:
            if normalization == "minmax":
                # min-max: 全値域を使用（小画像向け）
                tubeness_8bit = FilterBank._normalize_to_8bit(
                    tubeness, "minmax"
                )
            else:
                # percentile: 非ゼロ領域のみのパーセンタイルで正規化（1024px向け）。
                # _normalize_to_8bit() は全配列の percentile を使うため使用しない。
                # Tubeness は lambda_max>0 を 0 にしているため、血管応答のみで
                # パーセンタイルを取る必要があり、ここでは意図的にヘルパーを使わない。
                nonzero = tubeness[tubeness > 0]
                if len(nonzero) >= 2:
                    p1, p99 = np.percentile(
                        nonzero, [percentile_low, percentile_high]
                    )
                    if p99 > p1:
                        tubeness_norm = np.clip(
                            255 * (tubeness - p1) / (p99 - p1), 0, 255
                        )
                    else:
                        tubeness_norm = 255 * tubeness / tubeness.max()
                else:
                    tubeness_norm = 255 * tubeness / tubeness.max()
                tubeness_8bit = tubeness_norm.astype(np.uint8)
        else:
            tubeness_8bit = np.zeros_like(image, dtype=np.uint8)

        # Auto Local Threshold (Sauvola, radius=15)
        # sauvola_k: ImageJ デフォルト0.5より高めで、血管検出感度を向上（点状化抑制）
        window_size = 31  # radius=15 -> window=(2*15+1)=31
        threshold = threshold_sauvola(
            tubeness_8bit, window_size=window_size, k=sauvola_k
        )
        binary = (tubeness_8bit > threshold).astype(np.uint8) * 255

        return binary

    @staticmethod
    def multiscale_tubeness(
        image: np.ndarray,
        sigmas: Tuple[float, ...] = (0.8, 1.2, 2.0),
        beta: float = 0.5,
        c: float = 15,
        use_parallel: bool = True,
    ) -> np.ndarray:
        """
        マルチスケールTubeness Filter
        様々な太さの血管に対応

        Parameters:
        -----------
        image : np.ndarray
            入力画像
        sigmas : tuple
            スケールのリスト（血管の太さに対応）
        beta : float
            形状比の重み
        c : float
            構造強度の重み
        use_parallel : bool
            並列処理を使用するか

        Returns:
        --------
        tubeness : np.ndarray
            マルチスケールTubeness応答（0-255）
        """
        if use_parallel and len(sigmas) > 1:
            # 並列処理
            import multiprocessing
            from concurrent.futures import ThreadPoolExecutor, as_completed

            max_workers = min(len(sigmas), multiprocessing.cpu_count())
            responses = [None] * len(sigmas)

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_idx = {
                    executor.submit(
                        FilterBank.tubeness_filter_accurate,
                        image,
                        sigma,
                        beta,
                        c,
                    ): i
                    for i, sigma in enumerate(sigmas)
                }

                for future in as_completed(future_to_idx):
                    idx = future_to_idx[future]
                    try:
                        responses[idx] = future.result()
                    except Exception as e:
                        print(f"Error computing tubeness at scale {sigmas[idx]}: {e}")
                        responses[idx] = np.zeros_like(image, dtype=np.uint8)
        else:
            # 逐次処理
            responses = []
            for sigma in sigmas:
                response = FilterBank.tubeness_filter_accurate(
                    image, sigma=sigma, beta=beta, c=c
                )
                responses.append(response)

        # 最大応答を選択（各ピクセルで最も強い応答）
        max_response = np.max(responses, axis=0)

        return max_response.astype(np.uint8)

    @staticmethod
    def tubeness_filter(image: np.ndarray, sigma: float = 1.0) -> np.ndarray:
        """
        Tubeness Filter（後方互換性のため残す）

        注意: この関数は非推奨です。
        tubeness_filter_accurate() または multiscale_tubeness() を使用してください。

        Parameters:
        -----------
        image : np.ndarray
            入力画像
        sigma : float
            スケール

        Returns:
        --------
        tubeness : np.ndarray
            Tubeness応答画像
        """
        import warnings

        warnings.warn(
            "tubeness_filter() is deprecated. "
            "Use tubeness_filter_accurate() or multiscale_tubeness() instead.",
            DeprecationWarning,
            stacklevel=2,
        )

        # 正確な実装を呼び出す
        return FilterBank.tubeness_filter_accurate(image, sigma=sigma)

    @staticmethod
    def gabor_filter_bank(
        image: np.ndarray,
        orientations: Tuple[int, ...] = (0, 30, 60, 90, 120, 150),
        sigma: float = 2.0,
        wavelength: float = 8.0,
    ) -> np.ndarray:
        """
        Gabor Filter Bank
        複数方向のGaborフィルタを適用
        """
        from skimage.filters import gabor

        results = []
        for theta in orientations:
            theta_rad = np.deg2rad(theta)
            real, imag = gabor(
                image,
                frequency=1.0 / wavelength,
                theta=theta_rad,
                sigma_x=sigma,
                sigma_y=sigma,
            )
            # 絶対値を取る
            magnitude = np.sqrt(real**2 + imag**2)
            results.append(magnitude)

        # 最大値投影
        gabor_max = np.max(results, axis=0)

        # 正規化
        if gabor_max.max() > 0:
            gabor_max = 255 * (gabor_max / gabor_max.max())

        return gabor_max.astype(np.uint8)


class AdaptiveThresholder:
    """適応的二値化クラス"""

    @staticmethod
    def phansalkar(
        image: np.ndarray, radius: int = 15, k: float = 0.25, r: float = 0.5
    ) -> np.ndarray:
        """
        Phansalkar法による適応的二値化
        マクロのAuto Local Thresholdに対応
        """

        # 局所平均と標準偏差を計算
        mean = ndimage.uniform_filter(image.astype(float), size=2 * radius + 1)

        # 局所標準偏差
        mean_sq = ndimage.uniform_filter(image.astype(float) ** 2, size=2 * radius + 1)
        std = np.sqrt(mean_sq - mean**2)

        # Phansalkar閾値
        threshold = mean * (1 + k * np.exp(-r * mean) + k * (std / np.sqrt(mean_sq)))

        # 二値化
        binary = (image > threshold).astype(np.uint8) * 255

        return binary

    @staticmethod
    def adaptive_threshold(
        image: np.ndarray,
        method: str = "phansalkar",
        radius: int = 15,
        **kwargs,
    ) -> np.ndarray:
        """
        適応的二値化の統合インターフェース

        Parameters:
        -----------
        method : str
            'phansalkar', 'sauvola', 'niblack', 'mean', 'gaussian'
        """
        if method == "phansalkar":
            return AdaptiveThresholder.phansalkar(image, radius, **kwargs)

        elif method == "sauvola":
            from skimage.filters import threshold_sauvola

            threshold = threshold_sauvola(image, window_size=2 * radius + 1, **kwargs)
            return (image > threshold).astype(np.uint8) * 255

        elif method == "niblack":
            from skimage.filters import threshold_niblack

            threshold = threshold_niblack(image, window_size=2 * radius + 1, **kwargs)
            return (image > threshold).astype(np.uint8) * 255

        elif method == "mean":
            binary = cv2.adaptiveThreshold(
                image,
                255,
                cv2.ADAPTIVE_THRESH_MEAN_C,
                cv2.THRESH_BINARY,
                2 * radius + 1,
                -2,
            )
            return binary

        elif method == "gaussian":
            binary = cv2.adaptiveThreshold(
                image,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                2 * radius + 1,
                -2,
            )
            return binary

        else:
            raise ValueError(f"Unknown method: {method}")

    @staticmethod
    def sauvola(
        image: np.ndarray,
        radius: int = 15,
        k: float = 0.0,
        r: float = 0.0,
        white_objects: bool = True,
    ) -> np.ndarray:
        """
        ImageJ の Auto Local Threshold - Sauvola に相当

        Parameters:
        -----------
        image : np.ndarray
            入力画像（グレースケール、8-bit）
        radius : int
            局所ウィンドウの半径（デフォルト 15）
        k : float
            Sauvola パラメータ k（デフォルト 0、ImageJ では 0 の場合 0.5 を使用）
        r : float
            未使用（ImageJ 互換性のため）
        white_objects : bool
            True: 白い背景に黒いオブジェクト

        Returns:
        --------
        binary : np.ndarray
            二値化画像
        """
        from skimage.filters import threshold_sauvola

        # parameter_1 が 0 の場合、デフォルト値 0.5 を使用
        k = k if k != 0 else 0.5

        # window_size = 2 * radius + 1
        window_size = 2 * radius + 1

        # Sauvola 閾値を計算
        threshold = threshold_sauvola(image, window_size=window_size, k=k)

        # 二値化
        if white_objects:
            binary = (image > threshold).astype(np.uint8) * 255
        else:
            binary = (image <= threshold).astype(np.uint8) * 255

        return binary


class BinaryPostProcessor:
    """二値化後の後処理クラス"""

    @staticmethod
    def remove_small_objects(
        binary_img: np.ndarray,
        min_size: int = 50,
        use_mean_threshold: bool = True,
    ) -> np.ndarray:
        """
        小さなオブジェクトを除去
        ImageJ の removeSmallParticlesImproved に相当

        Parameters:
        -----------
        binary_img : np.ndarray
            二値化画像
        min_size : int
            最小サイズ（use_mean_threshold=Falseの場合に使用）
        use_mean_threshold : bool
            True: 平均面積より小さいオブジェクトを除去
            False: min_sizeより小さいオブジェクトを除去

        Returns:
        --------
        result : np.ndarray
            処理後の二値化画像
        """
        from skimage import measure

        if binary_img is None or binary_img.size == 0:
            return binary_img

        result = binary_img.copy()

        # 閾値200-255で二値化
        _, thresholded = cv2.threshold(result, 200, 255, cv2.THRESH_BINARY)

        # ラベリング（connectivity=2は8近傍）
        labels = measure.label(thresholded > 0, connectivity=2)
        props = measure.regionprops(labels)

        if len(props) == 0:
            return result

        if use_mean_threshold:
            # 平均面積を計算
            total_area = sum(prop.area for prop in props)
            mean_area = total_area / len(props)

            # 平均面積より小さいオブジェクトを除去
            for prop in props:
                if prop.area < mean_area:
                    result[labels == prop.label] = 0
        else:
            # 指定サイズより小さいオブジェクトを除去
            for prop in props:
                if prop.area < min_size:
                    result[labels == prop.label] = 0

        return result

    @staticmethod
    def fill_holes(binary_img: np.ndarray) -> np.ndarray:
        """穴を埋める"""
        return ndimage.binary_fill_holes(binary_img).astype(np.uint8) * 255

    @staticmethod
    def morphological_closing(
        binary_img: np.ndarray, kernel_size: int = 3
    ) -> np.ndarray:
        """モルフォロジカルクロージング"""
        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (kernel_size, kernel_size)
        )
        return cv2.morphologyEx(binary_img, cv2.MORPH_CLOSE, kernel)

    @staticmethod
    def morphological_opening(
        binary_img: np.ndarray, kernel_size: int = 3
    ) -> np.ndarray:
        """モルフォロジカルオープニング"""
        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (kernel_size, kernel_size)
        )
        return cv2.morphologyEx(binary_img, cv2.MORPH_OPEN, kernel)

    @staticmethod
    def despeckle(
        binary_img: np.ndarray, min_size: int = 50, max_iterations: int = 1
    ) -> np.ndarray:
        """ImageJ の Despeckle に相当するノイズ除去"""
        if binary_img is None or binary_img.size == 0:
            return binary_img

        result = binary_img.copy()
        for _ in range(max_iterations):
            if len(result.shape) == 2:
                result = cv2.medianBlur(result, 3)
        return result

    @staticmethod
    def _despeckle_morphological(
        binary_img: np.ndarray, erosion_size: int = 3
    ) -> np.ndarray:
        """
        1回の erosion + morphological reconstruction でスぺックル除去。
        反復なし・タイムアウトなし。Phase4 用。

        Parameters:
        -----------
        binary_img : np.ndarray
            二値画像（0/255）
        erosion_size : int
            エロージョン用カーネル一辺

        Returns:
        --------
        result : np.ndarray
            処理後の画像
        """
        if binary_img is None or binary_img.size == 0:
            return binary_img
        kernel = np.ones((erosion_size, erosion_size), np.uint8)
        seed = cv2.erode(binary_img, kernel, iterations=1)
        seed_f = seed.astype(np.float64)
        mask_f = binary_img.astype(np.float64)
        result = reconstruction(seed_f, mask_f, method="dilation")
        return result.astype(np.uint8)

    @staticmethod
    def denoise_improved(
        binary_img: np.ndarray,
        max_iterations: int = 5,
        remove_small_particles: bool = True,
        method: str = "morphological",
        erosion_size: int = 3,
    ) -> np.ndarray:
        """
        ImageJマクロの denoiseImproved に相当
        method="morphological"（デフォルト）: 1回 erosion + reconstruction。反復なし・タイムアウトなし。
        method="iterative": 従来の反復 Despeckle（面積が変化しなくなるまで、max_iterations で打ち切り）。

        Parameters:
        -----------
        binary_img : np.ndarray
            二値化画像
        max_iterations : int
            最大反復回数（method="iterative" のときのみ使用）
        remove_small_particles : bool
            小粒子除去を実行するか
        method : str
            "morphological"（デフォルト）または "iterative"
        erosion_size : int
            method="morphological" のときのエロージョンカーネル一辺

        Returns:
        --------
        result : np.ndarray
            ノイズ除去後の画像
        """
        if binary_img is None or binary_img.size == 0:
            return binary_img

        if method == "morphological":
            result = BinaryPostProcessor._despeckle_morphological(
                binary_img, erosion_size=erosion_size
            )
        else:
            result = binary_img.copy()
            for iteration in range(max_iterations):
                area1 = np.sum(result > 0)
                if len(result.shape) == 2:
                    result = cv2.medianBlur(result, 3)
                area2 = np.sum(result > 0)
                if area1 == area2:
                    break
                if iteration == max_iterations - 1:
                    print(
                        f"Warning: Despeckle timeout (fixed limit: {max_iterations})"
                    )

        if remove_small_particles:
            result = BinaryPostProcessor.remove_small_particles_improved(result)

        return result

    @staticmethod
    def remove_small_particles_improved(binary_img: np.ndarray) -> np.ndarray:
        """
        ImageJマクロの removeSmallParticlesImproved に相当
        平均面積より小さいパーティクルを除去

        Parameters:
        -----------
        binary_img : np.ndarray
            二値化画像

        Returns:
        --------
        result : np.ndarray
            処理後の画像
        """
        from skimage import measure

        if binary_img is None or binary_img.size == 0:
            return binary_img

        result = binary_img.copy()

        # 閾値200-255で二値化
        _, thresholded = cv2.threshold(result, 200, 255, cv2.THRESH_BINARY)

        # パーティクル解析（connectivity=2は8近傍）
        labels = measure.label(thresholded > 0, connectivity=2)
        props = measure.regionprops(labels)

        if len(props) == 0:
            return result

        # 総面積と平均面積を計算
        total_area = sum(prop.area for prop in props)
        particle_count = len(props)
        mean_area = total_area / particle_count

        # 平均面積より小さいパーティクルを黒で塗りつぶし
        for prop in props:
            if prop.area < mean_area:
                result[labels == prop.label] = 0

        return result

    @staticmethod
    def remove_small_particles(
        binary_img: np.ndarray,
        min_size: int = 50,
        use_mean_threshold: bool = True,
    ) -> np.ndarray:
        """ImageJ の removeSmallParticlesImproved に相当"""
        from skimage import measure

        if binary_img is None or binary_img.size == 0:
            return binary_img

        result = binary_img.copy()
        _, thresholded = cv2.threshold(result, 200, 255, cv2.THRESH_BINARY)
        labels = measure.label(thresholded > 0, connectivity=2)
        props = measure.regionprops(labels)

        if len(props) == 0:
            return result

        if use_mean_threshold:
            total_area = sum(prop.area for prop in props)
            mean_area = total_area / len(props)
            for prop in props:
                if prop.area < mean_area:
                    result[labels == prop.label] = 0
        else:
            for prop in props:
                if prop.area < min_size:
                    result[labels == prop.label] = 0

        return result
