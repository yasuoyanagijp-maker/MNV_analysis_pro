import subprocess
import sys
from pathlib import Path

from tools.patch_mac_v123_resign import _run


def test_run_check_false_returns_nonzero_instead_of_raising():
    proc = _run(["bash", "-c", "echo fail-stderr >&2; exit 7"], check=False)
    assert proc.returncode == 7
    assert "fail-stderr" in (proc.stderr or "")


def test_run_check_true_raises_on_failure():
    try:
        _run(["bash", "-c", "exit 3"], check=True)
    except subprocess.CalledProcessError as exc:
        assert exc.returncode == 3
    else:
        raise AssertionError("expected CalledProcessError")
