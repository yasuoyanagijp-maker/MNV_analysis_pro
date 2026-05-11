#!/usr/bin/env bash
# =============================================================================
# build_win.sh — ARIAKE OCTA Windows ビルドスクリプト (Bash for Windows)
# =============================================================================
# フロー: PyInstaller ビルド -> 成果物の確認 -> ZIP 圧縮
#
# 使い方:
#   ./build_win.sh                   # 通常ビルド
#   ./build_win.sh --clean           # dist/ build/ を削除してから実行
#   ./build_win.sh --debug           # デバッグコンソールを有効にしてビルド
# =============================================================================

set -euo pipefail

# ── カラー出力 ────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; CYAN='\033[0;36m'; RED='\033[0;31m'; BOLD='\033[1m'; NC='\033[0m'
log_info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }
log_step()    { echo -e "\n${BOLD}${BLUE}━━ $* ━━${NC}"; }
log_success() { echo -e "${GREEN}[✓]${NC}    $*"; }

# ── 設定 ──────────────────────────────────────────────────────────────────────
APP_NAME="ARIAKE_OCTA"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIST_DIR="${SCRIPT_DIR}/dist"
BUILD_DIR="${SCRIPT_DIR}/build"
SPEC_FILE="${SCRIPT_DIR}/ARIAKE_OCTA_win.spec"
PYTHON_EXE="python"

# 仮想環境の自動検出
if [ -f "${SCRIPT_DIR}/.venv/Scripts/python.exe" ]; then
    PYTHON_EXE="${SCRIPT_DIR}/.venv/Scripts/python.exe"
    log_info "Using virtual environment Python: ${PYTHON_EXE}"
elif [ -f "${SCRIPT_DIR}/.venv/bin/python" ]; then
    PYTHON_EXE="${SCRIPT_DIR}/.venv/bin/python"
    log_info "Using virtual environment Python: ${PYTHON_EXE}"
fi

# ── 引数パース ─────────────────────────────────────────────────────────────────
DO_CLEAN=false
DEBUG_MODE=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --clean) DO_CLEAN=true ;;
        --debug) DEBUG_MODE=true ;;
        -h|--help)
            echo "Usage: ./build_win.sh [--clean] [--debug]"
            exit 0 ;;
        *) log_warn "Unknown option: $1" ;;
    esac
    shift
done

# ── ヘッダー ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${BLUE}╔══════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${BLUE}║  Windows  ARIAKE OCTA — Windows EXE Builder  ║${NC}"
echo -e "${BOLD}${BLUE}╚══════════════════════════════════════════════╝${NC}"
echo ""

# ── クリーン ──────────────────────────────────────────────────────────────────
if [ "$DO_CLEAN" = true ]; then
    log_step "クリーン"
    rm -rf "$DIST_DIR" "$BUILD_DIR"
    log_success "dist/ build/ を削除しました"
fi

mkdir -p "$DIST_DIR"

# ── 必須ツールの確認 ─────────────────────────────────────────────────────────
log_step "必須ツールの確認"
if ! "$PYTHON_EXE" --version &>/dev/null; then
    log_error "Python が見つかりません。パスを確認してください。"
    exit 1
fi
log_success "Python 確認済み: $("$PYTHON_EXE" --version 2>&1)"

# PyInstaller の確認とインストール
if ! "$PYTHON_EXE" -m PyInstaller --version &>/dev/null; then
    log_info "PyInstaller をインストール中..."
    "$PYTHON_EXE" -m pip install pyinstaller --quiet
else
    log_success "PyInstaller 確認済み: $("$PYTHON_EXE" -m PyInstaller --version 2>&1)"
fi

# 主要依存パッケージの確認
log_info "依存パッケージの確認中..."
pkgs=("flet" "fastapi" "uvicorn" "multipart" "cv2" "skimage" "PIL" "imagecodecs")
for pkg in "${pkgs[@]}"; do
    if ! "$PYTHON_EXE" -c "import $pkg" &>/dev/null; then
        log_warn "$pkg が見つかりません。ビルド前にインストールしてください。"
    fi
done

# ── PyInstaller ビルド ────────────────────────────────────────────────────────
log_step "PyInstaller ビルド"
log_info "使用 spec: $(basename "$SPEC_FILE")"

if [ "$DEBUG_MODE" = true ]; then
    log_info "Debug mode enabled"
    export PYI_DEBUG=1
fi

"$PYTHON_EXE" -m PyInstaller \
    --clean \
    --noconfirm \
    --distpath="$DIST_DIR" \
    --workpath="$BUILD_DIR" \
    "$SPEC_FILE"

if [ $? -ne 0 ]; then
    log_error "ビルドに失敗しました。"
    exit 1
fi

EXE_PATH="${DIST_DIR}/${APP_NAME}/${APP_NAME}.exe"
if [ ! -f "$EXE_PATH" ]; then
    log_error "EXE が見つかりません: ${EXE_PATH}"
    exit 1
fi

log_success "PyInstaller ビルド完了: ${EXE_PATH}"

# ── ZIP 圧縮 ──────────────────────────────────────────────────────────────────
log_step "ZIP 圧縮"
ZIP_OUT="${DIST_DIR}/${APP_NAME}.zip"
rm -f "$ZIP_OUT"

# Windows では zip コマンドがない場合があるため、powershell をフォールバックに使用
if command -v zip &>/dev/null; then
    (cd "$DIST_DIR" && zip -r "${APP_NAME}.zip" "${APP_NAME}")
else
    log_info "zip コマンドが見つからないため、PowerShell で圧縮します..."
    powershell.exe -Command "Compress-Archive -Path '${DIST_DIR}/${APP_NAME}/*' -DestinationPath '${ZIP_OUT}' -Force"
fi

log_success "ZIP 作成完了: ${ZIP_OUT}"

# ── 完了サマリー ──────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${GREEN}║  ✅  ビルド完了                               ║${NC}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  出力フォルダ: ${DIST_DIR}/${APP_NAME}"
echo -e "  実行ファイル: ${EXE_PATH}"
echo -e "  配布用 ZIP  : ${ZIP_OUT}"
echo ""
echo "インストール手順:"
echo "  1. ${APP_NAME}.zip を展開します。"
echo "  2. 展開されたフォルダ内の ${APP_NAME}.exe を実行します。"
echo ""
