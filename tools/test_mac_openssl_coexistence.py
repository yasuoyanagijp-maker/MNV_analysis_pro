from pathlib import Path

from tools.mac_openssl_coexistence import (
    classify_libcrypto_dep,
    desired_libcrypto_name,
    openssl_major_from_compat,
    openssl_major_from_name,
    parse_otool_l,
)


BROKEN_LIBSSL3 = """/app/Contents/Frameworks/cv2/.dylibs/libssl.3.dylib:
\t@rpath/libssl.3.dylib (compatibility version 3.0.0, current version 3.0.0)
\t@rpath/libcrypto.1.1.dylib (compatibility version 3.0.0, current version 3.0.0)
\t/usr/lib/libSystem.B.dylib (compatibility version 1.0.0, current version 1292.100.5)
"""

PYTHON_SSL = """/app/Contents/Frameworks/python3.9/lib-dynload/_ssl.cpython-39-darwin.so:
\t@rpath/libssl.1.1.dylib (compatibility version 1.1.0, current version 1.1.0)
\t@rpath/libcrypto.1.1.dylib (compatibility version 1.1.0, current version 1.1.0)
\t/usr/lib/libSystem.B.dylib (compatibility version 1.0.0, current version 1311.0.0)
"""

FIXED_LIBSSL3 = """/app/Contents/Frameworks/cv2/.dylibs/libssl.3.dylib:
\t@rpath/libssl.3.dylib (compatibility version 3.0.0, current version 3.0.0)
\t@loader_path/libcrypto.3.dylib (compatibility version 3.0.0, current version 3.0.0)
\t/usr/lib/libSystem.B.dylib (compatibility version 1.0.0, current version 1292.100.5)
"""


def test_compat_version_is_source_of_truth():
    assert openssl_major_from_compat("3.0.0") == "3"
    assert openssl_major_from_compat("1.1.0") == "1.1"
    assert openssl_major_from_compat("1.0.0") is None


def test_name_fallback():
    assert openssl_major_from_name("@rpath/libcrypto.3.dylib") == "3"
    assert openssl_major_from_name("@rpath/libcrypto.1.1.dylib") == "1.1"


def test_classify_rewritten_ssl3_still_openssl3():
    major = classify_libcrypto_dep("@rpath/libcrypto.1.1.dylib", "3.0.0")
    assert major == "3"


def test_classify_python_ssl_stays_openssl11():
    major = classify_libcrypto_dep("@rpath/libcrypto.1.1.dylib", "1.1.0")
    assert major == "1.1"


def test_classify_skips_apple_libressl():
    assert classify_libcrypto_dep("/usr/lib/libcrypto.44.dylib", "1.0.0") is None


def test_classify_ignores_libssl_load_commands():
    assert classify_libcrypto_dep("@rpath/libssl.3.dylib", "3.0.0") is None


def test_parse_otool_l_splits_id_and_deps():
    ident, deps = parse_otool_l(BROKEN_LIBSSL3)
    assert ident is not None
    assert ident.install_name == "@rpath/libssl.3.dylib"
    assert len(deps) == 2
    crypto = [d for d in deps if "libcrypto" in d.install_name][0]
    assert crypto.install_name == "@rpath/libcrypto.1.1.dylib"
    assert crypto.compat == "3.0.0"
    assert classify_libcrypto_dep(crypto.install_name, crypto.compat) == "3"


def test_desired_name_prefers_sibling_loader_path(tmp_path: Path):
    dylib_dir = tmp_path / "cv2" / ".dylibs"
    dylib_dir.mkdir(parents=True)
    (dylib_dir / "libcrypto.3.dylib").write_bytes(b"fake")
    libssl = dylib_dir / "libssl.3.dylib"
    libssl.write_bytes(b"fake")
    assert desired_libcrypto_name(libssl, "3") == "@loader_path/libcrypto.3.dylib"


def test_desired_name_uses_rpath_without_sibling(tmp_path: Path):
    libdir = tmp_path / "lib-dynload"
    libdir.mkdir()
    ssl_so = libdir / "_ssl.cpython-39-darwin.so"
    ssl_so.write_bytes(b"fake")
    assert desired_libcrypto_name(ssl_so, "1.1") == "@rpath/libcrypto.1.1.dylib"


def test_broken_sample_is_a_mismatch():
    ident, deps = parse_otool_l(BROKEN_LIBSSL3)
    crypto = [d for d in deps if "libcrypto" in d.install_name][0]
    name_major = openssl_major_from_name(crypto.install_name)
    classified = classify_libcrypto_dep(crypto.install_name, crypto.compat)
    assert name_major == "1.1"
    assert classified == "3"
    assert name_major != classified


def test_fixed_and_python_samples_are_consistent():
    for sample in (FIXED_LIBSSL3, PYTHON_SSL):
        _, deps = parse_otool_l(sample)
        for dep in deps:
            major = classify_libcrypto_dep(dep.install_name, dep.compat)
            if major is None:
                continue
            name_major = openssl_major_from_name(dep.install_name)
            assert name_major == major
