"""default_picker_dir: Desktop first, home fallback."""

from pathlib import Path

from src.utils.app_paths import default_picker_dir


def test_uses_desktop_when_present(tmp_path: Path, monkeypatch):
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    monkeypatch.delenv("XDG_DESKTOP_DIR", raising=False)
    monkeypatch.setattr("src.utils.app_paths._windows_desktop_dir", lambda: None)
    assert default_picker_dir(tmp_path) == desktop.resolve()


def test_falls_back_to_home_without_desktop(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("XDG_DESKTOP_DIR", raising=False)
    monkeypatch.setattr("src.utils.app_paths._windows_desktop_dir", lambda: None)
    assert default_picker_dir(tmp_path) == tmp_path.resolve()


def test_japanese_desktop_name(tmp_path: Path, monkeypatch):
    desktop = tmp_path / "デスクトップ"
    desktop.mkdir()
    monkeypatch.delenv("XDG_DESKTOP_DIR", raising=False)
    monkeypatch.setattr("src.utils.app_paths._windows_desktop_dir", lambda: None)
    assert default_picker_dir(tmp_path) == desktop.resolve()


def test_xdg_desktop_dir_env(tmp_path: Path, monkeypatch):
    desktop = tmp_path / "MyDesktop"
    desktop.mkdir()
    monkeypatch.setenv("XDG_DESKTOP_DIR", str(desktop))
    monkeypatch.setattr("src.utils.app_paths._windows_desktop_dir", lambda: None)
    assert default_picker_dir(tmp_path) == desktop.resolve()


def test_onedrive_desktop(tmp_path: Path, monkeypatch):
    desktop = tmp_path / "OneDrive" / "Desktop"
    desktop.mkdir(parents=True)
    monkeypatch.delenv("XDG_DESKTOP_DIR", raising=False)
    monkeypatch.setattr("src.utils.app_paths._windows_desktop_dir", lambda: None)
    assert default_picker_dir(tmp_path) == desktop.resolve()
