"""Normalize and inspect user-supplied folder paths for batch analysis.

Pasting a Finder path, a ``file://`` URL, or a Terminal-style escaped path used
to fail without any message. Permission errors from macOS (TCC) were also
swallowed by ``Path.glob``, so a blocked folder looked like "no images".
"""

from __future__ import annotations

import errno
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import unquote, urlparse

IMAGE_EXTENSIONS = frozenset({".tif", ".tiff", ".png", ".jpg", ".jpeg"})

_INVISIBLE = dict.fromkeys(
    map(ord, "\u200b\u200c\u200d\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2060\ufeff"),
    None,
)
_QUOTES = "'\"\u2018\u2019\u201c\u201d`"
_MAX_SUBFOLDERS = 60


def normalize_user_path(raw: object) -> str:
    """Return a clean filesystem path string from pasted text ("" when empty)."""
    text = str(raw or "").translate(_INVISIBLE).strip()
    text = text.strip(_QUOTES).strip()
    if not text:
        return ""
    if text.lower().startswith("file:"):
        parsed = urlparse(text)
        text = unquote(parsed.path or "")
        if os.name == "nt" and re.match(r"^/[A-Za-z]:", text):
            text = text[1:]
    elif os.name != "nt":
        text = re.sub(r"\\(.)", r"\1", text)
    text = text.rstrip()
    if text.startswith("~"):
        text = os.path.expanduser(text)
    if len(text) > 1 and text.endswith(("/", os.sep)):
        text = text.rstrip("/" + os.sep) or text[:1]
    return text


def is_image_file(path: Path) -> bool:
    name = path.name
    return (
        not name.startswith(".")
        and path.suffix.lower() in IMAGE_EXTENSIONS
    )


def list_images(folder: Path) -> List[Path]:
    """Images directly inside ``folder``, matched case-insensitively.

    Raises OSError (including PermissionError) instead of hiding it.
    """
    found: List[Path] = []
    for entry in folder.iterdir():
        if not is_image_file(entry):
            continue
        try:
            if entry.is_file():
                found.append(entry)
        except OSError:
            continue
    found.sort(key=lambda p: p.name.lower())
    return found


def describe_os_error(exc: BaseException, path: object = "") -> str:
    code = getattr(exc, "errno", None)
    where = f" ({path})" if path else ""
    if isinstance(exc, PermissionError) or code in (errno.EPERM, errno.EACCES):
        return (
            "macOS がこのフォルダへのアクセスを許可していません" + where + "。"
            "システム設定 → プライバシーとセキュリティ → ファイルとフォルダ"
            "（またはフルディスクアクセス）で ARIAKE OCTA を許可するか、"
            "ホーム直下など別の場所へフォルダをコピーしてください。"
        )
    if isinstance(exc, FileNotFoundError) or code == errno.ENOENT:
        return f"フォルダが見つかりません{where}。"
    return f"フォルダを読めませんでした{where}: {type(exc).__name__}: {exc}"


@dataclass
class FolderInspection:
    folder: Optional[Path] = None
    files: List[Path] = field(default_factory=list)
    error: str = ""
    note: str = ""
    subfolders_with_images: List[Tuple[str, int]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.error and self.folder is not None and bool(self.files)


def _count_images_in_subfolders(folder: Path) -> List[Tuple[str, int]]:
    hits: List[Tuple[str, int]] = []
    try:
        children = sorted(
            (c for c in folder.iterdir() if not c.name.startswith(".")),
            key=lambda p: p.name.lower(),
        )
    except OSError:
        return hits
    for child in children[:_MAX_SUBFOLDERS]:
        try:
            if not child.is_dir():
                continue
            count = len(list_images(child))
        except OSError:
            continue
        if count:
            hits.append((child.name, count))
    return hits


def inspect_image_folder(raw: object) -> FolderInspection:
    """Resolve ``raw`` to a folder and list its images, with a reason on failure."""
    text = normalize_user_path(raw)
    result = FolderInspection()
    if not text:
        result.error = "フォルダのパスが空です。"
        return result

    path = Path(text)
    if not path.is_absolute():
        result.error = (
            f"「{text}」は絶対パスではありません。Finder でフォルダを選び、"
            "Option+Cmd+C（パス名をコピー）で貼り付けてください。"
            "Cmd+C ではフォルダ名しかコピーされません。"
        )
        return result

    try:
        if path.is_file():
            result.note = f"ファイルが指定されたため、親フォルダを使います: {path.parent}"
            path = path.parent
        if not path.is_dir():
            result.error = f"フォルダが見つかりません: {path}"
            return result
        files = list_images(path)
    except OSError as exc:
        result.error = describe_os_error(exc, path)
        return result

    result.folder = path
    result.files = files
    if files:
        return result

    result.subfolders_with_images = _count_images_in_subfolders(path)
    if result.subfolders_with_images:
        listed = ", ".join(
            f"{name} ({count}枚)" for name, count in result.subfolders_with_images[:5]
        )
        result.error = (
            f"このフォルダの直下に画像（tif / tiff / png / jpg / jpeg）がありません。"
            f"画像があるサブフォルダ: {listed}。そのフォルダを選んでください。"
        )
    else:
        result.error = (
            f"このフォルダに画像（tif / tiff / png / jpg / jpeg）がありません: {path}"
        )
    return result
