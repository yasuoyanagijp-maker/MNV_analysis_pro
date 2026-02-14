"""
パターン分類モジュール
MNVサブタイプの分類とComplexity Score計算
"""

from typing import Dict, Optional, Tuple

import numpy as np

from .pattern_metrics import (
    calculate_complexity_from_components,
    calculate_trunk_distribution_score,
    load_mnv_classification_ref,
)


class ComplexityScorer:
    """
    Complexity Score計算クラス
    calculateComplexityScore に対応
    """

    @staticmethod
    def calculate(
        branch_density_center: float,
        branch_density_periphery: float,
        loop_density_center: float,
        loop_density_periphery: float,
        loops_center: int,
        loops_periphery: int,
        euler_center: int,
        euler_periphery: int,
        trunk_eccentricity: float,
        angular_cv: float,
        thick_vessel_center_ratio: float,
        diameter_ratio: float,
    ) -> Tuple[float, Dict]:
        """
        Complexity Scoreを計算（共通実装へ委譲）
        """
        return calculate_complexity_from_components(
            branch_density_center,
            branch_density_periphery,
            loop_density_center,
            loop_density_periphery,
            loops_center,
            loops_periphery,
            euler_center,
            euler_periphery,
            trunk_eccentricity,
            angular_cv,
            thick_vessel_center_ratio,
            diameter_ratio,
        )

    @staticmethod
    def _calculate_trunk_score(
        trunk_eccentricity: float,
        angular_cv: float,
        thick_vessel_center_ratio: float,
        diameter_ratio: float,
    ) -> float:
        """Delegate to common trunk distribution score."""
        return float(
            calculate_trunk_distribution_score(
                trunk_eccentricity,
                angular_cv,
                thick_vessel_center_ratio,
                diameter_ratio,
            )
        )


class MNVClassifier:
    """
    MNVサブタイプ分類クラス
    classifyMNVbyLoopsDetailed に対応
    """

    @staticmethod
    def classify(
        complexity_score: float,
        stability_score: float,
        trunk_pattern: str,
        suggested_pattern: Optional[str] = None,
    ) -> Dict[str, any]:
        """
        MNVサブタイプを分類

        Parameters:
        -----------
        complexity_score : float
            複雑性スコア
        stability_score : float
            安定性スコア
        trunk_pattern : str
            Trunkパターン（MEDUSA/INTERMEDIATE/SEAFAN）
        suggested_pattern : str, optional
            推奨パターン（ユーザー選択用）

        Returns:
        --------
        classification : dict
            'subtype': サブタイプ名
            'confidence': 信頼度（0-1）
            'maturity_index': 成熟度指数
            'suggested': 推奨パターン
        """
        # 推奨パターンを決定
        if complexity_score < 40 and stability_score > 85:
            suggested = "Dead tree"
        elif 40 <= complexity_score < 65:
            suggested = "Tree in bud"
        elif complexity_score >= 55 and trunk_pattern == "SEAFAN":
            suggested = "Seafan"
        elif complexity_score >= 75 and trunk_pattern == "MEDUSA":
            suggested = "Medusa"
        elif complexity_score >= 65:
            suggested = "Glomerular"
        elif trunk_pattern == "INTERMEDIATE":
            suggested = "Tree in bud"
        else:
            suggested = "Tree in bud"

        # ユーザー選択がある場合はそれを使用
        if suggested_pattern is not None:
            selected = suggested_pattern
        else:
            selected = suggested

        # 信頼度計算
        confidence = MNVClassifier._calculate_confidence(
            selected, complexity_score, stability_score, trunk_pattern
        )

        # 成熟度指数
        maturity_index = 50 + (stability_score - complexity_score) / 2
        maturity_index = np.clip(maturity_index, 0, 100)

        return {
            "subtype": selected,
            "confidence": confidence,
            "maturity_index": maturity_index,
            "suggested": suggested,
            "complexity_score": complexity_score,
            "stability_score": stability_score,
        }

    @staticmethod
    def _calculate_confidence(
        subtype: str,
        complexity_score: float,
        stability_score: float,
        trunk_pattern: str,
    ) -> float:
        """
        信頼度を計算

        Parameters:
        -----------
        subtype : str
            選択されたサブタイプ
        complexity_score : float
            複雑性スコア
        stability_score : float
            安定性スコア
        trunk_pattern : str
            Trunkパターン

        Returns:
        --------
        confidence : float
            信頼度（0-1）
        """
        confidence = 0.5  # デフォルト

        if subtype == "Dead tree":
            if complexity_score < 35 and stability_score > 85:
                confidence = 0.95
            elif complexity_score < 45 and stability_score > 80:
                confidence = 0.80
            elif complexity_score < 55:
                confidence = 0.65

        elif subtype == "Tree in bud":
            if 40 <= complexity_score < 65 and stability_score < 80:
                confidence = 0.90
            elif 35 <= complexity_score < 70:
                confidence = 0.75
            else:
                confidence = 0.60

        elif subtype == "Seafan":
            if trunk_pattern == "SEAFAN" and complexity_score >= 55:
                confidence = 0.95
            elif trunk_pattern == "INTERMEDIATE" and complexity_score >= 50:
                confidence = 0.80
            elif trunk_pattern == "SEAFAN":
                confidence = 0.70
            else:
                confidence = 0.60

        elif subtype == "Medusa":
            if trunk_pattern == "MEDUSA" and complexity_score >= 75:
                confidence = 0.95
            elif trunk_pattern == "MEDUSA" and complexity_score >= 70:
                confidence = 0.80
            elif complexity_score >= 65:
                confidence = 0.70
            else:
                confidence = 0.60

        elif subtype == "Glomerular":
            if complexity_score >= 65 and stability_score > 70:
                confidence = 0.90
            elif complexity_score >= 60:
                confidence = 0.75
            elif complexity_score >= 55:
                confidence = 0.65
            else:
                confidence = 0.55

        return confidence


def _ref_p(ref: Dict, metric: str, p: int, default: float = 0.0) -> float:
    """Get P{p} percentile for metric from ref, or default if missing.

    For percentiles not in JSON (e.g. P30), interpolates linearly between
    adjacent percentiles (P25, P40, etc.).
    """
    m = ref.get(metric)
    if not isinstance(m, dict):
        return default
    v = m.get(f"P{p}")
    if v is not None:
        return float(v)
    # Linear interpolation for percentiles not in JSON
    ps = [10, 25, 40, 50, 60, 65, 75, 90]
    vals = [m.get(f"P{x}") for x in ps]
    if any(v is None for v in vals):
        return default
    vals = [float(x) for x in vals]
    if p <= ps[0]:
        return vals[0]
    if p >= ps[-1]:
        return vals[-1]
    for i, px in enumerate(ps[:-1]):
        if px <= p <= ps[i + 1]:
            t = (p - px) / (ps[i + 1] - px)
            return vals[i] + t * (vals[i + 1] - vals[i])
    return default


def classify_morphology_final(
    complexity_score: float,
    stability_score: float,
    trunk_pattern: str,
    size_class: str,
    eccentricity: float = -1.0,
    radial_uniformity: float = -1.0,
    angular_cv: float = -1.0,
    suggested_pattern: Optional[str] = None,
) -> Optional[Dict[str, object]]:
    """Level 1 morphology classification using JSON reference percentiles.

    Order: Dead tree -> Medusa -> Seafan -> Glomerular -> Tree in bud.
    Dead tree: complexity < P10 (~10%). Medusa: MEDUSA + >=P65. Seafan: SEAFAN + >=P40.
    Glomerular: >=P30 (trunk-independent). Tree in bud: remainder (~15-25%).


    Returns:
        Dict compatible with MNVClassifier (subtype, confidence, maturity_index,
        suggested, complexity_score, stability_score). None if ref JSON not found.
    """
    ref = load_mnv_classification_ref(size_class)
    if ref is None:
        return None

    p10 = _ref_p(ref, "complexity_score", 10, 4.0)
    p30 = _ref_p(ref, "complexity_score", 30, 30.0)
    p40 = _ref_p(ref, "complexity_score", 40, 40.0)
    p60 = _ref_p(ref, "complexity_score", 60, 60.0)
    p65 = _ref_p(ref, "complexity_score", 65, 65.0)

    if complexity_score < p10:
        suggested = "Dead tree"
    elif trunk_pattern == "MEDUSA" and complexity_score >= p65:
        suggested = "Medusa"
    elif trunk_pattern == "SEAFAN" and complexity_score >= p40:
        suggested = "Seafan"
    elif complexity_score >= p30:
        suggested = "Glomerular"
    elif trunk_pattern == "INTERMEDIATE":
        suggested = "Tree in bud"
    else:
        suggested = "Tree in bud"

    selected = suggested_pattern if suggested_pattern is not None else suggested

    confidence = _confidence_morphology(
        selected, complexity_score, trunk_pattern, p10, p30, p40, p60, p65
    )
    maturity_index = 50 + (stability_score - complexity_score) / 2
    maturity_index = float(np.clip(maturity_index, 0, 100))

    return {
        "subtype": selected,
        "confidence": confidence,
        "maturity_index": maturity_index,
        "suggested": suggested,
        "complexity_score": complexity_score,
        "stability_score": stability_score,
    }


def _confidence_morphology(
    subtype: str,
    complexity_score: float,
    trunk_pattern: str,
    p10: float,
    p30: float,
    p40: float,
    p60: float,
    p65: float,
) -> float:
    """Confidence for Level 1 morphology (ref-based thresholds)."""
    if subtype == "Dead tree":
        if complexity_score < p10 * 0.9:
            return 0.95
        if complexity_score < p10:
            return 0.80
        return 0.65
    if subtype == "Tree in bud":
        return 0.75
    if subtype == "Seafan":
        if trunk_pattern == "SEAFAN" and complexity_score >= p40:
            return 0.95
        if trunk_pattern == "INTERMEDIATE" and complexity_score >= p40 * 0.9:
            return 0.80
        return 0.70
    if subtype == "Medusa":
        if trunk_pattern == "MEDUSA" and complexity_score >= p65:
            return 0.95
        if trunk_pattern == "MEDUSA" and complexity_score >= p65 * 0.9:
            return 0.80
        return 0.70
    if subtype == "Glomerular":
        if complexity_score >= p30:
            return 0.90
        return 0.75
    return 0.60


def check_arteriolarized(
    ref: Dict[str, object],
    segment_count: float,
    junction_density: float,
    loop_total: float,
    mean_diameter_um: float,
) -> bool:
    """Coscas-style arteriolarization: thick vessels, high segment/junction/loop.

    Returns True if multiple indicators exceed reference percentiles.
    """
    p50_art = _ref_p(ref, "arteriolarization_segment_count", 50, 200.0)
    p60_junc = _ref_p(ref, "junction_density", 60, 16.0)
    p60_loop = _ref_p(ref, "loop_total", 60, 60.0)
    p50_diam = _ref_p(ref, "mean_diameter_um", 50, 18.0)
    hits = 0
    if segment_count >= p50_art:
        hits += 1
    if junction_density >= p60_junc:
        hits += 1
    if loop_total >= p60_loop:
        hits += 1
    if mean_diameter_um >= p50_diam:
        hits += 1
    return hits >= 3


def classify_pathophysiology_final(
    maturity_index: float,
    stability_score: float,
    segment_count: float,
    junction_density: float,
    endpoint_density: float,
    loop_total: float,
    mean_diameter_um: float,
    cv_diameter: float,
    size_class: str,
    treatment_history: int = 0,
) -> Optional[str]:
    """Level 2 pathophysiology: Arteriolarized, Mature Quiescent, Active, Transitional.

    treatmentHistory=0: checkAbnormalized false, no treatment-induced Transitional.
    Returns None if ref JSON not found (caller may skip or use fallback).
    """
    ref = load_mnv_classification_ref(size_class)
    if ref is None:
        return None

    if check_arteriolarized(
        ref, segment_count, junction_density, loop_total, mean_diameter_um
    ):
        return "Arteriolarized"

    p25_m = _ref_p(ref, "maturity_index", 25, 25.0)
    p40_m = _ref_p(ref, "maturity_index", 40, 35.0)
    p75_m = _ref_p(ref, "maturity_index", 75, 45.0)
    p25_s = _ref_p(ref, "stability_score", 25, 25.0)
    p40_s = _ref_p(ref, "stability_score", 40, 40.0)
    p75_s = _ref_p(ref, "stability_score", 75, 60.0)

    if maturity_index >= p75_m and stability_score >= p75_s:
        return "Mature Quiescent"
    if maturity_index < p40_m or stability_score < p40_s:
        return "Active"
    return "Transitional"


# Morphology x Pathophysiology: invalid = logical contradiction
_INVALID_COMBINATIONS = frozenset(
    {
        ("Medusa", "Mature Quiescent"),
        ("Seafan", "Mature Quiescent"),
    }
)
_RARE_COMBINATIONS = frozenset(
    {
        ("Dead tree", "Arteriolarized"),
        ("Dead tree", "Active"),
    }
)


def validate_combination_final(
    morphology_subtype: str, pathophysiology: Optional[str]
) -> Dict[str, object]:
    """Level 3: validate morphology x pathophysiology combination.

    Returns dict with: status (valid|invalid|rare|typical), message.
    """
    if pathophysiology is None:
        return {"status": "valid", "message": ""}

    pair = (morphology_subtype, pathophysiology)
    if pair in _INVALID_COMBINATIONS:
        return {
            "status": "invalid",
            "message": f"{morphology_subtype} + {pathophysiology} is inconsistent",
        }
    if pair in _RARE_COMBINATIONS:
        return {
            "status": "rare",
            "message": f"{morphology_subtype} + {pathophysiology} is uncommon",
        }
    return {"status": "typical", "message": ""}


def compute_overall_confidence(
    subtype_confidence: float, validation_status: str
) -> float:
    """Adjust confidence by combination validation (Level 3)."""
    if validation_status == "invalid":
        return subtype_confidence * 0.5
    if validation_status == "rare":
        return subtype_confidence * 0.85
    return subtype_confidence
