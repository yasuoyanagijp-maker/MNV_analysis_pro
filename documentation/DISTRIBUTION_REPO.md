# 公開配布リポジトリ（ARIAKE_OCTA-distribution）

開発用リポジトリ `MNV_analysis_pro` を **private** に戻しつつ、**ZIP とマニュアルだけ public** に公開するための構成です。

## 構成

| リポジトリ | 公開 | 内容 |
|-----------|------|------|
| `MNV_analysis_pro` | private（予定） | ソースコード・ビルド・内部文書 |
| `ARIAKE_OCTA-distribution` | **public** | Releases（ZIP）・USER_MANUAL・documentation/ |

## 公開 URL（配布先に案内する URL）

- **ダウンロード**: https://github.com/yasuoyanagijp-maker/ARIAKE_OCTA-distribution/releases
- **操作マニュアル**: https://github.com/yasuoyanagijp-maker/ARIAKE_OCTA-distribution/blob/main/USER_MANUAL.md
- **簡易版**: https://github.com/yasuoyanagijp-maker/ARIAKE_OCTA-distribution/blob/main/documentation/ARIAKE_OCTA_操作マニュアル_簡易版.md

## 初回セットアップ（1回だけ）

### 1. GitHub Fine-grained PAT を作成

**詳細手順（推奨・更新リマインダ込み）**: [DISTRIBUTION_SYNC_TOKEN.md](DISTRIBUTION_SYNC_TOKEN.md)

要点:

- 作成 URL: https://github.com/settings/personal-access-tokens/new
- **Resource owner**: `yasuoyanagijp-maker`
- **Repository access**: `MNV_analysis_pro`（Contents **Read-only**）, `ARIAKE_OCTA-distribution`（Contents **Read and write**）
- **Expiration**: 90 days 推奨（カレンダーに更新リマインダ）
- **禁止**: `gh auth login` の OAuth トークンを Actions シークレットの長期値にしない（ローカル CLI 用）

### 2. シークレットを登録

```bash
gh secret set DISTRIBUTION_SYNC_TOKEN --repo yasuoyanagijp-maker/MNV_analysis_pro
```

または UI: `MNV_analysis_pro` → Settings → Secrets and variables → Actions → `DISTRIBUTION_SYNC_TOKEN`

| Name | Value |
|------|-------|
| `DISTRIBUTION_SYNC_TOKEN` | 上記 Fine-grained PAT |

### 3. 初回同期

GitHub Actions → **Sync distribution repo** → **Run workflow**

- `sync_docs`: true
- `mirror_release_tag`: 必要なら `v1.2.1-mac` / `v1.2.1-win` 等（複数回実行）

### 4. 本体リポジトリを private 化

配布リポジトリへの同期が確認できたら:

```bash
gh repo edit yasuoyanagijp-maker/MNV_analysis_pro --visibility private
```

## 日常運用

1. `MNV_analysis_pro` でビルド
2. `MNV_analysis_pro` に Release を publish（従来どおり）
3. Actions が自動で `ARIAKE_OCTA-distribution` にマニュアルと ZIP をミラー
4. 配布メール・返信では **distribution リポジトリの Releases URL** を案内

手動同期:

```bash
export GH_TOKEN="..."   # DISTRIBUTION_SYNC_TOKEN と同じ PAT
SYNC_RELEASE=true RELEASE_TAG=v1.2.1-mac GITHUB_REPOSITORY=yasuoyanagijp-maker/MNV_analysis_pro \
  ./.github/scripts/sync-distribution.sh
```

## 配布メールでの案内例

```
ダウンロード:
https://github.com/yasuoyanagijp-maker/ARIAKE_OCTA-distribution/releases

操作マニュアル:
https://github.com/yasuoyanagijp-maker/ARIAKE_OCTA-distribution/blob/main/documentation/ARIAKE_OCTA_操作マニュアル_簡易版.md
```
