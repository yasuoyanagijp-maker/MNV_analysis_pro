#!/usr/bin/env bash
# Sync user-facing docs and (optionally) release assets to the public distribution repo.
set -euo pipefail

DIST_OWNER="${DIST_OWNER:-yasuoyanagijp-maker}"
DIST_REPO="${DIST_REPO:-ARIAKE_OCTA-distribution}"
DIST_REMOTE="https://github.com/${DIST_OWNER}/${DIST_REPO}.git"
SOURCE_REPO="${GITHUB_REPOSITORY:-${DIST_OWNER}/MNV_analysis_pro}"
WORKROOT="${GITHUB_WORKSPACE:-$(cd "$(dirname "$0")/../.." && pwd)}"
STAGING="$(mktemp -d)"
DRY_RUN="${DRY_RUN:-false}"

cleanup() { rm -rf "${STAGING}"; }
trap cleanup EXIT

echo "==> Preparing distribution content from ${WORKROOT}"

CONTENT="${STAGING}/content"
mkdir -p "${CONTENT}/documentation"

cp "${WORKROOT}/USER_MANUAL.md" "${CONTENT}/"
cp "${WORKROOT}/documentation/README.md" "${CONTENT}/documentation/"
cp "${WORKROOT}/documentation/ARIAKE_OCTA_操作マニュアル_簡易版.md" "${CONTENT}/documentation/"
cp "${WORKROOT}/documentation/ARIAKE_OCTA_詳細ユーザーマニュアル_V2.md" "${CONTENT}/documentation/"
cp "${WORKROOT}/documentation/ARIAKE_OCTA_詳細ユーザーマニュアル_V2_付録_マクロ本文.md" "${CONTENT}/documentation/"
cp "${WORKROOT}/documentation/collaboration.md" "${CONTENT}/documentation/"
cp "${WORKROOT}/documentation/roi_method.md" "${CONTENT}/documentation/"

# How-to videos are source files in this repo and must be copied into the
# distribution tree. rsync --delete previously wiped documentation/videos/
# because staging did not include them (commit 70cbdc6 on ARIAKE_OCTA-distribution).
# Copy only these two public operation clips (no patient data).
VIDEOS_SRC="${WORKROOT}/documentation/videos"
VIDEOS_DST="${CONTENT}/documentation/videos"
mkdir -p "${VIDEOS_DST}"
cp "${VIDEOS_SRC}/ARIAKE_OCTA_howto.mp4" "${VIDEOS_DST}/"
cp "${VIDEOS_SRC}/ARIAKE_OCTA_grader2_folder.mp4" "${VIDEOS_DST}/"

# Public README body must match ARIAKE_OCTA-distribution main
# (squash merge of PR #3, commit ed38218). Do not revert to old ZIP
# names or a plaintext login password.
cat > "${CONTENT}/README.md" <<'EOF'
# ARIAKE OCTA — 配布・マニュアル

本リポジトリは **ARIAKE OCTA** の **公開配布用** です。  
アプリ本体（ZIP）のダウンロードと、ユーザー向けマニュアルを提供します。

現行版は **v1.2.5** です。

## ダウンロード

[v1.2.5 の Releases](https://github.com/yasuoyanagijp-maker/ARIAKE_OCTA-distribution/releases/tag/v1.2.5) から、お使いの OS に合う ZIP を取得してください。

| OS | ファイル |
|----|----------|
| macOS（Apple Silicon） | [`ARIAKE_OCTA_mac_v1.2.5.zip`](https://github.com/yasuoyanagijp-maker/ARIAKE_OCTA-distribution/releases/download/v1.2.5/ARIAKE_OCTA_mac_v1.2.5.zip) |
| macOS（Intel） | [`ARIAKE_OCTA_macOS_Intel_v1.2.5.zip`](https://github.com/yasuoyanagijp-maker/ARIAKE_OCTA-distribution/releases/download/v1.2.5/ARIAKE_OCTA_macOS_Intel_v1.2.5.zip) |
| Windows | [`ARIAKE_OCTA_win_v1.2.5.zip`](https://github.com/yasuoyanagijp-maker/ARIAKE_OCTA-distribution/releases/download/v1.2.5/ARIAKE_OCTA_win_v1.2.5.zip) |

**Apple Silicon 用と Intel 用は別 ZIP です。** Apple Silicon に Intel 用は入れないでください。

チップの見分け方: Apple メニュー（画面左上）→ **このMacについて**。

- **チップ** が Apple M1 / M2 / M3 / M4 など → Apple Silicon 用（`ARIAKE_OCTA_mac_v1.2.5.zip`）
- **プロセッサ** が Intel と出る → Intel 用（`ARIAKE_OCTA_macOS_Intel_v1.2.5.zip`）

## Mac へのインストール（v1.2.5）

同梱の **`Macインストール手順.txt`** が正です。Apple の公証は使っていません。

1. ZIP をダブルクリックして展開する。Finder で `ARIAKE_OCTA.app` と `インストール.command` が同じフォルダにあることを確認する。
2. **macOS 15（Sequoia）以降**では、右クリック →「開く」だけでは失敗することがあります。次の（A）または（B）で `インストール.command` を実行してください。

**【（A）ターミナル方式（推奨）】**

フォルダへ移動するコマンド（`cd`）は不要です。

1. ターミナルを開く。
2. `xattr -cr ` と入力する（**`-cr` のあと半角スペース**。まだ Enter は押さない）。
3. Finder の展開フォルダをターミナルへドラッグ＆ドロップする。パスが付いたら Enter。
4. Finder に戻り、`インストール.command` をダブルクリックする。

**【（B）システム設定方式】**

1. `インストール.command` を一度ダブルクリックする（ブロックされます）。
2. Apple メニュー → システム設定 → プライバシーとセキュリティ。
3. ページ下部の **「このまま開く」** → 確認の **「開く」** → Mac のログインパスワード（アプリのパスワードではありません）。

**macOS 14 以前**は、右クリック（または Control + クリック）→「開く」でも起動できます。

3. 画面の案内に従い Applications へ入れます。すでに入っている場合は上書きの確認で Enter。
4. 次回以降は Launchpad または Applications の **ARIAKE_OCTA** から起動します。

**起動時の Dock**

- Dock に **ARIAKE_OCTA** と **Flet** のアイコンが二つ出ることがあります。想定どおりです。
- Intel Mac では起動時に Dock がしばらく跳ねることがあります。待ってください。機能には影響しません。

**ログインで「Connection Error: All connection attempts failed」と出る場合**

パスワードや施設コードの入力ミスではありません。同じ Mac 内の解析エンジンに届いていない状態です。  
ターミナルで `codesign --deep` を繰り返さないでください。もう一度（A）の `xattr -cr` を行ったうえで、`インストール.command` で Applications へ入れ直してください。

## Windows へのインストール（v1.2.5）

1. ZIP 内のファイルを**すべて**展開する。
2. `ARIAKE_OCTA.exe` と `_internal` フォルダを**同じ場所**に置いたまま、`ARIAKE_OCTA.exe` を実行する（片方だけ別フォルダへ移さない）。
3. SmartScreen（Windows によって PC が保護されました）が出たら **詳細情報** → **実行**。

## マニュアル

| 内容 | リンク |
|------|--------|
| 操作・起動（詳細） | [USER_MANUAL.md](USER_MANUAL.md) |
| 操作の要点（Confirm Selection 等） | [documentation/ARIAKE_OCTA_操作マニュアル_簡易版.md](documentation/ARIAKE_OCTA_操作マニュアル_簡易版.md) |
| 詳細ユーザーマニュアル V2 | [documentation/ARIAKE_OCTA_詳細ユーザーマニュアル_V2.md](documentation/ARIAKE_OCTA_詳細ユーザーマニュアル_V2.md) |
| 多施設グレーディング通知（各サイト／Team YY） | [documentation/collaboration.md](documentation/collaboration.md) |
| ROI の指定方法（手動囲み・血管同定） | [documentation/roi_method.md](documentation/roi_method.md) |

## 操作ビデオ

インストール（Mac/Windows）の手順ではなく、**解析画面の操作**を示したものです（日本語字幕・音声なし）。

| 内容 | リンク | 目安 |
|------|--------|------|
| 第1グレーダー（Confirm Selection → ROI → 解析 → 結果保存） | [documentation/videos/ARIAKE_OCTA_howto.mp4](documentation/videos/ARIAKE_OCTA_howto.mp4) | 約1分10秒 |
| 第2リーダー（ローカル自動スキャン・フォルダ指定） | [documentation/videos/ARIAKE_OCTA_grader2_folder.mp4](documentation/videos/ARIAKE_OCTA_grader2_folder.mp4) | 約12秒 |

**第1グレーダー**

<video controls src="documentation/videos/ARIAKE_OCTA_howto.mp4"></video>

**第2リーダー（フォルダ指定）**

<video controls src="documentation/videos/ARIAKE_OCTA_grader2_folder.mp4"></video>

## ログイン（初回起動時）

ログイン情報は、必要な方はメール（yasuo.yanagi@gmail.com）でお問い合わせください。

## 画像の選択（重要）

解析開始時は **画像ファイル単位ではなくフォルダ単位** で指定してください。

1. 新しいフォルダを作成する  
2. 解析したい画像をそのフォルダに入れる  
3. アプリでその **フォルダ** を選び、「Confirm Selection」を押す  

## お問い合わせ

柳 靖雄（お花茶屋眼科）  
yasuo.yanagi.jp@gmail.com

---

*ソースコードは非公開リポジトリで管理しています。本リポジトリは配布物とマニュアルのみを公開しています。*

EOF

CLONE="${STAGING}/repo"
git clone --depth 1 "${DIST_REMOTE}" "${CLONE}" 2>/dev/null || {
  mkdir -p "${CLONE}"
  cd "${CLONE}"
  git init -b main
  git remote add origin "${DIST_REMOTE}"
  cd - >/dev/null
}

# P-filters keep documentation/videos/ if a copy is ever skipped, so --delete
# cannot remove the emailed how-to paths again.
rsync -a --delete --exclude='.git' \
  --filter='P /documentation/videos/' \
  --filter='P /documentation/videos/**' \
  "${CONTENT}/" "${CLONE}/"

cd "${CLONE}"
if [[ "${DRY_RUN}" == "true" ]]; then
  echo "==> DRY_RUN: resulting files (no commit, no push, no release mirror)"
  find . -path './.git' -prune -o -type f -print | sed 's|^\./||' | sort
  echo "==> DRY_RUN: git status --short"
  git status --short
  exit 0
fi
if [[ -n "${GH_TOKEN:-}" ]]; then
  git remote set-url origin "https://x-access-token:${GH_TOKEN}@github.com/${DIST_OWNER}/${DIST_REPO}.git"
fi
git add -A
if git diff --cached --quiet; then
  echo "==> No documentation changes to publish"
else
  git -c user.name="github-actions[bot]" -c user.email="41898282+github-actions[bot]@users.noreply.github.com" \
    commit -m "Sync user manuals from ${SOURCE_REPO}"
  git push -u origin main
  echo "==> Documentation synced"
fi

if [[ "${SYNC_RELEASE:-false}" == "true" && -n "${RELEASE_TAG:-}" ]]; then
  echo "==> Mirroring release ${RELEASE_TAG} from ${SOURCE_REPO}"
  ASSET_DIR="${STAGING}/assets"
  mkdir -p "${ASSET_DIR}"
  gh release download "${RELEASE_TAG}" --repo "${SOURCE_REPO}" --dir "${ASSET_DIR}"
  NOTES="$(gh release view "${RELEASE_TAG}" --repo "${SOURCE_REPO}" --json body --jq .body)"
  if gh release view "${RELEASE_TAG}" --repo "${DIST_OWNER}/${DIST_REPO}" >/dev/null 2>&1; then
    gh release upload "${RELEASE_TAG}" "${ASSET_DIR}"/* --repo "${DIST_OWNER}/${DIST_REPO}" --clobber
    if [[ -n "${NOTES}" ]]; then
      NOTES_FILE="$(mktemp)"
      printf '%s\n' "${NOTES}" > "${NOTES_FILE}"
      gh release edit "${RELEASE_TAG}" --repo "${DIST_OWNER}/${DIST_REPO}" --notes-file "${NOTES_FILE}"
      rm -f "${NOTES_FILE}"
    fi
  else
    gh release create "${RELEASE_TAG}" "${ASSET_DIR}"/* \
      --repo "${DIST_OWNER}/${DIST_REPO}" \
      --title "${RELEASE_TAG}" \
      --notes "${NOTES:-Mirrored from ${SOURCE_REPO}.}"
  fi
  echo "==> Release ${RELEASE_TAG} mirrored"
fi
