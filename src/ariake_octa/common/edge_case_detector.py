"""
Edge Case Detector for ARIAKE OCTA Analysis System

低品質画像、極端な血管密度、FAZ未検出などのエッジケースを自動検出します。

Author: GitHub Copilot
Version: 2.0.0-phase4
Date: 2026-01-22
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

import numpy as np


class SeverityLevel(Enum):
    """問題の重症度レベル"""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class EdgeCaseIssue:
    """エッジケース問題データクラス"""

    category: str
    severity: SeverityLevel
    message: str
    detected_value: float
    threshold: float
    recommendation: str
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """辞書に変換"""
        return {
            "category": self.category,
            "severity": self.severity.value,
            "message": self.message,
            "detected_value": round(self.detected_value, 4),
            "threshold": round(self.threshold, 4),
            "recommendation": self.recommendation,
            "metadata": self.metadata,
        }


class EdgeCaseDetector:
    """
    エッジケース検出クラス

    Features:
    - 画像品質評価
    - 血管密度異常検出
    - FAZ検出失敗チェック
    - メトリクス異常値検出
    - 推奨事項の自動生成
    """

    # 閾値定義
    THRESHOLDS = {
        # 画像品質
        "min_snr": 3.0,
        "max_snr": 50.0,
        "min_contrast": 0.1,
        "max_contrast": 1.0,
        "min_mean_intensity": 10.0,
        "max_mean_intensity": 250.0,
        # 血管密度（VD）
        "min_vd_superficial": 0.15,  # 15%
        "max_vd_superficial": 0.65,  # 65%
        "min_vd_deep": 0.10,
        "max_vd_deep": 0.60,
        # FAZ
        "min_faz_area": 0.10,  # mm²
        "max_faz_area": 1.50,  # mm²
        "min_faz_circularity": 0.50,
        # MNV血管密度
        "min_mnv_density": 0.01,  # 1%
        "max_mnv_density": 0.50,  # 50%
        "min_lesion_area": 0.01,  # mm²
        "max_lesion_area": 10.0,  # mm²
        # スケルトン
        "min_num_branches": 3,
        "max_num_branches": 500,
        "min_tortuosity": 1.0,
        "max_tortuosity": 3.0,
        "min_fractal_dimension": 1.0,
        "max_fractal_dimension": 2.0,
    }

    def __init__(self, strict_mode: bool = False):
        """
        初期化

        Parameters:
        -----------
        strict_mode : bool
            厳格モード（より厳しい閾値を適用）
        """
        self.strict_mode = strict_mode
        self.issues: List[EdgeCaseIssue] = []

        # 厳格モード時は閾値を調整
        if strict_mode:
            self.THRESHOLDS = self.THRESHOLDS.copy()
            self.THRESHOLDS["min_snr"] = 5.0
            self.THRESHOLDS["min_contrast"] = 0.15
            self.THRESHOLDS["min_vd_superficial"] = 0.20

    def check_image_quality(
        self, image: np.ndarray, quality_metrics: Dict
    ) -> List[EdgeCaseIssue]:
        """
        画像品質をチェック

        Parameters:
        -----------
        image : np.ndarray
            入力画像
        quality_metrics : dict
            品質メトリクス（SNR, contrast等）

        Returns:
        --------
        issues : list
            検出された問題のリスト
        """
        issues = []

        # SNRチェック
        if "snr" in quality_metrics:
            snr = quality_metrics["snr"]
            if snr < self.THRESHOLDS["min_snr"]:
                issues.append(
                    EdgeCaseIssue(
                        category="image_quality",
                        severity=SeverityLevel.WARNING,
                        message=f"Low SNR detected: {snr:.2f}",
                        detected_value=snr,
                        threshold=self.THRESHOLDS["min_snr"],
                        recommendation="画像品質が低い可能性があります。再撮影を検討してください。",
                    )
                )
            elif snr > self.THRESHOLDS["max_snr"]:
                issues.append(
                    EdgeCaseIssue(
                        category="image_quality",
                        severity=SeverityLevel.INFO,
                        message=f"Unusually high SNR: {snr:.2f}",
                        detected_value=snr,
                        threshold=self.THRESHOLDS["max_snr"],
                        recommendation="SNRが異常に高い値です。画像処理済みの可能性があります。",
                    )
                )

        # コントラストチェック
        if "contrast" in quality_metrics:
            contrast = quality_metrics["contrast"]
            if contrast < self.THRESHOLDS["min_contrast"]:
                issues.append(
                    EdgeCaseIssue(
                        category="image_quality",
                        severity=SeverityLevel.WARNING,
                        message=f"Low contrast: {contrast:.3f}",
                        detected_value=contrast,
                        threshold=self.THRESHOLDS["min_contrast"],
                        recommendation="コントラストが低いです。CLAHE強度を上げることを検討してください。",
                    )
                )

        # 平均輝度チェック
        mean_intensity = np.mean(image)
        if mean_intensity < self.THRESHOLDS["min_mean_intensity"]:
            issues.append(
                EdgeCaseIssue(
                    category="image_quality",
                    severity=SeverityLevel.ERROR,
                    message=f"Image too dark: mean={mean_intensity:.1f}",
                    detected_value=mean_intensity,
                    threshold=self.THRESHOLDS["min_mean_intensity"],
                    recommendation="画像が暗すぎます。露出補正または再撮影が必要です。",
                )
            )
        elif mean_intensity > self.THRESHOLDS["max_mean_intensity"]:
            issues.append(
                EdgeCaseIssue(
                    category="image_quality",
                    severity=SeverityLevel.ERROR,
                    message=f"Image too bright: mean={mean_intensity:.1f}",
                    detected_value=mean_intensity,
                    threshold=self.THRESHOLDS["max_mean_intensity"],
                    recommendation="画像が明るすぎます。露出補正または再撮影が必要です。",
                )
            )

        return issues

    def check_vd_metrics(self, vd_results: Dict) -> List[EdgeCaseIssue]:
        """
        VDメトリクスの異常をチェック

        Parameters:
        -----------
        vd_results : dict
            VD解析結果

        Returns:
        --------
        issues : list
            検出された問題のリスト
        """
        issues = []

        # Superficial VDチェック
        vd_sup = vd_results.get("vd_superficial_overall", 0)
        if vd_sup < self.THRESHOLDS["min_vd_superficial"]:
            issues.append(
                EdgeCaseIssue(
                    category="vessel_density",
                    severity=SeverityLevel.WARNING,
                    message=f"Very low superficial VD: {vd_sup*100:.1f}%",
                    detected_value=vd_sup,
                    threshold=self.THRESHOLDS["min_vd_superficial"],
                    recommendation="Superficial VDが極端に低いです。画像品質または病態を確認してください。",
                )
            )
        elif vd_sup > self.THRESHOLDS["max_vd_superficial"]:
            issues.append(
                EdgeCaseIssue(
                    category="vessel_density",
                    severity=SeverityLevel.WARNING,
                    message=f"Very high superficial VD: {vd_sup*100:.1f}%",
                    detected_value=vd_sup,
                    threshold=self.THRESHOLDS["max_vd_superficial"],
                    recommendation="Superficial VDが極端に高いです。二値化閾値を確認してください。",
                )
            )

        # Deep VDチェック
        vd_deep = vd_results.get("vd_deep_overall", 0)
        if vd_deep < self.THRESHOLDS["min_vd_deep"]:
            issues.append(
                EdgeCaseIssue(
                    category="vessel_density",
                    severity=SeverityLevel.WARNING,
                    message=f"Very low deep VD: {vd_deep*100:.1f}%",
                    detected_value=vd_deep,
                    threshold=self.THRESHOLDS["min_vd_deep"],
                    recommendation="Deep VDが極端に低いです。画像品質または病態を確認してください。",
                )
            )

        # FAZ検出チェック
        faz_area = vd_results.get("faz_area_mm2", 0)
        if faz_area == 0:
            issues.append(
                EdgeCaseIssue(
                    category="faz_detection",
                    severity=SeverityLevel.ERROR,
                    message="FAZ not detected",
                    detected_value=0.0,
                    threshold=self.THRESHOLDS["min_faz_area"],
                    recommendation="FAZが検出されませんでした。画像中心位置または品質を確認してください。",
                )
            )
        elif faz_area < self.THRESHOLDS["min_faz_area"]:
            issues.append(
                EdgeCaseIssue(
                    category="faz_detection",
                    severity=SeverityLevel.WARNING,
                    message=f"Very small FAZ: {faz_area:.3f} mm²",
                    detected_value=faz_area,
                    threshold=self.THRESHOLDS["min_faz_area"],
                    recommendation="FAZ面積が非常に小さいです。検出精度を確認してください。",
                )
            )
        elif faz_area > self.THRESHOLDS["max_faz_area"]:
            issues.append(
                EdgeCaseIssue(
                    category="faz_detection",
                    severity=SeverityLevel.WARNING,
                    message=f"Very large FAZ: {faz_area:.3f} mm²",
                    detected_value=faz_area,
                    threshold=self.THRESHOLDS["max_faz_area"],
                    recommendation="FAZ面積が非常に大きいです。病態進行の可能性があります。",
                )
            )

        # FAZ円形度チェック
        faz_circularity = vd_results.get("faz_circularity", 0)
        if 0 < faz_circularity < self.THRESHOLDS["min_faz_circularity"]:
            issues.append(
                EdgeCaseIssue(
                    category="faz_detection",
                    severity=SeverityLevel.INFO,
                    message=f"Low FAZ circularity: {faz_circularity:.3f}",
                    detected_value=faz_circularity,
                    threshold=self.THRESHOLDS["min_faz_circularity"],
                    recommendation="FAZの円形度が低いです。不規則な形状の可能性があります。",
                )
            )

        return issues

    def check_mnv_metrics(self, mnv_results: Dict) -> List[EdgeCaseIssue]:
        """
        MNVメトリクスの異常をチェック

        Parameters:
        -----------
        mnv_results : dict
            MNV解析結果

        Returns:
        --------
        issues : list
            検出された問題のリスト
        """
        issues = []

        # 血管密度チェック
        vessel_density = mnv_results.get("vessel_density_percent", 0) / 100.0
        if vessel_density < self.THRESHOLDS["min_mnv_density"]:
            issues.append(
                EdgeCaseIssue(
                    category="mnv_analysis",
                    severity=SeverityLevel.WARNING,
                    message=f"Very low MNV vessel density: {vessel_density*100:.2f}%",
                    detected_value=vessel_density,
                    threshold=self.THRESHOLDS["min_mnv_density"],
                    recommendation="MNV血管密度が極端に低いです。画像品質または検出閾値を確認してください。",
                )
            )
        elif vessel_density > self.THRESHOLDS["max_mnv_density"]:
            issues.append(
                EdgeCaseIssue(
                    category="mnv_analysis",
                    severity=SeverityLevel.WARNING,
                    message=f"Very high MNV vessel density: {vessel_density*100:.2f}%",
                    detected_value=vessel_density,
                    threshold=self.THRESHOLDS["max_mnv_density"],
                    recommendation="MNV血管密度が極端に高いです。二値化閾値を確認してください。",
                )
            )

        # 病変面積チェック
        lesion_area = mnv_results.get("lesion_area_mm2", 0)
        if lesion_area > 0:
            if lesion_area < self.THRESHOLDS["min_lesion_area"]:
                issues.append(
                    EdgeCaseIssue(
                        category="mnv_analysis",
                        severity=SeverityLevel.INFO,
                        message=f"Very small lesion: {lesion_area:.3f} mm²",
                        detected_value=lesion_area,
                        threshold=self.THRESHOLDS["min_lesion_area"],
                        recommendation="病変面積が非常に小さいです。早期病変の可能性があります。",
                    )
                )
            elif lesion_area > self.THRESHOLDS["max_lesion_area"]:
                issues.append(
                    EdgeCaseIssue(
                        category="mnv_analysis",
                        severity=SeverityLevel.WARNING,
                        message=f"Very large lesion: {lesion_area:.3f} mm²",
                        detected_value=lesion_area,
                        threshold=self.THRESHOLDS["max_lesion_area"],
                        recommendation="病変面積が非常に大きいです。進行病変の可能性があります。",
                    )
                )
        else:
            issues.append(
                EdgeCaseIssue(
                    category="mnv_analysis",
                    severity=SeverityLevel.ERROR,
                    message="No lesion detected",
                    detected_value=0.0,
                    threshold=self.THRESHOLDS["min_lesion_area"],
                    recommendation="MNV病変が検出されませんでした。画像品質または検出閾値を確認してください。",
                )
            )

        # スケルトン解析チェック
        num_branches = mnv_results.get("skeleton_num_branches", 0)
        if num_branches > 0:
            if num_branches < self.THRESHOLDS["min_num_branches"]:
                issues.append(
                    EdgeCaseIssue(
                        category="skeleton_analysis",
                        severity=SeverityLevel.INFO,
                        message=f"Very few branches: {num_branches}",
                        detected_value=num_branches,
                        threshold=self.THRESHOLDS["min_num_branches"],
                        recommendation="血管分岐が非常に少ないです。単純な血管構造の可能性があります。",
                    )
                )
            elif num_branches > self.THRESHOLDS["max_num_branches"]:
                issues.append(
                    EdgeCaseIssue(
                        category="skeleton_analysis",
                        severity=SeverityLevel.WARNING,
                        message=f"Too many branches: {num_branches}",
                        detected_value=num_branches,
                        threshold=self.THRESHOLDS["max_num_branches"],
                        recommendation="血管分岐が異常に多いです。ノイズまたは検出パラメータを確認してください。",
                    )
                )

        # トルトゥオシティチェック
        tortuosity = mnv_results.get("skeleton_tortuosity_mean", 0)
        if tortuosity > 0:
            if tortuosity > self.THRESHOLDS["max_tortuosity"]:
                issues.append(
                    EdgeCaseIssue(
                        category="skeleton_analysis",
                        severity=SeverityLevel.INFO,
                        message=f"High tortuosity: {tortuosity:.3f}",
                        detected_value=tortuosity,
                        threshold=self.THRESHOLDS["max_tortuosity"],
                        recommendation="血管の屈曲度が高いです。血管の蛇行が顕著です。",
                    )
                )

        # フラクタル次元チェック
        fractal_dim = mnv_results.get("skeleton_fractal_dimension", 0)
        if fractal_dim > 0:
            if fractal_dim < self.THRESHOLDS["min_fractal_dimension"]:
                issues.append(
                    EdgeCaseIssue(
                        category="skeleton_analysis",
                        severity=SeverityLevel.WARNING,
                        message=f"Unusual fractal dimension: {fractal_dim:.3f}",
                        detected_value=fractal_dim,
                        threshold=self.THRESHOLDS["min_fractal_dimension"],
                        recommendation="フラクタル次元が低すぎます。計算エラーの可能性があります。",
                    )
                )
            elif fractal_dim > self.THRESHOLDS["max_fractal_dimension"]:
                issues.append(
                    EdgeCaseIssue(
                        category="skeleton_analysis",
                        severity=SeverityLevel.WARNING,
                        message=f"Unusual fractal dimension: {fractal_dim:.3f}",
                        detected_value=fractal_dim,
                        threshold=self.THRESHOLDS["max_fractal_dimension"],
                        recommendation="フラクタル次元が高すぎます。計算エラーの可能性があります。",
                    )
                )

        return issues

    def detect_all(
        self,
        image: Optional[np.ndarray] = None,
        quality_metrics: Optional[Dict] = None,
        vd_results: Optional[Dict] = None,
        mnv_results: Optional[Dict] = None,
    ) -> Dict:
        """
        全てのエッジケースをチェック

        Parameters:
        -----------
        image : np.ndarray, optional
            入力画像
        quality_metrics : dict, optional
            品質メトリクス
        vd_results : dict, optional
            VD解析結果
        mnv_results : dict, optional
            MNV解析結果

        Returns:
        --------
        report : dict
            検出レポート
        """
        self.issues.clear()

        # 各種チェック実行
        if image is not None and quality_metrics is not None:
            self.issues.extend(self.check_image_quality(image, quality_metrics))

        if vd_results is not None:
            self.issues.extend(self.check_vd_metrics(vd_results))

        if mnv_results is not None:
            self.issues.extend(self.check_mnv_metrics(mnv_results))

        # レポート生成
        return self.generate_report()

    def generate_report(self) -> Dict:
        """
        検出レポートを生成

        Returns:
        --------
        report : dict
            問題の統計とリスト
        """
        # 重症度別に集計
        severity_counts = {"info": 0, "warning": 0, "error": 0, "critical": 0}

        for issue in self.issues:
            severity_counts[issue.severity.value] += 1

        # カテゴリ別に集計
        category_counts = {}
        for issue in self.issues:
            category_counts[issue.category] = category_counts.get(issue.category, 0) + 1

        return {
            "total_issues": len(self.issues),
            "severity_counts": severity_counts,
            "category_counts": category_counts,
            "has_critical": severity_counts["critical"] > 0,
            "has_error": severity_counts["error"] > 0,
            "issues": [issue.to_dict() for issue in self.issues],
        }

    def print_report(self):
        """レポートを表示"""
        report = self.generate_report()

        print("\n" + "=" * 70)
        print("🔍 Edge Case Detection Report")
        print("=" * 70)

        if report["total_issues"] == 0:
            print("✅ No issues detected - All metrics are within normal range")
            print("=" * 70)
            return

        # サマリー
        print("\n【Summary】")
        print(f"  Total issues: {report['total_issues']}")
        print(f"  Critical: {report['severity_counts']['critical']}")
        print(f"  Error: {report['severity_counts']['error']}")
        print(f"  Warning: {report['severity_counts']['warning']}")
        print(f"  Info: {report['severity_counts']['info']}")

        # 詳細
        print(f"\n【Details】")
        for i, issue_dict in enumerate(report["issues"], 1):
            severity_icon = {
                "info": "ℹ️",
                "warning": "⚠️",
                "error": "❌",
                "critical": "🔴",
            }
            icon = severity_icon[issue_dict["severity"]]

            print(f"\n  {i}. {icon} [{issue_dict['category'].upper()}]")
            print(f"     {issue_dict['message']}")
            print(
                f"     Detected: {issue_dict['detected_value']:.4f} | Threshold: {issue_dict['threshold']:.4f}"
            )
            print(f"     💡 {issue_dict['recommendation']}")

        print("\n" + "=" * 70)

    def get_critical_issues(self) -> List[EdgeCaseIssue]:
        """重大な問題のみを取得"""
        return [
            issue
            for issue in self.issues
            if issue.severity in [SeverityLevel.CRITICAL, SeverityLevel.ERROR]
        ]

    def is_acceptable(self) -> bool:
        """解析結果が許容範囲内か判定"""
        critical_count = sum(
            1 for issue in self.issues if issue.severity == SeverityLevel.CRITICAL
        )
        error_count = sum(
            1 for issue in self.issues if issue.severity == SeverityLevel.ERROR
        )

        # Critical または Error が2つ以上あれば不合格
        return (critical_count == 0) and (error_count < 2)
