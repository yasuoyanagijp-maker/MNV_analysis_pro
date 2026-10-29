"""Ensure repo-root and ``src/`` are importable (same convention as run_flet.sh)."""

from __future__ import annotations

import sys
from pathlib import Path

_PKG_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _PKG_DIR.parents[2]
_SRC = _REPO_ROOT / "src"


def ensure_import_paths() -> Path:
    for candidate in (str(_REPO_ROOT), str(_SRC)):
        if candidate not in sys.path:
            sys.path.insert(0, candidate)
    return _REPO_ROOT


def repo_root() -> Path:
    return _REPO_ROOT
