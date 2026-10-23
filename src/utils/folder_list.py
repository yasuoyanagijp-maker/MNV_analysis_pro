"""Server-side folder listing for the in-app explorer.

macOS TCC can make Desktop / Documents / Downloads exist but unlistable
(``Operation not permitted``) when the app has no Files-and-Folders grant.
The explorer used to treat that as a hard error and render an empty dialog.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from src.utils.app_paths import default_picker_dir, get_base_data_dir


def is_listable_dir(path: Path) -> bool:
    """True when ``path`` is a directory whose children can be iterated."""
    try:
        if not path.is_dir():
            return False
        next(path.iterdir(), None)
        return True
    except OSError:
        return False


def first_listable_picker_dir(
    home: Optional[Path] = None,
    *,
    data_dir: Optional[Path] = None,
) -> Path:
    """Desktop (or OS equivalent) when listable, else home, else app data."""
    home_path = Path(home) if home is not None else Path.home()
    candidates: List[Path] = [default_picker_dir(home_path), home_path]
    fallback = _resolve_data_dir(data_dir)
    if fallback is not None:
        candidates.append(fallback)

    seen = set()
    for cand in candidates:
        try:
            resolved = cand.resolve()
        except OSError:
            resolved = cand
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        if is_listable_dir(resolved):
            return resolved
    return home_path


def list_directory_contents(
    path: Optional[str] = None,
    *,
    home: Optional[Path] = None,
    data_dir: Optional[Path] = None,
) -> Dict:
    """List a folder for ``GET /ls``.

    Always prefers a readable directory over ``{"error": ...}`` so the UI
    can show ``..`` / siblings instead of a blank pane.
    """
    home_path = Path(home) if home is not None else Path.home()
    requested = (path or "").strip()
    start = Path(requested) if requested else first_listable_picker_dir(
        home_path, data_dir=data_dir
    )

    last_error = None
    for target in _listing_targets(start, home_path, data_dir):
        listing, err = _try_list(target)
        if listing is not None:
            if _same_path(target, start):
                return listing
            warning = f"Could not open {start}. Showing {target} instead."
            if err or last_error:
                warning = f"{warning} ({err or last_error})"
            listing["warning"] = warning
            listing["requested_path"] = str(start)
            return listing
        last_error = err

    return {
        "error": last_error or "Invalid directory path",
        "path": str(start),
        "items": [],
    }


def _listing_targets(
    start: Path, home_path: Path, data_dir: Optional[Path]
) -> List[Path]:
    targets: List[Path] = [start]
    try:
        parents = list(start.parents)[:4]
    except OSError:
        parents = []
    targets.extend(parents)
    targets.append(home_path)
    fallback = _resolve_data_dir(data_dir)
    if fallback is not None:
        targets.append(fallback)

    seen = set()
    unique: List[Path] = []
    for cand in targets:
        try:
            key = str(cand.resolve())
        except OSError:
            key = str(cand)
        if key in seen:
            continue
        seen.add(key)
        unique.append(cand)
    return unique


def _try_list(path: Path):
    try:
        if not path.exists() or not path.is_dir():
            return None, "Invalid directory path"
    except OSError as exc:
        return None, str(exc)

    try:
        children = list(path.iterdir())
    except OSError as exc:
        return None, str(exc)

    items = []
    try:
        if path.parent != path:
            items.append(
                {"name": "..", "path": str(path.parent), "is_dir": True}
            )
    except OSError:
        pass

    try:
        children.sort(key=lambda p: p.name.lower())
    except OSError:
        pass

    for item in children:
        try:
            if item.name.startswith("."):
                continue
            items.append(
                {
                    "name": item.name,
                    "path": str(item.absolute()),
                    "is_dir": item.is_dir(),
                }
            )
        except OSError:
            continue

    try:
        current = str(path.absolute())
    except OSError:
        current = str(path)
    return {"items": items, "current_path": current}, None


def _resolve_data_dir(data_dir: Optional[Path]) -> Optional[Path]:
    if data_dir is not None:
        return data_dir
    try:
        return get_base_data_dir()
    except OSError:
        return None


def _same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return str(left) == str(right)
