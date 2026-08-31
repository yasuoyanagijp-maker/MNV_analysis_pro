#!/usr/bin/env bash
# =============================================================================
# package_mac_release.sh — assemble Mac distribution ZIP for GitHub Releases
# =============================================================================
# Prerequisite: ./build_mac.sh --skip-notarize (dist/ARIAKE_OCTA.app must exist)
#
# Usage:
#   ./package_mac_release.sh --arm64              # ARIAKE_OCTA_mac.zip
#   ./package_mac_release.sh --intel              # ARIAKE_OCTA_macOS_Intel_vX.Y.Z.zip
#   ./package_mac_release.sh --arm64 --version 1.2.4
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="ARIAKE_OCTA"
APP_PATH="${SCRIPT_DIR}/dist/${APP_NAME}.app"
DIST_DIR="${SCRIPT_DIR}/dist"
VERSION="1.2.4"
TARGET_ARCH="arm64"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --arm64)  TARGET_ARCH="arm64" ;;
        --intel)  TARGET_ARCH="x86_64" ;;
        --version) VERSION="$2"; shift ;;
        -h|--help)
            echo "Usage: ./package_mac_release.sh [--arm64|--intel] [--version X.Y.Z]"
            exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
    shift
done

if [[ ! -d "$APP_PATH" ]]; then
    echo "[package_mac_release] ERROR: ${APP_PATH} not found. Run ./build_mac.sh first." >&2
    exit 1
fi

if [[ -x "${SCRIPT_DIR}/tools/verify_mac_app_arch.sh" ]]; then
    "${SCRIPT_DIR}/tools/verify_mac_app_arch.sh" "$APP_PATH" "$TARGET_ARCH"
fi

STAGE="${DIST_DIR}/release_mac_${TARGET_ARCH}"
rm -rf "$STAGE"
if [[ "$TARGET_ARCH" == "arm64" ]]; then
    BUNDLE_DIR="${STAGE}/ARIAKE_OCTA_mac_v${VERSION}"
    ZIP_NAME="ARIAKE_OCTA_mac.zip"
else
    BUNDLE_DIR="${STAGE}/ARIAKE_OCTA_macOS_Intel_v${VERSION}"
    ZIP_NAME="ARIAKE_OCTA_macOS_Intel_v${VERSION}.zip"
fi
mkdir -p "$BUNDLE_DIR"

echo "[package_mac_release] copying .app and install helpers..."
ditto --noqtn --norsrc "$APP_PATH" "${BUNDLE_DIR}/${APP_NAME}.app"
cp "${SCRIPT_DIR}/インストール.command" "${BUNDLE_DIR}/"
cp "${SCRIPT_DIR}/Macインストール手順.txt" "${BUNDLE_DIR}/"
chmod +x "${BUNDLE_DIR}/インストール.command"

# Remove AppleDouble resource forks that break Gatekeeper on some Macs
find "$BUNDLE_DIR" -name '._*' -delete 2>/dev/null || true
if command -v dot_clean >/dev/null 2>&1; then
    dot_clean -m "$BUNDLE_DIR" 2>/dev/null || true
fi

ZIP_PATH="${DIST_DIR}/${ZIP_NAME}"
rm -f "$ZIP_PATH"
(
    cd "$STAGE"
    zip -r -y "$ZIP_PATH" "$(basename "$BUNDLE_DIR")"
)

echo "[package_mac_release] created ${ZIP_PATH} ($(du -sh "$ZIP_PATH" | cut -f1))"
echo "[package_mac_release] contents:"
unzip -l "$ZIP_PATH" | head -20
