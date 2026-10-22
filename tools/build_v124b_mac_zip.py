#!/usr/bin/env python3
"""Bake the Optovue 3mm patch into a published Mac v1.2.4 zip.

The result is a full installer zip labeled 1.2.4b. It is not a new
PyInstaller build: the v1.2.4 .app is kept, the patch sources are copied
in, dotted Frameworks directories are renamed for codesign, and the
current インストール.command is bundled so the Mac re-signs on install.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import plistlib
import stat
import subprocess
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "tools" / "mac_adhoc_codesign.sh"

import sys

sys.path.insert(0, str(ROOT / "tools" / "optovue_3mm_patch"))
from build_patches import MAC_FILES  # noqa: E402


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    subprocess.run(cmd, cwd=cwd, check=True)


def _find_app(extracted: Path) -> Path:
    apps = [
        path
        for path in extracted.rglob("ARIAKE_OCTA.app")
        if path.is_dir() and (path / "Contents" / "Info.plist").is_file()
    ]
    if len(apps) != 1:
        raise SystemExit(f"expected one ARIAKE_OCTA.app, found {len(apps)}")
    return apps[0]


def _purge_bytecode(app: Path, rel: str) -> None:
    rel_path = Path(rel)
    pyc_rel = Path(str(rel_path.with_suffix(".pyc")))
    base = rel_path.stem
    parent = rel_path.parent
    contents = app / "Contents"
    doomed: list[Path] = []
    for path in contents.rglob("*.pyc"):
        try:
            relative = path.relative_to(contents)
        except ValueError:
            continue
        parts = relative.parts
        under_root = relative in {
            Path("Resources") / pyc_rel,
            Path("Frameworks") / pyc_rel,
            Path("MacOS") / pyc_rel,
        }
        same_module = parts[-1] == pyc_rel.name and Path(*parts).match(str(pyc_rel))
        cached = (
            len(parts) >= 2
            and parts[-2] == "__pycache__"
            and parts[-1].startswith(f"{base}.cpython-")
            and parts[-1].endswith(".pyc")
            and Path(*parts[:-2]) == parent
        )
        if under_root or same_module or cached:
            doomed.append(path)
    for path in doomed:
        path.unlink(missing_ok=True)


def _overlay(app: Path) -> None:
    resources = app / "Contents" / "Resources"
    for rel in MAC_FILES:
        data = (ROOT / rel).read_bytes()
        dest = resources / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        for root_name in ("Frameworks", "MacOS"):
            other = app / "Contents" / root_name / rel
            if other.parent.exists():
                other.write_bytes(data)
        if rel.endswith(".py"):
            _purge_bytecode(app, rel)
    dashboard = resources / "src" / "flet_ui" / "pages" / "dashboard.py"
    text = dashboard.read_text(encoding="utf-8")
    if "3 mm (Optovue)" not in text:
        raise SystemExit("overlay did not install the Optovue wizard")


def _set_version(app: Path, version: str) -> None:
    plist_path = app / "Contents" / "Info.plist"
    with plist_path.open("rb") as handle:
        info = plistlib.load(handle)
    current = str(info.get("CFBundleShortVersionString", ""))
    if current not in {"1.2.4", version}:
        raise SystemExit(f"refusing to relabel {current!r} as {version}")
    info["CFBundleShortVersionString"] = version
    info["CFBundleVersion"] = version
    with plist_path.open("wb") as handle:
        plistlib.dump(info, handle, fmt=plistlib.FMT_XML)


def _assert_signable(app: Path) -> None:
    frameworks = app / "Contents" / "Frameworks"
    if not frameworks.is_dir():
        return
    for dirpath, dirnames, _filenames in os.walk(frameworks, followlinks=False):
        current = Path(dirpath)
        if any(part.endswith(".framework") for part in current.parts):
            dirnames[:] = []
            continue
        for name in dirnames:
            if "." not in name or name.endswith(".framework"):
                continue
            path = current / name
            if path.is_symlink():
                continue
            if path.is_dir():
                raise SystemExit(f"dotted directory was not renamed: {path}")


def _install_helpers(bundle: Path, version: str) -> None:
    command = (ROOT / "インストール.command").read_bytes().replace(b"\r\n", b"\n")
    helper = HELPER.read_bytes().replace(b"\r\n", b"\n")
    notes = (ROOT / "Macインストール手順.txt").read_text(encoding="utf-8")
    notes = notes.replace(
        "macOS インストール手順（v1.2.4）",
        f"macOS インストール手順（v{version}）",
        1,
    )
    (bundle / "インストール.command").write_bytes(command)
    (bundle / "mac_adhoc_codesign.sh").write_bytes(helper)
    (bundle / "Macインストール手順.txt").write_text(notes, encoding="utf-8")
    os.chmod(bundle / "インストール.command", 0o755)
    os.chmod(bundle / "mac_adhoc_codesign.sh", 0o755)
    stale = [
        path
        for path in bundle.rglob("*")
        if path.name == ".DS_Store" or path.name.startswith("._")
    ]
    for path in stale:
        if path.is_file() or path.is_symlink():
            path.unlink()


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = info.external_attr >> 16
    return stat.S_ISLNK(mode)


def _verify_zip(path: Path, version: str) -> None:
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        plist_name = next(name for name in names if name.endswith("ARIAKE_OCTA.app/Contents/Info.plist"))
        info = plistlib.loads(zf.read(plist_name))
        if info.get("CFBundleShortVersionString") != version:
            raise SystemExit(f"zip version is {info.get('CFBundleShortVersionString')!r}")
        dashboard = next(
            name
            for name in names
            if name.endswith("Contents/Resources/src/flet_ui/pages/dashboard.py")
        )
        if "3 mm (Optovue)" not in zf.read(dashboard).decode("utf-8"):
            raise SystemExit("zip is missing the Optovue wizard")
        dylib_links = []
        dylib_dirs = []
        for info in zf.infolist():
            name = info.filename
            if ".framework/" in name:
                continue
            bare = name.rstrip("/")
            if not bare.endswith(".dylibs"):
                continue
            if _is_symlink(info):
                dylib_links.append(name)
            elif name.endswith("/"):
                dylib_dirs.append(name)
        if not dylib_links:
            raise SystemExit("no Frameworks .dylibs symlink in the zip")
        if dylib_dirs:
            raise SystemExit(f"real .dylibs directories remain: {dylib_dirs}")
        command = next(name for name in names if name.endswith("/インストール.command"))
        helper = next(name for name in names if name.endswith("/mac_adhoc_codesign.sh"))
        if b"mac_adhoc_codesign.sh" not in zf.read(command):
            raise SystemExit("installer does not call the codesign helper")
        if b"__dot__" not in zf.read(helper):
            raise SystemExit("codesign helper is missing the rename step")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    print(f"wrote {path} ({path.stat().st_size} bytes) sha256 {digest}")


def build_zip(src_zip: Path, out_zip: Path, version: str = "1.2.4b") -> None:
    folder = (
        f"ARIAKE_OCTA_macOS_Intel_v{version}"
        if "Intel" in src_zip.name or "intel" in src_zip.name
        else f"ARIAKE_OCTA_mac_v{version}"
    )
    with tempfile.TemporaryDirectory() as tmp:
        extracted = Path(tmp) / "src"
        stage = Path(tmp) / "stage"
        extracted.mkdir()
        stage.mkdir()
        _run(["unzip", "-q", str(src_zip), "-d", str(extracted)])
        app = _find_app(extracted)
        _overlay(app)
        _set_version(app, version)
        _run(["bash", str(HELPER), "prepare", str(app)])
        _assert_signable(app)
        bundle = app.parent
        dest = stage / folder
        bundle.rename(dest)
        _install_helpers(dest, version)
        out_zip.parent.mkdir(parents=True, exist_ok=True)
        if out_zip.exists():
            out_zip.unlink()
        _run(["zip", "-r", "-y", "-q", str(out_zip.resolve()), folder], cwd=stage)
    _verify_zip(out_zip, version)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a Mac v1.2.4b zip from v1.2.4")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", default="1.2.4b")
    args = parser.parse_args()
    build_zip(args.input.resolve(), args.output.resolve(), args.version)


if __name__ == "__main__":
    main()
