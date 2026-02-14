"""
ImageJ Compatibility Validator for ARIAKE OCTA Analysis System

ImageJの計算結果と比較し、互換性を検証します。

Author: GitHub Copilot
Version: 2.0.0-phase4
Date: 2026-01-22
"""

import json
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np


@dataclass
class ValidationResult:
    """検証結果データクラス"""

    metric_name: str
    ariake_value: float
    imagej_value: float
    difference: float
    relative_error_percent: float
    is_acceptable: bool
    tolerance_percent: float

    def to_dict(self) -> Dict:
        """辞書に変換"""
        return {
            "metric_name": self.metric_name,
            "ariake_value": round(self.ariake_value, 6),
            "imagej_value": round(self.imagej_value, 6),
            "difference": round(self.difference, 6),
            "relative_error_percent": round(self.relative_error_percent, 2),
            "is_acceptable": self.is_acceptable,
            "tolerance_percent": self.tolerance_percent,
        }


class ImageJValidator:
    """
    ImageJ互換性検証クラス

    Features:
    - ImageJ基準値との比較
    - 相対誤差計算
    - 許容範囲判定
    - 差分レポート生成
    """

    # デフォルト許容誤差（％）
    DEFAULT_TOLERANCES = {
        "faz_area_mm2": 5.0,  # ±5%
        "faz_perimeter_mm": 5.0,
        "faz_circularity": 3.0,  # ±3%
        "vessel_density": 2.0,  # ±2%
        "vessel_area_mm2": 5.0,
        "vd_superficial_overall": 2.0,
        "vd_deep_overall": 2.0,
        "skeleton_total_length_mm": 5.0,
        "skeleton_num_branches": 10.0,  # ±10%（離散値）
        "fractal_dimension": 5.0,
    }

    def __init__(
        self,
        custom_tolerances: Optional[Dict[str, float]] = None,
        strict_mode: bool = False,
    ):
        """
        初期化

        Parameters:
        -----------
        custom_tolerances : dict, optional
            カスタム許容誤差（メトリクス名 -> 許容誤差%）
        strict_mode : bool
            厳格モード（許容誤差を半分にする）
        """
        self.tolerances = self.DEFAULT_TOLERANCES.copy()

        if custom_tolerances:
            self.tolerances.update(custom_tolerances)

        if strict_mode:
            self.tolerances = {k: v / 2 for k, v in self.tolerances.items()}

        self.validation_results: List[ValidationResult] = []

    def compare_metric(
        self,
        metric_name: str,
        ariake_value: float,
        imagej_value: float,
        tolerance_percent: Optional[float] = None,
    ) -> ValidationResult:
        """
        単一メトリクスを比較

        Parameters:
        -----------
        metric_name : str
            メトリクス名
        ariake_value : float
            ARIAKE計算値
        imagej_value : float
            ImageJ基準値
        tolerance_percent : float, optional
            許容誤差（％）

        Returns:
        --------
        result : ValidationResult
            検証結果
        """
        # 許容誤差の決定
        if tolerance_percent is None:
            tolerance_percent = self.tolerances.get(metric_name, 10.0)

        # 差分計算
        difference = ariake_value - imagej_value

        # 相対誤差計算（ImageJ値を基準）
        if imagej_value != 0:
            relative_error_percent = abs(difference / imagej_value) * 100
        else:
            # ImageJ値が0の場合は絶対誤差で判定
            relative_error_percent = abs(difference) * 100

        # 許容範囲判定
        is_acceptable = relative_error_percent <= tolerance_percent

        result = ValidationResult(
            metric_name=metric_name,
            ariake_value=ariake_value,
            imagej_value=imagej_value,
            difference=difference,
            relative_error_percent=relative_error_percent,
            is_acceptable=is_acceptable,
            tolerance_percent=tolerance_percent,
        )

        self.validation_results.append(result)
        return result

    def compare_results(
        self,
        ariake_results: Dict,
        imagej_results: Dict,
        metrics_to_compare: Optional[List[str]] = None,
    ) -> Dict:
        """
        複数のメトリクスを一括比較

        Parameters:
        -----------
        ariake_results : dict
            ARIAKE解析結果
        imagej_results : dict
            ImageJ基準結果
        metrics_to_compare : list, optional
            比較するメトリクス名のリスト（Noneの場合は全て）

        Returns:
        --------
        summary : dict
            比較サマリー
        """
        self.validation_results.clear()

        # 比較するメトリクスの決定
        if metrics_to_compare is None:
            metrics_to_compare = list(
                set(ariake_results.keys()) & set(imagej_results.keys())
            )

        # 各メトリクスを比較
        for metric_name in metrics_to_compare:
            if metric_name in ariake_results and metric_name in imagej_results:
                ariake_val = ariake_results[metric_name]
                imagej_val = imagej_results[metric_name]

                # 数値型のみ比較
                if isinstance(ariake_val, (int, float, np.number)) and isinstance(
                    imagej_val, (int, float, np.number)
                ):
                    self.compare_metric(
                        metric_name, float(ariake_val), float(imagej_val)
                    )

        return self.generate_summary()

    def generate_summary(self) -> Dict:
        """
        検証サマリーを生成

        Returns:
        --------
        summary : dict
            検証結果のサマリー
        """
        if not self.validation_results:
            return {"error": "No validation results"}

        total_count = len(self.validation_results)
        acceptable_count = sum(1 for r in self.validation_results if r.is_acceptable)
        unacceptable_count = total_count - acceptable_count

        # 統計計算
        errors = [r.relative_error_percent for r in self.validation_results]

        summary = {
            "total_metrics": total_count,
            "acceptable_metrics": acceptable_count,
            "unacceptable_metrics": unacceptable_count,
            "pass_rate_percent": round(acceptable_count / total_count * 100, 2),
            "mean_error_percent": round(np.mean(errors), 2),
            "max_error_percent": round(max(errors), 2),
            "min_error_percent": round(min(errors), 2),
            "std_error_percent": round(np.std(errors), 2),
            "results": [r.to_dict() for r in self.validation_results],
        }

        return summary

    def print_report(self, show_all: bool = False):
        """
        検証レポートを表示

        Parameters:
        -----------
        show_all : bool
            全ての結果を表示するか（Falseの場合は不合格のみ）
        """
        summary = self.generate_summary()

        if "error" in summary:
            print(f"⚠️  {summary['error']}")
            return

        print("\n" + "=" * 80)
        print("🔬 ImageJ Compatibility Validation Report")
        print("=" * 80)

        # サマリー
        print("\n【Summary】")
        print(f"  Total metrics compared: {summary['total_metrics']}")
        print(f"  ✅ Acceptable: {summary['acceptable_metrics']}")
        print(f"  ❌ Unacceptable: {summary['unacceptable_metrics']}")
        print(f"  📊 Pass rate: {summary['pass_rate_percent']:.2f}%")
        print(f"  📈 Mean error: {summary['mean_error_percent']:.2f}%")
        print(f"  📈 Max error: {summary['max_error_percent']:.2f}%")

        # 詳細
        if show_all:
            print(f"\n【All Results】")
            print(
                f"{'Metric':<30} {'ARIAKE':<12} {'ImageJ':<12} {'Error%':<10} {'Status':<10}"
            )
            print("-" * 80)

            for result in self.validation_results:
                status = "✅ PASS" if result.is_acceptable else "❌ FAIL"
                print(
                    f"{result.metric_name:<30} "
                    f"{result.ariake_value:<12.6f} "
                    f"{result.imagej_value:<12.6f} "
                    f"{result.relative_error_percent:<10.2f} "
                    f"{status:<10}"
                )
        else:
            # 不合格のみ表示
            failed_results = [r for r in self.validation_results if not r.is_acceptable]
            if failed_results:
                print(f"\n【❌ Failed Metrics】")
                print(
                    f"{'Metric':<30} {'ARIAKE':<12} {'ImageJ':<12} {'Error%':<10} {'Tolerance%':<12}"
                )
                print("-" * 80)

                for result in failed_results:
                    print(
                        f"{result.metric_name:<30} "
                        f"{result.ariake_value:<12.6f} "
                        f"{result.imagej_value:<12.6f} "
                        f"{result.relative_error_percent:<10.2f} "
                        f"{result.tolerance_percent:<12.2f}"
                    )
            else:
                print(f"\n✅ All metrics passed validation!")

        print("\n" + "=" * 80)

    def save_report(self, filepath: str):
        """
        レポートをJSON形式で保存

        Parameters:
        -----------
        filepath : str
            保存先ファイルパス
        """
        summary = self.generate_summary()

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

    def is_compatible(self, threshold_percent: float = 90.0) -> bool:
        """
        ImageJとの互換性を判定

        Parameters:
        -----------
        threshold_percent : float
            合格閾値（％）

        Returns:
        --------
        is_compatible : bool
            互換性があるか
        """
        summary = self.generate_summary()
        if "error" in summary:
            return False

        return summary["pass_rate_percent"] >= threshold_percent

    def get_largest_discrepancies(self, n: int = 5) -> List[ValidationResult]:
        """
        最大の差異があるメトリクスを取得

        Parameters:
        -----------
        n : int
            取得する数

        Returns:
        --------
        results : list
            誤差の大きい順のリスト
        """
        sorted_results = sorted(
            self.validation_results,
            key=lambda r: r.relative_error_percent,
            reverse=True,
        )
        return sorted_results[:n]

    @staticmethod
    def load_imagej_baseline(filepath: str) -> Dict:
        """
        ImageJ基準値をファイルから読み込み

        Parameters:
        -----------
        filepath : str
            基準値ファイルパス（JSON形式）

        Returns:
        --------
        baseline : dict
            基準値辞書
        """
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def create_baseline_template() -> Dict:
        """
        ImageJ基準値のテンプレートを生成

        Returns:
        --------
        template : dict
            基準値テンプレート
        """
        return {
            "test_case_name": "Sample OCTA Image",
            "image_filename": "sample.tif",
            "pixel_size_mm": 0.003,
            "vd_metrics": {
                "faz_area_mm2": 0.0,
                "faz_perimeter_mm": 0.0,
                "faz_circularity": 0.0,
                "vd_superficial_overall": 0.0,
                "vd_deep_overall": 0.0,
            },
            "mnv_metrics": {
                "vessel_area_mm2": 0.0,
                "vessel_density_percent": 0.0,
                "skeleton_total_length_mm": 0.0,
                "skeleton_num_branches": 0,
                "skeleton_fractal_dimension": 0.0,
            },
            "notes": "Fill in ImageJ values here",
        }
