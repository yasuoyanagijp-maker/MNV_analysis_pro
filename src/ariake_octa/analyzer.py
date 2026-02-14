"""
ARIAKE Analyzer - Main Entry Point

Unified interface for VD and MNV analysis
"""

from pathlib import Path
from typing import Dict, List, Union

import numpy as np

from .common import CSVExporter, ImageLoader, ImageQualityValidator, ParameterLogger
from .mnv import MNVPipeline
from .vd import VDPipeline


class ARIAKEAnalyzer:
    """
    メインエントリポイント

    VD解析とMNV解析を自動判定して実行

    Example:
        >>> from ariake_octa import ARIAKEAnalyzer
        >>> analyzer = ARIAKEAnalyzer()
        >>>
        >>> # VD analysis (pair images)
        >>> results = analyzer.analyze(['superficial.tif', 'deep.tif'])
        >>>
        >>> # MNV analysis (single image)
        >>> results = analyzer.analyze(['mnv.tif'])
        >>>
        >>> # Save results
        >>> analyzer.save_results(results, 'output/patient001')
    """

    def __init__(self, pixel_size_mm: float = 0.00744):
        """
        Args:
            pixel_size_mm: ピクセルサイズ（mm/pixel）
                          標準値: 0.744 μm/pixel = 0.00744 mm/pixel
        """
        self.pixel_size_mm = pixel_size_mm

        # パイプライン初期化
        self.vd_pipeline = VDPipeline(pixel_size_mm=pixel_size_mm)
        self.mnv_pipeline = MNVPipeline(pixel_size_mm=pixel_size_mm)

        # ユーティリティ
        self.image_loader = ImageLoader()
        self.validator = ImageQualityValidator()
        self.csv_exporter = CSVExporter()
        self.param_logger = ParameterLogger()

    def analyze(
        self,
        images: Union[List[str], List[np.ndarray]],
        mode: str = "auto",
        validate: bool = True,
    ) -> Dict:
        """
        解析を実行

        Args:
            images: 画像パスまたはnumpy配列のリスト
            mode: 解析モード ('auto', 'vd', 'mnv')
            validate: 画像品質検証を実行するか

        Returns:
            dict: 解析結果
                - VD: 24メトリクス + メタデータ
                - MNV: 基本メトリクス + 中間結果（Phase 1）

        Raises:
            ValueError: 画像数不正、画像品質不足
            RuntimeError: 解析失敗
        """
        # 画像読み込み
        if isinstance(images[0], str):
            images = self._load_images(images)

        # モード自動判定
        if mode == "auto":
            mode = self._detect_mode(images)

        print(f"Analysis mode: {mode.upper()}")

        # 画像品質検証
        if validate:
            self._validate_images(images, mode)

        # 解析実行
        if mode == "vd":
            results = self._analyze_vd(images)
        elif mode == "mnv":
            results = self._analyze_mnv(images)
        else:
            raise ValueError(f"Unknown analysis mode: {mode}")

        return results

    def _load_images(self, image_paths: List[str]) -> List[np.ndarray]:
        """画像ファイルを読み込み"""
        print(f"Loading {len(image_paths)} image(s)...")

        images = []
        for path in image_paths:
            print(f"  Loading: {path}")
            image = self.image_loader.load(path)
            images.append(image)

        print("Loading completed.")
        return images

    def _detect_mode(self, images: List[np.ndarray]) -> str:
        """解析モードを自動判定"""
        n_images = len(images)

        if n_images == 2:
            print("  Detected: Pair images → VD analysis")
            return "vd"
        elif n_images == 1:
            print("  Detected: Single image → MNV analysis")
            return "mnv"
        else:
            raise ValueError(
                f"Invalid number of images: {n_images}. " f"Expected 1 (MNV) or 2 (VD)."
            )

    def _validate_images(self, images: List[np.ndarray], mode: str) -> None:
        """画像品質を検証"""
        print("Validating image quality...")

        for i, image in enumerate(images):
            result = self.validator.validate(
                image, self.pixel_size_mm, analysis_type=mode.upper()
            )

            if not result["is_valid"]:
                print(f"  Image {i+1}: ⚠️  Warning")
                for warning in result["warnings"]:
                    print(f"    - {warning}")
            else:
                print(
                    f"  Image {i+1}: ✓ OK (SNR={result['snr_db']:.1f} dB, Contrast={result['contrast']:.3f})"
                )

        print("Validation completed.")

    def _analyze_vd(self, images: List[np.ndarray]) -> Dict:
        """VD解析を実行"""
        if len(images) != 2:
            raise ValueError(
                f"VD analysis requires pair images (Superficial + Deep), "
                f"but got {len(images)} image(s)."
            )

        print("\nRunning VD analysis...")
        results = self.vd_pipeline.process(images[0], images[1])
        print("VD analysis completed.")

        return results

    def _analyze_mnv(self, images: List[np.ndarray]) -> Dict:
        """MNV解析を実行"""
        if len(images) != 1:
            raise ValueError(
                f"MNV analysis requires single image, "
                f"but got {len(images)} image(s)."
            )

        print("\nRunning MNV analysis...")
        results = self.mnv_pipeline.process(images[0])
        print("MNV analysis completed.")

        return results

    def save_results(
        self, results: Dict, output_dir: str, file_id: str = "result"
    ) -> None:
        """
        解析結果を保存

        Args:
            results: 解析結果辞書
            output_dir: 出力ディレクトリ
            file_id: ファイル識別子
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        analysis_type = results.get("analysis_type", "unknown")

        print(f"\nSaving results to: {output_dir}")

        # CSV出力（メトリクスのみ）
        metrics = {
            k: v
            for k, v in results.items()
            if k not in ["intermediate_results", "image_shape"]
        }

        csv_path = output_path / f"{file_id}_{analysis_type}.csv"
        self.csv_exporter.export_metrics(metrics, str(csv_path))
        print(f"  Saved: {csv_path.name}")

        # パラメータログ
        if analysis_type == "VD":
            params = self.vd_pipeline.params
        elif analysis_type == "MNV":
            params = self.mnv_pipeline.params
        else:
            params = {}

        log_path = output_path / f"{file_id}_parameters.json"
        self.param_logger.log(params, str(log_path))
        print(f"  Saved: {log_path.name}")

        print("Results saved successfully.")

    def batch_analyze(
        self,
        image_sets: List[List[str]],
        file_ids: List[str],
        output_dir: str,
        mode: str = "auto",
    ) -> List[Dict]:
        """
        複数画像セットを一括解析

        Args:
            image_sets: 画像パスのリストのリスト
            file_ids: ファイル識別子のリスト
            output_dir: 出力ディレクトリ
            mode: 解析モード

        Returns:
            results_list: 解析結果のリスト
        """
        results_list = []

        print(f"\n{'='*60}")
        print(f"Batch Analysis: {len(image_sets)} image sets")
        print(f"{'='*60}\n")

        for i, (images, file_id) in enumerate(zip(image_sets, file_ids), 1):
            print(f"\n[{i}/{len(image_sets)}] Processing: {file_id}")
            print(f"{'-'*60}")

            try:
                results = self.analyze(images, mode=mode)
                results_list.append(results)

                # 個別保存
                self.save_results(results, output_dir, file_id)

            except Exception as e:
                print(f"  ❌ Error: {e}")
                results_list.append({"error": str(e), "file_id": file_id})

        # 一括CSV出力
        batch_csv = Path(output_dir) / f"batch_results_{mode}.csv"
        self.csv_exporter.export_batch(results_list, str(batch_csv), file_ids)
        print(f"\n📊 Batch results saved: {batch_csv}")

        return results_list
