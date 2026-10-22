#!/usr/bin/env python3
"""The v1.2.4b zip keeps Optovue sources and a signable shapely/.dylibs."""

from __future__ import annotations

import plistlib
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_v124b_mac_zip import build_zip  # noqa: E402


def _plist(version: str) -> bytes:
    info = {
        "CFBundleShortVersionString": version,
        "CFBundleVersion": version,
    }
    return plistlib.dumps(info, fmt=plistlib.FMT_XML)


def test_relabels_and_renames() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        bundle = root / "ARIAKE_OCTA_mac_v1.2.4"
        app = bundle / "ARIAKE_OCTA.app"
        contents = app / "Contents"
        (contents / "Resources" / "src" / "core").mkdir(parents=True)
        (contents / "Resources" / "src" / "core" / "mnv_pipeline.py").write_text(
            "old = True\n", encoding="utf-8"
        )
        pages = contents / "Resources" / "src" / "flet_ui" / "pages"
        pages.mkdir(parents=True)
        (pages / "dashboard.pyc").write_bytes(b"old-wizard")
        dylibs = contents / "Frameworks" / "shapely" / ".dylibs"
        dylibs.mkdir(parents=True)
        (dylibs / "libfoo.dylib").write_bytes(b"not-a-macho")
        nested = (
            contents
            / "Frameworks"
            / "Python.framework"
            / "Versions"
            / "lib"
            / ".dylibs"
        )
        nested.mkdir(parents=True)
        (nested / "keep").write_bytes(b"leave-me")
        (contents / "Info.plist").write_bytes(_plist("1.2.4"))
        (app / "Contents" / "._junk").write_bytes(b"appledouble")
        (bundle / "インストール.command").write_text("echo old\n", encoding="utf-8")
        src_zip = root / "ARIAKE_OCTA_mac.zip"
        subprocess.run(
            ["zip", "-r", "-y", "-q", str(src_zip), bundle.name],
            cwd=root,
            check=True,
        )
        out_zip = root / "ARIAKE_OCTA_mac_v1.2.4b.zip"
        build_zip(src_zip, out_zip, "1.2.4b")

        unpacked = root / "out"
        subprocess.run(["unzip", "-q", str(out_zip), "-d", str(unpacked)], check=True)
        made = unpacked / "ARIAKE_OCTA_mac_v1.2.4b" / "ARIAKE_OCTA.app"
        with (made / "Contents" / "Info.plist").open("rb") as handle:
            info = plistlib.load(handle)
        assert info["CFBundleShortVersionString"] == "1.2.4b"
        assert info["CFBundleVersion"] == "1.2.4b"
        dashboard = (
            made / "Contents" / "Resources" / "src" / "flet_ui" / "pages" / "dashboard.py"
        ).read_text(encoding="utf-8")
        assert "3 mm (Optovue)" in dashboard
        assert not list(made.rglob("dashboard.pyc"))
        link = made / "Contents" / "Frameworks" / "shapely" / ".dylibs"
        assert link.is_symlink()
        assert os_readlink(link) == "__dot__dylibs"
        assert (made / "Contents" / "Frameworks" / "shapely" / "__dot__dylibs" / "libfoo.dylib").is_file()
        kept = (
            made
            / "Contents"
            / "Frameworks"
            / "Python.framework"
            / "Versions"
            / "lib"
            / ".dylibs"
        )
        assert kept.is_dir() and not kept.is_symlink()
        assert (kept / "keep").is_file()
        assert not list(made.rglob("._*"))
        command = (unpacked / "ARIAKE_OCTA_mac_v1.2.4b" / "インストール.command").read_text(
            encoding="utf-8"
        )
        assert "mac_adhoc_codesign.sh" in command
        helper = (unpacked / "ARIAKE_OCTA_mac_v1.2.4b" / "mac_adhoc_codesign.sh").read_text(
            encoding="utf-8"
        )
        assert "__dot__" in helper
        notes = (unpacked / "ARIAKE_OCTA_mac_v1.2.4b" / "Macインストール手順.txt").read_text(
            encoding="utf-8"
        )
        assert "v1.2.4b" in notes.splitlines()[1]


def os_readlink(path: Path) -> str:
    return path.readlink().as_posix()


def test_zip_marks_symlink() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        bundle = root / "in"
        app = bundle / "ARIAKE_OCTA.app" / "Contents"
        (app / "Resources").mkdir(parents=True)
        (app / "Info.plist").write_bytes(_plist("1.2.4"))
        (app / "Frameworks" / "cv2" / ".dylibs").mkdir(parents=True)
        (app / "Frameworks" / "cv2" / ".dylibs" / "lib.dylib").write_bytes(b"x")
        src_zip = root / "ARIAKE_OCTA_macOS_Intel_v1.2.4.zip"
        subprocess.run(
            ["zip", "-r", "-y", "-q", str(src_zip), "in"],
            cwd=root,
            check=True,
        )
        out_zip = root / "out.zip"
        build_zip(src_zip, out_zip, "1.2.4b")
        with zipfile.ZipFile(out_zip) as zf:
            assert any(name.startswith("ARIAKE_OCTA_macOS_Intel_v1.2.4b/") for name in zf.namelist())
            info = zf.getinfo(
                "ARIAKE_OCTA_macOS_Intel_v1.2.4b/ARIAKE_OCTA.app/Contents/Frameworks/cv2/.dylibs"
            )
            mode = info.external_attr >> 16
            assert stat.S_ISLNK(mode), mode


if __name__ == "__main__":
    test_relabels_and_renames()
    test_zip_marks_symlink()
    print("ok")
