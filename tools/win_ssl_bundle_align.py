#!/usr/bin/env python3
"""Copy this Python's OpenSSL DLLs into a frozen Windows _internal folder.

PyInstaller may pick an older libcrypto-3.dll from OpenCV. _ssl.pyd must load
the OpenSSL it was built against (same class of bug as the Intel Mac 3.2 vs 3.3
mismatch). Run after PyInstaller, before zipping.

Usage:
  python tools/win_ssl_bundle_align.py --internal dist/ARIAKE_OCTA/_internal
  python tools/win_ssl_bundle_align.py --internal dist/ARIAKE_OCTA/_internal --ssl-smoke
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

OPENSSL_DLL_GLOBS = ("libssl*.dll", "libcrypto*.dll")
OPENSSL_VERSION_RE = re.compile(rb"OpenSSL \d+\.\d+\.\d+[^\x00]{0,48}")


def openssl_version_from_file(path: Path) -> str:
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    match = OPENSSL_VERSION_RE.search(data)
    if not match:
        return ""
    return match.group(0).decode("ascii", errors="replace").strip()


def iter_python_openssl_dlls(prefix: Path) -> List[Path]:
    found: List[Path] = []
    seen = set()
    folders: Sequence[Path] = (prefix, prefix / "DLLs", prefix / "Library" / "bin")
    for folder in folders:
        if not folder.is_dir():
            continue
        for pat in OPENSSL_DLL_GLOBS:
            for src in sorted(folder.glob(pat)):
                if not src.is_file() or src.name in seen:
                    continue
                seen.add(src.name)
                found.append(src)
    return found


def copy_openssl_dlls(prefix: Path, internal: Path) -> List[Path]:
    internal.mkdir(parents=True, exist_ok=True)
    copied: List[Path] = []
    for src in iter_python_openssl_dlls(prefix):
        dest = internal / src.name
        shutil.copy2(src, dest)
        copied.append(dest)
    return copied


def find_ssl_pyd(internal: Path) -> Optional[Path]:
    matches = [p for p in internal.rglob("_ssl*.pyd") if p.is_file()]
    return sorted(matches)[0] if matches else None


def verify_internal(internal: Path) -> None:
    ssl_pyd = find_ssl_pyd(internal)
    crypto = list(internal.glob("libcrypto*.dll"))
    ssl_dll = list(internal.glob("libssl*.dll"))
    if ssl_pyd is not None and not crypto:
        raise SystemExit(
            f"[win_ssl_bundle_align] {ssl_pyd.name} is present but no libcrypto*.dll in {internal}"
        )
    if ssl_pyd is not None and not ssl_dll:
        raise SystemExit(
            f"[win_ssl_bundle_align] {ssl_pyd.name} is present but no libssl*.dll in {internal}"
        )


def python_openssl_version(python: Path) -> str:
    import subprocess

    proc = subprocess.run(
        [str(python), "-c", "import ssl; print(ssl.OPENSSL_VERSION)"],
        check=False,
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        return ""
    return (proc.stdout or "").strip()


def smoke_load_dlls(internal: Path) -> None:
    if sys.platform != "win32":
        print("[ssl-smoke] skipped (not Windows)", flush=True)
        return
    import ctypes

    for path in sorted(internal.glob("libcrypto*.dll")) + sorted(internal.glob("libssl*.dll")):
        try:
            ctypes.WinDLL(str(path))
        except OSError as exc:
            raise SystemExit(f"[ssl-smoke] LoadLibrary {path.name} failed: {exc}") from exc
        print(f"[ssl-smoke] LoadLibrary {path.name} OK", flush=True)
    ssl_pyd = find_ssl_pyd(internal)
    if ssl_pyd is None:
        return
    try:
        ctypes.WinDLL(str(ssl_pyd))
    except OSError as exc:
        err = str(exc)
        if "X509_STORE_get1_objects" in err or "libcrypto" in err.lower():
            raise SystemExit(f"[ssl-smoke] {ssl_pyd.name} OpenSSL mismatch: {exc}") from exc
        print(f"[ssl-smoke] {ssl_pyd.name} load skipped ({exc})", flush=True)
        return
    print(f"[ssl-smoke] LoadLibrary {ssl_pyd.name} OK", flush=True)


def report(paths: Iterable[Path]) -> None:
    for path in paths:
        ver = openssl_version_from_file(path) or "version unknown"
        print(f"  {path.name}: {ver}", flush=True)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--internal", required=True, help="Frozen _internal directory")
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Interpreter whose OpenSSL DLLs should be shipped",
    )
    parser.add_argument(
        "--ssl-smoke",
        action="store_true",
        help="LoadLibrary bundled libcrypto/libssl (Windows)",
    )
    args = parser.parse_args(argv)
    internal = Path(args.internal).expanduser().resolve()
    python = Path(args.python).expanduser()
    prefix = Path(sys.base_prefix)
    if python.resolve() != Path(sys.executable).resolve():
        import subprocess

        proc = subprocess.run(
            [str(python), "-c", "import sys; print(sys.base_prefix)"],
            check=False,
            text=True,
            capture_output=True,
        )
        if proc.returncode == 0 and (proc.stdout or "").strip():
            prefix = Path(proc.stdout.strip())
    print(f"[win_ssl_bundle_align] Python ssl.OPENSSL_VERSION={python_openssl_version(python) or 'unknown'}", flush=True)
    print(f"[win_ssl_bundle_align] copy OpenSSL DLLs from {prefix} -> {internal}", flush=True)
    copied = copy_openssl_dlls(prefix, internal)
    if not copied:
        print("  no libssl*/libcrypto* DLLs next to this Python (nothing to copy)", flush=True)
    else:
        report(copied)
    verify_internal(internal)
    leftover = list(internal.glob("libcrypto*.dll")) + list(internal.glob("libssl*.dll"))
    if leftover:
        print("[win_ssl_bundle_align] bundled OpenSSL after copy:", flush=True)
        report(leftover)
    if args.ssl_smoke:
        smoke_load_dlls(internal)
    print("[win_ssl_bundle_align] OK", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
