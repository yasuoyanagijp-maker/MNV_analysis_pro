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
#   ./build_mac.sh --intel           # Intel Mac 用を明示（Intel Mac 上でのみ有効）
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
APP_VERSION="1.0.0"
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
    [[ "$ARCH" != "$TARGET_ARCH" ]] && log_warn "クロスビルド: ホスト ${ARCH} → ターゲット ${TARGET_ARCH}"
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
    exit 1
fi
log_success ".venv を確認"

# ── ビルドツールのインストール ─────────────────────────────────────────────────
log_step "ビルドツールのインストール確認"
source "${SCRIPT_DIR}/.venv/bin/activate"

for pkg in pyinstaller "streamlit-desktop-app" dmgbuild; do
    if ! python -c "import ${pkg//-/_}" &>/dev/null 2>&1; then
        log_info "${pkg} をインストール中..."
        pip install "$pkg" --quiet
    else
        log_success "${pkg} 確認済み"
    fi
done

# pywebview も確認
python -c "import webview" &>/dev/null 2>&1 && log_success "pywebview 確認済み" || {
    log_info "pywebview をインストール中..."
    pip install pywebview --quiet
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

    pyinstaller \
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
fi

# ── libcrypto バージョン衝突の修正 ────────────────────────────────────────────
# 問題: _ssl.so のビルド時にリンクした SSL ライブラリとバンドル libcrypto が不一致だとクラッシュ。
#       - Xcode Python: /usr/lib/libcrypto.44.dylib（Apple LibreSSL）→ システムのまま触らない
#       - Homebrew Python: libcrypto.3.dylib（OpenSSL 3.x）→ 差し替え処理が必要な場合あり
# 修正: Apple の /usr/lib を参照している場合は何もせず、OpenSSL 系のときのみ差し替え。
log_step "libcrypto バージョン衝突の修正"

FRAMEWORKS_DIR="${APP_PATH}/Contents/Frameworks"

# Python の _ssl.so を取得（PyInstaller 後のアプリ内）
VENV_SSL_SO=$(find "${FRAMEWORKS_DIR}" -name "_ssl.cpython-*.so" | head -1)
RUN_LIBCRYPTO_FIX=false

if [[ -n "$VENV_SSL_SO" ]]; then
    log_info "Python _ssl.so: ${VENV_SSL_SO}"

    # _ssl.so が元々リンクしている libcrypto のパスを特定
    LIBCRYPTO_REF=$(otool -L "$VENV_SSL_SO" 2>/dev/null | grep libcrypto | awk '{print $1}' | head -1)

    # Apple のシステム libcrypto (/usr/lib) を参照している場合は触らない
    if [[ "$LIBCRYPTO_REF" == /usr/lib/* ]] || [[ "$LIBCRYPTO_REF" == /System/* ]]; then
        log_info "_ssl.so は Apple のシステム libcrypto を参照（${LIBCRYPTO_REF}）。差し替え不要。"
    else
        RUN_LIBCRYPTO_FIX=true
    fi
fi

if [[ "$RUN_LIBCRYPTO_FIX" == true ]]; then
    NEED_OPENSSL_11=false
    if [[ "$LIBCRYPTO_REF" == *"libcrypto.3"* ]]; then
        NEED_OPENSSL_11=false
    elif [[ "$LIBCRYPTO_REF" == *"1.1"* || "$LIBCRYPTO_REF" == *"libcrypto.1"* ]]; then
        NEED_OPENSSL_11=true
    else
        NEED_OPENSSL_11=true
    fi

    if [[ "$NEED_OPENSSL_11" == true ]]; then
        LIBCRYPTO_DYLIB_NAME="libcrypto.1.1.dylib"
        SEARCH_DIRS="/opt/homebrew/opt/openssl@1.1/lib /usr/local/opt/openssl@1.1/lib"
    else
        LIBCRYPTO_DYLIB_NAME="libcrypto.3.dylib"
        SEARCH_DIRS="/opt/homebrew/opt/openssl@3/lib /usr/local/opt/openssl@3/lib"
    fi

    log_info "_ssl.so の参照: ${LIBCRYPTO_REF} → ${LIBCRYPTO_DYLIB_NAME} を使用"

    CORRECT_LIBCRYPTO=""
    for d in $SEARCH_DIRS; do
        if [[ -f "${d}/${LIBCRYPTO_DYLIB_NAME}" ]]; then
            CORRECT_LIBCRYPTO="${d}/${LIBCRYPTO_DYLIB_NAME}"
            break
        fi
    done
    if [[ -z "$CORRECT_LIBCRYPTO" && "$LIBCRYPTO_REF" == /* && -f "$LIBCRYPTO_REF" ]]; then
        CORRECT_LIBCRYPTO="$LIBCRYPTO_REF"
    fi

    if [[ -n "$CORRECT_LIBCRYPTO" && -f "$CORRECT_LIBCRYPTO" ]]; then
        log_info "正しい libcrypto を発見: ${CORRECT_LIBCRYPTO}"
        
        # 正しい libcrypto を Frameworks に必ず配置
        LIBCRYPTO_DEST="${FRAMEWORKS_DIR}/${LIBCRYPTO_DYLIB_NAME}"
        log_info "libcrypto を配置: ${LIBCRYPTO_DEST}"
        cp -vf "$CORRECT_LIBCRYPTO" "$LIBCRYPTO_DEST"
        chmod 755 "$LIBCRYPTO_DEST"

        # 同名校が既に別の場所にあれば内容を差し替え
        if [[ -d "${APP_PATH}" ]]; then
            while IFS= read -r bundled_lib; do
                [[ -z "$bundled_lib" || "$bundled_lib" == "$LIBCRYPTO_DEST" ]] && continue
                if [[ -L "$bundled_lib" ]]; then continue; fi
                if [[ "$(basename "$bundled_lib")" == "$LIBCRYPTO_DYLIB_NAME" ]]; then
                    log_info "libcrypto を差し替え中: ${bundled_lib}"
                    chmod +w "$bundled_lib"
                    cp -vf "$CORRECT_LIBCRYPTO" "$bundled_lib"
                    chmod 755 "$bundled_lib"
                fi
            done < <(find "${APP_PATH}" -name "*libcrypto*.dylib*" 2>/dev/null)
        fi

        # メイン実行ファイルの RPATH に Frameworks を追加（@rpath 解決のため）
        EXE_PATH="${APP_PATH}/Contents/MacOS/${APP_NAME}"
        if [[ -f "$EXE_PATH" ]]; then
            if ! otool -l "$EXE_PATH" 2>/dev/null | grep -q "path @executable_path/../Frameworks"; then
                log_info "exe に RPATH を追加: @executable_path/../Frameworks"
                install_name_tool -add_rpath "@executable_path/../Frameworks" "$EXE_PATH" 2>/dev/null || true
            fi
        fi

        # すべてのバイナリ内の libcrypto 参照を @rpath/${LIBCRYPTO_DYLIB_NAME} に更新
        log_info "バイナリのリンク参照を更新中..."
        RPATH_CRYPTO="@rpath/${LIBCRYPTO_DYLIB_NAME}"
        if [[ -d "${APP_PATH}" ]]; then
            find "${APP_PATH}" \( -name "*.so" -o -name "*.dylib" -o -perm +111 -type f \) 2>/dev/null | while read -r binary; do
                # libcrypto への依存関係があるか確認
                deps=$(otool -L "$binary" 2>/dev/null | grep libcrypto | awk '{print $1}') || continue
                for current_ref in $deps; do
                    if [[ "$current_ref" != "$RPATH_CRYPTO" ]]; then
                        install_name_tool -change "$current_ref" "$RPATH_CRYPTO" "$binary" 2>/dev/null || true
                    fi
                done
            done
        fi
        log_success "libcrypto の一括置換と参照の更新を完了しました"

        # 差し替え後に再署名（アドホック）— バイナリ変更で署名が無効になるため
        log_info "アドホック署名を実行..."
        codesign --force --deep --sign - "${APP_PATH}"
    else
        log_warn "正しい libcrypto が見つかりません。Homebrew で openssl@1.1 または openssl@3 をインストールしてください: brew install openssl@3"
    fi
elif [[ -z "$VENV_SSL_SO" ]]; then
    log_warn "Python の _ssl.so が見つかりません (スキップ)"
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

log_info "署名中（Hardened Runtime + entitlements）..."
# --deep: .app 内すべての .dylib / framework に再帰署名
codesign \
    --force \
    --deep \
    --sign "${DEVELOPER_ID}" \
    --options runtime \
    --entitlements "${ENTITLEMENTS}" \
    --timestamp \
    "${APP_PATH}"

log_info "署名の検証..."
codesign --verify --deep --strict --verbose=2 "${APP_PATH}"
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
echo    "    DMG を開く → ARIAKE OCTA.app を Applications フォルダへドラッグ"
echo ""
