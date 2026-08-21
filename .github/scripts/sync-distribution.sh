#!/usr/bin/env bash
# Sync user-facing docs and (optionally) release assets to the public distribution repo.
set -euo pipefail

DIST_OWNER="${DIST_OWNER:-yasuoyanagijp-maker}"
DIST_REPO="${DIST_REPO:-ARIAKE_OCTA-distribution}"
DIST_REMOTE="https://github.com/${DIST_OWNER}/${DIST_REPO}.git"
SOURCE_REPO="${GITHUB_REPOSITORY:-${DIST_OWNER}/MNV_analysis_pro}"
WORKROOT="${GITHUB_WORKSPACE:-$(cd "$(dirname "$0")/../.." && pwd)}"
STAGING="$(mktemp -d)"

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

cat > "${CONTENT}/README.md" <<'EOF'
# ARIAKE OCTA — 配布・マニュアル

本リポジトリは **ARIAKE OCTA** の **公開配布用** です。  
アプリ本体（ZIP）のダウンロードと、ユーザー向けマニュアルを提供します。

## ダウンロード

[Releases](https://github.com/yasuoyanagijp-maker/ARIAKE_OCTA-distribution/releases) から OS に合わせて ZIP を取得してください。

| OS | ファイル名の目安 |
|----|------------------|
| macOS（Apple Silicon） | `ARIAKE_OCTA_mac.zip` 等 |
| macOS（Intel） | `ARIAKE_OCTA_macOS_Intel_*.zip` |
| Windows | `ARIAKE_OCTA.zip` |

## マニュアル

| 内容 | リンク |
|------|--------|
| 操作・起動（詳細） | [USER_MANUAL.md](USER_MANUAL.md) |
| 操作の要点（Confirm Selection 等） | [documentation/ARIAKE_OCTA_操作マニュアル_簡易版.md](documentation/ARIAKE_OCTA_操作マニュアル_簡易版.md) |
| 詳細ユーザーマニュアル V2 | [documentation/ARIAKE_OCTA_詳細ユーザーマニュアル_V2.md](documentation/ARIAKE_OCTA_詳細ユーザーマニュアル_V2.md) |
| 多施設グレーディング通知（各サイト／Team YY） | [documentation/collaboration.md](documentation/collaboration.md) |
| ROI の指定方法（手動囲み・血管同定） | [documentation/roi_method.md](documentation/roi_method.md) |

## ログイン（初回起動時）

- **ユーザー名**: ローマ字表記  
- **パスワード**: `ariake2024`

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

rsync -a --delete --exclude='.git' "${CONTENT}/" "${CLONE}/"

cd "${CLONE}"
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
  else
    gh release create "${RELEASE_TAG}" "${ASSET_DIR}"/* \
      --repo "${DIST_OWNER}/${DIST_REPO}" \
      --title "${RELEASE_TAG}" \
      --notes "${NOTES:-Mirrored from ${SOURCE_REPO}.}"
  fi
  echo "==> Release ${RELEASE_TAG} mirrored"
fi
