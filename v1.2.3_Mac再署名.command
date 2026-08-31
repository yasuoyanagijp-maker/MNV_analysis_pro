#!/bin/bash
# =============================================================================
# ARIAKE OCTA — v1.2.3 Mac 再署名パッチ（前原型のみ）
#
# 右クリック →「開く」で実行してください（初回はダブルクリック不可の場合あり）
#
# 対象: 既定 /Applications/ARIAKE_OCTA.app（第1引数で別パス可）
# 処理: *.dist-info 除去 → xattr -cr → ad-hoc codesign（HR なし）→ 検証 → 起動
#
# 【効く】起動直後 SIGKILL / codesign が fastapi-*.dist-info で失敗（前原型）
# 【効かない】ログイン後 Connection Error（瀧澤型・Intel 木住野型）
#           → v1.2.4 ZIP（arm64 または Intel）が必要
# 公証は使いません。
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HELPER="${SCRIPT_DIR}/tools/patch_mac_v123_resign.py"
if [[ ! -f "$HELPER" ]]; then
    HELPER="${SCRIPT_DIR}/patch_mac_v123_resign.py"
fi

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

echo ""
echo -e "${YELLOW}[重要]${NC} 初回は本ファイルを右クリック →「開く」で実行してください。"
echo ""

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo -e "${RED}[エラー]${NC} macOS 専用です。"
    read -p "Enterキーで閉じる..."
    exit 1
fi

if [[ ! -f "$HELPER" ]]; then
    echo -e "${RED}[エラー]${NC} ヘルパーが見つかりません: patch_mac_v123_resign.py"
    echo "  リポジトリから v1.2.3_Mac再署名.command と tools/ を同じ構成で置いてください。"
    read -p "Enterキーで閉じる..."
    exit 1
fi

PYTHON=""
for candidate in python3 /usr/bin/python3; do
    if command -v "$candidate" &>/dev/null; then
        PYTHON="$candidate"
        break
    fi
done
if [[ -z "$PYTHON" ]]; then
    echo -e "${RED}[エラー]${NC} python3 が見つかりません。"
    read -p "Enterキーで閉じる..."
    exit 1
fi

APP_ARG=()
if [[ $# -gt 0 ]]; then
    APP_ARG=("$1")
fi

set +e
"$PYTHON" "$HELPER" "${APP_ARG[@]}"
STATUS=$?
set -e

if [[ $STATUS -ne 0 ]]; then
    echo ""
    echo -e "${RED}再署名に失敗しました。${NC} 上のメッセージを確認してください。"
    echo "ログイン Connection Error の場合は v1.2.4 ZIP が必要です（本パッチでは直りません）。"
fi

read -p "Enterキーで閉じる..."
exit "$STATUS"
