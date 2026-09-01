#!/usr/bin/env bash
# =============================================================================
# build_mac.sh — ARIAKE OCTA macOS DMG ビルドスクリプト
# =============================================================================
# フロー: PyInstaller → codesign → dmgbuild → notarytool → stapler → 検証
#
# 事前準備:
#   1. Apple Developer Program に加入済み
#   2. Xcode Command Line Tools インストール済み: xcode-select --install
#   3. Keychain に "Developer ID Application" 証明書がインストール済み
#   4. App-specific password を Keychain に保存済み（初回のみ）:
#      xcrun notarytool store-credentials "ARIAKE_NOTARY" \
#        --apple-id "YOUR_APPLE_ID" \
#        --team-id  "YOUR_TEAM_ID" \
#        --password "xxxx-xxxx-xxxx-xxxx"  # App-specific password
#
# 使い方:
#   ./build_mac.sh                   # 通常ビルド（全工程・アーキ自動選択）
#   ./build_mac.sh --arm64           # Apple Silicon (M1/M2/M3) 用を明示
#   ./build_mac.sh --intel           # Intel (x86_64) 用。venv の Python も x86_64 であること
#                                    # （Intel Mac または M1+Rosetta + python.org Intel 3.9）
#   ./build_mac.sh --build-only      # PyInstaller ビルドのみ
#   ./build_mac.sh --sign-only       # 署名・公証のみ（ビルド済み前提）
#   ./build_mac.sh --skip-notarize   # 公証をスキップ（テスト用）
#   ./build_mac.sh --clean           # dist/ build/ を削除してから実行
# =============================================================================

set -euo pipefail

# ── カラー出力 ────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
log_info()    { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }
log_step()    { echo -e "\n${BOLD}${BLUE}━━ $* ━━${NC}"; }
log_success() { echo -e "${GREEN}[✓]${NC}    $*"; }

# ── ★ ここを実際の値に書き換えてください ★ ──────────────────────────────────
APPLE_ID="YOUR_APPLE_ID@example.com"          # 例: doctor@example.com
TEAM_ID="XXXXXXXXXX"                          # 10文字の Team ID
DEVELOPER_ID="Developer ID Application: Your Name (XXXXXXXXXX)"
KEYCHAIN_PROFILE="ARIAKE_NOTARY"             # notarytool store-credentials で設定した名前
APP_NAME="ARIAKE_OCTA"                        # .app / .dmg のベース名
APP_BUNDLE_ID="com.ariake.octa"              # Bundle Identifier
APP_VERSION="1.2.4"
# ─────────────────────────────────────────────────────────────────────────────

# ── パス設定 ──────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="${SCRIPT_DIR}/.venv/bin/python"
VENV_PIP="${SCRIPT_DIR}/.venv/bin/pip"
DIST_DIR="${SCRIPT_DIR}/dist"
BUILD_DIR="${SCRIPT_DIR}/build"
APP_PATH="${DIST_DIR}/${APP_NAME}.app"
DMG_PATH="${DIST_DIR}/${APP_NAME}.dmg"
ZIP_PATH="${DIST_DIR}/${APP_NAME}.zip"
WRAPPER="${SCRIPT_DIR}/wrapper.py"
ENTITLEMENTS="${SCRIPT_DIR}/entitlements.plist"
DMG_SETTINGS="${SCRIPT_DIR}/dmgbuild_settings.py"

# ── フラグ ────────────────────────────────────────────────────────────────────
BUILD_ONLY=false
SIGN_ONLY=false
SKIP_NOTARIZE=false
DO_CLEAN=false
FORCE_ARCH=""  # 空=自動, arm64, x86_64

while [[ $# -gt 0 ]]; do
    case "$1" in
        --build-only)    BUILD_ONLY=true ;;
        --sign-only)     SIGN_ONLY=true ;;
        --skip-notarize) SKIP_NOTARIZE=true ;;
        --clean)         DO_CLEAN=true ;;
        --arm64)         FORCE_ARCH="arm64" ;;
        --intel)         FORCE_ARCH="x86_64" ;;
        -h|--help)
            echo "Usage: ./build_mac.sh [--arm64|--intel|--build-only|--sign-only|--skip-notarize|--clean]"
            exit 0 ;;
        *) log_warn "Unknown: $1" ;;
    esac
    shift
done

# ── ヘッダー ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${BLUE}╔══════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${BLUE}║  🍎  ARIAKE OCTA — macOS DMG Builder         ║${NC}"
echo -e "${BOLD}${BLUE}╚══════════════════════════════════════════════╝${NC}"
echo ""

# ── macOS 確認 ─────────────────────────────────────────────────────────────────
if [[ "$(uname -s)" != "Darwin" ]]; then
    log_error "macOS が必要です"; exit 1
fi

ARCH="$(uname -m)"
MACOS_VER="$(sw_vers -productVersion)"
# ビルド対象アーキテクチャ（--arm64/--intel で上書き可能）
if [[ -n "$FORCE_ARCH" ]]; then
    TARGET_ARCH="$FORCE_ARCH"
    if [[ "$ARCH" != "$TARGET_ARCH" ]]; then
        log_warn "ホスト ${ARCH} → ターゲット ${TARGET_ARCH}"
        if [[ "$TARGET_ARCH" == "x86_64" ]]; then
            log_warn "Intel zip は Python / venv も x86_64 必須。arm64 Homebrew Python では失敗します。"
            log_warn "M1/M2/M3: arch -x86_64 /usr/local/bin/python3.9 -m venv .venv-intel && ln -sfn .venv-intel .venv"
        fi
    fi
else
    TARGET_ARCH="$ARCH"
fi
log_info "macOS ${MACOS_VER} / ホスト:${ARCH} ターゲット:${TARGET_ARCH}"

# ── プレースホルダー検出 ──────────────────────────────────────────────────────
log_step "設定値の確認"
PLACEHOLDER_FOUND=false
[[ "$APPLE_ID"      == *"YOUR_APPLE_ID"*   ]] && { log_warn "APPLE_ID が未設定です";      PLACEHOLDER_FOUND=true; }
[[ "$TEAM_ID"       == "XXXXXXXXXX"        ]] && { log_warn "TEAM_ID が未設定です";       PLACEHOLDER_FOUND=true; }
[[ "$DEVELOPER_ID"  == *"Your Name"*       ]] && { log_warn "DEVELOPER_ID が未設定です";  PLACEHOLDER_FOUND=true; }

if [[ "$PLACEHOLDER_FOUND" == true && "$SKIP_NOTARIZE" != true ]]; then
    log_warn "開発者情報が未設定のため --skip-notarize モードで続行します"
    SKIP_NOTARIZE=true
fi

# ── アドホック署名のフォールバック ──────────────────────────────────────────────
if [[ "$SKIP_NOTARIZE" == true && "$PLACEHOLDER_FOUND" == true ]]; then
    log_info "開発者情報が未設定かつ公証スキップのため、アドホック署名 (-) を使用します"
    DEVELOPER_ID="-"
fi
log_success "設定確認完了"

# ── 必須ツール確認 ────────────────────────────────────────────────────────────
log_step "必須ツールの確認"
for tool in xcode-select codesign xcrun; do
    command -v "$tool" &>/dev/null && log_success "$tool" || {
        log_error "$tool が見つかりません"
        [[ "$tool" == "xcode-select" ]] && log_error "  → xcode-select --install を実行してください"
        exit 1
    }
done

# 仮想環境の確認
if [[ ! -x "$VENV_PYTHON" ]]; then
    log_error ".venv が見つかりません。先に ./run.sh --setup-only を実行してください"
    log_error "Intel ビルドなら x86_64 Python 3.9 で: arch -x86_64 /usr/local/bin/python3.9 -m venv .venv"
    exit 1
fi
log_success ".venv を確認"

REQUIRE_PY_ARCH="${SCRIPT_DIR}/tools/require_mac_python_arch.sh"
if [[ -f "$REQUIRE_PY_ARCH" ]]; then
    log_info "venv Python が ${TARGET_ARCH} か確認中..."
    bash "$REQUIRE_PY_ARCH" "$VENV_PYTHON" "$TARGET_ARCH"
    log_success "venv Python は ${TARGET_ARCH}"
else
    log_warn "tools/require_mac_python_arch.sh がありません（アーキ確認をスキップ）"
fi

# ── ビルドツールのインストール ─────────────────────────────────────────────────
log_step "ビルドツールのインストール確認"
source "${SCRIPT_DIR}/.venv/bin/activate"

for pkg in pyinstaller "streamlit-desktop-app" dmgbuild; do
    case "$pkg" in
        pyinstaller) import_cmd='import PyInstaller' ;;
        streamlit-desktop-app) import_cmd='import streamlit_desktop_app' ;;
        dmgbuild) import_cmd='import dmgbuild' ;;
        *) import_cmd="import ${pkg//-/_}" ;;
    esac
    if ! "$VENV_PYTHON" -c "$import_cmd" &>/dev/null 2>&1; then
        log_info "${pkg} をインストール中..."
        "$VENV_PYTHON" -m pip install "$pkg" --quiet
    else
        log_success "${pkg} 確認済み"
    fi
done

# pywebview も確認
"$VENV_PYTHON" -c "import webview" &>/dev/null 2>&1 && log_success "pywebview 確認済み" || {
    log_info "pywebview をインストール中..."
    "$VENV_PYTHON" -m pip install pywebview --quiet
}

# ── クリーン ──────────────────────────────────────────────────────────────────
if [[ "$DO_CLEAN" == true ]]; then
    log_step "クリーン"
    rm -rf "$DIST_DIR" "$BUILD_DIR"
    log_success "dist/ build/ を削除しました"
fi

mkdir -p "$DIST_DIR"

# ── PyInstaller ビルド ────────────────────────────────────────────────────────
if [[ "$SIGN_ONLY" != true ]]; then
    log_step "PyInstaller ビルド"

    # 既存の .app を削除
    [[ -d "$APP_PATH" ]] && rm -rf "$APP_PATH"

    # アーキテクチャ別 spec を選択
    SPEC_FILE="${SCRIPT_DIR}/ARIAKE_OCTA_${TARGET_ARCH}.spec"
    if [[ ! -f "$SPEC_FILE" ]]; then
        log_error "spec が見つかりません: ${SPEC_FILE}"
        exit 1
    fi
    log_info "使用 spec: $(basename "$SPEC_FILE")"
    export ARIAKE_MAC_APP_VERSION="${APP_VERSION}"

    "$VENV_PYTHON" -m PyInstaller \
        --clean \
        --noconfirm \
        --distpath="${DIST_DIR}" \
        --workpath="${BUILD_DIR}" \
        "$SPEC_FILE"

    if [[ ! -d "$APP_PATH" ]]; then
        log_error "ビルドに失敗しました: ${APP_PATH} が見つかりません"
        exit 1
    fi
    log_success "PyInstaller ビルド完了: ${APP_PATH}"

    VERIFY_ARCH="${SCRIPT_DIR}/tools/verify_mac_app_arch.sh"
    if [[ -x "$VERIFY_ARCH" ]]; then
        log_info "アーキテクチャ整合性を検証中（${TARGET_ARCH} のみ）..."
        "$VERIFY_ARCH" "$APP_PATH" "$TARGET_ARCH"
        log_success "アーキテクチャ検証 OK"
    fi
fi

# ── OpenSSL 1.1 と 3 の共存 ────────────────────────────────────────────────
# Python 3.9 の _ssl.so は libcrypto.1.1、OpenCV は libssl.3 / libcrypto.3。
# 以前は _ssl.so に合わせて全バイナリを 1.1 に付け替えており、cv2 import が
# Symbol not found: _ASYNC_WAIT_CTX_get_status で落ちていた。
# 互換バージョン（Mach-O compatibility version）を正とし、混在させない。
log_step "OpenSSL 1.1 / 3 共存（cv2 を 1.1 に付け替えない）"
OPENSSL_FIX="${SCRIPT_DIR}/tools/mac_openssl_coexistence.py"
if [[ -f "$OPENSSL_FIX" ]]; then
    FIX_PY="${VENV_PYTHON}"
    if [[ ! -x "$FIX_PY" ]]; then
        FIX_PY="python3"
    fi
    "$FIX_PY" "$OPENSSL_FIX" --fix "$APP_PATH" --verify "$APP_PATH"
    log_success "OpenSSL 1.1 と 3 を共存させた"
else
    log_warn "mac_openssl_coexistence.py が見つかりません（スキップ）"
fi

# ── pip メタデータ除去（codesign --deep 破壊要因）────────────────────────────
# collect_all が *.dist-info を Frameworks に置くと codesign が
# 「bundle format unrecognized」で失敗し、起動時 CODESIGNING Invalid Page になる。
log_step "codesign 互換のため pip メタデータを除去"
STRIP_POISON="${SCRIPT_DIR}/tools/strip_mac_codesign_poison.sh"
if [[ -x "$STRIP_POISON" ]]; then
    "$STRIP_POISON" "$APP_PATH"
    log_success "pip メタデータ除去完了"
else
    log_warn "strip_mac_codesign_poison.sh が見つかりません（スキップ）"
fi

# ── 署名 ─────────────────────────────────────────────────────────────────────
log_step "コード署名"

# 拡張属性のクリア（Gatekeeper エラー防止）
log_info "拡張属性をクリア中..."
xattr -cr "$APP_PATH"

# entitlements.plist の確認
if [[ ! -f "$ENTITLEMENTS" ]]; then
    log_error "entitlements.plist が見つかりません: ${ENTITLEMENTS}"
    exit 1
fi

log_info "署名中..."
# --deep: .app 内すべての .dylib / framework に再帰署名
# アドホック（公証なし配布）では Hardened Runtime を付けない。
# --options runtime だと未公証の解析エンジン子プロセスが
# CODESIGNING Invalid Page で SIGKILL される（macOS 26 / M1 で確認）。
if [[ "$DEVELOPER_ID" == "-" ]]; then
    log_info "アドホック署名（Hardened Runtime なし・公証なし研究配布）..."
    if ! codesign --force --deep --sign - "${APP_PATH}"; then
        log_error "codesign に失敗しました。Frameworks 内に *.dist-info が残っていないか確認してください。"
        exit 1
    fi
else
    log_info "Developer ID 署名（Hardened Runtime + entitlements）..."
    if ! codesign \
        --force \
        --deep \
        --sign "${DEVELOPER_ID}" \
        --options runtime \
        --entitlements "${ENTITLEMENTS}" \
        --timestamp \
        "${APP_PATH}"; then
        log_error "codesign に失敗しました。"
        exit 1
    fi
fi

log_info "署名の検証..."
if ! codesign --verify --deep --strict --verbose=2 "${APP_PATH}"; then
    log_error "codesign --verify に失敗しました。"
    exit 1
fi
VERIFY_READY="${SCRIPT_DIR}/tools/verify_mac_codesign_ready.sh"
if [[ -x "$VERIFY_READY" ]]; then
    "$VERIFY_READY" "$APP_PATH"
fi
log_success "署名完了"

# ── DMG 作成 ─────────────────────────────────────────────────────────────────
log_step "DMG 作成"

[[ -f "$DMG_PATH" ]] && rm -f "$DMG_PATH"

log_info "hdiutil で DMG を作成中..."
hdiutil create \
    -volname "${APP_NAME}" \
    -srcfolder "${APP_PATH}" \
    -ov \
    -format UDZO \
    "${DMG_PATH}"

if [[ ! -f "$DMG_PATH" ]]; then
    log_error "DMG 作成に失敗しました"
    exit 1
fi
log_success "DMG 作成完了: ${DMG_PATH}"

# ── 公証 (Notarization) ───────────────────────────────────────────────────────
if [[ "$SKIP_NOTARIZE" != true && "$BUILD_ONLY" != true ]]; then
    log_step "公証 (Notarization)"

    # DMG を zip に変換して提出
    log_info "DMG を zip に圧縮中..."
    [[ -f "$ZIP_PATH" ]] && rm -f "$ZIP_PATH"
    ditto -c -k --keepParent "${DMG_PATH}" "${ZIP_PATH}"

    log_info "Apple に公証を提出中（数分かかる場合があります）..."
    xcrun notarytool submit "${ZIP_PATH}" \
        --keychain-profile "${KEYCHAIN_PROFILE}" \
        --wait \
        --timeout 600

    log_info "DMG に staple 中..."
    xcrun stapler staple "${DMG_PATH}"
    log_success "公証・staple 完了"

    # zip 削除
    rm -f "${ZIP_PATH}"
else
    log_warn "公証をスキップしました（--skip-notarize または開発者情報未設定）"
    log_warn "配布前に以下を実行してください:"
    log_warn "  xcrun notarytool submit ${DMG_PATH} --keychain-profile ARIAKE_NOTARY --wait"
    log_warn "  xcrun stapler staple ${DMG_PATH}"
fi

# ── 最終検証 ─────────────────────────────────────────────────────────────────
log_step "最終検証"

log_info ".app の署名検証..."
codesign --verify --deep --strict "${APP_PATH}" && log_success ".app 署名 OK" || log_warn ".app 署名に問題があります"

if [[ "$SKIP_NOTARIZE" != true ]]; then
    log_info "Gatekeeper による DMG 検証..."
    spctl --assess --type open --context context:primary-signature "${DMG_PATH}" -v 2>&1 | tee /tmp/spctl_result.txt
    if grep -q "accepted" /tmp/spctl_result.txt; then
        log_success "Gatekeeper: accepted ✅"
    else
        log_warn "Gatekeeper 検証結果:"
        cat /tmp/spctl_result.txt
    fi
fi

# ── 完了サマリー ──────────────────────────────────────────────────────────────
DMG_SIZE=$(du -sh "${DMG_PATH}" 2>/dev/null | cut -f1 || echo "unknown")
echo ""
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${GREEN}║  ✅  ビルド完了                               ║${NC}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${BOLD}DMG   :${NC} ${DMG_PATH}"
echo -e "  ${BOLD}サイズ:${NC} ${DMG_SIZE}"
echo -e "  ${BOLD}署名  :${NC} ${DEVELOPER_ID}"
if [[ "$SKIP_NOTARIZE" != true ]]; then
    echo -e "  ${BOLD}公証  :${NC} 完了（staple 済み）"
else
    echo -e "  ${BOLD}公証  :${NC} ${YELLOW}未実施 — 配布前に notarytool を実行してください${NC}"
fi
echo ""
echo -e "  ${BOLD}インストール手順（配布先）:${NC}"
echo    "    ZIP: ./package_mac_release.sh --arm64 --version ${APP_VERSION}"
echo    "    または DMG を開く → ARIAKE OCTA.app を Applications フォルダへドラッグ"
echo ""
