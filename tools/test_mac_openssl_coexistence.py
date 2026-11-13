import tempfile
import unittest
from pathlib import Path

from tools.mac_openssl_coexistence import (
    classify_libcrypto_dep,
    desired_libcrypto_name,
    find_bundled_ssl_so,
    openssl_like_symbol,
    openssl_major_from_compat,
    openssl_major_from_name,
    openssl_version_from_file,
    parse_openssl_version_text,
    parse_otool_l,
    ssl_needed_major_from_otool,
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

PYTHON_SSL3 = """/app/Contents/Frameworks/python3.9/lib-dynload/_ssl.cpython-39-darwin.so:
\t@rpath/libssl.3.dylib (compatibility version 3.0.0, current version 3.3.0)
\t@rpath/libcrypto.3.dylib (compatibility version 3.0.0, current version 3.3.0)
\t/usr/lib/libSystem.B.dylib (compatibility version 1.0.0, current version 1311.0.0)
"""


class TestMacOpensslCoexistence(unittest.TestCase):
    def test_compat_version_is_source_of_truth(self):
        self.assertEqual(openssl_major_from_compat("3.0.0"), "3")
        self.assertEqual(openssl_major_from_compat("1.1.0"), "1.1")
        self.assertIsNone(openssl_major_from_compat("1.0.0"))

    def test_name_fallback(self):
        self.assertEqual(openssl_major_from_name("@rpath/libcrypto.3.dylib"), "3")
        self.assertEqual(openssl_major_from_name("@rpath/libcrypto.1.1.dylib"), "1.1")

    def test_classify_rewritten_ssl3_still_openssl3(self):
        self.assertEqual(classify_libcrypto_dep("@rpath/libcrypto.1.1.dylib", "3.0.0"), "3")

    def test_classify_python_ssl_stays_openssl11(self):
        self.assertEqual(classify_libcrypto_dep("@rpath/libcrypto.1.1.dylib", "1.1.0"), "1.1")

    def test_classify_skips_apple_libressl(self):
        self.assertIsNone(classify_libcrypto_dep("/usr/lib/libcrypto.44.dylib", "1.0.0"))

    def test_classify_ignores_libssl_load_commands(self):
        self.assertIsNone(classify_libcrypto_dep("@rpath/libssl.3.dylib", "3.0.0"))

    def test_parse_otool_l_splits_id_and_deps(self):
        ident, deps = parse_otool_l(BROKEN_LIBSSL3)
        self.assertIsNotNone(ident)
        self.assertEqual(ident.install_name, "@rpath/libssl.3.dylib")
        self.assertEqual(len(deps), 2)
        crypto = [d for d in deps if "libcrypto" in d.install_name][0]
        self.assertEqual(crypto.install_name, "@rpath/libcrypto.1.1.dylib")
        self.assertEqual(crypto.compat, "3.0.0")
        self.assertEqual(classify_libcrypto_dep(crypto.install_name, crypto.compat), "3")

    def test_desired_name_prefers_sibling_loader_path(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp_path = Path(raw)
            dylib_dir = tmp_path / "cv2" / ".dylibs"
            dylib_dir.mkdir(parents=True)
            (dylib_dir / "libcrypto.3.dylib").write_bytes(b"fake")
            libssl = dylib_dir / "libssl.3.dylib"
            libssl.write_bytes(b"fake")
            self.assertEqual(desired_libcrypto_name(libssl, "3"), "@loader_path/libcrypto.3.dylib")

    def test_desired_name_uses_rpath_without_sibling(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp_path = Path(raw)
            libdir = tmp_path / "lib-dynload"
            libdir.mkdir()
            ssl_so = libdir / "_ssl.cpython-39-darwin.so"
            ssl_so.write_bytes(b"fake")
            self.assertEqual(desired_libcrypto_name(ssl_so, "1.1"), "@rpath/libcrypto.1.1.dylib")

    def test_broken_sample_is_a_mismatch(self):
        _ident, deps = parse_otool_l(BROKEN_LIBSSL3)
        crypto = [d for d in deps if "libcrypto" in d.install_name][0]
        name_major = openssl_major_from_name(crypto.install_name)
        classified = classify_libcrypto_dep(crypto.install_name, crypto.compat)
        self.assertEqual(name_major, "1.1")
        self.assertEqual(classified, "3")
        self.assertNotEqual(name_major, classified)

    def test_fixed_and_python_samples_are_consistent(self):
        for sample in (FIXED_LIBSSL3, PYTHON_SSL):
            _, deps = parse_otool_l(sample)
            for dep in deps:
                major = classify_libcrypto_dep(dep.install_name, dep.compat)
                if major is None:
                    continue
                name_major = openssl_major_from_name(dep.install_name)
                self.assertEqual(name_major, major)

    def test_ssl_needed_major_detects_openssl3_and_11(self):
        self.assertEqual(ssl_needed_major_from_otool(PYTHON_SSL3), "3")
        self.assertEqual(ssl_needed_major_from_otool(PYTHON_SSL), "1.1")

    def test_openssl_version_parse_and_file_bytes(self):
        self.assertEqual(parse_openssl_version_text("OpenSSL 3.2.0 23 Nov 2023"), (3, 2, 0))
        self.assertEqual(parse_openssl_version_text("OpenSSL 3.3.2 4 Jun 2024"), (3, 3, 2))
        older = parse_openssl_version_text("OpenSSL 3.2.0 23 Nov 2023")
        newer = parse_openssl_version_text("OpenSSL 3.3.2 4 Jun 2024")
        self.assertIsNotNone(older)
        self.assertIsNotNone(newer)
        self.assertGreater(newer, older)
        with tempfile.TemporaryDirectory() as raw:
            blob = Path(raw) / "libcrypto.3.dylib"
            blob.write_bytes(b"junk\x00OpenSSL 3.2.0 23 Nov 2023\x00more")
            self.assertEqual(openssl_version_from_file(blob), "OpenSSL 3.2.0 23 Nov 2023")

    def test_openssl_like_symbol_catches_x509_store(self):
        self.assertTrue(openssl_like_symbol("_X509_STORE_get1_objects"))
        self.assertTrue(openssl_like_symbol("SSL_new"))
        self.assertFalse(openssl_like_symbol("_PyInit__ssl"))
        self.assertFalse(openssl_like_symbol("_malloc"))

    def test_find_bundled_ssl_so_prefers_lib_dynload(self):
        with tempfile.TemporaryDirectory() as raw:
            app = Path(raw) / "ARIAKE_OCTA.app"
            other = app / "Contents" / "Frameworks" / "_ssl.cpython-39-darwin.so"
            dyn = (
                app
                / "Contents"
                / "Frameworks"
                / "python3.9"
                / "lib-dynload"
                / "_ssl.cpython-39-darwin.so"
            )
            other.parent.mkdir(parents=True)
            dyn.parent.mkdir(parents=True)
            other.write_bytes(b"x")
            dyn.write_bytes(b"y")
            self.assertEqual(find_bundled_ssl_so(app), dyn)


if __name__ == "__main__":
    unittest.main()
