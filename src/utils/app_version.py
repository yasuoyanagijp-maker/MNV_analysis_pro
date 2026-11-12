"""Single user-facing app version for Mac, Windows, and Linux source runs."""

from __future__ import annotations

import sys
from pathlib import Path

_FALLBACK = "1.2.5"


def get_app_version() -> str:
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "VERSION")
    here = Path(__file__).resolve()
    candidates.append(here.parents[2] / "VERSION")
    candidates.append(Path.cwd() / "VERSION")
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if text:
            return text.lstrip("v")
    return _FALLBACK


def format_app_version_label() -> str:
    return f"v{get_app_version()}"
