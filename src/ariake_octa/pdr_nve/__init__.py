"""
PDR NVE / NVD analysis on wide-field OCTA (raw metrics only).

This package is intentionally isolated from the MNV app: it does not write
standardized 0–100 scores or a maturity index (those reference distributions
are MNV 3×3 / 6×6 mm). Existing MNV / VD entry points are not imported here.
"""

from .pipeline import PdrNveConfig, analyze_pair

__all__ = ["PdrNveConfig", "analyze_pair"]
