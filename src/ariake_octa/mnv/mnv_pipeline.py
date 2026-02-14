"""
MNV (Macular Neovascularization) Pipeline

Complete pipeline for MNV analysis from single OCT-A image
Phase 2: 80メトリクス完全実装
"""

from typing import Dict

import numpy as np

from ..vd.phansalkar_filter import PhansalkarBinarizer
from .color_coded_binary import ColorCodedBinary
from .fd_ring_analyzer import FlowDeficitRingAnalyzer
from .filter_fusion import FilterFusion
from .flow_deficit_visualizer import FlowDeficitVisualizer
from .image_saver import ImageSaver
from .log_filter import LoGFilter


# skeleton_analysis モジュールから DiameterAnalyzer, HighSkewnessAnalyzer をインポート
import sys
from pathlib import Path
_core_path = Path(__file__).resolve().parent.parent.parent.parent / "src" / "core"
if str(_core_path.parent) not in sys.path:
    sys.path.insert(0, str(_core_path.parent))
from core.skeleton_analysis import DiameterAnalyzer, HighSkewnessAnalyzer
# Phase 2 新モジュール
from .mnv_lesion_detector import MNVLesionDetector
from .mnv_preprocessor import MNVPreprocessor
from .regional_analyzer import RegionalAnalyzer
from .skeleton_analyzer import SkeletonAnalyzer
from .tubeness_filter import TubenessFilter

# Phase 3 可視化モジュール
from .visualization_rgb import VisualizationRGB


class MNVPipeline:
    """
    MNV解析パイプライン（精密・診断向け）- Phase 2完全版

    特徴:
    - LoG + Tubeness 融合フィルタ
    - 多段階前処理（CLAHE + 背景除去）
    - MNV病変検出（複雑な形状対応）
    - 詳細なスケルトン解析（分岐、端点、ループ、トルトゥオシティ、フラクタル次元）
    - Center/Periphery領域別解析
    - Flow Deficit 3環解析
    - 処理時間: ~25秒/画像
    - 出力: 60メトリクス（Phase 2完全実装）

    臨床用途:
    - 加齢黄斑変性（AMD）の精密診断
    - MNVサブタイプ分類
    - 治療効果判定
    """

    def __init__(self, pixel_size_mm: float = 0.003):
        """
        Args:
            pixel_size_mm: ピクセルサイズ（mm/pixel）
                標準値: 0.003 mm/pixel（6mm視野の場合）
        """
        self.pixel_size_mm = pixel_size_mm

        # Phase 1モジュール
        self.preprocessor = MNVPreprocessor(
            clahe_clip_limit=3.0, clahe_blocksize=127, background_sigma=5.0
        )
        self.log_filter = LoGFilter(sigma=1.0)  # FeatureJ Laplacian
        self.tubeness = TubenessFilter(scales=[1.0, 2.0, 3.0])
        self.fusion = FilterFusion(method="weighted_sum", weights=[0.5, 0.5])
        self.binarizer = PhansalkarBinarizer(window_radius=15)

        # Phase 2モジュール
        self.lesion_detector = MNVLesionDetector(
            min_area_mm2=0.05,
            merge_distance_mm=0.3,
            morphology_radius_mm=0.05,
            pixel_size_mm=pixel_size_mm,
        )
        self.skeleton_analyzer = SkeletonAnalyzer(pixel_size_mm=pixel_size_mm)
        self.regional_analyzer = RegionalAnalyzer(
            center_radius_mm=0.5, pixel_size_mm=pixel_size_mm
        )
        self.fd_analyzer = FlowDeficitRingAnalyzer(
            ring_widths_mm=[0.2, 0.4, 0.6],
            min_fd_area_mm2=0.001,
            pixel_size_mm=pixel_size_mm,
        )

        # Phase 3 可視化モジュール
        self.visualizer_rgb = VisualizationRGB(pixel_size_mm=pixel_size_mm)
        self.visualizer_color = ColorCodedBinary()
        self.visualizer_fd = FlowDeficitVisualizer(pixel_size_mm=pixel_size_mm)
        self.image_saver = ImageSaver(jpeg_quality=95)

        # 処理パラメータ（MNV最適化、ImageJマクロ準拠）
        self.params = {
            "log_sigma": 1.0,  # FeatureJ Laplacian
            "tubeness_scales": [1.0, 2.0, 3.0],  # マルチスケール
            "fusion_weights": [0.5, 0.5],  # 加重和（LoG:Tubeness = 1:1）
            "phansalkar_window_radius": 15,
            "clahe_clip_limit": 3.0,  # ImageJ: clip_limit=3
            "clahe_blocksize": 127,  # ImageJ: blocksize=127
            "background_sigma": 5.0,  # ガウシアンブラー
        }

    def process(self, image: np.ndarray) -> Dict:
        """
        MNV解析を実行（Phase 2完全版: 60メトリクス）

        Args:
            image: MNV画像 (H×W numpy array, uint8)

        Returns:
            dict: 60メトリクス + 中間結果

        処理ステップ:
            Step 1-5: フィルタ処理・二値化（Phase 1）
            Step 6: MNV病変検出
            Step 7: スケルトン解析（全体）
            Step 8: 領域別解析（Center/Periphery）
            Step 9: Flow Deficit 3環解析
        """
        # ===== Phase 1: フィルタ処理・二値化 =====
        # Step 1: 前処理（CLAHE + 背景除去）
        preprocessed = self.preprocessor.preprocess(image)

        # Step 2: LoGフィルタ適用
        log_filtered = self.log_filter.apply(preprocessed, sigma=1.0)

        # Step 3: Tubenessフィルタ適用
        tube_filtered = self.tubeness.apply(preprocessed, scales=[1.0, 2.0, 3.0])

        # Step 4: 融合
        fused = self.fusion.fuse(log_filtered, tube_filtered, weights=[0.5, 0.5])

        # Step 5: 二値化
        binary = self.binarizer.binarize(fused)

        # ===== Phase 2: 詳細解析 =====
        # Step 6: MNV病変検出
        lesion_info = self.lesion_detector.detect(binary, fused_response=fused)
        lesion_mask = lesion_info["lesion_mask"]
        lesion_center = (lesion_info["center_y"], lesion_info["center_x"])

        # Step 7: スケルトン解析（全体）
        skeleton_results = self.skeleton_analyzer.analyze(binary, roi_mask=lesion_mask)

        # Step 8: 領域別解析（Center/Periphery）
        regional_results = self.regional_analyzer.analyze(
            binary, lesion_center, self.skeleton_analyzer
        )

        # Step 9: Flow Deficit 3環解析
        fd_results = self.fd_analyzer.analyze(binary, lesion_center, lesion_mask)

        # ===== メトリクス統合 =====
        metrics = self._compile_metrics(
            image, binary, lesion_info, skeleton_results, regional_results, fd_results
        )

        # 中間結果を保存
        metrics["intermediate_results"] = {
            "preprocessed": preprocessed,
            "log_filtered": log_filtered,
            "tubeness_filtered": tube_filtered,
            "fused": fused,
            "binary": binary,
            "lesion_mask": lesion_mask,
            "skeleton": skeleton_results["skeleton"],
            "center_mask": regional_results["center_mask"],
            "periphery_mask": regional_results["periphery_mask"],
            "fd_mask": fd_results["fd_mask"],
        }

        # メタデータ
        metrics["pixel_size_mm"] = self.pixel_size_mm
        metrics["analysis_type"] = "MNV"
        metrics["image_shape"] = image.shape
        metrics["pipeline_version"] = "2.0.0-phase3"
        metrics["original_image"] = image

        return metrics

    def _compile_metrics(
        self,
        original: np.ndarray,
        binary: np.ndarray,
        lesion_info: Dict,
        skeleton_results: Dict,
        regional_results: Dict,
        fd_results: Dict,
    ) -> Dict:
        """
        全てのメトリクスを1つの辞書に統合

        Returns:
            dict: 60メトリクス
        """
        h, w = binary.shape
        total_area_mm2 = (h * w) * (self.pixel_size_mm**2)

        # 血管ピクセル数
        vessel_pixels = binary.sum()
        vessel_area_mm2 = vessel_pixels * (self.pixel_size_mm**2)
        vessel_density = (vessel_pixels / (h * w)) * 100  # %

        # 画像品質
        signal = original.mean()
        noise = original.std()
        snr = signal / (noise + 1e-10)
        quality_score = min(snr * 10, 100)

        # メトリクス統合（60メトリクス）
        metrics = {
            # === 基本メトリクス (6個) ===
            "vessel_area_mm2": float(vessel_area_mm2),
            "vessel_density_percent": float(vessel_density),
            "total_area_mm2": float(total_area_mm2),
            "quality_score": float(quality_score),
            "vessel_pixels": int(vessel_pixels),
            "total_pixels": int(h * w),
            # === 病変情報 (6個) ===
            "lesion_center_x_mm": lesion_info["center_x_mm"],
            "lesion_center_y_mm": lesion_info["center_y_mm"],
            "lesion_area_mm2": lesion_info["area_mm2"],
            "lesion_num_components": lesion_info["num_components"],
            "lesion_bbox_width": lesion_info["bounding_box"][3]
            - lesion_info["bounding_box"][1],
            "lesion_bbox_height": lesion_info["bounding_box"][2]
            - lesion_info["bounding_box"][0],
            # === スケルトン解析（全体）(10個) ===
            "skeleton_num_branches": skeleton_results["num_branches"],
            "skeleton_num_junctions": skeleton_results["num_junctions"],
            "skeleton_num_endpoints": skeleton_results["num_endpoints"],
            "skeleton_num_loops": skeleton_results["num_loops"],
            "skeleton_total_length_mm": skeleton_results["total_length_mm"],
            "skeleton_avg_branch_length_mm": skeleton_results[
                "average_branch_length_mm"
            ],
            "skeleton_tortuosity_mean": skeleton_results["tortuosity_mean"],
            "skeleton_tortuosity_std": skeleton_results["tortuosity_std"],
            "skeleton_fractal_dimension": skeleton_results["fractal_dimension"],
            "skeleton_vessel_density": (
                skeleton_results["total_length_mm"] / lesion_info["area_mm2"]
                if lesion_info["area_mm2"] > 0
                else 0.0
            ),
            # === Center領域 (12個) ===
            "center_area_mm2": regional_results["center_area_mm2"],
            "center_vessel_length_mm": regional_results["center_vessel_length_mm"],
            "center_vessel_density": regional_results["center_vessel_density"],
            "center_num_branches": regional_results["center_num_branches"],
            "center_num_junctions": regional_results["center_num_junctions"],
            "center_num_endpoints": regional_results["center_num_endpoints"],
            "center_num_loops": regional_results["center_num_loops"],
            "center_avg_branch_length_mm": regional_results[
                "center_avg_branch_length_mm"
            ],
            "center_tortuosity_mean": regional_results["center_tortuosity_mean"],
            "center_tortuosity_std": regional_results["center_tortuosity_std"],
            "center_fractal_dimension": regional_results["center_fractal_dimension"],
            "center_complexity_score": regional_results["center_complexity_score"],
            # === Periphery領域 (12個) ===
            "periphery_area_mm2": regional_results["periphery_area_mm2"],
            "periphery_vessel_length_mm": regional_results[
                "periphery_vessel_length_mm"
            ],
            "periphery_vessel_density": regional_results["periphery_vessel_density"],
            "periphery_num_branches": regional_results["periphery_num_branches"],
            "periphery_num_junctions": regional_results["periphery_num_junctions"],
            "periphery_num_endpoints": regional_results["periphery_num_endpoints"],
            "periphery_num_loops": regional_results["periphery_num_loops"],
            "periphery_avg_branch_length_mm": regional_results[
                "periphery_avg_branch_length_mm"
            ],
            "periphery_tortuosity_mean": regional_results["periphery_tortuosity_mean"],
            "periphery_tortuosity_std": regional_results["periphery_tortuosity_std"],
            "periphery_fractal_dimension": regional_results[
                "periphery_fractal_dimension"
            ],
            "periphery_complexity_score": regional_results[
                "periphery_complexity_score"
            ],
            # === Flow Deficit Ring 1 (4個) ===
            "ring1_fd_area_mm2": fd_results["ring1_fd_area_mm2"],
            "ring1_fd_ratio_percent": fd_results["ring1_fd_ratio_percent"],
            "ring1_fd_count": fd_results["ring1_fd_count"],
            "ring1_avg_fd_area_mm2": fd_results["ring1_avg_fd_area_mm2"],
            # === Flow Deficit Ring 2 (4個) ===
            "ring2_fd_area_mm2": fd_results["ring2_fd_area_mm2"],
            "ring2_fd_ratio_percent": fd_results["ring2_fd_ratio_percent"],
            "ring2_fd_count": fd_results["ring2_fd_count"],
            "ring2_avg_fd_area_mm2": fd_results["ring2_avg_fd_area_mm2"],
            # === Flow Deficit Ring 3 (4個) ===
            "ring3_fd_area_mm2": fd_results["ring3_fd_area_mm2"],
            "ring3_fd_ratio_percent": fd_results["ring3_fd_ratio_percent"],
            "ring3_fd_count": fd_results["ring3_fd_count"],
            "ring3_avg_fd_area_mm2": fd_results["ring3_avg_fd_area_mm2"],
            # === Flow Deficit Overall (2個) ===
            "overall_fd_area_mm2": fd_results["overall_fd_area_mm2"],
            "overall_fd_ratio_percent": fd_results["overall_fd_ratio_percent"],
        }

        return metrics

    def get_visualization(self, metrics: Dict) -> Dict[str, np.ndarray]:
        """
        可視化用画像を生成（Phase 3完全版）

        Returns:
            visualizations: {
                'rgb': RGB合成画像,
                'color_coded': 擬似カラー画像,
                'flow_deficit': Flow Deficit可視化,
                'binary': 二値画像,
                'original': 元画像
            }
        """
        intermediate = metrics.get("intermediate_results", {})
        original_image = metrics.get("original_image")

        if not intermediate or original_image is None:
            return {}

        # 中間結果取得
        binary = intermediate.get("binary")
        lesion_mask = intermediate.get("lesion_mask")
        fd_mask = intermediate.get("fd_mask")

        # 病変中心
        lesion_center = (
            metrics.get("lesion_center_y_mm", 0) / self.pixel_size_mm,
            metrics.get("lesion_center_x_mm", 0) / self.pixel_size_mm,
        )

        visualizations = {}

        # 1. RGB合成可視化
        try:
            rgb_vis = self.visualizer_rgb.create_rgb_visualization(
                original_image, binary, lesion_mask, metrics=metrics
            )
            visualizations["rgb"] = rgb_vis
        except Exception as e:
            print(f"Warning: RGB visualization failed: {e}")

        # 2. 擬似カラー可視化
        try:
            color_coded = self.visualizer_color.create_color_coded(
                binary, enhance_contrast=True
            )
            visualizations["color_coded"] = color_coded
        except Exception as e:
            print(f"Warning: Color-coded visualization failed: {e}")

        # 3. Flow Deficit可視化
        try:
            fd_vis = self.visualizer_fd.create_fd_visualization(
                fd_mask, lesion_center, background_image=original_image
            )
            # 凡例追加
            fd_vis = self.visualizer_fd.create_with_legend(fd_vis)
            visualizations["flow_deficit"] = fd_vis
        except Exception as e:
            print(f"Warning: Flow Deficit visualization failed: {e}")

        # 4. 基本画像
        visualizations["binary"] = binary
        visualizations["original"] = original_image

        return visualizations

    def save_visualizations(
        self, metrics: Dict, output_dir: str, file_id: str
    ) -> Dict[str, str]:
        """
        可視化画像を保存

        Parameters
        ----------
        metrics : dict
            解析結果
        output_dir : str
            出力ディレクトリ
        file_id : str
            ファイルID

        Returns
        -------
        dict
            保存されたファイルパスの辞書
        """
        # 可視化画像生成
        visualizations = self.get_visualization(metrics)

        # 保存
        saved_paths = self.image_saver.save_mnv_visualizations(
            visualizations, output_dir, file_id
        )

        return saved_paths
