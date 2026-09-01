#!/usr/bin/env python3
"""Keep OpenSSL 1.1 and 3 side-by-side inside a macOS .app.

v1.2.4-mac rewrote *every* libcrypto install name to match Python's _ssl.so
(OpenSSL 1.1). OpenCV's libssl.3.dylib still needs OpenSSL 3 symbols
(_ASYNC_WAIT_CTX_get_status), so cv2 import dies and the login UI never
reaches FastAPI.

install_name_tool -change keeps the Mach-O compatibility version, so a
broken rewrite looks like:

    @rpath/libcrypto.1.1.dylib (compatibility version 3.0.0, ...)

Compatibility version is the source of truth. Never point an OpenSSL 3
binary at libcrypto.1.1, or an OpenSSL 1.1 binary at libcrypto.3.

Usage:
  python3 tools/mac_openssl_coexistence.py --fix /Applications/ARIAKE_OCTA.app
  python3 tools/mac_openssl_coexistence.py --fix /Applications/ARIAKE_OCTA.app --sign
  python3 tools/mac_openssl_coexistence.py --verify /Applications/ARIAKE_OCTA.app
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

MACHO_MAGICS = {
    b"\xfe\xed\xfa\xce",
    b"\xce\xfa\xed\xfe",
    b"\xfe\xed\xfa\xcf",
    b"\xcf\xfa\xed\xfe",
    b"\xca\xfe\xba\xbe",
    b"\xbe\xba\xfe\xca",
}

DEP_RE = re.compile(
    r"^\t(\S+)\s+\(compatibility version ([0-9.]+), current version ([0-9.]+)\)"
)

FILENAMES = {"1.1": "libcrypto.1.1.dylib", "3": "libcrypto.3.dylib"}
RPATHS = {"1.1": "@rpath/libcrypto.1.1.dylib", "3": "@rpath/libcrypto.3.dylib"}
HOMEBREW_DIRS = {
    "1.1": (
        "/opt/homebrew/opt/openssl@1.1/lib",
        "/usr/local/opt/openssl@1.1/lib",
    ),
    "3": (
        "/opt/homebrew/opt/openssl@3/lib",
        "/usr/local/opt/openssl@3/lib",
    ),
}


@dataclass(frozen=True)
class Dep:
    install_name: str
    compat: str
    current: str


def openssl_major_from_compat(compat: str) -> Optional[str]:
    if compat.startswith("3."):
        return "3"
    if compat.startswith("1.1"):
        return "1.1"
    return None


def openssl_major_from_name(install_name: str) -> Optional[str]:
    base = Path(install_name).name
    if "libcrypto.3" in base or "libssl.3" in base:
        return "3"
    if "1.1" in base:
        return "1.1"
    return None


def is_system_lib(install_name: str) -> bool:
    return install_name.startswith("/usr/lib/") or install_name.startswith("/System/")


def classify_libcrypto_dep(install_name: str, compat: str) -> Optional[str]:
    """Return '1.1' or '3' for a libcrypto load command, else None (leave alone)."""
    if is_system_lib(install_name):
        return None
    if "libcrypto" not in Path(install_name).name:
        return None
    from_compat = openssl_major_from_compat(compat)
    if from_compat:
        return from_compat
    return openssl_major_from_name(install_name)


def desired_libcrypto_name(binary: Path, major: str) -> str:
    filename = FILENAMES[major]
    sibling = binary.parent / filename
    try:
        if sibling.exists():
            return f"@loader_path/{filename}"
    except OSError:
        pass
    return RPATHS[major]


def parse_otool_l(text: str) -> Tuple[Optional[Dep], List[Dep]]:
    """Parse `otool -L` output into (id, dependencies)."""
    deps: List[Dep] = []
    ident: Optional[Dep] = None
    for raw in text.splitlines():
        match = DEP_RE.match(raw)
        if not match:
            continue
        item = Dep(match.group(1), match.group(2), match.group(3))
        if ident is None:
            ident = item
        else:
            deps.append(item)
    return ident, deps


def is_macho(path: Path) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    try:
        with path.open("rb") as fh:
            magic = fh.read(4)
    except OSError:
        return False
    return magic in MACHO_MAGICS


def iter_macho(app: Path) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(app):
        dirnames[:] = [d for d in dirnames if d not in {".git", "__pycache__"}]
        for name in filenames:
            path = Path(dirpath) / name
            if path.suffix in {".so", ".dylib"} or os.access(path, os.X_OK):
                if is_macho(path):
                    yield path


def _run(cmd: Sequence[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=check, text=True, capture_output=True)


def otool_l(path: Path) -> str:
    proc = _run(["otool", "-L", str(path)], check=False)
    if proc.returncode != 0:
        return ""
    return proc.stdout or ""


def make_writable(path: Path) -> None:
    mode = path.stat().st_mode
    if not mode & stat.S_IWUSR:
        path.chmod(mode | stat.S_IWUSR)


def real_libcrypto_candidates(app: Path, major: str) -> List[Path]:
    filename = FILENAMES[major]
    found: List[Path] = []
    for path in app.rglob(filename):
        if path.is_symlink():
            continue
        if path.is_file() and is_macho(path):
            found.append(path)
    for directory in HOMEBREW_DIRS[major]:
        candidate = Path(directory) / filename
        if candidate.is_file():
            found.append(candidate)
    return found


def ensure_frameworks_copy(app: Path, major: str) -> Optional[Path]:
    dest = app / "Contents" / "Frameworks" / FILENAMES[major]
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_symlink():
        try:
            target = dest.resolve(strict=False)
        except OSError:
            target = None
        dest.unlink()
        if target is not None and target.is_file():
            shutil.copy2(target, dest)
    if not dest.is_file() or not is_macho(dest):
        sources = [p for p in real_libcrypto_candidates(app, major) if p != dest]
        if not sources:
            return None
        shutil.copy2(sources[0], dest)
    dest.chmod(0o755)
    make_writable(dest)
    _run(["install_name_tool", "-id", RPATHS[major], str(dest)], check=False)
    return dest


def ensure_exe_rpath(app: Path) -> None:
    exe = app / "Contents" / "MacOS" / "ARIAKE_OCTA"
    if not exe.is_file():
        return
    proc = _run(["otool", "-l", str(exe)], check=False)
    text = proc.stdout or ""
    if "@executable_path/../Frameworks" in text:
        return
    make_writable(exe)
    _run(
        ["install_name_tool", "-add_rpath", "@executable_path/../Frameworks", str(exe)],
        check=False,
    )


def collect_mismatches(app: Path) -> List[str]:
    errors: List[str] = []
    for binary in iter_macho(app):
        ident, deps = parse_otool_l(otool_l(binary))
        for dep in deps:
            major = classify_libcrypto_dep(dep.install_name, dep.compat)
            if major is None:
                continue
            name_major = openssl_major_from_name(dep.install_name)
            if name_major and name_major != major:
                rel = binary.relative_to(app)
                errors.append(
                    f"{rel}: {dep.install_name} is OpenSSL {name_major} but "
                    f"compatibility {dep.compat} is OpenSSL {major}"
                )
    return errors


def needed_majors(app: Path) -> Dict[str, int]:
    counts = {"1.1": 0, "3": 0}
    for binary in iter_macho(app):
        _, deps = parse_otool_l(otool_l(binary))
        for dep in deps:
            major = classify_libcrypto_dep(dep.install_name, dep.compat)
            if major:
                counts[major] += 1
    return counts


def retarget_binary(binary: Path) -> int:
    ident, deps = parse_otool_l(otool_l(binary))
    changed = 0
    for dep in deps:
        major = classify_libcrypto_dep(dep.install_name, dep.compat)
        if major is None:
            continue
        desired = desired_libcrypto_name(binary, major)
        if dep.install_name == desired:
            continue
        make_writable(binary)
        proc = _run(
            ["install_name_tool", "-change", dep.install_name, desired, str(binary)],
            check=False,
        )
        if proc.returncode == 0:
            changed += 1
        else:
            print(
                f"  warn: install_name_tool failed on {binary}: {proc.stderr.strip()}",
                file=sys.stderr,
            )
    if ident is not None and "libcrypto" in Path(ident.install_name).name:
        major = classify_libcrypto_dep(ident.install_name, ident.compat)
        if major:
            desired_id = RPATHS[major]
            if ident.install_name != desired_id and binary.name == FILENAMES[major]:
                make_writable(binary)
                _run(["install_name_tool", "-id", desired_id, str(binary)], check=False)
    return changed


def fix_app(app: Path) -> int:
    if not app.is_dir():
        raise SystemExit(f"[mac_openssl_coexistence] not an app bundle: {app}")
    ensure_exe_rpath(app)
    counts = needed_majors(app)
    for major, n in counts.items():
        if n == 0:
            continue
        dest = ensure_frameworks_copy(app, major)
        if dest is None:
            raise SystemExit(
                f"[mac_openssl_coexistence] need libcrypto {major} "
                f"({n} refs) but no copy was found in the app or Homebrew"
            )
        print(f"  Frameworks/{FILENAMES[major]} <- {dest}", flush=True)
    changed = 0
    for binary in iter_macho(app):
        changed += retarget_binary(binary)
    print(f"  retargeted {changed} libcrypto load command(s)", flush=True)
    return changed


def verify_app(app: Path) -> None:
    if not app.is_dir():
        raise SystemExit(f"[mac_openssl_coexistence] not an app bundle: {app}")
    errors = collect_mismatches(app)
    counts = needed_majors(app)
    frameworks = app / "Contents" / "Frameworks"
    for major, n in counts.items():
        if n == 0:
            continue
        dest = frameworks / FILENAMES[major]
        if dest.is_symlink() or not dest.is_file():
            errors.append(f"missing real {dest.relative_to(app)} (needed by {n} refs)")
    if errors:
        print("[mac_openssl_coexistence] ERROR: OpenSSL 1.1/3 mix-up:", file=sys.stderr)
        for line in errors:
            print(f"  {line}", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"[mac_openssl_coexistence] OK (OpenSSL 1.1 refs={counts['1.1']}, "
        f"OpenSSL 3 refs={counts['3']})",
        flush=True,
    )


def adhoc_sign(app: Path) -> None:
    _run(["xattr", "-cr", str(app)], check=False)
    print("  codesign --force --deep --sign -", flush=True)
    proc = _run(["codesign", "--force", "--deep", "--sign", "-", str(app)], check=False)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr or proc.stdout or "codesign failed\n")
        raise SystemExit(proc.returncode)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fix", metavar="APP", help="Retarget mixed libcrypto refs")
    parser.add_argument("--verify", metavar="APP", help="Fail if 1.1 and 3 are mixed")
    parser.add_argument(
        "--sign",
        action="store_true",
        help="Ad-hoc codesign after --fix (for already-installed apps)",
    )
    args = parser.parse_args(argv)
    if not args.fix and not args.verify:
        parser.error("specify --fix and/or --verify")
    if args.fix:
        app = Path(args.fix).expanduser().resolve()
        print(f"[mac_openssl_coexistence] fix {app}", flush=True)
        fix_app(app)
        if args.sign:
            adhoc_sign(app)
    if args.verify:
        app = Path(args.verify).expanduser().resolve()
        verify_app(app)
    elif args.fix:
        verify_app(Path(args.fix).expanduser().resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
