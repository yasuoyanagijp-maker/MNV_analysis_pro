#!/usr/bin/env bash
# Fail unless PYTHON_BIN is a single-arch interpreter matching EXPECTED (arm64|x86_64).
# Intel zip MUST be built with x86_64 Python 3.9 — arm64 Homebrew Python produces
# IncompatibleBinaryArchError / an arm64 .app even when --intel is passed.
set -euo pipefail

PY="${1:?Usage: require_mac_python_arch.sh PYTHON_BIN arm64|x86_64}"
EXPECTED="${2:?Expected architecture: arm64 or x86_64}"

if [[ "$EXPECTED" != "arm64" && "$EXPECTED" != "x86_64" ]]; then
    echo "[require_mac_python_arch] ERROR: unsupported arch '${EXPECTED}' (use arm64 or x86_64)" >&2
    exit 1
fi

if [[ ! -e "$PY" ]]; then
    echo "[require_mac_python_arch] ERROR: not found: ${PY}" >&2
    exit 1
fi

# Follow venv symlinks so `file` reports the real Mach-O, not "symbolic link".
RESOLVED="$PY"
for _ in 1 2 3 4 5 6 7 8; do
    if [[ -L "$RESOLVED" ]]; then
        link="$(readlink "$RESOLVED")"
        if [[ "$link" != /* ]]; then
            RESOLVED="$(cd "$(dirname "$RESOLVED")" && pwd)/${link}"
        else
            RESOLVED="$link"
        fi
    else
        break
    fi
done

MACHINE="$("$PY" -c "import platform; print(platform.machine())" 2>/dev/null || true)"
case "$MACHINE" in
    x86_64|amd64|AMD64) MACHINE="x86_64" ;;
    arm64|aarch64|ARM64) MACHINE="arm64" ;;
esac

FILE_INFO=""
if command -v file >/dev/null 2>&1; then
    FILE_INFO="$(file -b "$RESOLVED" 2>/dev/null || true)"
fi

echo "[require_mac_python_arch] python=${PY}"
echo "[require_mac_python_arch] resolved=${RESOLVED}"
echo "[require_mac_python_arch] platform.machine=${MACHINE:-unknown}"
[[ -n "$FILE_INFO" ]] && echo "[require_mac_python_arch] file: ${FILE_INFO}"

if [[ "$MACHINE" != "$EXPECTED" ]]; then
    echo "[require_mac_python_arch] ERROR: Python is '${MACHINE:-unknown}', need ${EXPECTED}." >&2
    echo "  Intel zip: python.org macOS 64-bit Python 3.9 (x86_64). Confirm: file \"\$(which python3.9)\"" >&2
    echo "  Apple Silicon: softwareupdate --install-rosetta --agree-to-license" >&2
    echo "    then: arch -x86_64 /usr/local/bin/python3.9 -m venv .venv-intel" >&2
    echo "    ln -sfn .venv-intel .venv   # build_mac.sh reads .venv" >&2
    echo "    arch -x86_64 ./build_mac.sh --skip-notarize --clean --intel" >&2
    echo "  GitHub Actions: dispatch target_arch=x86_64 (runs-on macos-15-intel)." >&2
    echo "  Do NOT use arm64 Homebrew Python with --intel." >&2
    exit 1
fi

# Extra Mach-O check on macOS: reject arm64-only binaries when expecting x86_64.
if [[ "$(uname -s)" == "Darwin" && -n "$FILE_INFO" ]]; then
    if [[ "$EXPECTED" == "x86_64" && "$FILE_INFO" == *"arm64"* && "$FILE_INFO" != *"x86_64"* ]]; then
        echo "[require_mac_python_arch] ERROR: interpreter Mach-O is arm64-only: ${FILE_INFO}" >&2
        exit 1
    fi
    if [[ "$EXPECTED" == "arm64" && "$FILE_INFO" == *"x86_64"* && "$FILE_INFO" != *"arm64"* ]]; then
        echo "[require_mac_python_arch] ERROR: interpreter Mach-O is x86_64-only: ${FILE_INFO}" >&2
        exit 1
    fi
fi

echo "[require_mac_python_arch] OK — Python matches ${EXPECTED}"
