from math import exp


def calculate_complexity_score(metrics):
    """
    metrics: dict with keys expected by macro (center_branch, periphery_branch,
    loop_center, loop_periphery, euler_center, euler_periphery,
    trunk_eccentricity, angular_distribution_cv, thick_vessel_center_ratio,
    diameter_ratio)
    Returns complexityScore (0-100)
    """
    # safe extraction with defaults
    center_branch = metrics.get("center_branch", 0)
    periphery_branch = metrics.get("periphery_branch", 0)
    loop_center = metrics.get("loop_center", 0)
    loop_periphery = metrics.get("loop_periphery", 0)
    euler_center = metrics.get("euler_center", 0)
    euler_periphery = metrics.get("euler_periphery", 0)
    vessel_length_center = metrics.get("vessel_length_center", 1.0)
    vessel_length_periphery = metrics.get("vessel_length_periphery", 1.0)

    branchDensityCenter = center_branch / (
        vessel_length_center if vessel_length_center > 0 else 1.0
    )
    branchDensityPeriphery = periphery_branch / (
        vessel_length_periphery if vessel_length_periphery > 0 else 1.0
    )
    loopDensityCenter = loop_center / (
        vessel_length_center if vessel_length_center > 0 else 1.0
    )
    loopDensityPeriphery = loop_periphery / (
        vessel_length_periphery if vessel_length_periphery > 0 else 1.0
    )
    loopsCenter = loop_center + loop_periphery
    avgLoopDensity = (loopDensityCenter + loopDensityPeriphery) / 2.0
    totalLoops = loopsCenter
    avgEuler = (euler_center + euler_periphery) / 2.0
    eulerComplexity = -avgEuler
    # scores
    branchDensityScore = 100 * (
        1 - exp(-((branchDensityCenter + branchDensityPeriphery) / 2) / 15.0)
    )
    loopDensityScore = 100 * (1 - exp(-avgLoopDensity / 4.0))
    totalLoopsScore = 100 * (1 - exp(-totalLoops / 80.0))
    eulerScore = 100 * (1 - exp(-eulerComplexity / 30.0))
    # spatial
    cpLoopRatio = (loopDensityCenter) / (loopDensityPeriphery + 1e-6)
    cpBranchRatio = (branchDensityCenter) / (branchDensityPeriphery + 1e-6)
    avgDeviation = (abs(cpLoopRatio - 1.0) + abs(cpBranchRatio - 1.0)) / 2.0
    spatialScore = 100 * exp(-avgDeviation * 2)
    anastomoticIndex = totalLoops / (center_branch + periphery_branch + 1)
    anastomoticScore = 100 * (1 - exp(-anastomoticIndex / 0.3))
    trunkEcc = metrics.get("trunk_eccentricity", 0.5)
    angularCV = metrics.get("angular_distribution_cv", 0.5)
    thickCenterRatio = metrics.get("thick_vessel_center_ratio", 0.0)
    diameterRatio = metrics.get("diameter_center_periphery_ratio", 1.0)
    # trunkDistributionScore
    centralityScore = 100 * (1 - trunkEcc)
    radialityScore = 100 * exp(-angularCV * 2) if angularCV >= 0 else 50
    centralDensityBonus = (
        20 if thickCenterRatio > 15 else (10 if thickCenterRatio > 10 else 0)
    )
    if diameterRatio > 1.0 and diameterRatio < 1.5:
        diameterUniformity = 100 * (1.5 - diameterRatio) / 0.5
    elif diameterRatio >= 1.5:
        diameterUniformity = 0
    else:
        diameterUniformity = 50
    trunkDistributionScore = (
        centralityScore * 0.40
        + radialityScore * 0.30
        + diameterUniformity * 0.20
        + centralDensityBonus * 0.10
    )
    # final complexity
    complexityScore = (
        totalLoopsScore * 0.30
        + eulerScore * 0.30
        + trunkDistributionScore * 0.20
        + spatialScore * 0.12
        + anastomoticScore * 0.05
        + branchDensityScore * 0.03
    )
    if complexityScore < 0:
        complexityScore = 0
    if complexityScore > 100:
        complexityScore = 100
    return complexityScore


def classify_mnv(metrics):
    """
    High-level wrapper: returns patternClassification and confidence based on
    metrics and complexity/stability.
    """
    complexity = calculate_complexity_score(metrics)
    stability = metrics.get("stability_score", 50)
    # simple mapping inspired from macro
    if complexity < 40 and stability > 85:
        suggested = "Dead tree"
    elif complexity >= 40 and complexity < 65:
        suggested = "Tree in bud"
    elif complexity >= 55 and metrics.get("patternClassification", "") == "SEAFAN":
        suggested = "Seafan"
    elif complexity >= 75 and metrics.get("patternClassification", "") == "MEDUSA":
        suggested = "Medusa"
    elif complexity >= 65:
        suggested = "Glomerular"
    else:
        suggested = "Tree in bud"
    # confidence heuristic
    confidence = 0.6 + 0.4 * (min(100, complexity) / 100.0)
    return {"suggested": suggested, "complexity": complexity, "confidence": confidence}
