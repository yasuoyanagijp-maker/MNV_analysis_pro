"""
Caliber Uniformity Score U2 (device-/size_class-locked).

Default caliber uniformity for ARIAKE OCTA:
  Score = 0.75 * U(−NV Diameter CV) + 0.25 * U(−Dilated vessel fraction)
with stratum-locked piecewise scaling (median → 50), matching manuscript
reference cohorts (small / large / small_3mm).

PCA Stability Caliber remains available as fallback.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np

W_CV = 0.75
W_DIL = 0.25

DEVICE_LABELS = {
    "small": "Optovue Solix / AngioVue 6×6 mm",
    "large": "Zeiss PlexElite 9000 6×6 mm",
    "small_3mm": "Zeiss CIRRUS HD AngioPlex 3×3 mm (Angiography 3x3)",
}


def _iter_ref_candidates(filename: str = "caliber_u2_device_ref.json"):
    """Yield candidate paths for the U2 reference JSON."""
    here = Path(__file__).resolve()
    roots = [
        here.parents[2] / "resources" / "reference_metrics",
        here.parents[2] / "output",
        Path.cwd() / "resources" / "reference_metrics",
        Path.cwd() / "output",
    ]
    # PyInstaller / app bundle
    try:
        import sys

        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            roots.insert(0, Path(sys._MEIPASS) / "resources" / "reference_metrics")
    except Exception:
        pass
    for root in roots:
        yield root / filename


@lru_cache(maxsize=1)
def load_caliber_u2_device_ref() -> Optional[Dict[str, Any]]:
    for path in _iter_ref_candidates():
        if path.is_file():
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and "strata" in data:
                    return data
            except Exception:
                continue
    return None


def piecewise_scale(
    x: np.ndarray,
    x_min: float,
    x_median: float,
    x_max: float,
) -> np.ndarray:
    """Map values so median → 50 on a 0–100 scale (same as PCA Caliber)."""
    x = np.asarray(x, dtype=float)
    result = np.zeros_like(x, dtype=float)
    low = x <= x_median
    high = x > x_median
    if x_median > x_min:
        result[low] = 50.0 * (x[low] - x_min) / (x_median - x_min)
    if x_max > x_median:
        result[high] = 50.0 + 50.0 * (x[high] - x_median) / (x_max - x_median)
    return np.clip(result, 0.0, 100.0)


def infer_size_class_from_filename(file_name: str) -> str:
    """Heuristic size_class from File name (CSV / ICC). Prefer explicit FOV tokens."""
    n = str(file_name).lower()
    if "3x3" in n or "3×3" in n or "3 x 3" in n:
        return "small_3mm"
    if "angiovue" in n or "optovue" in n or "solix" in n:
        return "small"
    if "plexelite" in n or "plex elite" in n or re.search(r"\bplex\b", n):
        return "large"
    if "cirrus" in n or "angioplex" in n:
        return "small_3mm" if ("3x3" in n or "3×3" in n) else "large"
    if "6x6" in n or "6×6" in n:
        return "large"
    return "small_3mm"


def _axis_piecewise(raw: float, pw: Dict[str, float]) -> float:
    """Uniformity axis: lower raw → higher score via piecewise on (−raw)."""
    if not np.isfinite(raw):
        return float("nan")
    neg = np.asarray([-float(raw)], dtype=float)
    scored = piecewise_scale(neg, float(pw["min"]), float(pw["median"]), float(pw["max"]))
    return float(scored[0])


def calculate_caliber_u2_score(
    nv_diameter_cv: float,
    dilated_vessel_fraction: float,
    size_class: str = "small_3mm",
    ref: Optional[Dict[str, Any]] = None,
) -> Tuple[float, Dict[str, Any]]:
    """
    Compute Caliber Uniformity U2 (0–100).

    Parameters
    ----------
    nv_diameter_cv :
        ``NV Diameter (CV)`` (percent-like CV as exported in batch CSV).
    dilated_vessel_fraction :
        ``Dilated vessel (%)`` as ratio in [0, 1] (pipeline ``high_skew_percentage``).
        Values > 1.5 are treated as percent and divided by 100.
    size_class :
        ``small`` | ``large`` | ``small_3mm``.
    ref :
        Optional preloaded JSON; otherwise loaded from resources.

    Returns
    -------
    score, details
    """
    details: Dict[str, Any] = {
        "method": "caliber_u2_device_std",
        "size_class": size_class,
        "fallback": False,
    }
    ref = ref if ref is not None else load_caliber_u2_device_ref()
    if ref is None or size_class not in ref.get("strata", {}):
        details["fallback"] = True
        details["error"] = "missing_u2_ref"
        return float("nan"), details

    stratum = ref["strata"][size_class]
    weights = ref.get("weights", {})
    w_cv = float(weights.get("U_cv", W_CV))
    w_dil = float(weights.get("U_dil", W_DIL))

    nv = float(nv_diameter_cv)
    dil = float(dilated_vessel_fraction)
    if dil > 1.5:
        dil = dil / 100.0

    u_cv = _axis_piecewise(nv, stratum["neg_nv_cv_piecewise"])
    u_dil = _axis_piecewise(dil, stratum["neg_dilated_piecewise"])
    if not (np.isfinite(u_cv) and np.isfinite(u_dil)):
        details["fallback"] = True
        details["error"] = "non_finite_inputs"
        return float("nan"), details

    score = float(np.clip(w_cv * u_cv + w_dil * u_dil, 0.0, 100.0))
    details.update(
        {
            "device": stratum.get("device", DEVICE_LABELS.get(size_class, "")),
            "U_cv": u_cv,
            "U_dil": u_dil,
            "w_cv": w_cv,
            "w_dil": w_dil,
            "nv_diameter_cv": nv,
            "dilated_vessel_fraction": dil,
        }
    )
    return score, details


def calculate_maturity_index(caliber_uniformity: float, complexity: float) -> float:
    """Maturity Index = clip(50 + (Caliber − Complexity) / 2, 0, 100)."""
    if not (np.isfinite(caliber_uniformity) and np.isfinite(complexity)):
        return float("nan")
    return float(np.clip(50.0 + (float(caliber_uniformity) - float(complexity)) / 2.0, 0.0, 100.0))
