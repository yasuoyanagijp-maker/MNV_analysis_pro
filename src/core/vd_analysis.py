"""
VD (Vessel Density) 解析モジュール
Superficial層とDeep層の血管密度解析
"""

import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import cv2
import numpy as np

logger = logging.getLogger(__name__)


def _ensure_timing_log_visible() -> None:
    """Ensure [VD timing] logs are shown when root logging is not configured (e.g. run.sh)."""
    root = logging.getLogger()
    if not root.handlers:
        root.addHandler(logging.StreamHandler(sys.stdout))
    root.setLevel(logging.INFO)

# 相対インポートと絶対インポートの両方に対応
try:
    from ..ariake_octa.vd.faz_detector import EnhancedFAZSegmentation, FAZVisualization
    from ..ariake_octa.enhanced_faz_detection import ImprovedFAZDetector
    from ..ariake_octa.mnv.skeleton_analyzer import SkeletonAnalyzer
    from ..utils.file_handler import FileHandler
    from ..utils.image_utils import ImageProcessor, ScaleManager
    from ..utils.imagej_compatible_output import ImageJOutputManager
    from .roi_manager import FAZDetector
    from .vessel_detection import VDProcessor
except ImportError:
    # Streamlit等からの直接実行時
    from ariake_octa.vd.faz_detector import EnhancedFAZSegmentation, FAZVisualization
    from ariake_octa.enhanced_faz_detection import ImprovedFAZDetector
    from ariake_octa.mnv.skeleton_analyzer import SkeletonAnalyzer
    from utils.file_handler import FileHandler
    from utils.image_utils import ImageProcessor, ScaleManager
    from utils.imagej_compatible_output import ImageJOutputManager
    from core.roi_manager import FAZDetector
    from core.vessel_detection import VDProcessor


class VDAnalyzer:
    """
    VD解析の統合クラス
    executeVDAnalysis に対応
    """

    def __init__(
        self,
        input_dir: str,
        output_dir: str,
        scale_mm: float,
        side: str = "right",
        sup_suffix: str = "1.tif",
        deep_suffix: str = "2.tif",
        save_stages: bool = False,
        analyst_name: str = "Python Streamlit Analysis",
        use_enhanced_faz: bool = True,
        faz_method: str = "hybrid",
        faz_li_threshold_scale: float = 0.05,
        use_optimized_preprocessing: bool = False,
        use_faz_intensity_refinement: bool = False,
        faz_center_roi_ratio: float = 0.5,
        faz_intensity_percentile: float = 30.0,
        faz_distance_trim_ratio: float = 0.14,
        faz_distance_min_px: int = 1,
        single_image_mode: bool = False,
        single_image_explicit_path: Optional[Union[str, Path]] = None,
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
        side : str
            眼の側（"right" or "left"）
        sup_suffix : str
            Superficial画像のサフィックス
        deep_suffix : str
            Deep画像のサフィックス
        save_stages : bool
            処理段階を保存するか
        analyst_name : str
            解析者名（ログファイルに記録）
        use_enhanced_faz : bool
            Enhanced FAZ Segmentationを使用するか
        faz_method : str
            FAZ検出手法（'morphological', 'edge', 'region_growing', 'hybrid'）
        faz_li_threshold_scale : float
            FAZ用スケルトン生成時のLi閾値スケール（0.05推奨）
        use_optimized_preprocessing : bool
            TrueでHessian最適化前処理でスケルトン生成
        use_faz_intensity_refinement : bool
            Trueで中心の薄い血管を強度に基づき無血管にしFAZ候補を拡大
        faz_center_roi_ratio : float
            強度精査の中心ROIの幅・高さの割合 (0.5 = 50%)
        faz_intensity_percentile : float
            中心ROI内でこのパーセンタイル以下を「薄い」とみなす (0-100)
        faz_distance_trim_ratio : float
            FAZ境界の距離変換ベース正則化の強さ（大きいほど突起を強く刈る）
        faz_distance_min_px : int
            距離変換ベース正則化の最小トリム半径（px）
        single_image_mode : bool
            True: File Upload用。ペアなしで単一画像ごとにFAZを同定して処理
        single_image_explicit_path : str | Path | None
            single_image_mode 時に入力ディレクトリ内のこのファイルだけを処理する
        """
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.scale_mm = scale_mm
        self.side = side
        # 複数サフィックス対応（カンマ区切り例: "1.tif, 1.tiff"）
        if isinstance(sup_suffix, str):
            self.sup_suffixes = [s.strip() for s in sup_suffix.split(",") if s.strip()]
            self.sup_suffix = self.sup_suffixes[0] if self.sup_suffixes else sup_suffix
        else:
            self.sup_suffixes = list(sup_suffix)
            self.sup_suffix = self.sup_suffixes[0] if self.sup_suffixes else "1.tif"
        if not self.sup_suffixes:
            self.sup_suffixes = [self.sup_suffix]
        if isinstance(deep_suffix, str):
            self.deep_suffixes = [s.strip() for s in deep_suffix.split(",") if s.strip()]
            self.deep_suffix = self.deep_suffixes[0] if self.deep_suffixes else deep_suffix
        else:
            self.deep_suffixes = list(deep_suffix)
            self.deep_suffix = self.deep_suffixes[0] if self.deep_suffixes else "2.tif"
        if not self.deep_suffixes:
            self.deep_suffixes = [self.deep_suffix]
        self.save_stages = save_stages
        self.analyst_name = analyst_name
        self.use_enhanced_faz = use_enhanced_faz
        self.faz_method = faz_method
        self.faz_li_threshold_scale = faz_li_threshold_scale
        self.use_optimized_preprocessing = use_optimized_preprocessing
        self.use_faz_intensity_refinement = use_faz_intensity_refinement
        self.faz_center_roi_ratio = faz_center_roi_ratio
        self.faz_intensity_percentile = faz_intensity_percentile
        self.faz_distance_trim_ratio = faz_distance_trim_ratio
        self.faz_distance_min_px = faz_distance_min_px
        self.single_image_mode = single_image_mode
        self.single_image_explicit_path = (
            Path(single_image_explicit_path).expanduser().resolve()
            if single_image_explicit_path is not None
            else None
        )

        # 出力ディレクトリ作成
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.file_handler = FileHandler()
        self.image_processor = ImageProcessor()

    def analyze(self) -> Dict[str, Any]:
        """
        VD解析を実行

        Returns:
        --------
        results : dict
            解析結果
        """
        print("=== VD Analysis Started ===")
        _ensure_timing_log_visible()
        t_analysis_start = time.perf_counter()

        # ImageJ互換出力マネージャーを作成（画像保存用）
        t0 = time.perf_counter()
        main_folder_name = self.input_dir.name
        imagej_output = ImageJOutputManager(
            output_base_dir=str(self.output_dir.parent),
            main_folder_name=main_folder_name,
        )
        imagej_output.create_vd_structure()
        logger.info("[VD timing] create_vd_structure: %.3f s", time.perf_counter() - t0)

        # ファイルペアまたは単一画像を検索
        t0 = time.perf_counter()
        if self.single_image_mode:
            single_files = self._find_single_images()
            if self.single_image_explicit_path is not None:
                esp = self.single_image_explicit_path.resolve()
                selected = [
                    f for f in single_files if f.expanduser().resolve() == esp
                ]
                if selected:
                    single_files = selected
                elif esp.is_file():
                    single_files = [esp]
                else:
                    single_files = []
            if len(single_files) == 0:
                print("No image files found for single-image mode.")
                return {}
            print(f"Found {len(single_files)} single image(s) for processing")
        else:
            file_pairs = self._find_file_pairs()
            if len(file_pairs) == 0:
                print(
                    f"No file pairs found with superficial {self.sup_suffixes} and deep {self.deep_suffixes}"
                )
                return {}
            print(f"Found {len(file_pairs)} file pairs")
        logger.info("[VD timing] find_files: %.3f s", time.perf_counter() - t0)

        # 結果格納用
        results = {
            "patient_ids": [],
            "superficial_files": [],
            "deep_files": [],
            "faz_areas": [],
            "faz_circularities": [],
            "superficial_whole": [],
            "superficial_superior": [],
            "superficial_inferior": [],
            "superficial_temporal": [],
            "superficial_nasal": [],
            "deep_whole": [],
            "deep_superior": [],
            "deep_inferior": [],
            "deep_temporal": [],
            "deep_nasal": [],
            "fractal_dimension_superficial": [],
            "fractal_dimension_deep": [],
            "tortuosity_superficial": [],
            "tortuosity_deep": [],
        }

        # 各ペアまたは単一画像を処理（1症例ずつ順番に。QCはUIで1症例ごとに表示）
        if self.single_image_mode:
            items_to_process = [(f, None) for f in single_files]
        else:
            items_to_process = [(sup_file, deep_file) for sup_file, deep_file in file_pairs]

        for idx, (first_file, second_file) in enumerate(items_to_process):
            label = first_file.name
            print(f"\nProcessing {idx + 1}/{len(items_to_process)}: {label}")
            t_case_start = time.perf_counter()

            # patient_idを抽出
            patient_id = (
                Path(first_file.name).stem
                if self.single_image_mode
                else self._patient_id_from_superficial_filename(first_file.name)
            )

            try:
                if self.single_image_mode:
                    pair_result = self._process_single_file(
                        first_file, patient_id, imagej_output
                    )
                else:
                    pair_result = self._process_file_pair(
                        first_file, second_file, patient_id, imagej_output
                    )
                logger.info(
                    "[VD timing] case %d/%d (%s): %.3f s",
                    idx + 1,
                    len(items_to_process),
                    label,
                    time.perf_counter() - t_case_start,
                )

                # 結果を追加
                results["patient_ids"].append(patient_id)
                results["superficial_files"].append(first_file.name)
                results["deep_files"].append(
                    second_file.name if second_file else ""
                )
                results["faz_areas"].append(pair_result["faz_area"])
                results["faz_circularities"].append(pair_result["faz_circularity"])
                results["superficial_whole"].append(pair_result["superficial"]["whole"])
                results["superficial_superior"].append(
                    pair_result["superficial"]["superior"]
                )
                results["superficial_inferior"].append(
                    pair_result["superficial"]["inferior"]
                )
                results["superficial_temporal"].append(
                    pair_result["superficial"]["temporal"]
                )
                results["superficial_nasal"].append(pair_result["superficial"]["nasal"])
                results["deep_whole"].append(pair_result["deep"]["whole"])
                results["deep_superior"].append(pair_result["deep"]["superior"])
                results["deep_inferior"].append(pair_result["deep"]["inferior"])
                results["deep_temporal"].append(pair_result["deep"]["temporal"])
                results["deep_nasal"].append(pair_result["deep"]["nasal"])
                results["fractal_dimension_superficial"].append(
                    pair_result["fractal_dimension_superficial"]
                )
                results["fractal_dimension_deep"].append(
                    pair_result["fractal_dimension_deep"]
                )
                results["tortuosity_superficial"].append(
                    pair_result["tortuosity_superficial"]
                )
                results["tortuosity_deep"].append(pair_result["tortuosity_deep"])

                print(f"  ✓ Success: FAZ={pair_result['faz_area']:.3f} mm²")

            except Exception as e:
                print(f"  ✗ Error processing {first_file.name}: {str(e)}")
                # エラー時はデフォルト値を追加
                results["patient_ids"].append(patient_id)
                results["superficial_files"].append(first_file.name)
                results["deep_files"].append(
                    second_file.name if second_file else ""
                )
                for key in ["faz_areas", "faz_circularities"]:
                    results[key].append(0)
                for key in [
                    "superficial_whole",
                    "superficial_superior",
                    "superficial_inferior",
                    "superficial_temporal",
                    "superficial_nasal",
                    "deep_whole",
                    "deep_superior",
                    "deep_inferior",
                    "deep_temporal",
                    "deep_nasal",
                ]:
                    results[key].append(0)
                results["fractal_dimension_superficial"].append(0.0)
                results["fractal_dimension_deep"].append(0.0)
                results["tortuosity_superficial"].append(1.0)
                results["tortuosity_deep"].append(1.0)

        # CSV保存
        t0 = time.perf_counter()
        csv_path = self._save_results_csv(results)
        logger.info("[VD timing] save_results_csv: %.3f s", time.perf_counter() - t0)

        # ImageJ互換出力を生成
        t0 = time.perf_counter()
        self._create_imagej_compatible_output(results)
        logger.info(
            "[VD timing] create_imagej_compatible_output: %.3f s",
            time.perf_counter() - t0,
        )

        total_elapsed = time.perf_counter() - t_analysis_start
        logger.info("[VD timing] TOTAL: %.3f s", total_elapsed)
        print("\n=== VD Analysis Completed ===")
        print(f"Results saved to: {csv_path}")

        return results

    def _find_file_pairs(self) -> List[Tuple[Path, Path]]:
        """
        Superficial/Deepのファイルペアを検索。
        複数サフィックス対応（例: 1.tif と 1.tiff で visit1/visit2 の両方を検出）。
        ファイル名でソートし、1症例（1ペア）ずつ順に処理する順序を保つ。

        Returns:
        --------
        pairs : list of tuple
            (superficial_path, deep_path)のリスト
        """
        print("Searching for file pairs...")
        print(f"  Input directory: {self.input_dir}")
        print(f"  Superficial suffixes: {self.sup_suffixes}")
        print(f"  Deep suffixes: {self.deep_suffixes}")

        # サポートする画像形式
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

        # 全ての画像ファイルを取得
        all_files = []
        for ext in supported_exts:
            all_files.extend(self.input_dir.glob(f"*{ext}"))
            all_files.extend(self.input_dir.rglob(f"**/*{ext}"))

        # 重複を除去してソート
        all_files = sorted(list(set(all_files)))

        print(f"  Found {len(all_files)} image files")
        if all_files:
            print(f"  First few files: {[f.name for f in all_files[:5]]}")

        # 最長一致優先（1.tiff を 1.tif より先に判定）
        sup_suffixes_sorted = sorted(self.sup_suffixes, key=len, reverse=True)
        deep_suffixes_sorted = sorted(self.deep_suffixes, key=len, reverse=True)

        # Superficial: いずれかのサフィックスで終わるファイルを収集し名前でソート
        sup_files = []
        for f in all_files:
            for suf in sup_suffixes_sorted:
                if f.name.endswith(suf):
                    sup_files.append(f)
                    print(f"  ✓ Matched Superficial: {f.name}")
                    break

        sup_files.sort(key=lambda p: p.name)
        print(f"  Superficial files: {len(sup_files)}")

        pairs = []
        for sup_file in sup_files:
            # マッチしたサフィックス（最長一致）
            matched_sup = None
            for suf in sup_suffixes_sorted:
                if sup_file.name.endswith(suf):
                    matched_sup = suf
                    break
            if matched_sup is None:
                continue
            patient_id = sup_file.name[: -len(matched_sup)]

            # 対応するDeepファイルを探す（同じ patient_id + いずれかの deep サフィックス）
            deep_file = None
            for ds in deep_suffixes_sorted:
                candidate = sup_file.parent / (patient_id + ds)
                if candidate.exists():
                    deep_file = candidate
                    break

            if deep_file is not None:
                pairs.append((sup_file, deep_file))
                print(f"  Pairing: {sup_file.name} <-> {deep_file.name} ✓")
            else:
                print(f"  ✗ No deep file for: {sup_file.name} (patient_id={patient_id})")

        print(f"  Total pairs: {len(pairs)}")
        return pairs

    def _find_single_images(self) -> List[Path]:
        """
        Single image mode: 全画像ファイルを検索して返す（ペア不要）。
        File Upload 用。

        Returns:
        --------
        files : list of Path
            画像ファイルのリスト
        """
        supported_exts = [
            ".tif", ".tiff", ".jpg", ".jpeg", ".png",
            ".TIF", ".TIFF", ".JPG", ".JPEG", ".PNG",
        ]
        all_files = []
        for ext in supported_exts:
            all_files.extend(self.input_dir.glob(f"*{ext}"))
        all_files = sorted(list(set(all_files)))
        return all_files

    def _patient_id_from_superficial_filename(self, name: str) -> str:
        """Superficialファイル名から patient_id を抽出（複数サフィックス・最長一致）。"""
        for suf in sorted(self.sup_suffixes, key=len, reverse=True):
            if name.endswith(suf):
                return name[: -len(suf)]
        return name.replace(self.sup_suffix, "")  # fallback

    def _process_single_file(
        self,
        single_file: Path,
        patient_id: str,
        imagej_output: ImageJOutputManager = None,
    ) -> Dict[str, Any]:
        """
        単一画像を処理（File Upload用）。
        その画像に対してFAZを同定し、VD解析を実行。Deep層はN/A（0で埋める）。

        Parameters:
        -----------
        single_file : Path
            入力画像ファイル
        patient_id : str
            患者ID（ファイル名ベース）
        imagej_output : ImageJOutputManager, optional

        Returns:
        --------
        result : dict
            処理結果（superficial=単一画像のメトリクス、deep=0）
        """
        t_single_start = time.perf_counter()

        t0 = time.perf_counter()
        image = self.image_processor.load_image(str(single_file), as_gray=True)
        image = self.image_processor.ensure_8bit(image)

        if imagej_output is not None:
            imagej_output.save_vd_stage_image(
                image, patient_id, stage_name="original"
            )
        logger.info("[VD timing]   load_image: %.3f s", time.perf_counter() - t0)

        h, w = image.shape
        scale_manager = ScaleManager(w, self.scale_mm)
        vd_processor = VDProcessor(pipeline_type="High Precision")

        # FAZ検出（単一画像用）
        t0 = time.perf_counter()
        if self.use_enhanced_faz:
            pixel_size_mm = scale_manager.mm_per_pixel

            t_faz = time.perf_counter()
            faz_skeleton, combined_for_faz = (
                vd_processor.process_single_for_faz(
                    image,
                    li_threshold_scale=self.faz_li_threshold_scale,
                    use_optimized=self.use_optimized_preprocessing,
                )
            )
            logger.info(
                "[VD timing]     faz_skeleton_generation: %.3f s",
                time.perf_counter() - t_faz,
            )

            if self.save_stages:
                self._save_stage_image(faz_skeleton, patient_id, "faz_skeleton")

            if self.use_faz_intensity_refinement:
                t_faz = time.perf_counter()
                faz_skeleton = VDProcessor.refine_vessel_mask_by_intensity(
                    faz_skeleton,
                    combined_for_faz,
                    center_roi_ratio=self.faz_center_roi_ratio,
                    intensity_percentile=self.faz_intensity_percentile,
                )
                logger.info(
                    "[VD timing]     faz_intensity_refinement: %.3f s",
                    time.perf_counter() - t_faz,
                )
                if self.save_stages:
                    self._save_stage_image(
                        faz_skeleton, patient_id, "faz_skeleton_refined"
                    )

            binary_mask_for_faz = faz_skeleton > 0

            improved_detector = ImprovedFAZDetector(
                min_area_mm2=0.1,
                min_circularity=0.15,
                distance_trim_ratio=self.faz_distance_trim_ratio,
                distance_min_px=self.faz_distance_min_px,
            )
            t_faz = time.perf_counter()
            faz_mask, faz_metrics = improved_detector.detect(
                combined_for_faz,
                binary_mask_for_faz,
                mm_per_pixel=pixel_size_mm,
            )
            logger.info(
                "[VD timing]     faz_improved_detect: %.3f s",
                time.perf_counter() - t_faz,
            )
            if np.any(faz_mask) and faz_metrics.get("faz_area_mm2", 0) > 0:
                faz_metrics["segmentation_method"] = "improved"
            else:
                t_faz = time.perf_counter()
                enhanced_faz = EnhancedFAZSegmentation(
                    method=self.faz_method,
                    min_area_mm2=0.1,
                    max_area_mm2=15.0,
                    min_circularity=0.15,
                    pixel_size_mm=pixel_size_mm,
                )
                faz_mask, faz_metrics = enhanced_faz.segment(
                    image, binary_mask=binary_mask_for_faz
                )
                logger.info(
                    "[VD timing]     faz_enhanced_segment: %.3f s",
                    time.perf_counter() - t_faz,
                )

            if faz_mask is None:
                print(
                    "  Warning: Enhanced FAZ failed, falling back to traditional"
                )
                t_faz = time.perf_counter()
                faz_skeleton, _ = vd_processor.process_single_for_faz(
                    image,
                    li_threshold_scale=self.faz_li_threshold_scale,
                    use_optimized=self.use_optimized_preprocessing,
                )
                faz_detector = FAZDetector()
                faz_mask = faz_detector.detect_faz(faz_skeleton)
                faz_mask_expanded = faz_detector.expand_roi(faz_mask)
                faz_area, faz_circularity = self._measure_faz(
                    faz_mask_expanded, scale_manager
                )
                faz_metrics = {
                    "faz_area_mm2": faz_area,
                    "faz_circularity": faz_circularity,
                    "segmentation_method": "fallback_traditional",
                }
                logger.info(
                    "[VD timing]     faz_fallback_traditional: %.3f s",
                    time.perf_counter() - t_faz,
                )
            else:
                faz_mask_expanded = (faz_mask * 255).astype(np.uint8)
                faz_area = faz_metrics["faz_area_mm2"]
                faz_circularity = faz_metrics["faz_circularity"]
                print(
                    f"  Enhanced FAZ detected: {faz_area:.3f} mm² "
                    f"(circularity: {faz_circularity:.3f})"
                )
                faz_detector = FAZDetector()
        else:
            t_faz = time.perf_counter()
            faz_skeleton, _ = vd_processor.process_single_for_faz(
                image,
                li_threshold_scale=self.faz_li_threshold_scale,
                use_optimized=self.use_optimized_preprocessing,
            )
            logger.info(
                "[VD timing]     faz_skeleton_generation: %.3f s",
                time.perf_counter() - t_faz,
            )
            if self.save_stages:
                self._save_stage_image(faz_skeleton, patient_id, "faz_skeleton")
            faz_detector = FAZDetector()
            t_faz = time.perf_counter()
            faz_mask = faz_detector.detect_faz(faz_skeleton)
            faz_mask_expanded = faz_detector.expand_roi(faz_mask)
            faz_area, faz_circularity = self._measure_faz(
                faz_mask_expanded, scale_manager
            )
            logger.info(
                "[VD timing]     faz_traditional_detect_expand: %.3f s",
                time.perf_counter() - t_faz,
            )
            faz_metrics = {
                "faz_area_mm2": faz_area,
                "faz_circularity": faz_circularity,
                "segmentation_method": "traditional",
            }

        logger.info("[VD timing]   faz_detection: %.3f s", time.perf_counter() - t0)

        if self.save_stages:
            self._save_stage_image(faz_mask_expanded, patient_id, "faz_mask")
            if self.use_enhanced_faz and faz_mask is not None:
                faz_vis = FAZVisualization.draw_faz_contour(
                    image, faz_mask, color=(0, 255, 0), thickness=2
                )
                self._save_stage_image(faz_vis, patient_id, "faz_visualization")

        faz_area = faz_metrics["faz_area_mm2"]
        faz_circularity = faz_metrics["faz_circularity"]
        t0 = time.perf_counter()
        rois = faz_detector.create_concentric_rois(faz_mask_expanded, w, h)
        phansalkar_radius = int(24 / scale_manager.pixel_size_um)

        # 単一画像のVD処理
        single_binary = vd_processor.process_for_vd(
            image, faz_mask_expanded, phansalkar_radius=phansalkar_radius
        )
        logger.info("[VD timing]   process_for_vd: %.3f s", time.perf_counter() - t0)
        if self.save_stages:
            self._save_stage_image(single_binary, patient_id, "single_binary")

        t0 = time.perf_counter()
        single_results = self._measure_vessel_density(single_binary, rois)
        logger.info("[VD timing]   measure_vessel_density: %.3f s", time.perf_counter() - t0)

        t0 = time.perf_counter()
        pixel_size_mm = scale_manager.mm_per_pixel
        skeleton_analyzer = SkeletonAnalyzer(pixel_size_mm=pixel_size_mm)
        skel_result = skeleton_analyzer.analyze(
            single_binary, compute_loops=False
        )
        logger.info("[VD timing]   skeleton_analyzer: %.3f s", time.perf_counter() - t0)
        fractal_dim = skel_result["fractal_dimension"]
        tortuosity = skel_result["tortuosity_mean"]

        t0 = time.perf_counter()
        if imagej_output is not None:
            img_with_roi = image.copy()
            if len(img_with_roi.shape) == 2:
                img_with_roi = cv2.cvtColor(img_with_roi, cv2.COLOR_GRAY2RGB)
            img_with_roi[faz_mask_expanded > 0] = [255, 0, 0]
            imagej_output.save_vd_stage_image(
                img_with_roi, patient_id, stage_name="processed"
            )

        # 可視化（superficialとして保存＝QC表示と互換）
        self._save_visualization(
            image, single_binary, rois, patient_id, "superficial"
        )
        logger.info("[VD timing]   save_visualization: %.3f s", time.perf_counter() - t0)
        logger.info(
            "[VD timing]   _process_single_file total: %.3f s",
            time.perf_counter() - t_single_start,
        )
        # Deep用は空で良いが、同一ファイルでdeep可視化も作るとQC表示が崩れない
        # 単一画像モードではdeepはN/Aなので、superficialのコピーまたは何も保存しない
        # run_vd_batchは deep_img = output_dir / f"{pid}_deep_visualization.png" を参照
        # → 存在しなければスキップされるので、deepは保存しなくてOK

        return {
            "faz_area": faz_area,
            "faz_circularity": faz_circularity,
            "faz_metrics": faz_metrics,
            "superficial": single_results,
            "deep": {k: 0.0 for k in single_results},
            "fractal_dimension_superficial": fractal_dim,
            "fractal_dimension_deep": 0.0,
            "tortuosity_superficial": tortuosity,
            "tortuosity_deep": 1.0,
        }

    def _process_file_pair(
        self,
        sup_file: Path,
        deep_file: Path,
        patient_id: str,
        imagej_output: ImageJOutputManager = None,
    ) -> Dict[str, Any]:
        """
        1つのファイルペアを処理

        Parameters:
        -----------
        sup_file : Path
            Superficialファイル
        deep_file : Path
            Deepファイル
        patient_id : str
            患者ID
        imagej_output : ImageJOutputManager, optional
            ImageJ互換出力マネージャー（画像保存用）

        Returns:
        --------
        result : dict
            処理結果
        """
        t_pair_start = time.perf_counter()

        # Superficial画像を読み込み
        t0 = time.perf_counter()
        sup_image = self.image_processor.load_image(str(sup_file), as_gray=True)
        sup_image = self.image_processor.ensure_8bit(sup_image)

        # ImageJ互換の原画像を保存
        if imagej_output is not None:
            imagej_output.save_vd_stage_image(
                sup_image, patient_id, stage_name="original"
            )

        # Deep画像を読み込み
        deep_image = self.image_processor.load_image(str(deep_file), as_gray=True)
        deep_image = self.image_processor.ensure_8bit(deep_image)

        # サイズ確認
        h, w = sup_image.shape

        # Deepをリサイズ（必要に応じて）
        if deep_image.shape != sup_image.shape:
            deep_image = cv2.resize(deep_image, (w, h), interpolation=cv2.INTER_LINEAR)
        logger.info("[VD timing]   load_images: %.3f s", time.perf_counter() - t0)

        # スケール管理
        scale_manager = ScaleManager(w, self.scale_mm)

        # VDプロセッサ作成
        vd_processor = VDProcessor(pipeline_type="High Precision")

        # FAZ検出
        t0 = time.perf_counter()
        if self.use_enhanced_faz:
            # Enhanced FAZ Segmentationを使用
            pixel_size_mm = scale_manager.mm_per_pixel

            # まずsuperficialとdeepを組み合わせて前処理（Li=0.05推奨でスケルトン生成）
            t_faz = time.perf_counter()
            if self.use_optimized_preprocessing:
                faz_skeleton, combined_for_faz = (
                    vd_processor.process_combined_for_faz_optimized(
                        sup_image,
                        deep_image,
                        li_threshold_scale=self.faz_li_threshold_scale,
                    )
                )
            else:
                faz_skeleton, combined_for_faz = (
                    vd_processor.process_combined_for_faz(
                        sup_image,
                        deep_image,
                        li_threshold_scale=self.faz_li_threshold_scale,
                    )
                )
            logger.info(
                "[VD timing]     faz_skeleton_generation: %.3f s",
                time.perf_counter() - t_faz,
            )

            if self.save_stages:
                self._save_stage_image(faz_skeleton, patient_id, "faz_skeleton")

            # オプション: 中心の薄い血管を強度で無血管にしFAZ候補を拡大
            if self.use_faz_intensity_refinement:
                t_faz = time.perf_counter()
                faz_skeleton = VDProcessor.refine_vessel_mask_by_intensity(
                    faz_skeleton,
                    combined_for_faz,
                    center_roi_ratio=self.faz_center_roi_ratio,
                    intensity_percentile=self.faz_intensity_percentile,
                )
                logger.info(
                    "[VD timing]     faz_intensity_refinement: %.3f s",
                    time.perf_counter() - t_faz,
                )
                if self.save_stages:
                    self._save_stage_image(
                        faz_skeleton, patient_id, "faz_skeleton_refined"
                    )

            # スケルトン画像を反転してバイナリマスクとして使用
            # スケルトン: 0=血管なし（FAZ候補）、255=血管あり
            binary_mask_for_faz = faz_skeleton > 0  # True=血管あり

            # 改善案1: まず ImprovedFAZDetector を試す（強度精査の効果が反映される）
            improved_detector = ImprovedFAZDetector(
                min_area_mm2=0.1,
                min_circularity=0.15,
                distance_trim_ratio=self.faz_distance_trim_ratio,
                distance_min_px=self.faz_distance_min_px,
            )
            t_faz = time.perf_counter()
            faz_mask, faz_metrics = improved_detector.detect(
                combined_for_faz,
                binary_mask_for_faz,
                mm_per_pixel=pixel_size_mm,
            )
            logger.info(
                "[VD timing]     faz_improved_detect: %.3f s",
                time.perf_counter() - t_faz,
            )
            if np.any(faz_mask) and faz_metrics.get("faz_area_mm2", 0) > 0:
                faz_metrics["segmentation_method"] = "improved"
            else:
                t_faz = time.perf_counter()
                # フォールバック: EnhancedFAZSegmentation
                enhanced_faz = EnhancedFAZSegmentation(
                    method=self.faz_method,
                    min_area_mm2=0.1,
                    max_area_mm2=15.0,  # さらに拡張（実際のFAZは9.2 mm²程度）
                    min_circularity=0.15,  # さらに緩和（実際の円形度は0.19程度）
                    pixel_size_mm=pixel_size_mm,
                )
                faz_mask, faz_metrics = enhanced_faz.segment(
                    sup_image, binary_mask=binary_mask_for_faz
                )
                logger.info(
                    "[VD timing]     faz_enhanced_segment: %.3f s",
                    time.perf_counter() - t_faz,
                )

            if faz_mask is None:
                print(
                    "  Warning: Enhanced FAZ detection failed, falling back to traditional method"
                )
                # フォールバック: 従来の方法
                t_faz = time.perf_counter()
                if self.use_optimized_preprocessing:
                    faz_skeleton, _ = (
                        vd_processor.process_combined_for_faz_optimized(
                            sup_image,
                            deep_image,
                            li_threshold_scale=self.faz_li_threshold_scale,
                        )
                    )
                else:
                    faz_skeleton, _ = vd_processor.process_combined_for_faz(
                        sup_image,
                        deep_image,
                        li_threshold_scale=self.faz_li_threshold_scale,
                    )
                faz_detector = FAZDetector()
                faz_mask = faz_detector.detect_faz(faz_skeleton)
                faz_mask_expanded = faz_detector.expand_roi(faz_mask)
                faz_area, faz_circularity = self._measure_faz(
                    faz_mask_expanded, scale_manager
                )
                faz_metrics = {
                    "faz_area_mm2": faz_area,
                    "faz_circularity": faz_circularity,
                    "segmentation_method": "fallback_traditional",
                }
                logger.info(
                    "[VD timing]     faz_fallback_traditional: %.3f s",
                    time.perf_counter() - t_faz,
                )
            else:
                # Enhanced FAZ成功
                faz_mask_expanded = (faz_mask * 255).astype(np.uint8)
                faz_area = faz_metrics["faz_area_mm2"]
                faz_circularity = faz_metrics["faz_circularity"]
                print(
                    f"  Enhanced FAZ detected: {faz_area:.3f} mm² (circularity: {faz_circularity:.3f}, method: {faz_metrics.get('segmentation_method', self.faz_method)})"
                )
                # ROI作成のためにFAZDetectorを初期化
                faz_detector = FAZDetector()
        else:
            # 従来の方法を使用
            t_faz = time.perf_counter()
            if self.use_optimized_preprocessing:
                faz_skeleton, _ = vd_processor.process_combined_for_faz_optimized(
                    sup_image,
                    deep_image,
                    li_threshold_scale=self.faz_li_threshold_scale,
                )
            else:
                faz_skeleton, _ = vd_processor.process_combined_for_faz(
                    sup_image,
                    deep_image,
                    li_threshold_scale=self.faz_li_threshold_scale,
                )
            logger.info(
                "[VD timing]     faz_skeleton_generation: %.3f s",
                time.perf_counter() - t_faz,
            )

            if self.save_stages:
                self._save_stage_image(faz_skeleton, patient_id, "faz_skeleton")

            faz_detector = FAZDetector()
            t_faz = time.perf_counter()
            faz_mask = faz_detector.detect_faz(faz_skeleton)
            faz_mask_expanded = faz_detector.expand_roi(faz_mask)
            faz_area, faz_circularity = self._measure_faz(
                faz_mask_expanded, scale_manager
            )
            logger.info(
                "[VD timing]     faz_traditional_detect_expand: %.3f s",
                time.perf_counter() - t_faz,
            )
            faz_metrics = {
                "faz_area_mm2": faz_area,
                "faz_circularity": faz_circularity,
                "segmentation_method": "traditional",
            }

        # 共通処理: FAZDetectorがまだ定義されていない場合は初期化
        if "faz_detector" not in locals():
            faz_detector = FAZDetector()

        logger.info("[VD timing]   faz_detection: %.3f s", time.perf_counter() - t0)

        if self.save_stages:
            self._save_stage_image(faz_mask_expanded, patient_id, "faz_mask")
            # 可視化画像も保存
            if self.use_enhanced_faz and faz_mask is not None:
                faz_vis = FAZVisualization.draw_faz_contour(
                    sup_image, faz_mask, color=(0, 255, 0), thickness=2
                )
                self._save_stage_image(faz_vis, patient_id, "faz_visualization")

        # FAZ面積と真円度（メトリクスから取得）
        faz_area = faz_metrics["faz_area_mm2"]
        faz_circularity = faz_metrics["faz_circularity"]

        # 同心円ROI作成
        t0 = time.perf_counter()
        rois = faz_detector.create_concentric_rois(faz_mask_expanded, w, h)
        logger.info("[VD timing]   create_rois: %.3f s", time.perf_counter() - t0)

        # Phansalkar半径を計算
        phansalkar_radius = int(24 / scale_manager.pixel_size_um)  # 24μm

        # Superficial層を処理
        t0 = time.perf_counter()
        sup_binary = vd_processor.process_for_vd(
            sup_image, faz_mask_expanded, phansalkar_radius=phansalkar_radius
        )
        logger.info("[VD timing]   process_for_vd_superficial: %.3f s", time.perf_counter() - t0)

        if self.save_stages:
            self._save_stage_image(sup_binary, patient_id, "superficial_binary")

        t0 = time.perf_counter()
        sup_results = self._measure_vessel_density(sup_binary, rois)
        logger.info("[VD timing]   measure_vd_superficial: %.3f s", time.perf_counter() - t0)

        # Deep層を処理
        t0 = time.perf_counter()
        deep_binary = vd_processor.process_for_vd(
            deep_image, faz_mask_expanded, phansalkar_radius=phansalkar_radius
        )
        logger.info("[VD timing]   process_for_vd_deep: %.3f s", time.perf_counter() - t0)

        if self.save_stages:
            self._save_stage_image(deep_binary, patient_id, "deep_binary")

        t0 = time.perf_counter()
        deep_results = self._measure_vessel_density(deep_binary, rois)
        logger.info("[VD timing]   measure_vd_deep: %.3f s", time.perf_counter() - t0)

        # SkeletonAnalyzer で fractal dimension と tortuosity を計算
        t0 = time.perf_counter()
        pixel_size_mm = scale_manager.mm_per_pixel
        skeleton_analyzer = SkeletonAnalyzer(pixel_size_mm=pixel_size_mm)
        sup_skel_result = skeleton_analyzer.analyze(
            sup_binary, compute_loops=False
        )
        deep_skel_result = skeleton_analyzer.analyze(
            deep_binary, compute_loops=False
        )
        logger.info("[VD timing]   skeleton_analyzer: %.3f s", time.perf_counter() - t0)
        fractal_dim_sup = sup_skel_result["fractal_dimension"]
        fractal_dim_deep = deep_skel_result["fractal_dimension"]
        tortuosity_sup = sup_skel_result["tortuosity_mean"]
        tortuosity_deep = deep_skel_result["tortuosity_mean"]

        # ImageJ互換の処理済み画像を保存（ROI付き）
        t0 = time.perf_counter()
        if imagej_output is not None:
            # Superficial画像にROIを重ねて保存
            sup_with_roi = sup_image.copy()
            if len(sup_with_roi.shape) == 2:
                sup_with_roi = cv2.cvtColor(sup_with_roi, cv2.COLOR_GRAY2RGB)
            # FAZマスクを赤で描画
            sup_with_roi[faz_mask_expanded > 0] = [255, 0, 0]
            imagej_output.save_vd_stage_image(
                sup_with_roi, patient_id, stage_name="processed"
            )

        # 可視化を保存（QC表示用のため save_stages に依存せず常に保存）
        self._save_visualization(
            sup_image, sup_binary, rois, patient_id, "superficial"
        )
        self._save_visualization(deep_image, deep_binary, rois, patient_id, "deep")
        logger.info("[VD timing]   save_visualization: %.3f s", time.perf_counter() - t0)
        logger.info(
            "[VD timing]   _process_file_pair total: %.3f s",
            time.perf_counter() - t_pair_start,
        )

        # 結果を返す（拡張されたFAZメトリクス + FD/tortuosity を含む）
        result = {
            "faz_area": faz_area,
            "faz_circularity": faz_circularity,
            "faz_metrics": faz_metrics,  # 詳細なFAZメトリクス
            "superficial": sup_results,
            "deep": deep_results,
            "fractal_dimension_superficial": fractal_dim_sup,
            "fractal_dimension_deep": fractal_dim_deep,
            "tortuosity_superficial": tortuosity_sup,
            "tortuosity_deep": tortuosity_deep,
        }

        return result

    def _measure_faz(
        self, faz_mask: np.ndarray, scale_manager: ScaleManager
    ) -> Tuple[float, float]:
        """
        FAZの面積と真円度を測定

        Parameters:
        -----------
        faz_mask : np.ndarray
            FAZマスク
        scale_manager : ScaleManager
            スケール管理

        Returns:
        --------
        area_mm2 : float
            面積（mm²）
        circularity : float
            真円度
        """
        contours, _ = cv2.findContours(
            faz_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        if len(contours) == 0:
            return 0.0, 0.0

        contour = max(contours, key=cv2.contourArea)

        # 面積
        area_pixels = cv2.contourArea(contour)
        area_mm2 = area_pixels * (scale_manager.mm_per_pixel**2)

        # 真円度 = 4π × 面積 / 周長²
        perimeter = cv2.arcLength(contour, True)
        if perimeter > 0:
            circularity = 4 * np.pi * area_pixels / (perimeter**2)
        else:
            circularity = 0.0

        return area_mm2, circularity

    def _measure_vessel_density(
        self, binary: np.ndarray, rois: Dict[str, np.ndarray]
    ) -> Dict[str, float]:
        """
        各ROIで血管密度を測定

        Parameters:
        -----------
        binary : np.ndarray
            二値化された血管画像
        rois : dict
            ROIマスクの辞書

        Returns:
        --------
        densities : dict
            各ROIの血管密度（%）
        """
        densities = {}

        for roi_name in ["whole", "superior", "inferior", "temporal", "nasal"]:
            roi_mask = rois.get(roi_name)

            if roi_mask is None:
                densities[roi_name] = 0.0
                continue

            # ROI内の血管ピクセル
            vessel_in_roi = cv2.bitwise_and(binary, roi_mask)

            # 密度計算
            total_pixels = np.sum(roi_mask > 0)
            vessel_pixels = np.sum(vessel_in_roi > 0)

            if total_pixels > 0:
                density = (vessel_pixels / total_pixels) * 100
            else:
                density = 0.0

            densities[roi_name] = density

        # Temporal/Nasalを眼の側に応じて調整
        if self.side == "right":
            densities["temporal"] = densities["temporal"]
            densities["nasal"] = densities["nasal"]
        else:  # left
            # 左右を入れ替え
            temp = densities["temporal"]
            densities["temporal"] = densities["nasal"]
            densities["nasal"] = temp

        return densities

    def _save_stage_image(self, image: np.ndarray, patient_id: str, stage_name: str):
        """
        処理段階の画像を保存

        Parameters:
        -----------
        image : np.ndarray
            保存する画像
        patient_id : str
            患者ID
        stage_name : str
            段階名
        """
        output_path = self.output_dir / f"{patient_id}_{stage_name}.png"
        cv2.imwrite(str(output_path), image)

    def _save_visualization(
        self,
        original: np.ndarray,
        binary: np.ndarray,
        rois: Dict[str, np.ndarray],
        patient_id: str,
        layer_name: str,
    ):
        """
        可視化画像を保存

        Parameters:
        -----------
        original : np.ndarray
            元画像
        binary : np.ndarray
            二値画像
        rois : dict
            ROIマスク
        patient_id : str
            患者ID
        layer_name : str
            層名（superficial/deep）
        """
        # RGB画像を作成
        vis = cv2.cvtColor(original, cv2.COLOR_GRAY2BGR)

        # 血管を緑で重ね合わせ
        vis[binary > 0] = [0, 255, 0]

        # ROI境界を黄色で描画
        for roi_name in ["whole", "superior", "inferior", "temporal", "nasal"]:
            roi_mask = rois.get(roi_name)
            if roi_mask is not None:
                contours, _ = cv2.findContours(
                    roi_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
                )
                cv2.drawContours(vis, contours, -1, (0, 255, 255), 2)

        # スケールバーを追加
        h, w = vis.shape[:2]
        scale_bar_length = int(w * 0.2)  # 画像幅の20%
        cv2.rectangle(
            vis,
            (w - scale_bar_length - 20, h - 30),
            (w - 20, h - 20),
            (255, 255, 0),
            -1,
        )

        # 保存
        output_path = self.output_dir / f"{patient_id}_{layer_name}_visualization.png"
        cv2.imwrite(str(output_path), vis)

    def _save_results_csv(self, results: Dict) -> Path:
        """
        結果をCSVで保存

        Parameters:
        -----------
        results : dict
            結果データ

        Returns:
        --------
        csv_path : Path
            保存先パス
        """
        csv_path = self.output_dir / "VD_Results.csv"

        self.file_handler.save_results_csv(
            results, str(self.output_dir), "VD_Results.csv"
        )

        return csv_path

    def _create_imagej_compatible_output(self, results: Dict):
        """
        ImageJ互換の出力を作成

        Parameters:
        -----------
        results : dict
            VD解析結果
        """
        # メインフォルダー名を取得
        main_folder_name = self.input_dir.name

        # ImageJ互換出力マネージャーを作成
        # output_dirはすでにoutput/VDなので、親ディレクトリ(output)を使用
        imagej_output = ImageJOutputManager(
            output_base_dir=str(self.output_dir.parent),
            main_folder_name=main_folder_name,
        )

        # VD用ディレクトリ構造を作成
        imagej_output.create_vd_structure()

        # Results-VD.csvを作成
        vd_table_results = {
            "patient_ids": results.get("patient_ids", []),
            "superficial_files": results.get("superficial_files", []),
            "deep_files": results.get("deep_files", []),
            "faz_areas": results.get("faz_areas", []),
            "faz_circularity": results.get("faz_circularities", []),
            "superficial_vessel_densities": results.get("superficial_whole", []),
            "sup_superficial": results.get("superficial_superior", []),
            "temp_superficial": results.get("superficial_temporal", []),
            "nasal_superficial": results.get("superficial_nasal", []),
            "inf_superficial": results.get("superficial_inferior", []),
            "deep_vessel_densities": results.get("deep_whole", []),
            "sup_deep": results.get("deep_superior", []),
            "temp_deep": results.get("deep_temporal", []),
            "nasal_deep": results.get("deep_nasal", []),
            "inf_deep": results.get("deep_inferior", []),
            "fractal_dimension_superficial": results.get(
                "fractal_dimension_superficial", []
            ),
            "fractal_dimension_deep": results.get("fractal_dimension_deep", []),
            "tortuosity_superficial": results.get("tortuosity_superficial", []),
            "tortuosity_deep": results.get("tortuosity_deep", []),
        }

        csv_path = imagej_output.create_vd_table(vd_table_results)
        print(f"  ImageJ-compatible VD table saved: {csv_path}")

        # ログファイルを保存
        log_content = self._generate_vd_log(results)
        log_path = imagej_output.save_log_file(
            log_content, analyst_name=self.analyst_name, analysis_type="VD"
        )
        print(f"  Log file saved: {log_path}")

    def _generate_vd_log(self, results: Dict) -> str:
        """VD解析ログを生成"""
        log_lines = []
        log_lines.append("=== VD Analysis Started ===")
        log_lines.append(f"Input Directory: {self.input_dir}")
        log_lines.append(f"Output Directory: {self.output_dir}")
        log_lines.append(f"Scale: {self.scale_mm} mm")
        log_lines.append(f"Side: {self.side}")
        log_lines.append(f"Superficial Suffix: {self.sup_suffix}")
        log_lines.append(f"Deep Suffix: {self.deep_suffix}")
        log_lines.append("")
        log_lines.append(f"Found {len(results['patient_ids'])} file pairs")
        log_lines.append("")

        for i, patient_id in enumerate(results["patient_ids"]):
            log_lines.append(
                f"Processing pair {i+1}/{len(results['patient_ids'])}: {patient_id}"
            )
            log_lines.append(f"  Superficial: {results['superficial_files'][i]}")
            log_lines.append(f"  Deep: {results['deep_files'][i]}")
            log_lines.append(f"  FAZ Area: {results['faz_areas'][i]:.3f} mm²")
            log_lines.append(
                f"  Superficial Density: {results['superficial_whole'][i]:.2f}%"
            )
            log_lines.append(f"  Deep Density: {results['deep_whole'][i]:.2f}%")
            log_lines.append("")

        log_lines.append("=== VD Analysis Completed ===")

        return "\n".join(log_lines)
