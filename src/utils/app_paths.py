import re
import sys
import os
from pathlib import Path


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
        # On frozen app, use user's home directory to avoid permission issues in /Applications
        base = Path.home() / ".ariake_octa"
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
