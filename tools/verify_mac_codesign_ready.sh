#!/usr/bin/env bash
# Fail if *.dist-info / *.egg-info remain where codesign --deep would choke.
set -euo pipefail

APP_PATH="${1:?Usage: verify_mac_codesign_ready.sh ARIAKE_OCTA.app}"

if [[ ! -d "$APP_PATH" ]]; then
    echo "[verify_mac_codesign_ready] ERROR: not a directory: ${APP_PATH}" >&2
    exit 1
fi

bad=()
while IFS= read -r -d '' path; do
    bad+=("$path")
done < <(find "$APP_PATH/Contents/Frameworks" "$APP_PATH/Contents/Resources" -maxdepth 1 \( -name '*.dist-info' -o -name '*.egg-info' \) -print0 2>/dev/null)

if [[ ${#bad[@]} -gt 0 ]]; then
    echo "[verify_mac_codesign_ready] ERROR: ${#bad[@]} pip metadata dir(s) under Frameworks/Resources:" >&2
    printf '  %s\n' "${bad[@]}" >&2
    exit 1
fi

if [[ "$(uname -s)" == "Darwin" ]] && command -v codesign >/dev/null 2>&1; then
    if ! codesign --verify --deep --strict "$APP_PATH" 2>/tmp/codesign_verify.err; then
        echo "[verify_mac_codesign_ready] ERROR: codesign --verify failed:" >&2
        cat /tmp/codesign_verify.err >&2
        exit 1
    fi
    echo "[verify_mac_codesign_ready] OK (no pip metadata; codesign verify passed)"
else
    echo "[verify_mac_codesign_ready] OK (no pip metadata; codesign verify skipped on this host)"
fi
