import re
import sys
import os
from pathlib import Path
from typing import Optional


def sanitize_path_component(name: str) -> str:
    """
    Sanitize a string for safe use in a file or directory name.

    Replaces spaces (including full-width), and other problematic characters
    with underscores to prevent OS-level "Error 2" (file not found) issues
    on Windows and macOS when paths contain spaces.

    Parameters
    ----------
    name : str
        The raw name to sanitize (e.g. file stem, patient ID)

    Returns
    -------
    str
        A sanitized string safe for use in any OS path component.
    """
    # Replace full-width space (U+3000) and regular space with underscore
    name = name.replace("\u3000", "_").replace(" ", "_")
    # Replace any remaining characters that are problematic in paths
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    # Collapse multiple consecutive underscores
    name = re.sub(r'_+', '_', name)
    # Strip leading/trailing underscores
    return name.strip('_')

def get_base_data_dir() -> Path:
    """Returns a writable directory for application data."""
    if getattr(sys, "frozen", False):
        # On frozen app, use user's home directory
        base = Path.home() / "ARIAKE_OCTA_Data"
    else:
        # In development, use project root
        # Assuming this file is in src/utils/, project root is parent.parent.parent
        base = Path(__file__).resolve().parent.parent.parent
    
    base.mkdir(parents=True, exist_ok=True)
    return base

def get_upload_dir() -> Path:
    """Returns the directory for file uploads and transient data."""
    d = get_base_data_dir() / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    return d

def get_output_dir() -> Path:
    """Returns the directory for analysis results."""
    d = get_base_data_dir() / "output"
    d.mkdir(parents=True, exist_ok=True)
    return d

def get_exports_dir() -> Path:
    """Returns the directory for exported CSV/PDF files."""
    d = get_upload_dir() / "exports"
    d.mkdir(parents=True, exist_ok=True)
    return d


def default_picker_dir(home: Optional[Path] = None) -> Path:
    """Folder shown first in Select Folder: Desktop if present, else home.

    Matches the well-known ``desktop`` start location used by web directory
    pickers (File System Access API ``startIn: "desktop"``).
    """
    home_path = Path(home) if home is not None else Path.home()
    for cand in _desktop_candidates(home_path):
        try:
            if cand.is_dir():
                return cand.resolve()
        except OSError:
            continue
    try:
        return home_path.resolve()
    except OSError:
        return home_path


def _desktop_candidates(home: Path):
    """Yield likely Desktop paths for the current OS (existing or not)."""
    env_desktop = (os.environ.get("XDG_DESKTOP_DIR") or "").strip()
    if env_desktop:
        yield Path(os.path.expandvars(env_desktop)).expanduser()

    win_desktop = _windows_desktop_dir()
    if win_desktop is not None:
        yield win_desktop

    yield home / "Desktop"
    yield home / "デスクトップ"
    yield home / "OneDrive" / "Desktop"
    yield home / "OneDrive - Personal" / "Desktop"


def _windows_desktop_dir() -> Optional[Path]:
    """Actual Desktop folder on Windows (localized / OneDrive-aware)."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        buf = ctypes.create_unicode_buffer(getattr(wintypes, "MAX_PATH", 260))
        # CSIDL_DESKTOPDIRECTORY — the on-disk Desktop, not the virtual namespace
        hr = ctypes.windll.shell32.SHGetFolderPathW(None, 0x0010, None, 0, buf)
        if hr == 0 and buf.value:
            return Path(buf.value)
    except Exception:
        return None
    return None
