#!/usr/bin/env python3
"""Convenience wrapper: python tools/pdr_nve/run_pdr_nve.py --before ... --after ..."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
for p in (str(ROOT), str(SRC)):
    if p not in sys.path:
        sys.path.insert(0, p)

from ariake_octa.pdr_nve.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
