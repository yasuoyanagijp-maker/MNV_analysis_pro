#!/bin/bash
# ARIAKE OCTA — Optovue 3mm パッチ（macOS）
# 対象: インストール済み v1.2.4（Apple Silicon / Intel 共通。中身は Python と参照 JSON）
# 右クリック →「開く」で実行。引数で .app の場所を渡せる。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PAYLOAD="${SCRIPT_DIR}/payload"
APP="${1:-/Applications/ARIAKE_OCTA.app}"
APP="${APP%/}"

if [[ -f "${SCRIPT_DIR}/mac_adhoc_codesign.sh" ]]; then
  # shellcheck source=/dev/null
  source "${SCRIPT_DIR}/mac_adhoc_codesign.sh"
elif [[ -f "${SCRIPT_DIR}/../mac_adhoc_codesign.sh" ]]; then
  # shellcheck source=/dev/null
  source "${SCRIPT_DIR}/../mac_adhoc_codesign.sh"
else
  echo "[エラー] mac_adhoc_codesign.sh がパッチと同じフォルダにありません。" >&2
  exit 1
fi

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

_payload_junk() {
  case "$(basename "$1")" in
    .DS_Store|._*) return 0 ;;
  esac
  return 1
}

# PyInstaller noarchive stores dashboard.pyc beside, or instead of, dashboard.py.
# A sourceless .pyc earlier on sys.path keeps the pre-patch wizard on screen.
_purge_bytecode() {
  local rel="$1"
  local pyc_rel rel_dir base pyc root
  pyc_rel="${rel%.py}.pyc"
  rel_dir="$(dirname "$rel")"
  base="$(basename "$rel" .py)"
  while IFS= read -r -d '' pyc; do
    rm -f "$pyc"
  done < <(find "${APP}/Contents" -path "*/${pyc_rel}" -print0 2>/dev/null || true)
  while IFS= read -r -d '' pyc; do
    rm -f "$pyc"
  done < <(find "${APP}/Contents" -path "*/${rel_dir}/__pycache__/${base}.cpython-*.pyc" -print0 2>/dev/null || true)
  for root in "$RESOURCES" "${APP}/Contents/Frameworks" "${APP}/Contents/MacOS"; do
    rm -f "${root}/${pyc_rel}"
    rm -f "${root}/${rel_dir}/__pycache__/${base}".cpython-*.pyc
  done
}

_install_payload_file() {
  local src="$1"
  local rel="$2"
  local root dest parent
  for root in "$RESOURCES" "${APP}/Contents/Frameworks" "${APP}/Contents/MacOS"; do
    dest="${root}/${rel}"
    parent="$(dirname "$dest")"
    if [[ "$root" == "$RESOURCES" ]]; then
      mkdir -p "$parent"
      cp "$src" "$dest"
    elif [[ -d "$parent" || -L "$parent" ]]; then
      cp "$src" "$dest"
    fi
  done
  if [[ "$rel" == *.py ]]; then
    _purge_bytecode "$rel"
  fi
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
  if _payload_junk "$src"; then
    continue
  fi
  rel="${src#"${PAYLOAD}/"}"
  _install_payload_file "$src" "$rel"
  file_count=$((file_count + 1))
done < <(find "$PAYLOAD" -type f -print0)
echo "       ${file_count} ファイル"

echo "[2/4] 隔離属性をクリア..."
if [[ "$(uname)" == "Darwin" ]] && command -v xattr >/dev/null 2>&1; then
  xattr -cr "$APP"
else
  echo "       （このOSではスキップ）"
fi

echo "[3/4] アドホック再署名（.dylibs を署名できる形にします）..."
if [[ "$(uname)" == "Darwin" ]]; then
  if ! sign_mac_adhoc "$APP"; then
    fail "再署名に失敗しました。ARIAKE OCTA を終了したまま、この「パッチ適用.command」をもう一度実行してください。ターミナルで codesign --deep だけを繰り返すと、shapely/.dylibs で同じエラーになります。"
  fi
elif [[ "${ARIAKE_PATCH_SKIP_CODESIGN:-}" == "1" ]]; then
  prepare_mac_codesign "$APP"
  echo "       （検証用に再署名をスキップ）"
else
  fail "macOS 上で実行してください。"
fi

echo "[4/4] 完了"
echo ""
DASH="${RESOURCES}/src/flet_ui/pages/dashboard.py"
if [[ -f "$DASH" ]] && grep -q "3 mm (Optovue)" "$DASH"; then
  echo "確認: アプリ内の画面定義に「3 mm (Optovue)」が入っています。"
else
  echo "[警告] アプリ内の dashboard.py に「3 mm (Optovue)」が見つかりません。"
fi
echo "起動ウィザードの Step 2 に「3 mm (Optovue)」と「3 mm (Zeiss HD)」が出ます。"
echo "数値の Image Scale (mm) 一覧には出ません。そこでの 3.0 は Zeiss HD のままです。"
echo "すでに開いている場合は終了してから、Applications の ARIAKE OCTA を開き直してください。"
echo ""
if [[ "$(uname)" == "Darwin" && "${ARIAKE_PATCH_NO_OPEN:-}" != "1" ]]; then
  open "$APP" || true
fi
pause_end
