#!/bin/bash
# =============================================================================
# ARIAKE OCTA Analysis — インストーラー
# このファイルをダブルクリックするだけでインストールが完了します
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="ARIAKE_OCTA.app"
APP_SRC="${SCRIPT_DIR}/${APP_NAME}"
APP_DEST="/Applications/${APP_NAME}"

# カラー出力
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║  🔬  ARIAKE OCTA Analysis — インストーラー  ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# .app の存在確認
if [[ ! -d "$APP_SRC" ]]; then
    echo -e "${RED}[エラー]${NC} ${APP_NAME} が見つかりません。"
    echo "このファイルと ${APP_NAME} が同じフォルダにあることを確認してください。"
    read -p "Enterキーで閉じる..."
    exit 1
fi

# 既存インストールの確認
if [[ -d "$APP_DEST" ]]; then
    echo -e "${YELLOW}[確認]${NC} 既にインストールされています。上書きしますか？"
    read -p "上書きする場合は Enter、キャンセルは Ctrl+C を押してください..."
    rm -rf "$APP_DEST"
fi

# xattr クリア（Gatekeeperの警告を回避）
echo -e "${GREEN}[1/3]${NC} セキュリティ属性をクリア中..."
xattr -cr "$APP_SRC"

# Applications へコピー
echo -e "${GREEN}[2/3]${NC} Applications フォルダへインストール中..."
cp -r "$APP_SRC" /Applications/

if [[ ! -d "$APP_DEST" ]]; then
    echo -e "${RED}[エラー]${NC} インストールに失敗しました。"
    read -p "Enterキーで閉じる..."
    exit 1
fi

# 起動
echo -e "${GREEN}[3/3]${NC} アプリを起動中..."
open "$APP_DEST"

echo ""
echo "✅ インストール完了"
echo "次回以降は Applications フォルダの ARIAKE_OCTA をダブルクリックして起動できます。"
echo ""
read -p "Enterキーで閉じる..."
