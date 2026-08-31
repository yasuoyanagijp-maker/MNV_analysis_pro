"""PyInstaller helpers: drop paths that break macOS codesign --deep.

collect_all() pulls *.dist-info / *.egg-info into Contents/Frameworks.
codesign treats those directories as nested bundles, fails with
'bundle format unrecognized, invalid, or unsuitable', and leaves a
signature that macOS kills at launch (CODESIGNING Code 2 Invalid Page).
"""

from __future__ import annotations

import os
from typing import Any, Iterable, List, Sequence, Tuple

TocEntry = Tuple[str, str, str]


def is_codesign_poison(path: Any) -> bool:
    base = os.path.basename(str(path).rstrip("/\\"))
    if base.startswith("._"):
        return True
    return base.endswith(".dist-info") or base.endswith(".egg-info")


def filter_toc(toc: Iterable[TocEntry]) -> List[TocEntry]:
    return [item for item in toc if not is_codesign_poison(item[0])]


def collect_pkg_without_metadata(collect_all_fn, pkg: str):
    datas, binaries, hiddenimports = collect_all_fn(pkg)
    return filter_toc(datas), filter_toc(binaries), hiddenimports


def filter_analysis_metadata(analysis) -> None:
    analysis.datas = filter_toc(analysis.datas)
    analysis.binaries = filter_toc(analysis.binaries)
