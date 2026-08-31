#!/usr/bin/env bash
# Verify every Mach-O inside a .app matches one expected architecture (arm64 or x86_64).
# Fails on fat/universal binaries or wrong-arch slices (common PyInstaller packaging bug).
set -euo pipefail

APP_PATH="${1:?Usage: verify_mac_app_arch.sh ARIAKE_OCTA.app arm64|x86_64}"
EXPECTED="${2:?Expected architecture: arm64 or x86_64}"

if [[ "$EXPECTED" != "arm64" && "$EXPECTED" != "x86_64" ]]; then
    echo "[verify_mac_app_arch] ERROR: unsupported arch '${EXPECTED}' (use arm64 or x86_64)" >&2
    exit 1
fi

if [[ ! -d "$APP_PATH" ]]; then
    echo "[verify_mac_app_arch] ERROR: not a directory: ${APP_PATH}" >&2
    exit 1
fi

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "[verify_mac_app_arch] skip: not macOS (host cannot run lipo/file reliably)"
    exit 0
fi

WRONG=()
FAT=()
TOTAL=0

while IFS= read -r -d '' binary; do
    [[ -f "$binary" ]] || continue
    info="$(lipo -info "$binary" 2>/dev/null)" || continue
    TOTAL=$((TOTAL + 1))

    if [[ "$info" == *"Architectures in the fat file:"* ]]; then
        # Flet ships universal2 inside flet-macos.tar.gz; allow if expected slice is present.
        case "$binary" in
            *flet-macos*|*/Flet.app/*|*/flet_desktop/app/*)
                if [[ "$EXPECTED" == "arm64" && "$info" == *"arm64"* ]] || \
                   [[ "$EXPECTED" == "x86_64" && "$info" == *"x86_64"* ]]; then
                    TOTAL=$((TOTAL + 1))
                    continue
                fi
                ;;
        esac
        FAT+=("$binary")
        continue
    fi

    if [[ "$EXPECTED" == "arm64" ]]; then
        if [[ "$info" != *"arm64"* ]]; then
            WRONG+=("$binary :: $info")
        fi
    else
        if [[ "$info" != *"x86_64"* ]]; then
            WRONG+=("$binary :: $info")
        fi
    fi
done < <(find "$APP_PATH" \( -name "*.so" -o -name "*.dylib" -o -perm -111 -type f \) -print0 2>/dev/null)

echo "[verify_mac_app_arch] scanned ${TOTAL} Mach-O binaries in $(basename "$APP_PATH") (expect ${EXPECTED} only)"

if [[ ${#FAT} -gt 0 ]]; then
    echo "[verify_mac_app_arch] ERROR: ${#FAT} fat/universal binary(ies) — use single-arch build:" >&2
    printf '  %s\n' "${FAT[@]}" >&2
    exit 1
fi

if [[ ${#WRONG} -gt 0 ]]; then
    echo "[verify_mac_app_arch] ERROR: ${#WRONG} binary(ies) with wrong architecture:" >&2
    printf '  %s\n' "${WRONG[@]}" >&2
    exit 1
fi

MAIN_EXE="${APP_PATH}/Contents/MacOS/"*
if [[ -f "$MAIN_EXE" ]]; then
    main_info="$(lipo -info "$MAIN_EXE" 2>/dev/null || true)"
    echo "[verify_mac_app_arch] main executable: ${main_info}"
fi

echo "[verify_mac_app_arch] OK — coherent ${EXPECTED} build (${TOTAL} binaries)"
