"""Repo / pilot-root paths for visualization-boundary scripts."""

from pathlib import Path

PILOT_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = PILOT_ROOT.parents[1]
