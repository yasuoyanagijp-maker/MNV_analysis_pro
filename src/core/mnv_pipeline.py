"""
MNV解析の完全パイプライン
全てのMNV解析ステップを統合
"""

import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from ariake_octa.mnv.flow_deficit_visualizer import FlowDeficitVisualizer
from ariake_octa.mnv.regional_analyzer import RegionalAnalyzer
# 可視化モジュール
from ariake_octa.mnv.visualization_rgb import VisualizationRGB
from core.flow_deficit import FlowDeficitAnalyzer
from core.mnv_analysis import (SpatialDistributionAnalyzer,
                               TrunkVesselClassifier)
from core.pattern_classifier import (
    MNVClassifier,
    classify_morphology_final,
    classify_pathophysiology_final,
    compute_overall_confidence,
    validate_combination_final,
)
from core.pattern_metrics import (
    calculate_complexity_pca,
    calculate_trunk_distribution_score,
)
from core.roi_manager import ROIDetector, ROIModifier
from core.skeleton_analysis import (BranchAnalyzer, DiameterAnalyzer,
                                    EulerAnalyzer, FractalAnalyzer,
                                    HighSkewnessAnalyzer, SkeletonAnalyzer,
                                    TaggedSkeletonProcessor)
from utils.image_utils import ScaleManager
from utils.imagej_compatible_output import ImageJOutputManager

from .vessel_detection import MNVPreprocessor

# 小画像判定の閾値（mainstreamer と共通。変更時は両方で参照するため1箇所で定義）
SMALL_IMAGE_THRESHOLD = 800

# 解像度別フィルタデフォルト（analyze() 内で画像幅に応じて選択。ユーザー指定時は上書きしない）
FILTER_PARAMS_SMALL = {
    "otsu_scale": 0.75,
    "sauvola_k": 0.7,
    "percentile_low": 1.0,
    "percentile_high": 99.0,
    "sigma": 2.5,
    "beta": 0.5,
    "c": 15,
    "tubeness_denoise": "full",
    "normalization": "minmax",
}
FILTER_PARAMS_LARGE = {
    "otsu_scale": 0.7,  # 1024px optimized (Phase A 2026-02)
    "sauvola_k": 0.9,
    "percentile_low": 1.0,
    "percentile_high": 99.0,
    "sigma": 2.5,
    "beta": 0.5,
    "c": 15,
    "tubeness_denoise": "full",
    "normalization": "percentile",
}


def _skeleton_structure_to_branch_data(
    skeleton_structure: Dict,
    mm_per_pixel: float,
) -> Dict:
    """
    Convert SkeletonAnalyzer.analyze_skeleton_structure result to branch_data.

    ImageJ Analyze Skeleton gives per-branch segments; connectedComponents does not.
    Returns dict with 'endpoints': [(v1_y,v1_x,v2_y,v2_x),...], 'lengths': [px,...].
    """
    branches = skeleton_structure.get("branches", [])
    if not branches:
        return {"endpoints": [], "lengths": []}
    endpoints = []
    lengths = []
    for b in branches:
        if b.v1 is None or len(b.v1.points) == 0:
            continue
        p1 = b.v1.points[0]
        v1_x, v1_y = int(p1.x), int(p1.y)
        if b.v2 is not None and len(b.v2.points) > 0:
            p2 = b.v2.points[0]
            v2_x, v2_y = int(p2.x), int(p2.y)
        elif len(b.points) >= 1:
            p2 = b.points[-1]
            v2_x, v2_y = int(p2.x), int(p2.y)
        else:
            continue
        length_mm = float(b.length) if b.length > 0 else 0.0
        length_px = length_mm / mm_per_pixel if mm_per_pixel > 0 else 0.0
        endpoints.append((float(v1_y), float(v1_x), float(v2_y), float(v2_x)))
        lengths.append(length_px)
    return {"endpoints": endpoints, "lengths": lengths}


# ロガーの設定
def setup_logger(name: str, level=logging.INFO) -> logging.Logger:
    """詳細なロギング用のロガーを設定"""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # コンソールハンドラ
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


def validate_image(image: np.ndarray, step_name: str, logger: logging.Logger) -> bool:
    """画像データの検証"""
    try:
        if image is None:
            logger.error(f"{step_name}: Image is None")
            return False

        if not isinstance(image, np.ndarray):
            logger.error(f"{step_name}: Image is not numpy array, type={type(image)}")
            return False

        if image.size == 0:
            logger.error(f"{step_name}: Image is empty")
            return False

        logger.debug(
            f"{step_name}: Image validation - Shape={image.shape}, "
            f"Dtype={image.dtype}, Min={image.min()}, Max={image.max()}"
        )

        # 異常値チェック
        if np.isnan(image).any():
            logger.warning(f"{step_name}: Image contains NaN values")

        if np.isinf(image).any():
            logger.warning(f"{step_name}: Image contains Inf values")

        return True
    except Exception as e:
        logger.error(f"{step_name}: Validation error - {str(e)}")
        return False


class MNVPipeline:
    """
    MNV解析の完全パイプライン
    processFileImproved に対応
    """

    def __init__(
        self,
        scale_mm: float,
        mexican_hat_sigma: float = 1.0,
        tubeness_sigma: float = 2.5,
        save_stages: bool = True,
        verbose: bool = True,
        debug: bool = False,
        enable_roi_refinement: bool = True,
        filter_params: Optional[Dict] = None,
    ):  # ★ True に変更
        """
        Parameters:
        -----------
        scale_mm : float
            画像の実寸法（mm）
        mexican_hat_sigma : float
            Mexican Hatフィルタのsigma
        tubeness_sigma : float
            Tubenessフィルタのsigma
        save_stages : bool
            処理段階を保存するか
        verbose : bool
            詳細ログを出力するか
        debug : bool
            デバッグログを出力するか
        enable_roi_refinement : bool
            ROI精密修正を有効にするか（True=ImageJ互換、False=高速モード）
            デフォルト: True（ImageJと同じ動作）
        filter_params : dict, optional
            FilterBank用オプション: percentile_low, percentile_high,
            otsu_scale, sauvola_k
        """
        self.scale_mm = scale_mm
        self.mexican_hat_sigma = mexican_hat_sigma
        self.tubeness_sigma = tubeness_sigma
        self.save_stages = save_stages
        self.verbose = verbose
        self.debug = debug
        self.enable_roi_refinement = enable_roi_refinement
        # filter_params が外部から指定された場合はそのまま使用。
        # None の場合は analyze() 内で画像幅に応じて自動選択する。
        self._user_filter_params = filter_params
        self.filter_params = (
            filter_params
            if filter_params is not None
            else dict(FILTER_PARAMS_LARGE)  # analyze() で画像幅に応じて上書き
        )

        # ★ ImageJ互換: ROI座標を保持（ImageJのグローバル変数に相当）
        self.roi_contour = None  # 輪郭座標（numpy配列）
        self.roi_mask = None  # マスク画像
        self.roi_type = None  # ROIタイプ（将来の拡張用）

        # ロガーの設定
        log_level = (
            logging.DEBUG if debug else (logging.INFO if verbose else logging.WARNING)
        )
        self.logger = setup_logger("MNVPipeline", log_level)

    def analyze(
        self,
        image_path: str,
        output_dir: Optional[str] = None,
        flow_deficit_image_path: Optional[str] = None,
        roi_mask: Optional[np.ndarray] = None,
    ) -> Dict[str, any]:
        """
        MNV解析を実行

        Parameters:
        -----------
        image_path : str
            入力画像パス
        output_dir : str, optional
            出力ディレクトリ
        flow_deficit_image_path : str, optional
            Flow Deficit用画像パス
        roi_mask : np.ndarray, optional
            ROIマスク（Noneの場合は自動検出）

        Returns:
        --------
        results : dict
            解析結果
        """
        start_time = time.time()
        self.logger.info(f"\n=== Processing: {Path(image_path).name} ===")
        self.logger.info(f"Start Time: {datetime.now().strftime('%H:%M:%S')}\n")

        self.logger.info("=" * 60)
        self.logger.info("Starting MNV Analysis Pipeline")
        self.logger.info(f"Input file: {image_path}")
        self.logger.info(f"Scale: {self.scale_mm} mm")
        self.logger.debug(
            f"Parameters: mexican_hat_sigma={self.mexican_hat_sigma}, "
            f"tubeness_sigma={self.tubeness_sigma}"
        )

        try:
            # 画像を読み込み
            self.logger.info("Loading input image...")
            from utils.image_utils import ImageProcessor

            image_processor = ImageProcessor()
            image = image_processor.load_image(image_path, as_gray=True)
            image = image_processor.ensure_8bit(image)

            # 画像検証
            if not validate_image(image, "Input Image", self.logger):
                raise ValueError("Input image validation failed")

            h, w = image.shape
            self.logger.info(f"✓ Image loaded successfully: {w}x{h} pixels")
            self.logger.debug(f"  Memory usage: {image.nbytes / 1024 / 1024:.2f} MB")

            # スケール管理（面積算出用）
            scale_manager = ScaleManager(w, self.scale_mm)
            mm_per_px = scale_manager.mm_per_pixel
            self.logger.debug(
                f"  Scale manager: {scale_manager.mm_per_pixel:.6f} mm/pixel"
            )
            px_per_mm = (1.0 / mm_per_px) if mm_per_px > 0 else 0
            self.logger.info(
                f"  Scale: {self.scale_mm} mm / {w} px = "
                f"{mm_per_px:.6f} mm/px ({px_per_mm:.1f} px/mm)"
            )

            # Pixel size (mm per pixel) をパイプラインに保持して可視化モジュールへ渡す
            self.pixel_size_mm = scale_manager.mm_per_pixel
            self.logger.debug(
                f"  pixel_size_mm set to: {self.pixel_size_mm:.6f} mm/pixel"
            )

            # Step 1: ROI検出
            step_start = time.time()
            self.logger.info("-" * 60)
            self.logger.info("Step 1: ROI Detection")

            if roi_mask is None:
                self.logger.debug("  No ROI mask provided, detecting automatically...")
                roi_detector = ROIDetector()
                roi_mask, roi_type = roi_detector.detect_roi_automatic(image)
                self.logger.debug(f"  Detected ROI type: {roi_type}")

                # ★ ImageJ互換: 輪郭座標を抽出して保存
                contours, _ = cv2.findContours(
                    roi_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
                )
                self.roi_contour = max(contours, key=cv2.contourArea)
                self.roi_type = roi_type

                # ROI修正（ImageJ互換動作）
                if self.enable_roi_refinement:
                    self.logger.debug(
                        "  Applying ROI refinement (ImageJ compatible)..."
                    )
                    roi_modifier = ROIModifier()
                    # ★ ImageJ互換: 修正後の輪郭を取得
                    self.roi_contour = roi_modifier.modify_roi_get_contour(
                        image,
                        self.roi_contour,
                        iterations=5,  # ROI_MOD_ITERATIONS
                        search_radius=3,  # ROI_MOD_SEARCH_RADIUS
                        angle_threshold=0.5,  # ROI_MOD_ANGLE_THRESHOLD
                    )

                    # マスクを再作成
                    roi_mask = np.zeros(image.shape, dtype=np.uint8)
                    cv2.drawContours(roi_mask, [self.roi_contour], -1, 255, -1)
                    self.logger.debug("  ROI modification completed")
                else:
                    self.logger.debug("  ROI refinement disabled (fast mode)")
            else:
                self.logger.debug("  Using provided ROI mask")
                # ★ 寸法検証: roi_mask と image のサイズが一致することを確認
                if roi_mask.shape != image.shape:
                    self.logger.warning(
                        f"  ⚠ ROI mask shape {roi_mask.shape} != "
                        f"image shape {image.shape}, resizing..."
                    )
                    roi_mask = cv2.resize(
                        roi_mask, (w, h), interpolation=cv2.INTER_NEAREST
                    )
                    self.logger.debug(f"  ROI mask resized to {roi_mask.shape}")
                # ★ ImageJ互換: 外部から与えられたマスクから輪郭を抽出
                contours, _ = cv2.findContours(
                    roi_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
                )
                self.roi_contour = max(contours, key=cv2.contourArea)

            self.roi_mask = roi_mask

            # ★ デバッグ: ROI マスクを出力ディレクトリに保存
            if output_dir:
                debug_roi_path = Path(output_dir) / "debug_roi_mask.png"
                cv2.imwrite(str(debug_roi_path), roi_mask)
                self.logger.debug(f"  ROI mask saved: {debug_roi_path}")

            # ROI検証
            if not validate_image(roi_mask, "ROI Mask", self.logger):
                raise ValueError("ROI mask validation failed")

            # MNV面積を測定
            mnv_area_pixels = np.sum(roi_mask > 0)
            mnv_area_mm2 = mnv_area_pixels * (scale_manager.mm_per_pixel**2)
            roi_coverage = (mnv_area_pixels / (w * h)) * 100

            step_time = time.time() - step_start
            self.logger.debug(f"  Step 1 time: {step_time:.2f}s")

            self.logger.info("✓ ROI Detection completed")
            self.logger.info(
                f"  MNV Area: {mnv_area_mm2:.3f} mm² ({mnv_area_pixels} pixels)"
            )
            self.logger.info(f"  ROI Coverage: {roi_coverage:.1f}% of image")
            self.logger.debug(f"  Processing time: {step_time:.2f}s")

            # 警告チェック
            if roi_coverage < 5:
                self.logger.warning(
                    f"⚠ ROI coverage is very small ({roi_coverage:.1f}%)"
                )
            elif roi_coverage > 80:
                self.logger.warning(
                    f"⚠ ROI coverage is very large ({roi_coverage:.1f}%)"
                )

            if mnv_area_mm2 < 0.1:
                self.logger.warning(
                    f"⚠ MNV area is very small ({mnv_area_mm2:.3f} mm²)"
                )

            # ----------------------------------------------------------
            # 解像度に応じたフィルタパラメータの自動選択（800px で明確に分岐）
            # ----------------------------------------------------------
            # ユーザーが filter_params を指定した場合は上書きしない。
            if self._user_filter_params is not None:
                self.logger.info(
                    f"  Image width {w}px -> using user-supplied filter params"
                )
            elif w < SMALL_IMAGE_THRESHOLD:
                self.filter_params = dict(FILTER_PARAMS_SMALL)
                self.logger.info(
                    f"  Small image ({w}px < {SMALL_IMAGE_THRESHOLD}px)"
                    " -> FILTER_PARAMS_SMALL (otsu=0.75, k=0.7, minmax)"
                )
            else:
                self.filter_params = dict(FILTER_PARAMS_LARGE)
                self.logger.info(
                    f"  Large image ({w}px >= {SMALL_IMAGE_THRESHOLD}px)"
                    " -> FILTER_PARAMS_LARGE (otsu=0.7, k=0.9, percentile)"
                )

            # Step 2: 前処理
            step_start = time.time()
            self.logger.info("-" * 60)
            self.logger.info("Step 2: Image Preprocessing")
            self.logger.debug(f"  Mexican Hat sigma: {self.mexican_hat_sigma}")
            self.logger.debug(f"  Tubeness sigma: {self.tubeness_sigma}")
            self.logger.debug(
                f"  Filter params: otsu_scale={self.filter_params.get('otsu_scale')}, "
                f"sauvola_k={self.filter_params.get('sauvola_k')}, "
                f"normalization={self.filter_params.get('normalization', 'percentile')}"
            )

            preprocessor = MNVPreprocessor(
                mexican_hat_sigma=self.mexican_hat_sigma,
                tubeness_sigma=self.tubeness_sigma,
                filter_params=self.filter_params,
            )

            preprocess_results = preprocessor.preprocess_mnv(image, roi_mask)
            binary = preprocess_results["binary"]
            mex_hat = preprocess_results.get("mex_hat")
            tubeness = preprocess_results.get("tubeness")

            # デバッグ: 前処理中間画像を保存（output_dir 指定時）
            if output_dir:
                debug_dir = Path(output_dir)
                debug_dir.mkdir(parents=True, exist_ok=True)
                if mex_hat is not None:
                    cv2.imwrite(str(debug_dir / "debug_mex_hat.png"), mex_hat)
                if tubeness is not None:
                    cv2.imwrite(str(debug_dir / "debug_tubeness.png"), tubeness)
                if binary is not None:
                    cv2.imwrite(str(debug_dir / "debug_binary_combined.png"), binary)
                self.logger.debug(
                    "  Saved: debug_mex_hat.png, debug_tubeness.png, "
                    "debug_binary_combined.png"
                )

            # バイナリ画像検証
            if not validate_image(binary, "Binary Image", self.logger):
                raise ValueError("Binary image validation failed")

            # バイナリ画像の品質チェック
            if not np.all((binary == 0) | (binary == 255)):
                self.logger.warning("⚠ Binary image contains non-binary values")
                binary = ((binary > 0) * 255).astype(np.uint8)
                self.logger.debug("  Converted to strict binary (0/255)")

            # 血管面積を測定（ROI内のみ。ImageJ互換: area_total*(area_frac/100)=white_area）
            vessel_area_pixels = np.sum((binary > 0) & (roi_mask > 0))
            vessel_area_mm2 = vessel_area_pixels * (scale_manager.mm_per_pixel**2)
            # ImageJ: vessel_densities = vessel_Areas / MNV_Areas（ratio 0-1、%ではない）
            vessel_density = vessel_area_mm2 / mnv_area_mm2 if mnv_area_mm2 > 0 else 0

            step_time = time.time() - step_start
            self.logger.debug(f"  Step 2 time: {step_time:.2f}s")

            self.logger.info("✓ Preprocessing completed")
            self.logger.info(
                f"  Vessel Area: {vessel_area_mm2:.3f} mm² ({vessel_area_pixels} pixels)"
            )
            self.logger.info(f"  Vessel Density: {vessel_density * 100:.2f}%")
            self.logger.debug(f"  Processing time: {step_time:.2f}s")

            # 血管密度の警告
            if vessel_density < 0.05:
                self.logger.warning(
                    f"⚠ Very low vessel density ({vessel_density * 100:.2f}%)"
                )
            elif vessel_density > 0.8:
                self.logger.warning(
                    f"⚠ Unusually high vessel density ({vessel_density * 100:.2f}%)"
                )

            if vessel_area_pixels == 0:
                self.logger.error("✗ No vessels detected - analysis may fail")

            # Step 3: スケルトン解析
            step_start = time.time()
            self.logger.info("-" * 60)
            self.logger.info("Step 3: Skeleton Analysis")

            skeleton_results = self._perform_skeleton_analysis(
                binary, roi_mask, scale_manager
            )

            # スケルトン結果の検証
            if "skeleton" in skeleton_results:
                skeleton_pixels = np.sum(skeleton_results["skeleton"] > 0)
                self.logger.debug(f"  Skeleton pixels: {skeleton_pixels}")
                if skeleton_pixels == 0:
                    self.logger.warning("⚠ Skeleton is empty")

            step_time = time.time() - step_start
            self.logger.debug(f"  Step 3 time: {step_time:.2f}s")

            self.logger.info("✓ Skeleton Analysis completed")
            self.logger.info(
                f"  Total Length: {skeleton_results.get('vessel_length_mm', 0):.2f} mm"
            )
            self.logger.info(
                f"  Mean Diameter: {skeleton_results.get('mean_diameter_um', 0):.1f} μm"
            )
            self.logger.info(
                f"  Tortuosity: {skeleton_results.get('tortuosity', 0):.3f}"
            )
            self.logger.debug(
                f"  Junctions: {skeleton_results.get('num_junctions', 0)}"
            )
            self.logger.debug(f"  Branches: {skeleton_results.get('num_branches', 0)}")
            self.logger.debug(
                f"  Endpoints: {skeleton_results.get('num_endpoints', 0)}"
            )
            self.logger.debug(f"  Processing time: {step_time:.2f}s")

            # 異常値チェック
            if skeleton_results.get("vessel_length_mm", 0) == 0:
                self.logger.error("✗ No vessel length detected")
            if skeleton_results.get("tortuosity", 0) > 1.5:
                self.logger.warning(
                    f"⚠ High tortuosity detected ({skeleton_results['tortuosity']:.3f})"
                )

            # Step 4: 空間分布解析
            step_start = time.time()
            self.logger.info("-" * 60)
            self.logger.info("Step 4: Spatial Distribution Analysis")

            spatial_results = self._perform_spatial_analysis(
                skeleton_results["distance_map"],
                skeleton_results["thick_vessel_map"],
                roi_mask,
                scale_manager,
            )

            step_time = time.time() - step_start
            self.logger.debug(f"  Step 4 time: {step_time:.2f}s")

            self.logger.info("✓ Spatial Distribution Analysis completed")
            # Overall FD from skeleton (Step 3); Center/Periphery FD from Step 6
            self.logger.info(
                f"  Fractal Dimension: {skeleton_results.get('fractal_dimension', 0):.3f}"
            )
            self.logger.info(
                f"  Trunk Pattern: {spatial_results.get('trunk_pattern', 'Unknown')}"
            )
            self.logger.debug(
                f"  Trunk Eccentricity: {spatial_results.get('trunk_eccentricity', -1):.3f}"
            )
            self.logger.debug(f"  Processing time: {step_time:.2f}s")

            # フラクタル次元の妥当性チェック（Step 3 の refined_skeleton FD）
            fd = skeleton_results.get("fractal_dimension", 0)
            if fd < 0.9 or fd > 2.0:
                self.logger.warning(
                    f"⚠ Unusual fractal dimension ({fd:.3f}), expected range: 0.9-2.0"
                )

            # Step 5: Flow Deficit解析
            step_start = time.time()
            self.logger.info("-" * 60)
            self.logger.info("Step 5: Flow Deficit Analysis")

            if flow_deficit_image_path is not None:
                self.logger.debug(f"  Flow deficit image: {flow_deficit_image_path}")
                fd_results = self._perform_flow_deficit_analysis(
                    flow_deficit_image_path, roi_mask, scale_manager
                )
                self.logger.info(f"  FD R1: {fd_results.get('FD_percent_R1', 0):.2f}%")
                self.logger.info(f"  FD R2: {fd_results.get('FD_percent_R2', 0):.2f}%")
                self.logger.info(f"  FD R3: {fd_results.get('FD_percent_R3', 0):.2f}%")
            else:
                self.logger.debug(
                    "  No flow deficit image provided, using default values"
                )
                fd_results = self._get_default_fd_results()

            step_time = time.time() - step_start
            self.logger.debug(f"  Step 5 time: {step_time:.2f}s")

            self.logger.info("✓ Flow Deficit Analysis completed")
            self.logger.debug(f"  Processing time: {step_time:.2f}s")

            # Step 6: パターン分類
            step_start = time.perf_counter()
            self.logger.info("-" * 60)
            self.logger.info("Step 6: Pattern Classification")

            t6_1 = time.perf_counter()
            classification_results = self._perform_pattern_classification(
                skeleton_results, spatial_results, mnv_area_mm2
            )
            self.logger.debug(
                f"[Step6] 1. pattern_classification: {time.perf_counter()-t6_1:.3f}s"
            )

            t6_2 = time.perf_counter()
            image_stats = self._calculate_image_statistics(image, roi_mask)
            self.logger.debug(
                f"[Step6] 2. image_statistics: {time.perf_counter()-t6_2:.3f}s"
            )

            t6_3 = time.perf_counter()
            try:
                visualizer = VisualizationRGB(
                    pixel_size_mm=scale_manager.mm_per_pixel,
                    scale_bar_length_mm=0.5,
                    font_scale=0.6,
                )
                metrics_for_vis = {
                    "lesion_area_mm2": mnv_area_mm2,
                    "vessel_density_percent": vessel_density * 100
                    if vessel_density
                    else 0,
                    "skeleton_num_junctions": skeleton_results.get(
                        "num_junctions", 0
                    ),
                    "overall_fd_ratio_percent": fd_results.get(
                        "FD_percent_R1", 0
                    ),
                }
                vis_rgb = visualizer.create_rgb_visualization(
                    original_image=image,
                    binary_vessel=binary,
                    lesion_mask=roi_mask,
                    metrics=metrics_for_vis,
                    highskew_mask=skeleton_results.get(
                        "dilated_highSkew_for_visualization"
                    ),
                )
            except Exception as e:
                self.logger.warning(f"RGB visualization failed: {e}")
                vis_rgb = None
            self.logger.debug(
                f"[Step6] 3. rgb_visualization: {time.perf_counter()-t6_3:.3f}s"
            )

            # FD可視化画像（flow_deficit_image_path が指定されている場合のみ）
            fd_vis = None
            if flow_deficit_image_path is not None:
                try:
                    from utils.image_utils import ImageProcessor

                    image_processor = ImageProcessor()
                    fd_image = image_processor.load_image(
                        flow_deficit_image_path, as_gray=True
                    )
                    fd_image = image_processor.ensure_8bit(fd_image)
                    
                    # 【ROI転写】3.tif上で描画されたROIを4.tif（fd_image）の座標系に転写
                    # 3.tifと4.tifは位置が揃っている前提で、roi_maskをfd_imageのサイズにリサイズ
                    fd_h, fd_w = fd_image.shape
                    roi_h, roi_w = roi_mask.shape
                    
                    if (roi_h, roi_w) != (fd_h, fd_w):
                        self.logger.debug(
                            f"Transferring ROI from 3.tif ({roi_h}x{roi_w}) "
                            f"to 4.tif ({fd_h}x{fd_w}) coordinate system"
                        )
                        # ROIマスクを4.tifのサイズに転写（NEAREST補間でバイナリマスクを保持）
                        base_roi_mask = cv2.resize(
                            roi_mask.astype(np.uint8),
                            (fd_w, fd_h),
                            interpolation=cv2.INTER_NEAREST
                        ).astype(bool)
                    else:
                        # サイズが一致している場合はそのまま使用
                        base_roi_mask = (roi_mask > 0).astype(bool)
                        self.logger.debug(
                            f"ROI mask size matches FD image: {fd_h}x{fd_w}"
                        )
                    
                    # FD画像からFlow Deficit領域を抽出
                    _, fd_binary = cv2.threshold(
                        fd_image, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
                    )
                    # Flow Deficit = FD画像の暗い領域（Otsu では 0）
                    # base_roi_mask（転写されたROI）内の暗い領域をFD領域とする
                    fd_mask = (
                        (fd_binary == 0) & base_roi_mask
                    ).astype(bool)
                    # デバッグ: fd_maskの統計をログ出力
                    fd_mask_sum = np.sum(fd_mask)
                    self.logger.debug(
                        f"FD mask: dtype={fd_mask.dtype}, shape={fd_mask.shape}, "
                        f"sum={fd_mask_sum} (nonzero pixels), "
                        f"fd_binary dark pixels={np.sum(fd_binary == 0)}, "
                        f"roi pixels={np.sum(roi_mask > 0)}"
                    )
                    if fd_mask_sum == 0:
                        self.logger.warning(
                            "⚠ FD mask is empty - no Flow Deficit pixels found. "
                            "Check that fd_binary has dark regions (==0) within ROI."
                        )
                    # 病変中心を計算（転写されたROIマスクを使用）
                    contours, _ = cv2.findContours(
                        base_roi_mask.astype(np.uint8),
                        cv2.RETR_EXTERNAL,
                        cv2.CHAIN_APPROX_SIMPLE
                    )
                    if contours and cv2.moments(contours[0])["m00"] != 0:
                        M = cv2.moments(contours[0])
                        center_x = M["m10"] / M["m00"]
                        center_y = M["m01"] / M["m00"]
                        lesion_center = (center_y, center_x)
                    else:
                        lesion_center = (fd_h // 2, fd_w // 2)
                    self.logger.debug(
                        f"FD lesion center: (y={lesion_center[0]:.1f}, x={lesion_center[1]:.1f}), "
                        f"pixel_size_mm={scale_manager.mm_per_pixel:.6f}"
                    )
                    
                    # FlowDeficitVisualizerを初期化
                    fd_visualizer = FlowDeficitVisualizer(
                        pixel_size_mm=scale_manager.mm_per_pixel,
                        ring_widths_mm=[0.2, 0.4, 0.6],
                        blur_sigma=4.0,
                    )
                    # デバッグ: ring_widths_pixelsを確認
                    self.logger.debug(
                        f"FD ring widths (pixels): {fd_visualizer.ring_widths_pixels}"
                    )
                    
                    # 【可視化】4.tifを背景として使用し、転写されたROIから物理的拡張で3層のマスクを生成
                    # base_roi_mask（転写されたROI）を渡して、物理距離で3層に拡張
                    fd_vis = fd_visualizer.create_fd_visualization(
                        fd_mask=fd_mask,
                        lesion_center=lesion_center,
                        background_image=fd_image,  # 4.tifを背景として使用
                        roi_mask=base_roi_mask,  # 転写されたROIマスク（物理的拡張の起点）
                    )
                except Exception as e:
                    # 【詳細なエラーログ】FD可視化失敗の原因を記録
                    import traceback
                    error_trace = traceback.format_exc()
                    self.logger.error(
                        f"FD visualization failed: {e}\n"
                        f"Traceback:\n{error_trace}"
                    )
                    self.logger.debug(
                        f"FD visualization failure context: "
                        f"flow_deficit_image_path={flow_deficit_image_path}, "
                        f"roi_mask shape={roi_mask.shape if roi_mask is not None else None}, "
                        f"fd_image shape={fd_image.shape if 'fd_image' in locals() else None}"
                    )
                    fd_vis = None

            self.logger.debug(
                f"[Step6] Step 6 subtotal: {time.perf_counter()-step_start:.3f}s"
            )

            results = {
                "mnv_area_mm2": mnv_area_mm2,
                "vessel_area_mm2": vessel_area_mm2,
                "vessel_density": vessel_density,  # ImageJ互換: ratio (vessel_Areas/MNV_Areas)
                **skeleton_results,
                **spatial_results,
                **fd_results,
                **classification_results,
                **image_stats,  # 画像統計を追加
                "binary": binary,
                "roi_mask": roi_mask,
                "mex_hat": mex_hat,
                "tubeness": tubeness,
                "rgb": vis_rgb,
                "fd_visualization": fd_vis,
            }

            step_time = time.perf_counter() - step_start
            total_time = time.time() - start_time

            self.logger.debug(f"  Step 6 time: {step_time:.2f}s")

            self.logger.info("✓ Pattern Classification completed")
            self.logger.info(f"  Subtype: {results['mnv_subtype']}")
            self.logger.info(f"  Complexity Score: {results['complexity_score']:.1f}")
            self.logger.info(f"  Stability Score: {results['stability_score']:.1f}")
            self.logger.info(
                f"  Maturity Index: {results.get('maturity_index', 0):.1f}"
            )
            self.logger.debug(f"  Processing time: {step_time:.2f}s")

            self.logger.info("=" * 60)
            self.logger.info("✓ Analysis Pipeline Completed Successfully")
            self.logger.info(
                f"  Total Time: {total_time:.2f}s ({total_time/60:.1f}min)"
            )
            self.logger.info(f"  End Time: {datetime.now().strftime('%H:%M:%S')}")
            self.logger.info("=" * 60)

            return results

        except Exception as e:
            self.logger.error("=" * 60)
            self.logger.error("✗ Analysis Pipeline Failed")
            self.logger.error(f"  Error: {str(e)}")
            self.logger.error(f"  Error type: {type(e).__name__}")
            import traceback

            self.logger.debug(f"  Traceback:\n{traceback.format_exc()}")
            self.logger.error("=" * 60)
            raise

    def _perform_skeleton_analysis(
        self,
        binary: np.ndarray,
        roi_mask: np.ndarray,
        scale_manager: ScaleManager,
    ) -> Dict:
        """
        スケルトン解析を実行（修正版）
        ImageJの performSkeletonAnalysisImproved に対応
        """
        t0 = time.perf_counter()

        skeleton_analyzer = SkeletonAnalyzer(scale_manager.mm_per_pixel)
        skeleton = skeleton_analyzer.skeletonize(binary)
        skeleton = cv2.bitwise_and(skeleton, skeleton, mask=roi_mask)
        self.logger.debug(
            f"[Skeleton] 1. skeletonize: {time.perf_counter()-t0:.3f}s"
        )
        t1 = time.perf_counter()

        diameter_analyzer = DiameterAnalyzer(scale_manager.mm_per_pixel)
        distance_map = diameter_analyzer.create_distance_map(binary)
        distance_map_float = distance_map.astype(np.float32)
        distance_map_float[roi_mask == 0] = 0
        distance_map = distance_map_float.astype(distance_map.dtype)
        self.logger.debug(
            f"[Skeleton] 2. distance_map: {time.perf_counter()-t1:.3f}s"
        )
        t2 = time.perf_counter()

        diameter_stats = diameter_analyzer.analyze_diameter_statistics(
            distance_map, skeleton
        )
        self.logger.debug(
            f"[Skeleton] 3. diameter_stats: {time.perf_counter()-t2:.3f}s"
        )
        t3 = time.perf_counter()

        tagged_processor = TaggedSkeletonProcessor()
        tagged = tagged_processor.create_tagged_skeleton(skeleton)
        max_junction_area = tagged_processor.calculate_max_junction_area(tagged["blue"])
        refined_skeleton = tagged_processor.create_refined_skeleton(
            tagged, distance_map, max_junction_area
        )
        self.logger.debug(f"  Max junction area: {max_junction_area}")
        refined_pixels = np.sum(refined_skeleton > 0)
        self.logger.debug(
            f"[Skeleton] 4. tagged+refined_skeleton: {time.perf_counter()-t3:.3f}s"
        )
        t4 = time.perf_counter()

        skeleton_for_fractal = refined_skeleton if refined_pixels > 0 else skeleton
        if refined_pixels == 0:
            self.logger.warning(
                "  ⚠ Refined skeleton is empty, using original skeleton for fractal analysis"
            )
        fractal_analyzer = FractalAnalyzer()
        box_sizes, box_counts = fractal_analyzer.box_counting(skeleton_for_fractal)
        fractal_dim, r_squared = fractal_analyzer.calculate_fractal_dimension(
            box_sizes, box_counts
        )
        self.logger.debug(
            f"  Box counting: {len(box_sizes)} sizes, Fractal dim: {fractal_dim:.3f}"
        )
        self.logger.debug(
            f"[Skeleton] 5. fractal_dimension: {time.perf_counter()-t4:.3f}s"
        )
        t5 = time.perf_counter()

        euler_analyzer = EulerAnalyzer()
        euler_number, num_loops = euler_analyzer.calculate_euler_number(
            refined_skeleton
        )
        self.logger.debug(
            f"[Skeleton] 6. euler_number: {time.perf_counter()-t5:.3f}s"
        )
        t6 = time.perf_counter()

        skeleton_for_analysis = refined_skeleton if refined_pixels > 0 else skeleton
        refined_skeleton_structure = skeleton_analyzer.analyze_skeleton_structure(
            skeleton_for_analysis
        )
        self.logger.debug(
            f"[Skeleton] 7. analyze_skeleton_structure: {time.perf_counter()-t6:.3f}s"
        )

        self.logger.debug(
            f"  Skeleton structure: branches={refined_skeleton_structure['num_branches']}, "
            f"junctions={refined_skeleton_structure['num_junctions']}, "
            f"endpoints={refined_skeleton_structure['num_endpoints']}"
        )

        t7 = time.perf_counter()
        branch_analyzer = BranchAnalyzer(
            scale_manager.mm_per_pixel, diameter_stats["mean_diameter_um"]
        )
        tortuosity, total_length_mm = branch_analyzer.calculate_tortuosity(
            refined_skeleton_structure["branch_lengths"],
            refined_skeleton_structure["branch_euclidean_distances"],
        )

        self.logger.debug(
            f"  Tortuosity: {tortuosity:.3f}, Total length: {total_length_mm:.3f} mm"
        )

        mnv_area_mm2 = np.sum(roi_mask > 0) * (scale_manager.mm_per_pixel**2)

        corrected_diameter, corrected_length = (
            branch_analyzer.calculate_corrected_values(
                total_length_mm,
                mnv_area_mm2,
                refined_skeleton_structure["num_triple_points"],
                refined_skeleton_structure["num_quadruple_points"],
            )
        )

        densities = branch_analyzer.calculate_densities(
            total_length_mm,
            refined_skeleton_structure["num_branches"],
            refined_skeleton_structure["num_junctions"],
            refined_skeleton_structure["num_endpoints"],
            refined_skeleton_structure["num_triple_points"],
            refined_skeleton_structure["num_quadruple_points"],
        )
        self.logger.debug(
            f"[Skeleton] 8. tortuosity_densities: {time.perf_counter()-t7:.3f}s"
        )
        t8 = time.perf_counter()

        high_skew_analyzer = HighSkewnessAnalyzer(
            scale_manager.mm_per_pixel, scale_manager.pixel_size_um
        )

        (
            high_skew_skeleton,
            dilated_highSkew_for_visualization,
            high_skew_stats,
        ) = high_skew_analyzer.detect_high_skewness_segments(distance_map, skeleton)
        self.logger.debug(
            f"[Skeleton] 9. high_skewness_segments: {time.perf_counter()-t8:.3f}s"
        )
        t9 = time.perf_counter()

        mnv_area_pixels = np.sum(roi_mask > 0)
        mnv_area_mm2 = mnv_area_pixels * (scale_manager.mm_per_pixel**2)
        arteriolarization_results = high_skew_analyzer.analyze_segments(
            high_skew_skeleton, mnv_area_mm2, total_length_mm
        )
        self.logger.debug(
            f"[Skeleton] 10. arteriolarization_analyze: {time.perf_counter()-t9:.3f}s"
        )
        self.logger.debug(
            f"[Skeleton] Step 3 subtotal: {time.perf_counter()-t0:.3f}s"
        )

        # total_length_mm の扱い（キー競合なし）:
        # - vessel_length_mm: 全血管スケルトン長（上記 branch_analyzer 由来）
        # - arteriolarization_results["total_length_mm"]: 高歪度セグメントのみの総長
        #   → _PIPELINE_TO_IMAGEJ "Arteriolarization Total Length (mm)" にマッピング
        # - **arteriolarization_results でマージするため、最終 result の total_length_mm は
        #   意図どおり細動脈化（高歪度）の値となる（regional_results は total_length_mm を含まない）
        # Local Diameter Variation は arteriolarization_results に含まれる
        # （ImageJ 3918-3932: 各セグメントの平均ブランチ長の CV%）

        # 太い血管マップ
        thick_vessel_map = (distance_map > high_skew_stats["threshold"]).astype(
            np.uint8
        ) * 255

        return {
            "skeleton": skeleton,
            "refined_skeleton": refined_skeleton,
            "refined_skeleton_structure": refined_skeleton_structure,
            "distance_map": distance_map,
            "thick_vessel_map": thick_vessel_map,
            "high_skew_skeleton": high_skew_skeleton,
            "dilated_highSkew_for_visualization": dilated_highSkew_for_visualization,
            "mean_diameter_um": diameter_stats["mean_diameter_um"],
            "std_diameter_um": diameter_stats["std_diameter_um"],
            "max_diameter_um": diameter_stats["max_diameter_um"],
            "cv_diameter": diameter_stats["cv_diameter"],
            "vessel_length_mm": total_length_mm,
            "tortuosity": tortuosity,
            "num_branches": refined_skeleton_structure["num_branches"],
            "num_junctions": refined_skeleton_structure["num_junctions"],
            "num_endpoints": refined_skeleton_structure["num_endpoints"],
            "num_triple_points": refined_skeleton_structure["num_triple_points"],
            "num_quadruple_points": refined_skeleton_structure["num_quadruple_points"],
            "corrected_vessel_length_mm": corrected_length,
            "corrected_vessel_diameter_um": corrected_diameter,
            "fractal_dimension": fractal_dim,
            "euler_number": euler_number,
            "num_loops": num_loops,
            **densities,
            **arteriolarization_results,
        }

    def _perform_spatial_analysis(
        self,
        distance_map: np.ndarray,
        thick_vessel_map: np.ndarray,
        roi_mask: np.ndarray,
        scale_manager: ScaleManager,
    ) -> Dict:
        """空間分布解析を実行"""
        spatial_analyzer = SpatialDistributionAnalyzer(
            scale_manager.mm_per_pixel, scale_manager.pixel_size_um
        )

        # 画像サイズに応じて安定性スコアの参照クラスを切り替え
        try:
            image_width = scale_manager.image_width
        except AttributeError:
            image_width = 0

        if image_width > SMALL_IMAGE_THRESHOLD or self.scale_mm >= 6.0:
            spatial_analyzer.size_class = "large"
        else:
            spatial_analyzer.size_class = "small"

        spatial_results = spatial_analyzer.analyze(
            distance_map, thick_vessel_map, roi_mask
        )

        # Trunk分類
        _t_classify = time.time()
        trunk_classification = TrunkVesselClassifier.classify_trunk_pattern(
            spatial_results["trunk_eccentricity"],
            spatial_results["angular_distribution_cv"],
            spatial_results["radial_uniformity"],
            spatial_results["thick_vessel_center_ratio"],
            spatial_results["diameter_center_periphery_ratio"],
        )
        self.logger.debug(
            f"[Spatial] 8. classify_trunk_pattern: {time.time()-_t_classify:.3f}s"
        )

        return {
            **spatial_results,
            # ensure mm_per_pixel/pixel_size_um are included for downstream density calculations
            "mm_per_pixel": scale_manager.mm_per_pixel,
            "pixel_size_um": scale_manager.pixel_size_um,
            "trunk_pattern": trunk_classification["pattern"],
            "trunk_score": trunk_classification["score"],
        }

    def _perform_flow_deficit_analysis(
        self,
        image_path: str,
        roi_mask: np.ndarray,
        scale_manager: ScaleManager,
    ) -> Dict:
        """Flow Deficit解析を実行"""
        from utils.image_utils import ImageProcessor

        image_processor = ImageProcessor()

        fd_image = image_processor.load_image(image_path, as_gray=True)
        fd_image = image_processor.ensure_8bit(fd_image)

        # リサイズ（必要に応じて）
        h, w = roi_mask.shape
        if fd_image.shape != (h, w):
            fd_image = cv2.resize(fd_image, (w, h), interpolation=cv2.INTER_LINEAR)

        fd_analyzer = FlowDeficitAnalyzer(
            mm_per_pixel=scale_manager.mm_per_pixel,
            pixel_size_um=scale_manager.pixel_size_um,
            num_rings=3,
            enlarge_step_mm=0.2,
        )
        phansalkar_radius = int(24 / scale_manager.pixel_size_um)

        fd_results = fd_analyzer.analyze(
            fd_image, roi_mask, phansalkar_radius=phansalkar_radius
        )

        return fd_results

    def _get_default_fd_results(self) -> Dict:
        """Flow Deficit解析のデフォルト結果"""
        return {
            "FD_percent_R1": 0,
            "FD_percent_R2": 0,
            "FD_percent_R3": 0,
            "FD_average_area_R1": 0,
            "FD_average_area_R2": 0,
            "FD_average_area_R3": 0,
            "FD_number_R1": 0,
            "FD_number_R2": 0,
            "FD_number_R3": 0,
            "FD_density_R1": 0,
            "FD_density_R2": 0,
            "FD_density_R3": 0,
        }

    def _perform_pattern_classification(
        self,
        skeleton_results: Dict,
        spatial_results: Dict,
        mnv_area_mm2: float,
    ) -> Dict:
        """パターン分類を実行"""
        center_mask = spatial_results["center_mask"]
        periphery_mask = spatial_results["periphery_mask"]
        mm_per_pixel = spatial_results.get("mm_per_pixel", 0.01)

        skeleton = skeleton_results.get(
            "refined_skeleton", skeleton_results.get("skeleton")
        )
        branch_data = None
        ref_struct = skeleton_results.get("refined_skeleton_structure")
        _t_branch = time.perf_counter()
        if ref_struct is not None:
            branch_data = _skeleton_structure_to_branch_data(
                ref_struct, mm_per_pixel
            )
        self.logger.debug(
            f"[Step6] 1a. branch_data: {time.perf_counter()-_t_branch:.3f}s"
        )

        _t_regional = time.perf_counter()
        if skeleton is not None and np.any(skeleton > 0):
            regional = RegionalAnalyzer(
                center_radius_mm=0.5,
                pixel_size_mm=mm_per_pixel,
                enable_advanced_metrics=False,
            )
            regional_results = regional.analyze_regions_from_skeleton(
                skeleton=skeleton,
                center_mask=center_mask,
                periphery_mask=periphery_mask,
                skeleton_diameter_um=skeleton_results.get("mean_diameter_um"),
                branch_data=branch_data,
            )
            loops_center = regional_results["loop_center"]
            loops_periphery = regional_results["loop_periphery"]
            branch_density_center = (
                regional_results["center_branch_count"]
                / (2 * np.sum(center_mask > 0) * (mm_per_pixel**2))
                if np.sum(center_mask > 0) > 0
                else 0
            )
            branch_density_periphery = (
                regional_results["periphery_branch_count"]
                / (2 * np.sum(periphery_mask > 0) * (mm_per_pixel**2))
                if np.sum(periphery_mask > 0) > 0
                else 0
            )
            center_area = np.sum(center_mask > 0) * (mm_per_pixel**2)
            periphery_area = np.sum(periphery_mask > 0) * (mm_per_pixel**2)
            loop_density_center = loops_center / center_area if center_area > 0 else 0
            loop_density_periphery = (
                loops_periphery / periphery_area if periphery_area > 0 else 0
            )
        else:
            regional_results = {}
            center_area = np.sum(center_mask > 0) * (mm_per_pixel**2)
            periphery_area = np.sum(periphery_mask > 0) * (mm_per_pixel**2)
            loops_center = skeleton_results["num_loops"] // 2
            loops_periphery = skeleton_results["num_loops"] - loops_center
            loop_density_center = loops_center / center_area if center_area > 0 else 0
            loop_density_periphery = (
                loops_periphery / periphery_area if periphery_area > 0 else 0
            )
            branch_density_center = (
                skeleton_results["num_branches"] / (2 * center_area)
                if center_area > 0
                else 0
            )
            branch_density_periphery = (
                skeleton_results["num_branches"] / (2 * periphery_area)
                if periphery_area > 0
                else 0
            )
        self.logger.debug(
            f"[Step6] 1b. analyze_regions: {time.perf_counter()-_t_regional:.3f}s"
        )

        _t_complexity = time.perf_counter()
        size_class = spatial_results.get("size_class", "small")
        euler_center = (
            regional_results.get(
                "euler_center", skeleton_results["euler_number"] // 2
            )
            if regional_results
            else skeleton_results["euler_number"] // 2
        )
        euler_periphery = (
            regional_results.get(
                "euler_periphery",
                skeleton_results["euler_number"]
                - skeleton_results["euler_number"] // 2,
            )
            if regional_results
            else skeleton_results["euler_number"]
            - skeleton_results["euler_number"] // 2
        )
        vessel_length_center = float(
            regional_results.get("vessel_length_center", 0.0)
        )
        vessel_length_periphery = float(
            regional_results.get("vessel_length_periphery", 0.0)
        )
        total_length_mm = vessel_length_center + vessel_length_periphery
        center_branch_count = int(
            regional_results.get("center_branch_count", 0)
        )
        periphery_branch_count = int(
            regional_results.get("periphery_branch_count", 0)
        )
        junction_density = (
            (center_branch_count + periphery_branch_count) / total_length_mm
            if total_length_mm > 0.0
            else 0.0
        )
        tortuosity_center = float(
            regional_results.get("tortuosity_center", 1.0)
        )
        tortuosity_periphery = float(
            regional_results.get("tortuosity_periphery", 1.0)
        )
        fd_global = float(
            skeleton_results.get("fractal_dimension", 0.0)
        )
        trunk_score = calculate_trunk_distribution_score(
            spatial_results["trunk_eccentricity"],
            spatial_results["angular_distribution_cv"],
            spatial_results["thick_vessel_center_ratio"],
            spatial_results["diameter_center_periphery_ratio"],
        )
        complexity_score = calculate_complexity_pca(
            euler_center=float(euler_center),
            euler_periphery=float(euler_periphery),
            loop_total=float(loops_center + loops_periphery),
            junction_density=junction_density,
            tortuosity_center=tortuosity_center,
            tortuosity_periphery=tortuosity_periphery,
            fd_global=fd_global,
            trunk_score=trunk_score,
            size_class=size_class,
        )
        complexity_details = {"method": "pca"}
        self.logger.debug(
            f"[Step6] 1c. complexity_score: {time.perf_counter()-_t_complexity:.3f}s"
        )

        _t_classify = time.perf_counter()
        classification = classify_morphology_final(
            complexity_score=complexity_score,
            stability_score=spatial_results["stability_score"],
            trunk_pattern=spatial_results["trunk_pattern"],
            size_class=size_class,
            eccentricity=spatial_results.get("trunk_eccentricity", -1.0),
            radial_uniformity=spatial_results.get("radial_uniformity", -1.0),
            angular_cv=spatial_results.get("angular_distribution_cv", -1.0),
        )
        if classification is None:
            classification = MNVClassifier.classify(
                complexity_score=complexity_score,
                stability_score=spatial_results["stability_score"],
                trunk_pattern=spatial_results["trunk_pattern"],
            )
        self.logger.debug(
            f"[Step6] 1d. mnv_classify: {time.perf_counter()-_t_classify:.3f}s"
        )

        num_endpoints = skeleton_results.get("num_endpoints", 0)
        endpoint_density = (
            num_endpoints / total_length_mm if total_length_mm > 0.0 else 0.0
        )

        loop_total = loops_center + loops_periphery
        pathophysiology = classify_pathophysiology_final(
            maturity_index=classification["maturity_index"],
            stability_score=spatial_results["stability_score"],
            segment_count=float(skeleton_results.get("segment_count", 0)),
            junction_density=junction_density,
            endpoint_density=endpoint_density,
            loop_total=float(loop_total),
            mean_diameter_um=float(skeleton_results.get("mean_diameter_um", 0)),
            cv_diameter=float(skeleton_results.get("cv_diameter", 0)),
            size_class=size_class,
            treatment_history=0,
        )

        validation = validate_combination_final(
            classification["subtype"], pathophysiology
        )
        validation_status = validation.get("status", "valid")
        overall_confidence = compute_overall_confidence(
            classification["confidence"], validation_status
        )

        out = {
            "complexity_score": complexity_score,
            "complexity_details": complexity_details,
            "mnv_subtype": classification["subtype"],
            "subtype_confidence": classification["confidence"],
            "maturity_index": classification["maturity_index"],
            "junction_density": junction_density,
            "endpoint_density": endpoint_density,
            "pathophysiology": pathophysiology,
            "combination_validation": validation_status,
            "overall_confidence": overall_confidence,
        }
        if regional_results:
            out.update(regional_results)
        return out

    def _calculate_image_statistics(
        self, image: np.ndarray, roi_mask: np.ndarray
    ) -> Dict[str, float]:
        """
        元画像の統計を計算
        ImageJの getStatistics(MNVarea, MNVmean, MNVmin, MNVmax, MNVstd) 相当

        Parameters:
        -----------
        image : np.ndarray
            元画像
        roi_mask : np.ndarray
            ROIマスク

        Returns:
        --------
        stats : dict
            統計量と派生指標
        """
        # ROI内の画素値を取得
        roi_pixels = image[roi_mask > 0]

        if len(roi_pixels) == 0:
            return {
                "image_mean": 0,
                "image_std": 0,
                "image_max": 0,
                "image_min": 0,
                "mean_intensity": 0,
                "max_mean_ratio": 0,
                "standard_deviation": 0,
            }

        # 統計計算
        mean_val = float(np.mean(roi_pixels))
        std_val = float(np.std(roi_pixels))
        max_val = float(np.max(roi_pixels))
        min_val = float(np.min(roi_pixels))

        # ImageJと同じ派生指標を計算
        # mean_intensity[index] = MNVmean / MNVmax;
        mean_intensity = mean_val / max_val if max_val > 0 else 0

        # MNV_max_mean_ratio[index] = (MNVmax - MNVmean) / MNVstd;
        max_mean_ratio = (max_val - mean_val) / std_val if std_val > 0 else 0

        # standard_deviation[index] = 100 * MNVstd / MNVmean;
        standard_deviation = 100 * std_val / mean_val if mean_val > 0 else 0

        return {
            "image_mean": mean_val,
            "image_std": std_val,
            "image_max": max_val,
            "image_min": min_val,
            "mean_intensity": mean_intensity,
            "max_mean_ratio": max_mean_ratio,
            "standard_deviation": standard_deviation,
        }


class MNVBatchAnalyzer:
    """
    MNV解析のバッチ処理クラス
    executeMNVAnalysis に対応
    """

    def __init__(
        self,
        input_dir: str,
        output_dir: str,
        scale_mm: float,
        mnv_suffix: str = "3.tif",
        cc_suffix: str = "4.tif",
        save_stages: bool = False,
        enable_roi_refinement: bool = False,
        analyst_name: str = "Python Streamlit Analysis",
    ):
        """
        Parameters:
        -----------
        input_dir : str
            入力ディレクトリ
        output_dir : str
            出力ディレクトリ
        scale_mm : float
            画像の実寸法（mm）
        mnv_suffix : str
            MNV画像のサフィックス
        cc_suffix : str
            Choriocapillaris画像のサフィックス
        save_stages : bool
            処理段階を保存するか
        enable_roi_refinement : bool
            ROI精密修正を有効にするか（False=高速、True=高精度）
        analyst_name : str
            解析者名（ログファイルに記録）
        """
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.scale_mm = scale_mm
        self.mnv_suffix = mnv_suffix
        self.cc_suffix = cc_suffix
        self.save_stages = save_stages
        self.enable_roi_refinement = enable_roi_refinement
        self.analyst_name = analyst_name

        # 出力ディレクトリ作成
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.pipeline = MNVPipeline(
            scale_mm=scale_mm,
            save_stages=save_stages,
            enable_roi_refinement=enable_roi_refinement,
        )

    def analyze(self) -> Dict[str, any]:
        """
        バッチMNV解析を実行

        Returns:
        --------
        results : dict
            解析結果
        """
        self.pipeline.logger.info("=== MNV Analysis Started ===")

        # ImageJ互換出力マネージャーを作成（画像保存用）
        main_folder_name = self.input_dir.name
        imagej_output = ImageJOutputManager(
            output_base_dir=str(self.output_dir.parent),
            main_folder_name=main_folder_name,
        )
        imagej_output.create_mnv_structure()

        # ファイルを検索
        mnv_files = self._find_mnv_files()

        if len(mnv_files) == 0:
            self.pipeline.logger.warning(
                f"No MNV files found with suffix {self.mnv_suffix}"
            )
            return {}

        self.pipeline.logger.info(f"Found {len(mnv_files)} MNV files")

        # 結果格納用の辞書を初期化
        results = self._initialize_results_dict()

        # 各ファイルを処理
        for idx, mnv_file in enumerate(mnv_files):
            self.pipeline.logger.info(
                f"\nProcessing file {idx + 1}/{len(mnv_files)}: {mnv_file.name}"
            )

            # patient_idを抽出（末尾のサフィックスパターンを除去）
            mnv_pattern = (
                self.mnv_suffix.rsplit(".", 1)[0]
                if "." in self.mnv_suffix
                else self.mnv_suffix
            )
            if mnv_file.stem.endswith(mnv_pattern):
                patient_id = mnv_file.stem[: -len(mnv_pattern)]
            else:
                patient_id = mnv_file.stem

            try:
                # 対応するCC画像を検索
                cc_file = self._find_cc_file(mnv_file, patient_id)

                # 元画像を読み込み（可視化用）
                original_image = cv2.imread(str(mnv_file), cv2.IMREAD_GRAYSCALE)

                # CC画像を読み込み（FD可視化用）
                fd_image = None
                if cc_file:
                    fd_image = cv2.imread(str(cc_file), cv2.IMREAD_GRAYSCALE)

                # 解析実行
                result = self.pipeline.analyze(
                    image_path=str(mnv_file),
                    output_dir=str(self.output_dir),
                    flow_deficit_image_path=str(cc_file) if cc_file else None,
                )

                # 結果を追加
                self._append_result(results, patient_id, mnv_file.name, result)

                # ImageJ互換の可視化画像を保存（専用モジュール使用）
                self._save_mnv_images(
                    result,
                    patient_id,
                    imagej_output,
                    original_image=original_image,
                    fd_image=fd_image,
                )

                self.pipeline.logger.info(
                    f"  ✓ Success: {result['mnv_subtype']}"
                )

            except Exception as e:
                self.pipeline.logger.error(f"  ✗ Error: {str(e)}")
                import traceback

                self.pipeline.logger.debug(traceback.format_exc())

                # エラー時はデフォルト値を追加
                self._append_default_result(results, patient_id, mnv_file.name)

        # CSV保存
        csv_path = self._save_results_csv(results)

        # ImageJ互換出力を生成
        self._create_imagej_compatible_output(results)

        self.pipeline.logger.info("\n=== MNV Analysis Completed ===")
        self.pipeline.logger.info(f"Results saved to: {csv_path}")

        return results

    def _find_mnv_files(self) -> List[Path]:
        """
        MNV画像ファイルを検索（複数の画像形式に対応）
        """
        supported_exts = [
            ".tif",
            ".tiff",
            ".jpg",
            ".jpeg",
            ".png",
            ".TIF",
            ".TIFF",
            ".JPG",
            ".JPEG",
            ".PNG",
        ]

        # サフィックスパターンを抽出（拡張子を除く）
        mnv_pattern = (
            self.mnv_suffix.rsplit(".", 1)[0]
            if "." in self.mnv_suffix
            else self.mnv_suffix
        )

        # 全ての画像ファイルを取得
        all_files = []
        for ext in supported_exts:
            all_files.extend(self.input_dir.glob(f"*{ext}"))
            all_files.extend(self.input_dir.rglob(f"**/*{ext}"))

        # 重複を除去
        all_files = list(set(all_files))

        # MNVファイルをフィルタ（末尾でマッチング）
        mnv_files = [f for f in all_files if f.stem.endswith(mnv_pattern)]

        return sorted(mnv_files)

    def _find_cc_file(self, mnv_file: Path, patient_id: str) -> Optional[Path]:
        """
        対応するCC画像を検索（複数の画像形式に対応）
        """
        supported_exts = [
            ".tif",
            ".tiff",
            ".jpg",
            ".jpeg",
            ".png",
            ".TIF",
            ".TIFF",
            ".JPG",
            ".JPEG",
            ".PNG",
        ]

        # サフィックスパターンを抽出（拡張子を除く）
        mnv_pattern = (
            self.mnv_suffix.rsplit(".", 1)[0]
            if "." in self.mnv_suffix
            else self.mnv_suffix
        )
        cc_pattern = (
            self.cc_suffix.rsplit(".", 1)[0]
            if "." in self.cc_suffix
            else self.cc_suffix
        )

        # ベース名が異なる場合の対応
        # MNVファイルから末尾のパターンを除去してベース名を取得
        if mnv_file.stem.endswith(mnv_pattern):
            base_name = mnv_file.stem[: -len(mnv_pattern)]
        else:
            base_name = patient_id

        # 様々な拡張子でCCファイルを探す
        for ext in supported_exts:
            cc_file = mnv_file.parent / f"{base_name}{cc_pattern}{ext}"
            if cc_file.exists():
                return cc_file

        return None

    def _initialize_results_dict(self) -> Dict:
        """結果格納用の辞書を初期化"""
        return {
            "patient_ids": [],
            "filenames": [],
            "mnv_subtypes": [],
            "mnv_areas": [],
            "vessel_areas": [],
            "vessel_densities": [],
            "vessel_lengths": [],
            "mean_diameters": [],
            "tortuosities": [],
            "fractal_dimensions": [],
            "num_junctions": [],
            "num_branches": [],
            "num_endpoints": [],
            "complexity_scores": [],
            "stability_scores": [],
            "maturity_indices": [],
            "trunk_patterns": [],
            "trunk_eccentricities": [],
            "FD_percent_R1": [],
            "FD_percent_R2": [],
            "FD_percent_R3": [],
            "mean_intensities": [],
            "max_mean_ratios": [],
            "standard_deviations": [],
            "vessel_density_indices": [],
            "immature_vessel_area_indices": [],
            "arteriolarization_segment_counts": [],
            "arteriolarization_total_lengths": [],
            "arteriolarization_max_segment_lengths": [],
            "arteriolarization_densities": [],
            "arteriolarization_connectivity_indices": [],
            "arteriolarization_high_skew_percentages": [],
            "quality_control": [],
        }

    def _append_result(
        self, results: Dict, patient_id: str, filename: str, result: Dict
    ):
        """結果を追加"""
        results["patient_ids"].append(patient_id)
        results["filenames"].append(filename)
        results["mnv_subtypes"].append(result.get("mnv_subtype", "Unknown"))
        results["mnv_areas"].append(result.get("mnv_area_mm2", 0))
        results["vessel_areas"].append(result.get("vessel_area_mm2", 0))

        # Vessel density関連
        vessel_density = result.get("vessel_density", 0)
        mean_intensity = result.get("mean_intensity", 0)

        # vessel_density_index = vessel_densities[index] * mean_intensity[index] * 100
        vessel_density_index = vessel_density * mean_intensity * 100

        # immature_vessel_area_index = (1 - vessel_density_index / 100) * vessel_Areas[index]
        vessel_area_mm2 = result.get("vessel_area_mm2", 0)
        immature_vessel_area_index = (1 - vessel_density_index / 100) * vessel_area_mm2

        results["vessel_densities"].append(vessel_density)
        results["vessel_lengths"].append(result.get("vessel_length_mm", 0))
        results["mean_diameters"].append(result.get("mean_diameter_um", 0))
        results["tortuosities"].append(result.get("tortuosity", 0))
        results["fractal_dimensions"].append(result.get("fractal_dimension", 0))
        results["num_junctions"].append(result.get("num_junctions", 0))
        results["num_branches"].append(result.get("num_branches", 0))
        results["num_endpoints"].append(result.get("num_endpoints", 0))
        results["complexity_scores"].append(result.get("complexity_score", 0))
        results["stability_scores"].append(result.get("stability_score", 0))
        results["maturity_indices"].append(result.get("maturity_index", 0))
        results["trunk_patterns"].append(result.get("trunk_pattern", "Unknown"))
        results["trunk_eccentricities"].append(result.get("trunk_eccentricity", -1))
        results["FD_percent_R1"].append(result.get("FD_percent_R1", 0))
        results["FD_percent_R2"].append(result.get("FD_percent_R2", 0))
        results["FD_percent_R3"].append(result.get("FD_percent_R3", 0))

        # 画像統計関連（ImageJ互換）
        results["mean_intensities"].append(mean_intensity)
        results["max_mean_ratios"].append(result.get("max_mean_ratio", 0))
        results["standard_deviations"].append(result.get("standard_deviation", 0))
        results["vessel_density_indices"].append(vessel_density_index)
        results["immature_vessel_area_indices"].append(immature_vessel_area_index)

        # 細動脈化解析（Arteriolarization）
        results["arteriolarization_segment_counts"].append(
            result.get("segment_count", 0)
        )
        results["arteriolarization_total_lengths"].append(
            result.get("total_length_mm", 0)
        )
        results["arteriolarization_max_segment_lengths"].append(
            result.get("max_segment_length_mm", 0)
        )
        results["arteriolarization_densities"].append(result.get("density", 0))
        results["arteriolarization_connectivity_indices"].append(
            result.get("connectivity_index", 0)
        )
        results["arteriolarization_high_skew_percentages"].append(
            result.get("high_skew_percentage", 0)
        )

        results["quality_control"].append("Pass")

    def _save_mnv_images(
        self,
        result: Dict,
        patient_id: str,
        imagej_output: ImageJOutputManager,
        original_image: np.ndarray = None,
        fd_image: np.ndarray = None,
    ):
        """
        MNV解析結果の画像を保存（専用可視化モジュール使用）

        Parameters:
        -----------
        result : dict
            解析結果
        patient_id : str
            患者ID
        imagej_output : ImageJOutputManager
            ImageJ互換出力マネージャー
        original_image : np.ndarray, optional
            元画像（MNV RGB可視化用）
        fd_image : np.ndarray, optional
            FD画像（Flow Deficit可視化用）
        """
        try:
            # === MNV RGB可視化画像の生成 ===
            if "binary" in result and "roi_mask" in result:
                binary = result["binary"]
                roi_mask = result["roi_mask"]

                # 元画像は必ず与えられる前提（ImageJ互換動作）。無い場合はエラーにする
                if original_image is None:
                    self.logger.error("Original image is missing for visualization")
                    raise ValueError(
                        "Original image missing for visualization; expected grayscale image"
                    )

                # VisualizationRGBモジュールを使用（遅延import）
                from ariake_octa.mnv.visualization_rgb import VisualizationRGB

                visualizer = VisualizationRGB(
                    pixel_size_mm=self.pipeline.pixel_size_mm,
                    scale_bar_length_mm=0.5,
                    font_scale=0.6,
                )

                # メトリクスを準備
                vd_ratio = result.get("vessel_density", 0)
                metrics = {
                    "lesion_area_mm2": result.get("mnv_area_mm2", 0),
                    "vessel_density_percent": vd_ratio * 100 if vd_ratio else 0,
                    "skeleton_num_junctions": result.get("num_junctions", 0),
                    "overall_fd_ratio_percent": result.get("FD_percent_R1", 0),
                }

                # RGB可視化画像を作成 (ImageJ互換: dilated_highSkew を赤チャンネルに)
                rgb_vis = visualizer.create_rgb_visualization(
                    original_image=original_image,
                    binary_vessel=binary,
                    lesion_mask=roi_mask,
                    metrics=metrics,
                    highskew_mask=result.get(
                        "dilated_highSkew_for_visualization",
                        np.zeros_like(binary),
                    ),
                )

                # ImageJ互換形式で保存
                imagej_output.save_mnv_visualization(
                    rgb_vis,
                    patient_id,
                    result.get("mnv_area_mm2", None),
                    image_type="MNV",
                )
                self.pipeline.logger.info(
                    f"  ✓ MNV visualization saved: MNV_{patient_id}.jpg"
                )

            # === Flow Deficit可視化画像の生成 ===
            if fd_image is not None and "roi_mask" in result:
                roi_mask = result["roi_mask"]

                if "binary" in result:
                    binary = result["binary"]
                    # FD画像から二値化
                    _, fd_binary = cv2.threshold(
                        (
                            fd_image
                            if len(fd_image.shape) == 2
                            else cv2.cvtColor(fd_image, cv2.COLOR_BGR2GRAY)
                        ),
                        0,
                        255,
                        cv2.THRESH_BINARY + cv2.THRESH_OTSU,
                    )
                    fd_mask = (fd_binary > 0) & (binary == 0) & (roi_mask > 0)

                    # 病変中心を取得
                    lesion_center = self._get_lesion_center(roi_mask)

                    # FlowDeficitVisualizerモジュールを使用
                    fd_visualizer = FlowDeficitVisualizer(
                        pixel_size_mm=self.pipeline.pixel_size_mm,
                        ring_widths_mm=[0.2, 0.4, 0.6],
                        blur_sigma=4.0,
                    )

                    # FD可視化画像を作成
                    # 背景画像はFD解析用画像（fd_image）を使用
                    # roi_maskを渡してROI形状に追従した膨張リングを生成
                    fd_vis = fd_visualizer.create_fd_visualization(
                        fd_mask=fd_mask,
                        lesion_center=lesion_center,
                        background_image=fd_image,  # FD解析用画像をそのまま使用
                        roi_mask=roi_mask,  # ROI形状に追従した膨張リングのため必須
                    )

                    # ImageJ互換形式で保存
                    imagej_output.save_mnv_visualization(
                        fd_vis, patient_id, None, image_type="FD"
                    )
                    self.pipeline.logger.info(
                        f"  ✓ FD visualization saved: FD_{patient_id}.jpg"
                    )

        except Exception as e:
            self.pipeline.logger.warning(
                f"Could not save visualization images: {str(e)}"
            )
            import traceback

            self.pipeline.logger.debug(traceback.format_exc())

    def _get_lesion_center(self, roi_mask: np.ndarray) -> Tuple[float, float]:
        """病変マスクの中心座標を取得"""
        contours, _ = cv2.findContours(
            roi_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        if len(contours) > 0:
            M = cv2.moments(contours[0])
            if M["m00"] != 0:
                center_x = M["m10"] / M["m00"]
                center_y = M["m01"] / M["m00"]
                return (center_y, center_x)
        h, w = roi_mask.shape
        return (h // 2, w // 2)

    def _append_default_result(self, results: Dict, patient_id: str, filename: str):
        """デフォルト結果を追加（エラー時）"""
        results["patient_ids"].append(patient_id)
        results["filenames"].append(filename)
        results["mnv_subtypes"].append("Error")
        results["mnv_areas"].append(0)
        results["vessel_areas"].append(0)
        results["vessel_densities"].append(0)
        results["vessel_lengths"].append(0)
        results["mean_diameters"].append(0)
        results["tortuosities"].append(0)
        results["fractal_dimensions"].append(0)
        results["num_junctions"].append(0)
        results["num_branches"].append(0)
        results["num_endpoints"].append(0)
        results["complexity_scores"].append(0)
        results["stability_scores"].append(0)
        results["maturity_indices"].append(0)
        results["trunk_patterns"].append("Unknown")
        results["trunk_eccentricities"].append(-1)
        results["FD_percent_R1"].append(0)
        results["FD_percent_R2"].append(0)
        results["FD_percent_R3"].append(0)
        results["quality_control"].append("Fail")

    def _save_results_csv(self, results: Dict) -> Path:
        """結果をCSVで保存"""
        from ..utils.file_handler import FileHandler

        csv_path = self.output_dir / "MNV_Results.csv"

        file_handler = FileHandler()
        file_handler.save_results_csv(results, str(self.output_dir), "MNV_Results.csv")

        return csv_path

    def _create_imagej_compatible_output(self, results: Dict):
        """
        ImageJ互換の出力を作成

        Parameters:
        -----------
        results : dict
            MNV解析結果
        """
        # メインフォルダー名を取得
        main_folder_name = self.input_dir.name

        # ImageJ互換出力マネージャーを作成
        imagej_output = ImageJOutputManager(
            output_base_dir=str(self.output_dir.parent),
            main_folder_name=main_folder_name,
        )

        # MNV用ディレクトリ構造を作成
        imagej_output.create_mnv_structure()

        # MNV測定テーブルを作成
        mnv_table_results = self._format_results_for_imagej(results)
        csv_path = imagej_output.create_mnv_measurements_table(mnv_table_results)
        self.pipeline.logger.info(
            f"  ImageJ-compatible MNV table saved: {csv_path}"
        )

        # パラメータファイルを作成
        param_path = imagej_output.create_mnv_parameter_file(
            scale_mm=self.scale_mm,
            tubeness_sigma=1.0,  # デフォルト値
            log_sigma=1.0,  # デフォルト値
            num_files=len(results["patient_ids"]),
        )
        self.pipeline.logger.info(f"  Parameter file saved: {param_path}")

        # ログファイルを保存
        log_content = self._generate_mnv_log(results)
        log_path = imagej_output.save_log_file(
            log_content, analyst_name=self.analyst_name, analysis_type="MNV"
        )
        self.pipeline.logger.info(f"  Log file saved: {log_path}")

    def _format_results_for_imagej(self, results: Dict) -> Dict:
        """ImageJ互換フォーマットに変換"""
        # ImageJマクロのカラム名と完全一致させる
        formatted = {
            "patient_ids": results.get("patient_ids", []),
            "filenames": results.get("filenames", []),
            "mnv_subtype": results.get("mnv_subtypes", []),
            "mnv_area_mm2": results.get("mnv_areas", []),
            "vessel_area_mm2": results.get("vessel_areas", []),
            "vessel_density": results.get("vessel_densities", []),
            "vessel_density_index": results.get("vessel_density_indices", []),
            "immature_vessel_area_index": results.get(
                "immature_vessel_area_indices", []
            ),
            "vessel_length_mm": results.get("vessel_lengths", []),
            "high_skew_percentage": [0] * len(results.get("patient_ids", [])),  # 未実装
            "maturity_index": results.get("maturity_indices", []),
            "stability_score": results.get("stability_scores", []),
            "complexity_score": results.get("complexity_scores", []),
            "junction_density": [0] * len(results.get("patient_ids", [])),  # 計算が必要
            "endpoint_density": [0] * len(results.get("patient_ids", [])),  # 計算が必要
            "multiple_density": [0] * len(results.get("patient_ids", [])),  # 計算が必要
            "branch_density": [0] * len(results.get("patient_ids", [])),  # 計算が必要
            "FD_percent_R1": results.get("FD_percent_R1", []),
            "FD_average_area_R1": [0] * len(results.get("patient_ids", [])),
            "FD_number_R1": [0] * len(results.get("patient_ids", [])),
            "FD_density_R1": [0] * len(results.get("patient_ids", [])),
            "FD_percent_R2": results.get("FD_percent_R2", []),
            "FD_average_area_R2": [0] * len(results.get("patient_ids", [])),
            "FD_number_R2": [0] * len(results.get("patient_ids", [])),
            "FD_density_R2": [0] * len(results.get("patient_ids", [])),
            "FD_percent_R3": results.get("FD_percent_R3", []),
            "FD_average_area_R3": [0] * len(results.get("patient_ids", [])),
            "FD_number_R3": [0] * len(results.get("patient_ids", [])),
            "FD_density_R3": [0] * len(results.get("patient_ids", [])),
            "center_branch": [0] * len(results.get("patient_ids", [])),
            "vessel_length_center": [0] * len(results.get("patient_ids", [])),
            "tortuosity_center": [0] * len(results.get("patient_ids", [])),
            "FD_center": [0] * len(results.get("patient_ids", [])),
            "euler_center": [0] * len(results.get("patient_ids", [])),
            "loop_center": [0] * len(results.get("patient_ids", [])),
            "periphery_branch": [0] * len(results.get("patient_ids", [])),
            "vessel_length_periphery": [0] * len(results.get("patient_ids", [])),
            "tortuosity_periphery": [0] * len(results.get("patient_ids", [])),
            "FD_periphery": [0] * len(results.get("patient_ids", [])),
            "euler_periphery": [0] * len(results.get("patient_ids", [])),
            "loop_periphery": [0] * len(results.get("patient_ids", [])),
            "mean_intensity": results.get("mean_intensities", []),
            "fractal_dimension": results.get("fractal_dimensions", []),
            "tortuosity": results.get("tortuosities", []),
            "standard_deviation": results.get("standard_deviations", []),
            "cv_diameter": [0] * len(results.get("patient_ids", [])),
            "mean_diameter_um": results.get("mean_diameters", []),
            "num_endpoints": results.get("num_endpoints", []),
            "num_branches": results.get("num_branches", []),
            "num_junctions": results.get("num_junctions", []),
            "triple_points": [0] * len(results.get("patient_ids", [])),
            "quadruple_points": [0] * len(results.get("patient_ids", [])),
            "raw_vessel_length": [0] * len(results.get("patient_ids", [])),
            "raw_vessel_diameter": [0] * len(results.get("patient_ids", [])),
            "quality_control": results.get("quality_control", []),
        }

        return formatted

    def _generate_mnv_log(self, results: Dict) -> str:
        """MNV解析ログを生成"""
        log_lines = []
        log_lines.append("=== MNV Analysis Started ===")
        log_lines.append(f"Input Directory: {self.input_dir}")
        log_lines.append(f"Output Directory: {self.output_dir}")
        log_lines.append(f"Scale: {self.scale_mm} mm")
        log_lines.append(f"MNV Suffix: {self.mnv_suffix}")
        log_lines.append(f"CC Suffix: {self.cc_suffix}")
        log_lines.append("")
        log_lines.append(f"Found {len(results['patient_ids'])} MNV files")
        log_lines.append("")

        for i, patient_id in enumerate(results["patient_ids"]):
            log_lines.append(
                f"Processing {i+1}/{len(results['patient_ids'])}: {patient_id}"
            )
            log_lines.append(f"  File: {results['filenames'][i]}")
            log_lines.append(f"  MNV Area: {results['mnv_areas'][i]:.3f} mm²")
            log_lines.append(f"  Vessel Density: {results['vessel_densities'][i]:.2f}%")
            log_lines.append(f"  Subtype: {results['mnv_subtypes'][i]}")
            log_lines.append(f"  Quality: {results['quality_control'][i]}")
            log_lines.append("")

        log_lines.append("=== MNV Analysis Completed ===")

        return "\n".join(log_lines)
