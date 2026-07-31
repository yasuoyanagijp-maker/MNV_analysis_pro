# DISTRIBUTION_SYNC_TOKEN（Fine-grained PAT）

`MNV_analysis_pro` の GitHub Actions（`.github/workflows/sync-distribution.yml`）が、公開配布リポジトリ `ARIAKE_OCTA-distribution` へマニュアルと Release アセットをミラーするために使うシークレットです。

## なぜ Fine-grained PAT か

- `gh auth login` の **OAuth トークン**（`gist` / `repo` / `workflow` など）は、ローカル CLI 用です。Actions の長期シークレットに流用しないでください。
- Actions 用は **Fine-grained personal access token** を作成し、リポジトリシークレット名 `DISTRIBUTION_SYNC_TOKEN` に登録します。
- Fine-grained PAT の作成は GitHub Web UI が必要です（`gh api` では通常作成できません）。

## 作成手順（ブラウザ）

1. 次の URL を開く（要ログイン: `yasuoyanagijp-maker`）:  
   **https://github.com/settings/personal-access-tokens/new**
2. **Token name**: 例 `DISTRIBUTION_SYNC_TOKEN`（分かりやすい名前）
3. **Expiration**: **90 days** 推奨（1 year 可）。カレンダーに更新リマインダを入れる。
4. **Resource owner**: `yasuoyanagijp-maker`
5. **Repository access** → **Only select repositories**:
   - `ARIAKE_OCTA-distribution`
   - `MNV_analysis_pro`
6. **Permissions**（Repository permissions）:
   | リポジトリ | Contents | Metadata |
   |-----------|----------|----------|
   | `ARIAKE_OCTA-distribution` | **Read and write** | Read（自動） |
   | `MNV_analysis_pro` | **Read-only** | Read（自動） |
7. **Generate token** → 表示されたトークンをコピー（再表示不可）。

## シークレット登録

トークンをクリップボードに入れた状態で:

```bash
gh secret set DISTRIBUTION_SYNC_TOKEN --repo yasuoyanagijp-maker/MNV_analysis_pro
```

（プロンプトにトークンを貼り付けて Enter。値はログに出さない。）

または: `MNV_analysis_pro` → Settings → Secrets and variables → Actions → `DISTRIBUTION_SYNC_TOKEN` を更新。

## 動作確認

```bash
gh workflow run "Sync distribution repo" --repo yasuoyanagijp-maker/MNV_analysis_pro \
  -f sync_docs=true -f mirror_release_tag=v1.3.0-caliber-csv-tool
gh run list --repo yasuoyanagijp-maker/MNV_analysis_pro --workflow=sync-distribution.yml --limit 3
```

成功すれば `ARIAKE_OCTA-distribution` 側に docs / release が反映されます。

## ローカル手動同期（任意）

```bash
# シェルに PAT を一時 export（履歴・画面共有に注意）。終わったら unset
export GH_TOKEN='…'   # DISTRIBUTION_SYNC_TOKEN と同じ Fine-grained PAT
SYNC_RELEASE=true RELEASE_TAG=v1.3.0-caliber-csv-tool \
  GITHUB_REPOSITORY=yasuoyanagijp-maker/MNV_analysis_pro \
  ./.github/scripts/sync-distribution.sh
unset GH_TOKEN
```

## ローテーション

- 期限の **1〜2 週間前**に新 PAT を作成 → `gh secret set` で差し替え → 旧トークンを GitHub 上で Revoke。
- OAuth（`gh auth token`）をシークレットに入れ直さない。

## 関連

- 運用概要: [DISTRIBUTION_REPO.md](DISTRIBUTION_REPO.md)
- Workflow: `.github/workflows/sync-distribution.yml`
- Script: `.github/scripts/sync-distribution.sh`
