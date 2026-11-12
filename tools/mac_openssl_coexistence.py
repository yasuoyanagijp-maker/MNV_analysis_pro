#!/usr/bin/env python3
"""Keep OpenSSL 1.1 and 3 side-by-side inside a macOS .app, and ship the
OpenSSL *patch* that Python's _ssl.so was built against.

v1.2.4-mac rewrote *every* libcrypto install name to match Python's _ssl.so
(OpenSSL 1.1). OpenCV's libssl.3.dylib still needs OpenSSL 3 symbols
(_ASYNC_WAIT_CTX_get_status), so cv2 import dies and the login UI never
reaches FastAPI.

A later Intel GitHub Actions Python 3.9 links _ssl against OpenSSL 3.3+
(X509_STORE_get1_objects). PyInstaller still copies OpenCV's libcrypto.3.dylib
(OpenSSL 3.2.0, 23 Nov 2023) into Contents/Frameworks. import ssl then dies
and the Flet window closes. After the 1.1/3 name fix, overwrite the
Frameworks libssl/libcrypto *pair* with the dylibs that this Python's _ssl
was linked against. Do not point OpenCV's cv2/.dylibs copies at 1.1.

install_name_tool -change keeps the Mach-O compatibility version, so a
broken rewrite looks like:

    @rpath/libcrypto.1.1.dylib (compatibility version 3.0.0, ...)

Compatibility version is the source of truth. Never point an OpenSSL 3
binary at libcrypto.1.1, or an OpenSSL 1.1 binary at libcrypto.3.

Usage:
  python3 tools/mac_openssl_coexistence.py --fix /Applications/ARIAKE_OCTA.app
  python3 tools/mac_openssl_coexistence.py --fix /Applications/ARIAKE_OCTA.app --sign
  python3 tools/mac_openssl_coexistence.py --verify /Applications/ARIAKE_OCTA.app
  python3 tools/mac_openssl_coexistence.py --fix dist/ARIAKE_OCTA.app --verify dist/ARIAKE_OCTA.app --ssl-smoke
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
SSL_LIB_NAMES = {
    "1.1": {"ssl": "libssl.1.1.dylib", "crypto": "libcrypto.1.1.dylib"},
    "3": {"ssl": "libssl.3.dylib", "crypto": "libcrypto.3.dylib"},
}
OPENSSL_VERSION_RE = re.compile(r"OpenSSL\s+(\d+)\.(\d+)\.(\d+)")
OPENSSL_LIKE_PREFIXES = (
    "SSL_",
    "TLS_",
    "DTLS",
    "X509",
    "EVP_",
    "BIO_",
    "CRYPTO_",
    "OPENSSL_",
    "ERR_",
    "HMAC_",
    "RAND_",
    "SHA",
    "AES_",
    "PKCS",
    "OCSP",
    "CMS_",
    "ASN1_",
    "PEM_",
    "EC_",
    "RSA_",
    "DH_",
    "BN_",
    "NCONF_",
    "CONF_",
    "ENGINE_",
    "UI_",
    "COMP_",
    "SCT_",
    "KDF_",
    "OSSL_",
    "PROV_",
    "d2i_",
    "i2d_",
)
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


def openssl_like_symbol(sym: str) -> bool:
    s = sym.lstrip("_")
    return s.startswith(OPENSSL_LIKE_PREFIXES) or "X509" in s


def parse_openssl_version_text(text: str) -> Optional[Tuple[int, int, int]]:
    match = OPENSSL_VERSION_RE.search(text or "")
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def openssl_version_from_file(path: Path) -> str:
    """Return OPENSSL_VERSION_TEXT-like string from a dylib/DLL, or ''."""
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    match = re.search(rb"OpenSSL \d+\.\d+\.\d+[^\x00]{0,48}", data)
    if not match:
        return ""
    return match.group(0).decode("ascii", errors="replace").strip()


def find_bundled_ssl_so(app: Path) -> Optional[Path]:
    matches = [p for p in app.rglob("_ssl*.so") if p.is_file() and not p.is_symlink()]
    if not matches:
        return None
    for path in matches:
        if "lib-dynload" in path.parts:
            return path
    return sorted(matches)[0]


def ssl_needed_major_from_otool(text: str) -> Optional[str]:
    ident, deps = parse_otool_l(text)
    items = list(deps)
    if ident is not None:
        items.append(ident)
    for dep in items:
        base = Path(dep.install_name).name
        if "libssl.3" in base or "libcrypto.3" in base:
            return "3"
        if "libssl.1.1" in base or "libcrypto.1.1" in base:
            return "1.1"
        if "libssl" in base or "libcrypto" in base:
            from_compat = openssl_major_from_compat(dep.compat)
            if from_compat:
                return from_compat
    return None


def ssl_needed_major(ssl_so: Path) -> Optional[str]:
    return ssl_needed_major_from_otool(otool_l(ssl_so))


def nm_symbol_names(path: Path, *nm_args: str) -> set:
    proc = _run(["nm", *nm_args, str(path)], check=False)
    names = set()
    for raw in (proc.stdout or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        names.add(line.split()[-1])
    return names


def openssl_undefined_in_ssl(ssl_so: Path) -> set:
    return {s for s in nm_symbol_names(ssl_so, "-u") if openssl_like_symbol(s)}


def openssl_defined_in_pair(paths: Sequence[Path]) -> set:
    names: set = set()
    for path in paths:
        if path.is_file():
            names |= nm_symbol_names(path, "-gU")
    return names


def missing_ssl_symbols(ssl_so: Path, libs: Sequence[Path]) -> List[str]:
    needed = openssl_undefined_in_ssl(ssl_so)
    have = openssl_defined_in_pair(libs)
    return sorted(needed - have)


def python_ssl_so(python: Path) -> Optional[Path]:
    proc = _run(
        [
            str(python),
            "-c",
            "import _ssl, pathlib; print(pathlib.Path(_ssl.__file__).resolve())",
        ],
        check=False,
    )
    if proc.returncode != 0:
        return None
    text = (proc.stdout or "").strip()
    if not text:
        return None
    path = Path(text)
    return path if path.is_file() else None


def python_base_prefix(python: Path) -> Optional[Path]:
    proc = _run([str(python), "-c", "import sys; print(sys.base_prefix)"], check=False)
    if proc.returncode != 0:
        return None
    text = (proc.stdout or "").strip()
    return Path(text) if text else None


def python_openssl_version(python: Path) -> str:
    proc = _run(
        [str(python), "-c", "import ssl; print(ssl.OPENSSL_VERSION)"],
        check=False,
    )
    if proc.returncode != 0:
        return ""
    return (proc.stdout or "").strip()


def rpath_dirs(binary: Path) -> List[Path]:
    proc = _run(["otool", "-l", str(binary)], check=False)
    dirs: List[Path] = []
    lines = (proc.stdout or "").splitlines()
    for i, line in enumerate(lines):
        if "cmd LC_RPATH" not in line:
            continue
        for follow in lines[i : i + 6]:
            if "path " not in follow:
                continue
            raw = follow.strip().split("path ", 1)[-1]
            raw = raw.split(" (", 1)[0].strip()
            raw = raw.replace("@loader_path", str(binary.parent))
            raw = raw.replace("@executable_path", str(binary.parent))
            path = Path(raw)
            if path.is_dir():
                dirs.append(path)
            break
    return dirs


def resolve_linked_dylib(
    install_name: str, ssl_so: Path, extra_dirs: Sequence[Path]
) -> Optional[Path]:
    name = Path(install_name).name
    if install_name.startswith("@loader_path/"):
        candidate = ssl_so.parent / install_name.split("/", 1)[-1]
        if candidate.is_file():
            return candidate
    absolute = Path(install_name)
    if not install_name.startswith("@") and absolute.is_file():
        return absolute
    for directory in list(extra_dirs) + rpath_dirs(ssl_so) + [ssl_so.parent]:
        candidate = Path(directory) / name
        if candidate.is_file():
            return candidate
    return None


def openssl_pair_search_dirs(python: Path, ssl_so: Optional[Path]) -> List[Path]:
    dirs: List[Path] = []
    prefix = python_base_prefix(python)
    if prefix:
        dirs.extend([prefix / "lib", prefix / "lib" / "openssl", prefix])
    if ssl_so is not None:
        try:
            dirs.append(ssl_so.parents[2])
            dirs.append(ssl_so.parents[3] / "lib")
        except IndexError:
            pass
        dirs.extend(rpath_dirs(ssl_so))
        dirs.append(ssl_so.parent)
    for major_dirs in HOMEBREW_DIRS.values():
        dirs.extend(Path(p) for p in major_dirs)
    out: List[Path] = []
    seen = set()
    for directory in dirs:
        try:
            key = str(directory.resolve()) if directory.exists() else str(directory)
        except OSError:
            key = str(directory)
        if key in seen:
            continue
        seen.add(key)
        out.append(directory)
    return out


def find_openssl_pair_for_python(python: Path, major: str) -> Optional[Tuple[Path, Path]]:
    ssl_name = SSL_LIB_NAMES[major]["ssl"]
    crypto_name = SSL_LIB_NAMES[major]["crypto"]
    ssl_so = python_ssl_so(python)
    dirs = openssl_pair_search_dirs(python, ssl_so)
    ssl_src: Optional[Path] = None
    crypto_src: Optional[Path] = None
    if ssl_so is not None:
        _ident, deps = parse_otool_l(otool_l(ssl_so))
        for dep in deps:
            resolved = resolve_linked_dylib(dep.install_name, ssl_so, dirs)
            if resolved is None:
                continue
            base = Path(dep.install_name).name
            if "libssl" in base:
                ssl_src = resolved
            elif "libcrypto" in base:
                crypto_src = resolved
        if ssl_src is not None and crypto_src is None:
            sibling = ssl_src.parent / crypto_name
            if sibling.is_file():
                crypto_src = sibling
        if crypto_src is not None and ssl_src is None:
            sibling = crypto_src.parent / ssl_name
            if sibling.is_file():
                ssl_src = sibling
    if ssl_src is None or crypto_src is None:
        for directory in dirs:
            ssl_candidate = directory / ssl_name
            crypto_candidate = directory / crypto_name
            if ssl_candidate.is_file() and crypto_candidate.is_file():
                ssl_src, crypto_src = ssl_candidate, crypto_candidate
                break
    if ssl_src is not None and crypto_src is not None:
        return ssl_src, crypto_src
    return None


def frameworks_pair(app: Path, major: str) -> Tuple[Path, Path]:
    fw = app / "Contents" / "Frameworks"
    return fw / SSL_LIB_NAMES[major]["ssl"], fw / SSL_LIB_NAMES[major]["crypto"]


def install_openssl_pair(app: Path, major: str, ssl_src: Path, crypto_src: Path) -> None:
    fw = app / "Contents" / "Frameworks"
    fw.mkdir(parents=True, exist_ok=True)
    ssl_dest, crypto_dest = frameworks_pair(app, major)
    for src, dest in ((crypto_src, crypto_dest), (ssl_src, ssl_dest)):
        if dest.is_symlink() or dest.exists():
            if dest.exists() and dest.is_file() and not dest.is_symlink():
                make_writable(dest)
            dest.unlink()
        shutil.copy2(src, dest)
        dest.chmod(0o755)
        make_writable(dest)
        _run(["install_name_tool", "-id", f"@rpath/{dest.name}", str(dest)], check=False)
    retarget_binary(crypto_dest)
    retarget_binary(ssl_dest)


def pair_needs_replace(
    ssl_so: Path, libs: Sequence[Path], python: Path
) -> Tuple[bool, str]:
    existing = [p for p in libs if p.is_file()]
    if not existing:
        return True, "Frameworks OpenSSL pair missing"
    if shutil.which("nm"):
        missing = missing_ssl_symbols(ssl_so, existing)
        if missing:
            preview = ", ".join(missing[:8])
            return True, f"missing symbols ({preview})"
    py_ver = python_openssl_version(python)
    crypto = next((p for p in existing if "libcrypto" in p.name), existing[-1])
    bundled_ver = openssl_version_from_file(crypto)
    py_t = parse_openssl_version_text(py_ver)
    bun_t = parse_openssl_version_text(bundled_ver)
    if py_t and bun_t and py_t > bun_t:
        return True, f"bundled {bundled_ver} older than Python {py_ver}"
    if py_t and bun_t and py_t < bun_t:
        return False, f"bundled {bundled_ver} newer than Python {py_ver}; keep bundled"
    return False, f"OK ({bundled_ver or py_ver or 'unknown'})"


def align_python_openssl(app: Path, python: Path) -> None:
    ssl_so = find_bundled_ssl_so(app)
    if ssl_so is None:
        print("  no bundled _ssl*.so; skip Python OpenSSL align", flush=True)
        return
    major = ssl_needed_major(ssl_so)
    if major is None:
        rel = ssl_so.relative_to(app)
        print(f"  {rel}: no libssl/libcrypto load command; skip", flush=True)
        return
    ssl_dest, crypto_dest = frameworks_pair(app, major)
    py_ver = python_openssl_version(python)
    print(f"  Python ssl.OPENSSL_VERSION={py_ver or 'unknown'}", flush=True)
    print(f"  bundled _ssl needs OpenSSL {major}: {ssl_so.relative_to(app)}", flush=True)
    for path in (ssl_dest, crypto_dest):
        if path.is_file():
            print(
                f"  Frameworks/{path.name}: {openssl_version_from_file(path) or 'version unknown'}",
                flush=True,
            )
    replace, reason = pair_needs_replace(ssl_so, [ssl_dest, crypto_dest], python)
    if not replace:
        print(f"  OpenSSL align skip ({reason})", flush=True)
        return
    print(f"  OpenSSL align: {reason}", flush=True)
    pair = find_openssl_pair_for_python(python, major)
    if pair is None:
        raise SystemExit(
            f"[mac_openssl_coexistence] _ssl needs OpenSSL {major} but no matching "
            f"{SSL_LIB_NAMES[major]['ssl']} / {SSL_LIB_NAMES[major]['crypto']} "
            f"were found for {python}"
        )
    ssl_src, crypto_src = pair
    print(f"  copy ssl    {ssl_src}", flush=True)
    print(f"    {openssl_version_from_file(ssl_src) or 'unknown'}", flush=True)
    print(f"  copy crypto {crypto_src}", flush=True)
    print(f"    {openssl_version_from_file(crypto_src) or 'unknown'}", flush=True)
    install_openssl_pair(app, major, ssl_src, crypto_src)
    if shutil.which("nm"):
        missing = missing_ssl_symbols(ssl_so, [ssl_dest, crypto_dest])
        if missing:
            raise SystemExit(
                "[mac_openssl_coexistence] _ssl still missing OpenSSL symbols "
                "after align: " + ", ".join(missing[:12])
            )
    print(
        f"  Frameworks/{crypto_dest.name} now "
        f"{openssl_version_from_file(crypto_dest) or 'unknown'}",
        flush=True,
    )


def verify_ssl_symbols(app: Path) -> None:
    ssl_so = find_bundled_ssl_so(app)
    if ssl_so is None:
        return
    major = ssl_needed_major(ssl_so)
    if major is None:
        return
    if shutil.which("nm") is None:
        print("[mac_openssl_coexistence] ssl symbol check skipped (nm not found)", flush=True)
        return
    ssl_dest, crypto_dest = frameworks_pair(app, major)
    missing = missing_ssl_symbols(ssl_so, [ssl_dest, crypto_dest])
    if missing:
        print("[mac_openssl_coexistence] ERROR: _ssl OpenSSL symbols missing:", file=sys.stderr)
        for name in missing[:20]:
            print(f"  {name}", file=sys.stderr)
        raise SystemExit(1)
    print(
        "[mac_openssl_coexistence] _ssl OpenSSL symbols OK "
        f"(lib {openssl_version_from_file(crypto_dest) or 'unknown'})",
        flush=True,
    )


def smoke_dlopen_ssl(app: Path) -> None:
    if sys.platform != "darwin":
        print("[ssl-smoke] skipped (not Darwin)", flush=True)
        return
    ssl_so = find_bundled_ssl_so(app)
    if ssl_so is None:
        print("[ssl-smoke] skipped (no _ssl*.so)", flush=True)
        return
    major = ssl_needed_major(ssl_so) or "3"
    ssl_dest, crypto_dest = frameworks_pair(app, major)
    try:
        import ctypes
    except ImportError:
        print("[ssl-smoke] skipped (no ctypes)", flush=True)
        return
    for path in (crypto_dest, ssl_dest):
        if not path.is_file():
            raise SystemExit(f"[ssl-smoke] missing {path}")
        try:
            ctypes.CDLL(str(path))
        except OSError as exc:
            raise SystemExit(f"[ssl-smoke] dlopen {path.name} failed: {exc}") from exc
        print(f"[ssl-smoke] dlopen {path.name} OK", flush=True)
    try:
        ctypes.CDLL(str(ssl_so))
    except OSError as exc:
        err = str(exc)
        if "X509_STORE_get1_objects" in err or (
            "Symbol not found" in err and "libcrypto" in err
        ):
            raise SystemExit(f"[ssl-smoke] {ssl_so.name} OpenSSL mismatch: {exc}") from exc
        print(f"[ssl-smoke] {ssl_so.name} dlopen skipped ({exc})", flush=True)
        return
    print(f"[ssl-smoke] dlopen {ssl_so.name} OK", flush=True)


def adhoc_sign(app: Path) -> None:
    helper = Path(__file__).resolve().parent / "mac_adhoc_codesign.sh"
    if helper.is_file():
        print(f"  bash {helper.name} sign", flush=True)
        proc = _run(["bash", str(helper), "sign", str(app)], check=False)
        if proc.returncode != 0:
            sys.stderr.write(proc.stderr or proc.stdout or "codesign failed\n")
            raise SystemExit(proc.returncode)
        if proc.stdout:
            print(proc.stdout, end="" if proc.stdout.endswith("\n") else "\n", flush=True)
        return
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
        "--python",
        default=sys.executable,
        help="Interpreter whose _ssl OpenSSL pair should be shipped (default: this Python)",
    )
    parser.add_argument(
        "--sign",
        action="store_true",
        help="Ad-hoc codesign after --fix (for already-installed apps)",
    )
    parser.add_argument(
        "--ssl-smoke",
        action="store_true",
        help="dlopen bundled libssl/libcrypto and _ssl.so (Darwin)",
    )
    args = parser.parse_args(argv)
    if not args.fix and not args.verify:
        parser.error("specify --fix and/or --verify")
    python = Path(args.python).expanduser()
    if args.fix:
        app = Path(args.fix).expanduser().resolve()
        print(f"[mac_openssl_coexistence] fix {app}", flush=True)
        fix_app(app)
        print(f"[mac_openssl_coexistence] align _ssl OpenSSL from {python}", flush=True)
        align_python_openssl(app, python)
        if args.sign:
            adhoc_sign(app)
    if args.verify:
        app = Path(args.verify).expanduser().resolve()
        verify_app(app)
        verify_ssl_symbols(app)
        if args.ssl_smoke:
            smoke_dlopen_ssl(app)
    elif args.fix:
        app = Path(args.fix).expanduser().resolve()
        verify_app(app)
        verify_ssl_symbols(app)
        if args.ssl_smoke:
            smoke_dlopen_ssl(app)
    return 0


if __name__ == "__main__":
    sys.exit(main())
