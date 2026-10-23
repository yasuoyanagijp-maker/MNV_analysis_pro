"""Pasted folder paths and image discovery for the Optional path / Confirm flow."""

import os
from pathlib import Path

import pytest

from src.utils.folder_inputs import (
    describe_os_error,
    inspect_image_folder,
    list_images,
    normalize_user_path,
)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("  '/tmp/a b'  ", "/tmp/a b"),
        ('"/tmp/a b"', "/tmp/a b"),
        ("\u201c/tmp/a b\u201d", "/tmp/a b"),
        ("\u202a/tmp/a", "/tmp/a"),
        ("/tmp/a\\ b", "/tmp/a b"),
        ("file:///tmp/a%20b", "/tmp/a b"),
        ("/tmp/a/", "/tmp/a"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_user_path(raw, expected):
    if os.name == "nt":
        pytest.skip("posix path forms")
    assert normalize_user_path(raw) == expected


def test_normalize_expands_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert normalize_user_path("~/Desktop") == str(tmp_path / "Desktop")


def test_images_match_case_insensitively(tmp_path: Path):
    for name in ("A.TIF", "b.Tiff", "c.png", "d.JPG", "e.jpeg", "notes.txt", ".hidden.tif", "._x.tif"):
        (tmp_path / name).write_text("x")
    names = [p.name for p in list_images(tmp_path)]
    assert names == ["A.TIF", "b.Tiff", "c.png", "d.JPG", "e.jpeg"]


def test_inspect_ok_and_file_uses_parent(tmp_path: Path):
    (tmp_path / "a.tif").write_text("x")
    info = inspect_image_folder(str(tmp_path))
    assert info.ok and info.folder == tmp_path
    info = inspect_image_folder(str(tmp_path / "a.tif"))
    assert info.ok and info.folder == tmp_path and info.note


def test_inspect_relative_path_explains_finder_copy():
    info = inspect_image_folder("Desktop")
    assert "Option+Cmd+C" in info.error


def test_inspect_missing_folder(tmp_path: Path):
    info = inspect_image_folder(str(tmp_path / "nope"))
    assert "見つかりません" in info.error


def test_inspect_points_at_subfolders_with_images(tmp_path: Path):
    sub = tmp_path / "patient1"
    sub.mkdir()
    (sub / "x.tif").write_text("x")
    (tmp_path / "empty").mkdir()
    info = inspect_image_folder(str(tmp_path))
    assert not info.ok
    assert info.subfolders_with_images == [("patient1", 1)]
    assert "patient1" in info.error


def test_inspect_reports_permission_error_instead_of_no_images(tmp_path: Path, monkeypatch):
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    real_iterdir = Path.iterdir

    def fake_iterdir(self):
        if self == blocked:
            raise PermissionError(1, "Operation not permitted")
        return real_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", fake_iterdir)
    info = inspect_image_folder(str(blocked))
    assert "許可していません" in info.error
    assert "画像" not in info.error.split("。")[0]


def test_describe_os_error_other():
    assert "FileNotFoundError" not in describe_os_error(FileNotFoundError())
    assert "OSError" in describe_os_error(OSError(5, "io"))
