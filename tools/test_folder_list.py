"""In-app explorer listing: Desktop TCC fallback and skip of unreadable entries."""

from pathlib import Path

from src.utils.folder_list import (
    first_listable_picker_dir,
    is_listable_dir,
    list_directory_contents,
)


def test_lists_visible_entries_and_parent(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("XDG_DESKTOP_DIR", raising=False)
    monkeypatch.setattr("src.utils.app_paths._windows_desktop_dir", lambda: None)
    (tmp_path / "images").mkdir()
    (tmp_path / "scan.tif").write_text("x")
    (tmp_path / ".hidden").write_text("x")

    result = list_directory_contents(str(tmp_path), home=tmp_path, data_dir=tmp_path)
    names = [item["name"] for item in result["items"]]
    assert "images" in names
    assert "scan.tif" in names
    assert ".hidden" not in names
    assert ".." in names
    assert result["current_path"] == str(tmp_path.resolve())
    assert "error" not in result


def test_permission_error_falls_back_to_home(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("XDG_DESKTOP_DIR", raising=False)
    monkeypatch.setattr("src.utils.app_paths._windows_desktop_dir", lambda: None)
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    (desktop / "blocked.tif").write_text("x")
    (tmp_path / "visible.tif").write_text("ok")

    real_iterdir = Path.iterdir

    def fake_iterdir(self):
        if self.resolve() == desktop.resolve():
            raise PermissionError("Operation not permitted")
        return real_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", fake_iterdir)
    result = list_directory_contents(str(desktop), home=tmp_path, data_dir=tmp_path)
    names = [item["name"] for item in result["items"]]
    assert "visible.tif" in names
    assert result["current_path"] == str(tmp_path.resolve())
    assert "warning" in result
    assert "error" not in result


def test_missing_path_falls_back(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("XDG_DESKTOP_DIR", raising=False)
    monkeypatch.setattr("src.utils.app_paths._windows_desktop_dir", lambda: None)
    (tmp_path / "keep.txt").write_text("ok")
    missing = tmp_path / "does-not-exist"
    result = list_directory_contents(str(missing), home=tmp_path, data_dir=tmp_path)
    names = [item["name"] for item in result["items"]]
    assert "keep.txt" in names
    assert "warning" in result


def test_skips_unreadable_child(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("XDG_DESKTOP_DIR", raising=False)
    monkeypatch.setattr("src.utils.app_paths._windows_desktop_dir", lambda: None)
    good = tmp_path / "ok.tif"
    bad = tmp_path / "locked.tif"
    good.write_text("ok")
    bad.write_text("no")

    real_is_dir = Path.is_dir

    def fake_is_dir(self):
        if self.resolve() == bad.resolve():
            raise PermissionError("Operation not permitted")
        return real_is_dir(self)

    monkeypatch.setattr(Path, "is_dir", fake_is_dir)
    result = list_directory_contents(str(tmp_path), home=tmp_path, data_dir=tmp_path)
    names = [item["name"] for item in result["items"]]
    assert "ok.tif" in names
    assert "locked.tif" not in names
    assert "error" not in result


def test_first_listable_skips_blocked_desktop(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("XDG_DESKTOP_DIR", raising=False)
    monkeypatch.setattr("src.utils.app_paths._windows_desktop_dir", lambda: None)
    desktop = tmp_path / "Desktop"
    desktop.mkdir()

    real_iterdir = Path.iterdir

    def fake_iterdir(self):
        if self.resolve() == desktop.resolve():
            raise PermissionError("Operation not permitted")
        return real_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", fake_iterdir)
    assert first_listable_picker_dir(tmp_path, data_dir=tmp_path) == tmp_path.resolve()
    assert is_listable_dir(desktop) is False
    assert is_listable_dir(tmp_path) is True


def test_specs_declare_macos_folder_usage_keys():
    root = Path(__file__).resolve().parent.parent
    keys = (
        "NSDesktopFolderUsageDescription",
        "NSDocumentsFolderUsageDescription",
        "NSDownloadsFolderUsageDescription",
    )
    for name in (
        "ARIAKE_OCTA.spec",
        "ARIAKE_OCTA_arm64.spec",
        "ARIAKE_OCTA_x86_64.spec",
    ):
        text = (root / name).read_text(encoding="utf-8")
        for key in keys:
            assert key in text, f"{name} missing {key}"
