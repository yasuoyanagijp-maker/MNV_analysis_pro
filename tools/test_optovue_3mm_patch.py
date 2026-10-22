#!/usr/bin/env python3
"""Build the Optovue 3mm patch zips and apply the Mac script to a fake app."""

from __future__ import annotations

import os
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "optovue_3mm_patch"))

from build_patches import MAC_FILES, WIN_EXTRA, build  # noqa: E402


def _plist(version: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleShortVersionString</key>
  <string>{version}</string>
</dict>
</plist>
"""


def test_file_list_matches_v124_diff() -> None:
    tag = subprocess.run(
        ["git", "rev-parse", "--verify", "v1.2.4-mac"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if tag.returncode != 0:
        print("skip file-list check; v1.2.4-mac is not in this clone")
        return
    diff = subprocess.run(
        ["git", "diff", "--name-only", "v1.2.4-mac...HEAD", "--", "src", "resources"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    names = tuple(line for line in diff.stdout.splitlines() if line)
    assert names == MAC_FILES, (names, MAC_FILES)
    assert "src/utils/local_http.py" not in MAC_FILES
    assert WIN_EXTRA == ("src/utils/local_http.py",)


def test_zips_and_mac_apply() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "patches"
        written = build(out)
        by_name = {path.name: path for path in written}
        mac_zip = by_name["ARIAKE_OCTA_optovue_3mm_patch_mac_apple_silicon.zip"]
        intel_zip = by_name["ARIAKE_OCTA_optovue_3mm_patch_mac_intel.zip"]
        win_zip = by_name["ARIAKE_OCTA_optovue_3mm_patch_windows.zip"]

        with zipfile.ZipFile(mac_zip) as zf, zipfile.ZipFile(intel_zip) as zi:
            mac_payload = sorted(
                name.split("/payload/", 1)[1]
                for name in zf.namelist()
                if "/payload/" in name
            )
            intel_payload = sorted(
                name.split("/payload/", 1)[1]
                for name in zi.namelist()
                if "/payload/" in name
            )
        assert tuple(mac_payload) == MAC_FILES
        assert intel_payload == mac_payload
        info = zipfile.ZipFile(mac_zip).getinfo(
            "ARIAKE_OCTA_optovue_3mm_patch_mac_apple_silicon/パッチ適用.command"
        )
        assert info.external_attr >> 16 & stat.S_IXUSR
        sign_info = zipfile.ZipFile(mac_zip).getinfo(
            "ARIAKE_OCTA_optovue_3mm_patch_mac_apple_silicon/mac_adhoc_codesign.sh"
        )
        assert sign_info.external_attr >> 16 & stat.S_IXUSR
        intel_names = zipfile.ZipFile(intel_zip).namelist()
        assert any(name.endswith("/mac_adhoc_codesign.sh") for name in intel_names)

        with zipfile.ZipFile(win_zip) as zf:
            win_payload = sorted(
                name.split("/payload/", 1)[1]
                for name in zf.namelist()
                if "/payload/" in name
            )
            assert "src/utils/local_http.py" in win_payload
            assert any(name.endswith("パッチ適用.bat") for name in zf.namelist())
            assert any(name.endswith("apply_windows.ps1") for name in zf.namelist())
        assert tuple(win_payload) == tuple(sorted(MAC_FILES + WIN_EXTRA))

        stage = Path(tmp) / "mac"
        stage.mkdir()
        subprocess.run(["unzip", "-q", str(mac_zip), "-d", str(stage)], check=True)
        patch_dir = stage / "ARIAKE_OCTA_optovue_3mm_patch_mac_apple_silicon"
        app = Path(tmp) / "ARIAKE_OCTA.app"
        core = app / "Contents" / "Resources" / "src" / "core"
        core.mkdir(parents=True)
        (app / "Contents" / "Info.plist").write_text(_plist("1.2.4"), encoding="utf-8")
        (core / "mnv_pipeline.py").write_text("old\n", encoding="utf-8")
        (core / "mnv_pipeline.pyc").write_bytes(b"stale")
        cache = core / "__pycache__"
        cache.mkdir()
        (cache / "mnv_pipeline.cpython-39.pyc").write_bytes(b"stale")
        frameworks = app / "Contents" / "Frameworks"
        fw_core = frameworks / "src" / "core"
        fw_core.mkdir(parents=True)
        (fw_core / "mnv_pipeline.pyc").write_bytes(b"oldpyc")
        dylibs = frameworks / "shapely" / ".dylibs"
        dylibs.mkdir(parents=True)
        (dylibs / "libgeos.dylib").write_bytes(b"geos")
        numpy_libs = frameworks / "numpy.libs"
        numpy_libs.mkdir()
        (numpy_libs / "libquadmath.dylib").write_bytes(b"quad")
        fw_keep = frameworks / "Python.framework" / "lib-dynload" / ".dylibs"
        fw_keep.mkdir(parents=True)
        (fw_keep / "keep.dylib").write_bytes(b"keep")
        (frameworks / "Python.framework" / "Versions").mkdir()
        res_meta = app / "Contents" / "Resources" / "pkg.dist-info"
        res_meta.mkdir()
        (res_meta / "METADATA").write_text("name\n", encoding="utf-8")
        (patch_dir / "payload" / ".DS_Store").write_bytes(b"finder")
        (patch_dir / "payload" / "src" / "._mnv_pipeline.py").write_bytes(b"appledouble")

        env = os.environ.copy()
        env["ARIAKE_PATCH_SKIP_CODESIGN"] = "1"
        env["ARIAKE_PATCH_SKIP_PAUSE"] = "1"
        env["ARIAKE_PATCH_NO_OPEN"] = "1"
        proc = subprocess.run(
            ["bash", str(patch_dir / "パッチ適用.command"), str(app)],
            cwd=patch_dir,
            env=env,
            text=True,
            capture_output=True,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert f"{len(MAC_FILES)} ファイル" in proc.stdout
        patched = (core / "mnv_pipeline.py").read_text(encoding="utf-8")
        assert "optovue_3mm" in patched
        assert not (core / "mnv_pipeline.pyc").exists()
        assert not (cache / "mnv_pipeline.cpython-39.pyc").exists()
        assert not (fw_core / "mnv_pipeline.pyc").exists()
        assert "optovue_3mm" in (fw_core / "mnv_pipeline.py").read_text(encoding="utf-8")
        assert not (app / "Contents" / "Resources" / ".DS_Store").exists()
        assert not (app / "Contents" / "Resources" / "src" / "._mnv_pipeline.py").exists()
        link = frameworks / "shapely" / ".dylibs"
        assert link.is_symlink()
        assert os.readlink(link) == "__dot__dylibs"
        assert (frameworks / "shapely" / "__dot__dylibs" / "libgeos.dylib").read_bytes() == b"geos"
        assert (frameworks / "numpy__dot__libs").is_dir()
        assert (frameworks / "numpy.libs").is_symlink()
        framework = frameworks / "Python.framework"
        assert framework.is_dir() and not framework.is_symlink()
        assert (fw_keep / "keep.dylib").read_bytes() == b"keep"
        assert not (fw_keep.parent / "__dot__dylibs").exists()
        assert (res_meta / "METADATA").is_file()
        assert "3 mm (Optovue)" in proc.stdout
        json_path = (
            app
            / "Contents"
            / "Resources"
            / "resources"
            / "reference_metrics"
            / "complexity_ref_optovue_3mm.json"
        )
        assert json_path.is_file()
        assert not (
            app / "Contents" / "Resources" / "src" / "utils" / "local_http.py"
        ).exists()

        wrong = Path(tmp) / "old.app"
        wrong_core = wrong / "Contents" / "Resources" / "src" / "core"
        wrong_core.mkdir(parents=True)
        (wrong / "Contents" / "Info.plist").write_text(_plist("1.2.3"), encoding="utf-8")
        (wrong_core / "mnv_pipeline.py").write_text("old\n", encoding="utf-8")
        proc = subprocess.run(
            ["bash", str(patch_dir / "パッチ適用.command"), str(wrong)],
            cwd=patch_dir,
            env=env,
            text=True,
            capture_output=True,
        )
        assert proc.returncode != 0
        assert "v1.2.4" in (proc.stdout + proc.stderr)
        assert (wrong_core / "mnv_pipeline.py").read_text(encoding="utf-8") == "old\n"


if __name__ == "__main__":
    test_file_list_matches_v124_diff()
    test_zips_and_mac_apply()
    print("ok")
