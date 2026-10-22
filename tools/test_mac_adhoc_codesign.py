"""Directory rewrite that lets codesign --deep accept shapely/.dylibs."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "tools" / "mac_adhoc_codesign.sh"


def _prepare(app: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(HELPER), "prepare", str(app)],
        text=True,
        capture_output=True,
    )


def test_rename_dotted_framework_dirs_and_keep_symlinks_relative():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        app = Path(tmp) / "ARIAKE_OCTA.app"
        dylibs = app / "Contents" / "Frameworks" / "shapely" / ".dylibs"
        dylibs.mkdir(parents=True)
        (dylibs / "libgeos.dylib").write_bytes(b"geos")
        nested = dylibs / "vendor.libs"
        nested.mkdir()
        (nested / "lib.dylib").write_bytes(b"v")
        empty_dot = app / "Contents" / "Frameworks" / "cv2" / "__dot__dylibs"
        real_dot = empty_dot.parent / ".dylibs"
        real_dot.mkdir(parents=True)
        (real_dot / "libopencv.dylib").write_bytes(b"cv")
        empty_dot.mkdir()
        inside = app / "Contents" / "Frameworks" / "Python.framework" / "Resources" / ".dylibs"
        inside.mkdir(parents=True)
        (inside / "stay.dylib").write_bytes(b"stay")
        resources = app / "Contents" / "Resources" / "pkg.dist-info"
        resources.mkdir(parents=True)
        (resources / "METADATA").write_text("ok\n", encoding="utf-8")
        (app / "Contents" / "Frameworks" / "._junk").write_bytes(b"junk")

        proc = _prepare(app)
        assert proc.returncode == 0, proc.stdout + proc.stderr

        link = app / "Contents" / "Frameworks" / "shapely" / ".dylibs"
        assert link.is_symlink()
        assert os.readlink(link) == "__dot__dylibs"
        renamed = app / "Contents" / "Frameworks" / "shapely" / "__dot__dylibs"
        assert (renamed / "libgeos.dylib").read_bytes() == b"geos"
        assert (renamed / "vendor.libs").is_symlink()
        assert (renamed / "vendor__dot__libs" / "lib.dylib").read_bytes() == b"v"
        assert (link / "libgeos.dylib").read_bytes() == b"geos"

        cv_link = app / "Contents" / "Frameworks" / "cv2" / ".dylibs"
        assert cv_link.is_symlink()
        assert (app / "Contents" / "Frameworks" / "cv2" / "__dot__dylibs" / "libopencv.dylib").read_bytes() == b"cv"

        framework = app / "Contents" / "Frameworks" / "Python.framework"
        assert framework.is_dir() and not framework.is_symlink()
        assert inside.is_dir() and not inside.is_symlink()
        assert (inside / "stay.dylib").read_bytes() == b"stay"
        assert resources.is_dir() and not resources.is_symlink()
        assert not (app / "Contents" / "Frameworks" / "._junk").exists()

        again = _prepare(app)
        assert again.returncode == 0, again.stdout + again.stderr
        assert link.is_symlink()
        assert os.readlink(link) == "__dot__dylibs"
        assert (link / "libgeos.dylib").read_bytes() == b"geos"


def test_sign_on_linux_prepares_and_skips_codesign():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        app = Path(tmp) / "ARIAKE_OCTA.app"
        dylibs = app / "Contents" / "MacOS" / "shapely" / ".dylibs"
        dylibs.mkdir(parents=True)
        (dylibs / "libgeos.dylib").write_bytes(b"geos")
        proc = subprocess.run(
            ["bash", str(HELPER), "sign", str(app)],
            text=True,
            capture_output=True,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "codesign skipped" in proc.stdout
        link = dylibs
        assert link.is_symlink()
        assert (link / "libgeos.dylib").read_bytes() == b"geos"


if __name__ == "__main__":
    test_rename_dotted_framework_dirs_and_keep_symlinks_relative()
    test_sign_on_linux_prepares_and_skips_codesign()
    print("ok")
