#!/bin/bash
# 症例フォルダの CSV を 1 枚にまとめる（Mac の bash 3.2 でも動く）
# 右クリック →「開く」。または: bash merge_case_csv.command /path/to/parent
set -u

export LANG="${LANG:-en_US.UTF-8}"
export LC_ALL="${LC_ALL:-$LANG}"

HERE="$(cd "$(dirname "$0")" && pwd)"
PERL_SCRIPT="$HERE/merge_case_csv.pl"

notify() {
  printf '%s\n' "$1"
  if [ "$(uname -s)" = "Darwin" ]; then
    /usr/bin/osascript - "$1" <<'APPLESCRIPT'
on run argv
  display dialog (item 1 of argv) buttons {"OK"} default button "OK" with title "CSVを1枚にまとめる"
end run
APPLESCRIPT
  fi
}

reveal_file() {
  if [ "$(uname -s)" = "Darwin" ] && [ -e "$1" ]; then
    /usr/bin/open -R "$1" >/dev/null 2>&1 || true
  fi
}

if [ ! -f "$PERL_SCRIPT" ]; then
  notify "merge_case_csv.pl が同じフォルダにありません。"
  exit 1
fi

PERL_BIN="/usr/bin/perl"
if [ ! -x "$PERL_BIN" ]; then
  PERL_BIN="$(command -v perl || true)"
fi
if [ -z "$PERL_BIN" ]; then
  notify "このMacでは perl が見つかりません。"
  exit 1
fi

if [ $# -ge 1 ]; then
  if [ ! -d "$1" ]; then
    notify "フォルダが見つかりません: $1"
    exit 1
  fi
  ROOT="$(cd "$1" && pwd)"
else
  if ! command -v osascript >/dev/null 2>&1; then
    notify "フォルダ選択が使えません。ターミナルで、bash のうしろにこのファイルと親フォルダのパスを指定して実行してください。"
    exit 1
  fi
  ROOT="$(/usr/bin/osascript <<'APPLESCRIPT'
set theFolder to choose folder with prompt "症例フォルダが入っている親フォルダを選んでください（中のCSVは自動で探します）"
POSIX path of theFolder
APPLESCRIPT
)" || {
    printf '%s\n' "キャンセルしました。"
    exit 0
  }
  ROOT=$(printf '%s' "$ROOT" | tr -d '\r')
  ROOT="${ROOT%/}"
fi

set +e
ERR_FILE="$(mktemp)"
RESULT="$("$PERL_BIN" "$PERL_SCRIPT" "$ROOT" 2>"$ERR_FILE")"
status=$?
set +e

first_line=$(printf '%s\n' "$RESULT" | head -n 1)
kind=$(printf '%s' "$first_line" | cut -f 1)
rest=$(printf '%s' "$first_line" | cut -f 2-)

if [ "$status" -ne 0 ] || [ "$kind" != "OK" ]; then
  if [ -z "$rest" ]; then
    rest="$(cat "$ERR_FILE" 2>/dev/null)"
  fi
  if [ -z "$rest" ]; then
    rest="CSVをまとめられませんでした。"
  fi
  notify "$rest"
  printf '%s\n' "$RESULT"
  cat "$ERR_FILE" 2>/dev/null
  rm -f "$ERR_FILE"
  exit 1
fi
rm -f "$ERR_FILE"

out_path=$(printf '%s' "$first_line" | cut -f 2)
nfiles=$(printf '%s' "$first_line" | cut -f 3)
nrows=$(printf '%s' "$first_line" | cut -f 4)
nskipped=$(printf '%s' "$first_line" | cut -f 5)

message="CSVを1枚にまとめました。
解析CSV: ${nfiles} ファイル
データ行: ${nrows}
保存先:
${out_path}

元のCSVは変更していません。このファイルを柳までご返送ください。"
if [ "${nskipped:-0}" != "0" ]; then
  message="${message}
（対象外として読み飛ばしたファイル: ${nskipped}）"
fi

printf '%s\n' "$RESULT"
notify "$message"
reveal_file "$out_path"
exit 0
