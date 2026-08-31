import platform
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "require_mac_python_arch.sh"


def _host_pair():
    machine = platform.machine()
    if machine in ("x86_64", "amd64", "AMD64"):
        return "x86_64", "arm64"
    if machine in ("arm64", "aarch64", "ARM64"):
        return "arm64", "x86_64"
    return None


def test_require_mac_python_arch_ok_on_host():
    pair = _host_pair()
    if pair is None:
        return
    expected, _ = pair
    proc = subprocess.run(
        ["bash", str(SCRIPT), sys.executable, expected],
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "OK" in proc.stdout


def test_require_mac_python_arch_rejects_mismatch():
    pair = _host_pair()
    if pair is None:
        return
    _, other = pair
    proc = subprocess.run(
        ["bash", str(SCRIPT), sys.executable, other],
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode != 0
    assert "ERROR" in (proc.stderr or "")
