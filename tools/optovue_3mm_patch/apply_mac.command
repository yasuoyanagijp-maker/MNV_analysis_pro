#!/bin/bash
# ARIAKE OCTA — Optovue 3mm パッチ（macOS）
# 対象: インストール済み v1.2.4（Apple Silicon / Intel 共通。中身は Python と参照 JSON）
# 右クリック →「開く」で実行。引数で .app の場所を渡せる。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PAYLOAD="${SCRIPT_DIR}/payload"
APP="${1:-/Applications/ARIAKE_OCTA.app}"
APP="${APP%/}"

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║  ARIAKE OCTA — Optovue 3mm パッチ（Mac）     ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "対象: ${APP}"
echo ""

pause_end() {
  if [[ -t 0 && "${ARIAKE_PATCH_SKIP_PAUSE:-}" != "1" ]]; then
    read -r -p "Enterキーで閉じる..." _
  fi
}

fail() {
  echo "[エラー] $*" >&2
  pause_end
  exit 1
}

[[ -d "$PAYLOAD" ]] || fail "payload フォルダがありません。ZIP を展開したフォルダで実行してください。"
[[ -d "$APP" && "$APP" == *.app ]] || fail ".app が見つかりません: ${APP}"

PLIST="${APP}/Contents/Info.plist"
[[ -f "$PLIST" ]] || fail "Info.plist がありません。v1.2.4 の ARIAKE_OCTA.app を指定してください。"

VER=""
if command -v plutil >/dev/null 2>&1; then
  VER="$(plutil -extract CFBundleShortVersionString raw -o - "$PLIST" 2>/dev/null || true)"
fi
if [[ -z "$VER" ]]; then
  VER="$(awk '
    $0 ~ /<key>CFBundleShortVersionString<\/key>/ { found=1; next }
    found && $0 ~ /<string>/ {
      sub(/.*<string>/, "")
      sub(/<\/string>.*/, "")
      print
      exit
    }
  ' "$PLIST")"
fi
[[ "$VER" == "1.2.4" ]] || fail "このパッチは v1.2.4 用です（検出したバージョン: ${VER:-不明}）。"

RESOURCES="${APP}/Contents/Resources"
[[ -f "${RESOURCES}/src/core/mnv_pipeline.py" ]] || fail "アプリ内に src が見つかりません。v1.2.4 の構成ではありません。"

if command -v pgrep >/dev/null 2>&1 && pgrep -x ARIAKE_OCTA >/dev/null 2>&1; then
  fail "ARIAKE_OCTA が起動中です。終了してから、もう一度実行してください。"
fi

echo "[1/4] Python と参照 JSON を差し替え..."
file_count=0
while IFS= read -r -d '' src; do
  rel="${src#"${PAYLOAD}/"}"
  dest="${RESOURCES}/${rel}"
  mkdir -p "$(dirname "$dest")"
  cp "$src" "$dest"
  file_count=$((file_count + 1))
  if [[ "$dest" == *.py ]]; then
    base="$(basename "$dest" .py)"
    dir="$(dirname "$dest")"
    rm -f "${dir}/${base}.pyc"
    if [[ -d "${dir}/__pycache__" ]]; then
      rm -f "${dir}/__pycache__/${base}".cpython-*.pyc
    fi
  fi
done < <(find "$PAYLOAD" -type f -print0)
echo "       ${file_count} ファイル"

echo "[2/4] 隔離属性をクリア..."
if [[ "$(uname)" == "Darwin" ]] && command -v xattr >/dev/null 2>&1; then
  xattr -cr "$APP"
else
  echo "       （このOSではスキップ）"
fi

echo "[3/4] アドホック再署名（Hardened Runtime なし）..."
if [[ "$(uname)" == "Darwin" ]]; then
  if ! codesign --force --deep --sign - "$APP"; then
    fail "再署名に失敗しました。ターミナルで次を実行してください: xattr -cr \"${APP}\" && codesign --force --deep --sign - \"${APP}\""
  fi
elif [[ "${ARIAKE_PATCH_SKIP_CODESIGN:-}" == "1" ]]; then
  echo "       （検証用に再署名をスキップ）"
else
  fail "macOS 上で実行してください。"
fi

echo "[4/4] 完了"
echo ""
echo "3 mm (Optovue) と 3 mm (Zeiss HD) が起動ウィザードに出ます。"
echo "数値の 3.0 と、手入力の 3 mm は Zeiss HD のままです。"
echo ""
if [[ "$(uname)" == "Darwin" && "${ARIAKE_PATCH_NO_OPEN:-}" != "1" ]]; then
  open "$APP" || true
fi
pause_end
