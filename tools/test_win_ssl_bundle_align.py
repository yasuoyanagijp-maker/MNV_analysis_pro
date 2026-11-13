import tempfile
import unittest
from pathlib import Path

from tools.win_ssl_bundle_align import (
    copy_openssl_dlls,
    iter_python_openssl_dlls,
    openssl_version_from_file,
    verify_internal,
)


class TestWinSslBundleAlign(unittest.TestCase):
    def test_iter_python_openssl_dlls_skips_duplicates(self):
        with tempfile.TemporaryDirectory() as raw:
            prefix = Path(raw) / "Python312"
            dlls = prefix / "DLLs"
            dlls.mkdir(parents=True)
            (prefix / "libcrypto-3.dll").write_bytes(b"root")
            (dlls / "libcrypto-3.dll").write_bytes(b"dlls")
            (dlls / "libssl-3.dll").write_bytes(b"ssl")
            found = iter_python_openssl_dlls(prefix)
            names = [p.name for p in found]
            self.assertEqual(names.count("libcrypto-3.dll"), 1)
            self.assertIn("libssl-3.dll", names)

    def test_copy_overwrites_opencv_older_dll(self):
        with tempfile.TemporaryDirectory() as raw:
            prefix = Path(raw) / "Python312"
            prefix.mkdir()
            (prefix / "libcrypto-3.dll").write_bytes(b"\x00OpenSSL 3.3.2 4 Jun 2024\x00")
            (prefix / "libssl-3.dll").write_bytes(b"\x00OpenSSL 3.3.2 4 Jun 2024\x00")
            internal = Path(raw) / "_internal"
            internal.mkdir()
            (internal / "libcrypto-3.dll").write_bytes(b"\x00OpenSSL 3.2.0 23 Nov 2023\x00")
            (internal / "_ssl.pyd").write_bytes(b"pyd")
            copied = copy_openssl_dlls(prefix, internal)
            self.assertEqual({p.name for p in copied}, {"libcrypto-3.dll", "libssl-3.dll"})
            self.assertIn("3.3.2", openssl_version_from_file(internal / "libcrypto-3.dll"))
            verify_internal(internal)

    def test_verify_internal_fails_without_libcrypto(self):
        with tempfile.TemporaryDirectory() as raw:
            internal = Path(raw) / "_internal"
            internal.mkdir()
            (internal / "_ssl.pyd").write_bytes(b"pyd")
            with self.assertRaises(SystemExit) as caught:
                verify_internal(internal)
            self.assertIn("libcrypto", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
