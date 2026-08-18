"""Windows analysis thread / BLAS pinning (plan 1).

Call apply_plan1_env() before importing numpy / scipy / cv2 so OpenBLAS and
OpenMP pick up the worker cap. apply_plan1_imported_libs() caps OpenCV after
those imports.

ARIAKE_WIN_PERF_PLAN1:
  unset            -> disabled (opt-in; Hessian ThreadPool stays on)
  1 / true / on    -> enabled
  0 / false / off  -> disabled (baseline for A/B benches)

ARIAKE_BLAS_THREADS: integer worker cap (default 1).

Existing OMP_NUM_THREADS / OPENBLAS_NUM_THREADS / etc. are left in place
(setdefault). Keep the enablement logic in sync with wrapper_win.py
(_plan1_enabled / _apply_plan1_env_early), which cannot import this module
before numpy.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict

_TRUTHY = {"1", "true", "yes", "on"}
_FALSY = {"0", "false", "no", "off"}

_BLAS_ENV_KEYS = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "BLIS_NUM_THREADS",
)


def plan1_requested() -> bool:
    raw = (os.environ.get("ARIAKE_WIN_PERF_PLAN1") or "").strip().lower()
    if raw in _FALSY:
        return False
    if raw in _TRUTHY:
        return True
    return False


def blas_thread_count() -> int:
    raw = (os.environ.get("ARIAKE_BLAS_THREADS") or "1").strip()
    if raw.isdigit() and int(raw) >= 1:
        return int(raw)
    return 1


def apply_plan1_env() -> Dict[str, Any]:
    """Set BLAS/OpenMP env vars. Safe to call before numpy import."""
    info: Dict[str, Any] = {
        "enabled": False,
        "platform": sys.platform,
        "threads": None,
    }
    if not plan1_requested():
        return info
    n = str(blas_thread_count())
    for key in _BLAS_ENV_KEYS:
        os.environ.setdefault(key, n)
    info["enabled"] = True
    info["threads"] = int(n)
    return info


def apply_plan1_imported_libs() -> Dict[str, Any]:
    """Cap OpenCV (and threadpoolctl if present) after scientific imports."""
    info: Dict[str, Any] = {"cv2_threads": None, "threadpoolctl": False}
    if not plan1_requested():
        return info
    n = blas_thread_count()
    try:
        import cv2

        cv2.setNumThreads(n)
        info["cv2_threads"] = n
        try:
            info["cv2_get"] = int(cv2.getNumThreads())
        except Exception:
            pass
    except Exception:
        pass
    try:
        from threadpoolctl import threadpool_limits

        threadpool_limits(limits=n)
        info["threadpoolctl"] = True
    except Exception:
        pass
    return info


def use_filter_parallel() -> bool:
    """Hessian ThreadPoolExecutor. Off only when plan 1 is explicitly enabled."""
    return not plan1_requested()
