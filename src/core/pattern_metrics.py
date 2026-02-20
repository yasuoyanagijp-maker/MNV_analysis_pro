"""
共通のパターン関連メトリクス実装
- trunk distribution
- complexity score (2種): from component parameters と from center/periphery metrics
- stability metrics
- vessel pattern classification

目標: `regional_analyzer` と `pattern_classifier` から呼べる共通実装
"""

import json
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np

_STABILITY_REF_SMALL: Optional[Dict[str, Dict[str, float]]] = None
_STABILITY_REF_SMALL_LOADED: bool = False
_STABILITY_REF_LARGE: Optional[Dict[str, Dict[str, float]]] = None
_STABILITY_REF_LARGE_LOADED: bool = False

_COMPLEXITY_REF_SMALL: Optional[Dict[str, object]] = None
_COMPLEXITY_REF_SMALL_LOADED: bool = False
_COMPLEXITY_REF_LARGE: Optional[Dict[str, object]] = None
_COMPLEXITY_REF_LARGE_LOADED: bool = False

_MNV_CLASSIFICATION_REF_SMALL: Optional[Dict[str, object]] = None
_MNV_CLASSIFICATION_REF_SMALL_LOADED: bool = False
_MNV_CLASSIFICATION_REF_LARGE: Optional[Dict[str, object]] = None
_MNV_CLASSIFICATION_REF_LARGE_LOADED: bool = False
_MNV_CLASSIFICATION_REF_SMALL_3MM: Optional[Dict[str, object]] = None
_MNV_CLASSIFICATION_REF_SMALL_3MM_LOADED: bool = False

_STABILITY_REF_SMALL_3MM: Optional[Dict[str, Dict[str, float]]] = None
_STABILITY_REF_SMALL_3MM_LOADED: bool = False
_COMPLEXITY_REF_SMALL_3MM: Optional[Dict[str, object]] = None
_COMPLEXITY_REF_SMALL_3MM_LOADED: bool = False


def _iter_reference_json_candidates(filename: str):
    """Yield candidate JSON paths in preferred order.

    Preferred: resources/reference_metrics (stable, not run output)
    Fallback: output (legacy location for backward compatibility)
    """
    project_root = Path(__file__).resolve().parents[2]
    yield project_root / "resources" / "reference_metrics" / filename
    yield project_root / "output" / filename


def _load_reference_json(filename: str) -> Optional[Dict[str, object]]:
    """Load first available reference JSON from known locations."""
    for json_path in _iter_reference_json_candidates(filename):
        if not json_path.exists():
            continue
        try:
            with json_path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            continue
    return None


def _load_stability_ref_small() -> Optional[Dict[str, Dict[str, float]]]:
    """Load stability reference (mu/sigma) for small images from JSON if available."""
    global _STABILITY_REF_SMALL, _STABILITY_REF_SMALL_LOADED

    if _STABILITY_REF_SMALL_LOADED:
        return _STABILITY_REF_SMALL

    _STABILITY_REF_SMALL_LOADED = True
    try:
        data = _load_reference_json("stability_ref_small.json")
        if data is None:
            _STABILITY_REF_SMALL = None
            return None

        mapping: Dict[str, Dict[str, float]] = {}
        key_map = {
            "stab_cv": "cv",
            "stab_mean_adjacent_change": "mean_adjacent_change",
            "stab_residual_cv": "residual_cv",
            "stab_range_percent": "range_percent",
        }
        for json_key, metric_key in key_map.items():
            if json_key not in data:
                continue
            entry = data[json_key]
            mu = float(entry.get("mu", 0.0))
            sigma = float(entry.get("sigma", 0.0))
            mapping[metric_key] = {"mu": mu, "sigma": sigma}

        _STABILITY_REF_SMALL = mapping if mapping else None
    except Exception:
        _STABILITY_REF_SMALL = None

    return _STABILITY_REF_SMALL


def _load_stability_ref_large() -> Optional[Dict[str, Dict[str, float]]]:
    """Load stability reference (mu/sigma) for large images from JSON if available."""
    global _STABILITY_REF_LARGE, _STABILITY_REF_LARGE_LOADED

    if _STABILITY_REF_LARGE_LOADED:
        return _STABILITY_REF_LARGE

    _STABILITY_REF_LARGE_LOADED = True
    try:
        data = _load_reference_json("stability_ref_large.json")
        if data is None:
            _STABILITY_REF_LARGE = None
            return None

        mapping: Dict[str, Dict[str, float]] = {}
        key_map = {
            "stab_cv": "cv",
            "stab_mean_adjacent_change": "mean_adjacent_change",
            "stab_residual_cv": "residual_cv",
            "stab_range_percent": "range_percent",
        }
        for json_key, metric_key in key_map.items():
            if json_key not in data:
                continue
            entry = data[json_key]
            mu = float(entry.get("mu", 0.0))
            sigma = float(entry.get("sigma", 0.0))
            mapping[metric_key] = {"mu": mu, "sigma": sigma}

        _STABILITY_REF_LARGE = mapping if mapping else None
    except Exception:
        _STABILITY_REF_LARGE = None

    return _STABILITY_REF_LARGE


def _load_stability_ref_small_3mm() -> Optional[Dict[str, Dict[str, float]]]:
    """Load stability reference for 3mm images from JSON if available."""
    global _STABILITY_REF_SMALL_3MM, _STABILITY_REF_SMALL_3MM_LOADED

    if _STABILITY_REF_SMALL_3MM_LOADED:
        return _STABILITY_REF_SMALL_3MM

    _STABILITY_REF_SMALL_3MM_LOADED = True
    try:
        data = _load_reference_json("stability_ref_small_3mm.json")
        if data is None:
            _STABILITY_REF_SMALL_3MM = None
            return None

        mapping: Dict[str, Dict[str, float]] = {}
        key_map = {
            "stab_cv": "cv",
            "stab_mean_adjacent_change": "mean_adjacent_change",
            "stab_residual_cv": "residual_cv",
            "stab_range_percent": "range_percent",
        }
        for json_key, metric_key in key_map.items():
            if json_key not in data:
                continue
            entry = data[json_key]
            mu = float(entry.get("mu", 0.0))
            sigma = float(entry.get("sigma", 0.0))
            mapping[metric_key] = {"mu": mu, "sigma": sigma}

        _STABILITY_REF_SMALL_3MM = mapping if mapping else None
    except Exception:
        _STABILITY_REF_SMALL_3MM = None

    return _STABILITY_REF_SMALL_3MM


def _load_complexity_ref_small() -> Optional[Dict[str, object]]:
    """Load PCA reference for complexity metrics (small images) from JSON."""
    global _COMPLEXITY_REF_SMALL, _COMPLEXITY_REF_SMALL_LOADED

    if _COMPLEXITY_REF_SMALL_LOADED:
        return _COMPLEXITY_REF_SMALL

    _COMPLEXITY_REF_SMALL_LOADED = True
    try:
        data = _load_reference_json("complexity_ref_small.json")
        if data is None:
            _COMPLEXITY_REF_SMALL = None
            return None

        _COMPLEXITY_REF_SMALL = data
    except Exception:
        _COMPLEXITY_REF_SMALL = None

    return _COMPLEXITY_REF_SMALL


def _load_complexity_ref_large() -> Optional[Dict[str, object]]:
    """Load PCA reference for complexity metrics (large images) from JSON."""
    global _COMPLEXITY_REF_LARGE, _COMPLEXITY_REF_LARGE_LOADED

    if _COMPLEXITY_REF_LARGE_LOADED:
        return _COMPLEXITY_REF_LARGE

    _COMPLEXITY_REF_LARGE_LOADED = True
    try:
        data = _load_reference_json("complexity_ref_large.json")
        if data is None:
            _COMPLEXITY_REF_LARGE = None
            return None

        _COMPLEXITY_REF_LARGE = data
    except Exception:
        _COMPLEXITY_REF_LARGE = None

    return _COMPLEXITY_REF_LARGE


def _load_complexity_ref_small_3mm() -> Optional[Dict[str, object]]:
    """Load PCA reference for complexity (3mm images) from JSON."""
    global _COMPLEXITY_REF_SMALL_3MM, _COMPLEXITY_REF_SMALL_3MM_LOADED

    if _COMPLEXITY_REF_SMALL_3MM_LOADED:
        return _COMPLEXITY_REF_SMALL_3MM

    _COMPLEXITY_REF_SMALL_3MM_LOADED = True
    try:
        data = _load_reference_json("complexity_ref_small_3mm.json")
        _COMPLEXITY_REF_SMALL_3MM = data
    except Exception:
        _COMPLEXITY_REF_SMALL_3MM = None

    return _COMPLEXITY_REF_SMALL_3MM


def load_mnv_classification_ref(size_class: str) -> Optional[Dict[str, object]]:
    """Load MNV classification reference (percentiles) for Level 1/2/3 classification.

    Returns JSON with per-metric percentiles (P10, P25, P40, P50, P60, P65, P75, P90).
    Used by classifyMorphology_Final and classifyPathophysiology_Final.

    Args:
        size_class: "small_3mm" (user scale 3mm), "small" (image width < 800px), or "large" (>= 800px)

    Returns:
        Dict with keys: size_class, n_cases, percentiles, plus per-metric
        percentile dicts (e.g. complexity_score, stability_score, junction_density).
        None if JSON not found (caller should fallback to existing MNVClassifier).
    """
    global _MNV_CLASSIFICATION_REF_SMALL, _MNV_CLASSIFICATION_REF_SMALL_LOADED
    global _MNV_CLASSIFICATION_REF_LARGE, _MNV_CLASSIFICATION_REF_LARGE_LOADED
    global _MNV_CLASSIFICATION_REF_SMALL_3MM, _MNV_CLASSIFICATION_REF_SMALL_3MM_LOADED

    if size_class == "small_3mm":
        if _MNV_CLASSIFICATION_REF_SMALL_3MM_LOADED:
            return _MNV_CLASSIFICATION_REF_SMALL_3MM
        _MNV_CLASSIFICATION_REF_SMALL_3MM_LOADED = True
        try:
            data = _load_reference_json("mnv_classification_ref_small_3mm.json")
            _MNV_CLASSIFICATION_REF_SMALL_3MM = data
        except Exception:
            _MNV_CLASSIFICATION_REF_SMALL_3MM = None
        return _MNV_CLASSIFICATION_REF_SMALL_3MM

    if size_class == "small":
        if _MNV_CLASSIFICATION_REF_SMALL_LOADED:
            return _MNV_CLASSIFICATION_REF_SMALL
        _MNV_CLASSIFICATION_REF_SMALL_LOADED = True
        try:
            data = _load_reference_json("mnv_classification_ref_small.json")
            _MNV_CLASSIFICATION_REF_SMALL = data
        except Exception:
            _MNV_CLASSIFICATION_REF_SMALL = None
        return _MNV_CLASSIFICATION_REF_SMALL

    if size_class == "large":
        if _MNV_CLASSIFICATION_REF_LARGE_LOADED:
            return _MNV_CLASSIFICATION_REF_LARGE
        _MNV_CLASSIFICATION_REF_LARGE_LOADED = True
        try:
            data = _load_reference_json("mnv_classification_ref_large.json")
            _MNV_CLASSIFICATION_REF_LARGE = data
        except Exception:
            _MNV_CLASSIFICATION_REF_LARGE = None
        return _MNV_CLASSIFICATION_REF_LARGE

    return None


# Cap for adjacent-bin relative change (%) to avoid explosion when a bin is ~0
_MAX_ADJACENT_CHANGE_PERCENT = 1000.0


def _compute_stability_raw(diameters: np.ndarray) -> Dict[str, float]:
    """Compute raw stability-related metrics from a radial diameter profile."""
    diameters = np.asarray(diameters, dtype=float)
    n = diameters.size

    if n == 0:
        return {
            "n": 0.0,
            "mean": 0.0,
            "sd": 0.0,
            "cv": 0.0,
            "mean_adjacent_change": 0.0,
            "reversal_count": 0.0,
            "max_reversal_magnitude": 0.0,
            "residual_cv": 0.0,
            "range_percent": 0.0,
        }

    mean = float(np.mean(diameters))
    var = float(np.mean((diameters - mean) ** 2))
    sd = float(np.sqrt(var))
    cv = (sd / mean) * 100.0 if mean > 0.0 else 100.0

    if n > 1:
        # Safe denominator: avoid division by near-zero (empty bins -> 0 um)
        denom = np.maximum(diameters[:-1], max(mean * 0.01, 0.01))
        adjacent_changes = np.abs(np.diff(diameters)) / denom * 100.0
        adjacent_changes = np.minimum(adjacent_changes, _MAX_ADJACENT_CHANGE_PERCENT)
        mean_adjacent_change = float(np.mean(adjacent_changes))
    else:
        mean_adjacent_change = 0.0

    reversal_count = 0.0
    max_reversal_magnitude = 0.0
    for i in range(n - 1):
        if diameters[i + 1] < diameters[i]:
            reversal_count += 1.0
            denom_i = max(diameters[i], mean * 0.01, 0.01)
            magnitude = (diameters[i] - diameters[i + 1]) / denom_i * 100.0
            magnitude = min(magnitude, _MAX_ADJACENT_CHANGE_PERCENT)
            if magnitude > max_reversal_magnitude:
                max_reversal_magnitude = magnitude

    if n > 1:
        x = np.arange(n, dtype=float)
        coef = np.polyfit(x, diameters, 1)
        predicted = np.polyval(coef, x)
        residuals = diameters - predicted
        residual_sd = float(np.sqrt(np.mean(residuals**2)))
        residual_cv = residual_sd / (np.mean(np.abs(predicted)) + 1e-12) * 100.0
    else:
        residual_cv = 0.0

    min_d = float(np.min(diameters))
    max_d = float(np.max(diameters))
    range_val = max_d - min_d
    range_percent = (range_val / (mean + 1e-12)) * 100.0 if mean > 0.0 else 0.0

    return {
        "n": float(n),
        "mean": mean,
        "sd": sd,
        "cv": cv,
        "mean_adjacent_change": mean_adjacent_change,
        "reversal_count": reversal_count,
        "max_reversal_magnitude": max_reversal_magnitude,
        "residual_cv": residual_cv,
        "range_percent": range_percent,
    }


def calculate_trunk_distribution_score(
    trunk_ecc: float,
    angular_cv: float,
    thick_center_ratio: float,
    diameter_ratio: float,
) -> float:
    """
    Compute trunk distribution score (0-100)
    Logic ported from `regional_analyzer.calculate_trunk_distribution_score` / `_calculate_trunk_score`.
    """
    if trunk_ecc < 0 or angular_cv < 0:
        return 50.0

    centralityScore = 100.0 * (1.0 - trunk_ecc)
    radialityScore = 100.0 * np.exp(-angular_cv * 2.0)

    centralDensityBonus = 0.0
    if thick_center_ratio > 15.0:
        centralDensityBonus = 20.0
    elif thick_center_ratio > 10.0:
        centralDensityBonus = 10.0

    if diameter_ratio > 1.0 and diameter_ratio < 1.5:
        diameterUniformity = 100.0 * (1.5 - diameter_ratio) / 0.5
    elif diameter_ratio >= 1.5:
        diameterUniformity = 0.0
    else:
        diameterUniformity = 50.0

    trunkDistributionScore = (
        centralityScore * 0.40
        + radialityScore * 0.30
        + diameterUniformity * 0.20
        + centralDensityBonus * 0.10
    )

    trunkDistributionScore = float(np.clip(trunkDistributionScore, 0.0, 100.0))
    return trunkDistributionScore


def calculate_stability_metrics(
    diameters: np.ndarray,
    size_class: str = "small",
) -> float:
    """Compute stability score (0-100) for diameter profile."""
    diameters = np.asarray(diameters, dtype=float)
    if diameters.size == 0:
        return 0.0

    raw = _compute_stability_raw(diameters)

    # Preserve legacy behavior for perfectly constant arrays (existing tests rely on this).
    # For a truly constant profile, the standard deviation is exactly zero.
    if raw.get("sd", 0.0) == 0.0:
        return 100.0

    # Z-score + sigmoid mapping when reference stats are available.
    ref = None
    if size_class == "small_3mm":
        ref = _load_stability_ref_small_3mm()
    elif size_class == "small":
        ref = _load_stability_ref_small()
    elif size_class == "large":
        ref = _load_stability_ref_large()

    if ref is not None:

        def _z(x: float, mu: float, sigma: float) -> float:
            if sigma <= 0.0:
                return 0.0
            return (x - mu) / sigma

        def _sigmoid_score(z_val: float, alpha: float = 1.0, z0: float = 0.0) -> float:
            # Larger z (worse than mean) should reduce the score.
            return 100.0 / (1.0 + float(np.exp(alpha * (z_val - z0))))

        z_cv = _z(
            raw["cv"],
            ref.get("cv", {}).get("mu", 0.0),
            ref.get("cv", {}).get("sigma", 0.0),
        )
        z_adj = _z(
            raw["mean_adjacent_change"],
            ref.get("mean_adjacent_change", {}).get("mu", 0.0),
            ref.get("mean_adjacent_change", {}).get("sigma", 0.0),
        )
        z_res = _z(
            raw["residual_cv"],
            ref.get("residual_cv", {}).get("mu", 0.0),
            ref.get("residual_cv", {}).get("sigma", 0.0),
        )
        z_rng = _z(
            raw["range_percent"],
            ref.get("range_percent", {}).get("mu", 0.0),
            ref.get("range_percent", {}).get("sigma", 0.0),
        )

        cvScore = _sigmoid_score(z_cv)
        adjacentScore = _sigmoid_score(z_adj)
        residualScore = _sigmoid_score(z_res)
        rangeScore = _sigmoid_score(z_rng)

        compositeScore = 0.25 * (cvScore + adjacentScore + residualScore + rangeScore)
        return float(np.clip(compositeScore, 0.0, 100.0))

    # Fallback: legacy composite score (when reference stats are not available).
    mean = raw["mean"]
    sd = raw["sd"]
    cv = raw["cv"]
    mean_adjacent_change = raw["mean_adjacent_change"]
    residual_cv = raw["residual_cv"]
    range_percent = raw["range_percent"]
    reversal_count = raw["reversal_count"]
    max_reversal_magnitude = raw["max_reversal_magnitude"]

    cvScore = 100.0 - cv * 3.0
    if cvScore < 0.0:
        cvScore = 0.0

    expScore = 100.0 * np.exp(-sd / (mean + 1e-12))
    adjacentScore = 100.0 / (1.0 + mean_adjacent_change / 10.0)

    residualScore = 100.0 - residual_cv * 5.0
    if residualScore < 0.0:
        residualScore = 0.0

    reversalPenalty = reversal_count * 10.0 + max_reversal_magnitude * 2.0
    reversalScore = 100.0 - reversalPenalty
    if reversalScore < 0.0:
        reversalScore = 0.0

    rangeScore = 100.0 - range_percent * 2.0
    if rangeScore < 0.0:
        rangeScore = 0.0

    compositeScore = (
        cvScore * 0.20
        + expScore * 0.15
        + adjacentScore * 0.20
        + residualScore * 0.20
        + reversalScore * 0.15
        + rangeScore * 0.10
    )

    compositeScore = float(np.clip(compositeScore, 0.0, 100.0))
    return compositeScore


def classify_vessel_pattern(
    trunk_eccentricity: float,
    radial_uniformity: float,
    thick_center_ratio: float,
    diameter_ratio: float,
) -> Tuple[str, float]:
    """Return (pattern_name, total_score) following RegionalAnalyzer logic."""
    # Tier 1
    if trunk_eccentricity < 0.20:
        tier1 = 0
    elif trunk_eccentricity < 0.35:
        tier1 = 15
    elif trunk_eccentricity < 0.50:
        tier1 = 25
    else:
        tier1 = 40

    # Tier 2
    if radial_uniformity > 0.75:
        tier2 = 0
    elif radial_uniformity > 0.60:
        tier2 = 10
    elif radial_uniformity > 0.40:
        tier2 = 20
    else:
        tier2 = 30

    # Tier 3
    if thick_center_ratio > 15:
        tier3 = 0
    elif thick_center_ratio > 10:
        tier3 = 7
    elif thick_center_ratio > 5:
        tier3 = 13
    else:
        tier3 = 20

    # Tier 4
    if diameter_ratio > 1.4:
        tier4 = 0
    elif diameter_ratio > 1.2:
        tier4 = 3
    elif diameter_ratio > 1.0:
        tier4 = 7
    else:
        tier4 = 10

    totalScore = tier1 + tier2 + tier3 + tier4

    if totalScore < 30:
        pattern = "MEDUSA"
    elif totalScore < 60:
        pattern = "INTERMEDIATE"
    else:
        pattern = "SEAFAN"

    return pattern, float(totalScore)


def calculate_complexity_score_from_metrics(
    center_metrics: Dict,
    periphery_metrics: Dict,
    trunk_ecc: float,
    angular_cv: float,
) -> float:
    """Compute complexity score using center/periphery metrics (RegionalAnalyzer style)."""
    loops_center = int(center_metrics.get("n_loops", 0))
    loops_periphery = int(periphery_metrics.get("n_loops", 0))
    totalLoops = max(0, loops_center + loops_periphery)

    center_branches = int(center_metrics.get("count", 0))
    periphery_branches = int(periphery_metrics.get("count", 0))
    totalBranches = center_branches + periphery_branches

    # numeric safety
    totalLoopsScore = 100.0 * (1.0 - np.exp(-float(max(0, totalLoops)) / 80.0))

    euler_c = float(center_metrics.get("euler_number", 0))
    euler_p = float(periphery_metrics.get("euler_number", 0))
    avgEuler = (euler_c + euler_p) / 2.0
    eulerComplexity = max(0.0, -avgEuler)
    eulerScore = 100.0 * (1.0 - np.exp(-eulerComplexity / 30.0))

    loopDensityCenter = (
        loops_center / (center_metrics.get("total_length_mm", 1e-12))
        if center_metrics.get("total_length_mm", 0) > 0
        else 0.0
    )
    loopDensityPeriphery = (
        loops_periphery / (periphery_metrics.get("total_length_mm", 1e-12))
        if periphery_metrics.get("total_length_mm", 0) > 0
        else 0.0
    )
    # numeric safety: clamp
    if not np.isfinite(loopDensityCenter) or loopDensityCenter < 0.0:
        loopDensityCenter = 0.0
    if not np.isfinite(loopDensityPeriphery) or loopDensityPeriphery < 0.0:
        loopDensityPeriphery = 0.0

    cpLoopRatio = loopDensityCenter / (loopDensityPeriphery + 1e-12)
    cpBranchRatio = center_branches / (periphery_branches + 1e-12)
    loopRatioDeviation = abs(cpLoopRatio - 1.0)
    branchRatioDeviation = abs(cpBranchRatio - 1.0)
    avgDev = 0.5 * (loopRatioDeviation + branchRatioDeviation)
    spatialScore = 100.0 * np.exp(-avgDev * 2.0)

    anastomoticIndex = totalLoops / (totalBranches + 1.0)
    anastomoticScore = 100.0 * (1.0 - np.exp(-anastomoticIndex / 0.3))

    avgBranchDensity = (center_branches + periphery_branches) / max(1.0, totalBranches)
    branchDensityScore = 100.0 * (1.0 - np.exp(-avgBranchDensity / 15.0))

    trunkDist = calculate_trunk_distribution_score(
        trunk_ecc,
        angular_cv,
        float(center_metrics.get("thick_center_ratio", 0.0)),
        float(center_metrics.get("diameter_ratio", 1.0)),
    )

    complexityScore = (
        totalLoopsScore * 0.30
        + eulerScore * 0.30
        + trunkDist * 0.20
        + spatialScore * 0.12
        + anastomoticScore * 0.05
        + branchDensityScore * 0.03
    )

    if totalLoops > 150 and branchDensityScore < 50.0:
        complexityScore = max(complexityScore, 80.0)
    if eulerScore > 85.0:
        complexityScore = max(complexityScore, 80.0)
    if (
        trunk_ecc >= 0
        and trunk_ecc < 0.3
        and totalLoops > 100
        and angular_cv >= 0
        and angular_cv < 0.5
    ):
        complexityScore = max(complexityScore, 85.0)
    if trunk_ecc >= 0 and trunk_ecc > 0.6 and totalLoops > 120:
        complexityScore = max(complexityScore, 75.0)
    if totalLoops < 10 and eulerScore < 20.0:
        complexityScore = min(complexityScore, 25.0)

    complexityScore = float(np.clip(complexityScore, 0.0, 100.0))
    return complexityScore


def calculate_complexity_from_components(
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
    """Compatibility wrapper for `ComplexityScorer.calculate` signature."""
    avg_branch_density = (branch_density_center + branch_density_periphery) / 2.0
    branch_density_score = 100.0 * (1.0 - np.exp(-avg_branch_density / 15.0))
    branch_density_score = min(100.0, branch_density_score)

    avg_loop_density = (loop_density_center + loop_density_periphery) / 2.0
    # clamp non-finite or negative densities to zero for numerical stability
    if not np.isfinite(avg_loop_density) or avg_loop_density < 0.0:
        avg_loop_density = 0.0
    loop_density_score = 100.0 * (1.0 - np.exp(-avg_loop_density / 4.0))
    loop_density_score = min(100.0, loop_density_score)

    total_loops = int(loops_center + loops_periphery)
    total_loops = max(0, total_loops)
    total_loops_score = 100.0 * (1.0 - np.exp(-total_loops / 80.0))
    total_loops_score = min(100.0, total_loops_score)

    avg_euler = (euler_center + euler_periphery) / 2.0
    euler_complexity = -avg_euler
    euler_score = 100.0 * (1.0 - np.exp(-euler_complexity / 30.0))
    euler_score = max(0.0, min(100.0, euler_score))

    cp_loop_ratio = loop_density_center / (loop_density_periphery + 0.0001)
    cp_branch_ratio = branch_density_center / (branch_density_periphery + 0.0001)
    loop_ratio_deviation = abs(cp_loop_ratio - 1.0)
    branch_ratio_deviation = abs(cp_branch_ratio - 1.0)
    avg_deviation = (loop_ratio_deviation + branch_ratio_deviation) / 2.0
    spatial_score = 100.0 * np.exp(-avg_deviation * 2.0)

    total_branches = 1.0
    if total_loops > 0 and total_branches > 0:
        anastomotic_index = total_loops / total_branches
        anastomotic_score = 100.0 * (1.0 - np.exp(-anastomotic_index / 0.3))
        anastomotic_score = min(100.0, anastomotic_score)
    else:
        anastomotic_score = 0.0

    trunk_distribution_score = calculate_trunk_distribution_score(
        trunk_eccentricity,
        angular_cv,
        thick_vessel_center_ratio,
        diameter_ratio,
    )

    complexity_score = (
        total_loops_score * 0.30
        + euler_score * 0.30
        + trunk_distribution_score * 0.20
        + spatial_score * 0.12
        + anastomotic_score * 0.05
        + branch_density_score * 0.03
    )

    complexity_score = float(np.clip(complexity_score, 0.0, 100.0))

    if total_loops > 150 and branch_density_score < 50:
        complexity_score = max(complexity_score, 80.0)
    if euler_score > 85:
        complexity_score = max(complexity_score, 80.0)
    if trunk_eccentricity >= 0 and trunk_eccentricity < 0.3 and total_loops > 100:
        if angular_cv >= 0 and angular_cv < 0.5:
            complexity_score = max(complexity_score, 85.0)
    if trunk_eccentricity >= 0 and trunk_eccentricity > 0.6 and total_loops > 120:
        complexity_score = max(complexity_score, 75.0)
    if total_loops < 10 and euler_score < 20:
        complexity_score = min(complexity_score, 25.0)

    complexity_score = float(np.clip(complexity_score, 0.0, 100.0))

    details = {
        "branch_density_score": branch_density_score,
        "loop_density_score": loop_density_score,
        "total_loops_score": total_loops_score,
        "euler_score": euler_score,
        "spatial_score": spatial_score,
        "anastomotic_score": anastomotic_score,
        "trunk_distribution_score": trunk_distribution_score,
    }

    return complexity_score, details


def calculate_complexity_pca(
    *,
    euler_center: float,
    euler_periphery: float,
    loop_total: float,
    junction_density: float,
    tortuosity_center: float,
    tortuosity_periphery: float,
    fd_global: float,
    trunk_score: float,
    size_class: str = "small",
) -> float:
    """Compute PCA-based vascular complexity score (0-100).

    This uses:
      - Z-score normalization based on `complexity_ref_*.json`
      - PCA weights (PC1/PC2) estimated from reference data
      - Sigmoid mapping of PC1/PC2 to 0-100
      - Linear combination of PC1 score, PC2 score, and trunk score
    """
    if size_class == "small_3mm":
        ref = _load_complexity_ref_small_3mm()
    elif size_class == "small":
        ref = _load_complexity_ref_small()
    elif size_class == "large":
        ref = _load_complexity_ref_large()
    else:
        ref = None

    if ref is None:
        # Fallback: if reference is unavailable, return trunk score as a
        # conservative placeholder rather than raising.
        return float(np.clip(trunk_score, 0.0, 100.0))

    mu: Dict[str, float] = ref.get("mu", {})
    sigma: Dict[str, float] = ref.get("sigma", {})
    pc1_w: Dict[str, float] = ref.get("pc1_weights", {})
    pc2_w: Dict[str, float] = ref.get("pc2_weights", {})
    final_w: Dict[str, float] = ref.get("final_weights", {})

    # All possible features (from pipeline args). Ref may use a subset via ref["metrics"].
    euler_total = float(euler_center + euler_periphery)
    euler_total_inv = float(-(euler_center + euler_periphery))
    all_features = {
        "euler_total": euler_total,
        "euler_total_inv": euler_total_inv,
        "loop_total": float(loop_total),
        "junction_density": float(junction_density),
        "tortuosity_center": float(tortuosity_center),
        "tortuosity_periphery": float(tortuosity_periphery),
        "FD_global": float(fd_global),
    }
    metric_names = ref.get("metrics")
    if isinstance(metric_names, (list, tuple)) and len(metric_names) > 0:
        features = {k: all_features[k] for k in metric_names if k in all_features}
    else:
        # Legacy: no "metrics" key -> use original 6-variable set
        features = {
            "euler_total": all_features["euler_total"],
            "loop_total": all_features["loop_total"],
            "junction_density": all_features["junction_density"],
            "tortuosity_center": all_features["tortuosity_center"],
            "tortuosity_periphery": all_features["tortuosity_periphery"],
            "FD_global": all_features["FD_global"],
        }

    def _z(name: str, value: float) -> float:
        m = float(mu.get(name, 0.0))
        s = float(sigma.get(name, 0.0))
        if s <= 0.0:
            return 0.0
        return (value - m) / s

    # Z-scores for each metric
    z_vals: Dict[str, float] = {name: _z(name, val) for name, val in features.items()}

    # Principal component scores: linear combination of z-scores.
    pc1 = 0.0
    pc2 = 0.0
    for name, z_val in z_vals.items():
        w1 = float(pc1_w.get(name, 0.0))
        w2 = float(pc2_w.get(name, 0.0))
        pc1 += w1 * z_val
        pc2 += w2 * z_val

    def _sigmoid(x: float) -> float:
        # Standard logistic mapped to 0-100; higher PC => higher complexity.
        return 100.0 / (1.0 + float(np.exp(-x)))

    pc1_score = _sigmoid(pc1)
    pc2_score = _sigmoid(pc2)

    w_pc1 = float(final_w.get("PC1", 0.6))
    w_pc2 = float(final_w.get("PC2", 0.3))
    w_trunk = float(final_w.get("TrunkDist", 0.1))

    final = w_pc1 * pc1_score + w_pc2 * pc2_score + w_trunk * float(trunk_score)

    return float(np.clip(final, 0.0, 100.0))
