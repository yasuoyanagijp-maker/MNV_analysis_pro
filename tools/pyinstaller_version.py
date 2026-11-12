"""Read the single ARIAKE OCTA app version for PyInstaller specs and packagers."""

from __future__ import annotations

import os
from pathlib import Path


def read_app_version(project_root: str | os.PathLike[str] | None = None) -> str:
    env = (
        os.environ.get("ARIAKE_APP_VERSION")
        or os.environ.get("ARIAKE_MAC_APP_VERSION")
        or ""
    ).strip()
    if env:
        return env.lstrip("v")
    root = Path(project_root or os.getcwd())
    text = (root / "VERSION").read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"empty VERSION file at {root / 'VERSION'}")
    return text.lstrip("v")
