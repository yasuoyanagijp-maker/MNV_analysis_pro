#!/bin/bash
# =============================================================================
# ARIAKE OCTA Analysis — インストーラー
# 右クリック →「開く」で実行してください（初回はダブルクリック不可の場合あり）
#
# 公証（Apple notary）は使いません。代わりにこの端末上で:
#   1. xattr -cr … Gatekeeper の隔離属性を外す
#   2. codesign --sign - … アドホック再署名（Hardened Runtime なし）
# 公証（Apple notary）は使いません。代わりにこの端末上で:
#   1. xattr -cr … Gatekeeper の隔離属性を外す
#   2. codesign --sign - … アドホック再署名（Hardened Runtime なし）
# v1.2.4 以降はビルド時に *.dist-info を除去済みのため再署名が通ります。
# v1.2.3 では Frameworks/fastapi-*.dist-info 等により codesign --deep が失敗します。
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
echo -e "${YELLOW}[重要]${NC} 初回は「インストール.command」を"
echo "       右クリック →「開く」で実行してください。"
echo "       （ダブルクリックのみだと macOS にブロックされることがあります）"
echo "       詳細は同梱の Macインストール手順.txt を参照してください。"
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

# xattr クリア（Gatekeeper の「開発元未確認」回避。公証の代わりではない）
echo -e "${GREEN}[1/4]${NC} セキュリティ属性をクリア中..."
xattr -cr "$APP_SRC"

# Applications へコピー
echo -e "${GREEN}[2/4]${NC} Applications フォルダへインストール中..."
cp -r "$APP_SRC" /Applications/

if [[ ! -d "$APP_DEST" ]]; then
    echo -e "${RED}[エラー]${NC} インストールに失敗しました。"
    read -p "Enterキーで閉じる..."
    exit 1
fi

# この Mac 向けアドホック再署名。--options runtime は付けない
# （Hardened Runtime だと未公証の解析エンジンが SIGKILL される）。
echo -e "${GREEN}[3/4]${NC} このMac向けに再署名中（公証なし）..."
xattr -cr "$APP_DEST"
if codesign --force --deep --sign - "$APP_DEST"; then
    echo "       再署名が完了しました。"
else
    echo -e "${YELLOW}[警告]${NC} 再署名に失敗しました。ログインで Connection Error になることがあります。"
    echo "       ターミナルで次を実行してから、アプリを起動し直してください:"
    echo "         xattr -cr \"${APP_DEST}\""
    echo "         codesign --force --deep --sign - \"${APP_DEST}\""
fi

# 起動
echo -e "${GREEN}[4/4]${NC} アプリを起動中..."
open "$APP_DEST"

echo ""
echo "✅ インストール完了"
echo "次回以降は Applications フォルダの ARIAKE_OCTA をダブルクリックして起動できます。"
echo ""
read -p "Enterキーで閉じる..."
