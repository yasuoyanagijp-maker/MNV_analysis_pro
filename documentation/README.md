# 文書（documentation）

Git で管理する **ユーザー向け・理論向けマニュアル** をこのディレクトリにまとめています。ルートの `README.md` はプロジェクト概要の入り口、`USER_MANUAL.md` / `DEVELOPER.md` は従来どおりリポジトリ直下にあります。

## 収録ファイル

| 内容 | ファイル |
|------|----------|
| Flet 版・詳細（理論・マクロとの差分） | [ARIAKE_OCTA_詳細ユーザーマニュアル_V2.md](ARIAKE_OCTA_詳細ユーザーマニュアル_V2.md) |
| マクロ版ベースの整理・要約（付録） | [ARIAKE_OCTA_詳細ユーザーマニュアル_V2_付録_マクロ本文.md](ARIAKE_OCTA_詳細ユーザーマニュアル_V2_付録_マクロ本文.md) |
| 操作の要点（Confirm Selection 等） | [ARIAKE_OCTA_操作マニュアル_簡易版.md](ARIAKE_OCTA_操作マニュアル_簡易版.md) |
| ImageJ マクロ正本の置き場（予定） | [imagej-macro/README.md](imagej-macro/README.md) |

## ルート直下の関連文書

| 内容 | パス（リポジトリルートから） |
|------|------------------------------|
| 操作・起動の詳細 | `../USER_MANUAL.md` |
| 開発者向け | `../DEVELOPER.md` |
| プロジェクト概要 | `../README.md` |

## PDF にして配布する（印刷）

1. Cursor / VS Code で上記の `.md` を開く。  
2. **Markdown プレビュー**を表示する。  
3. プレビュー画面で **印刷**し、**PDF に保存**（または「Microsoft Print to PDF」等）を選ぶ。  

表や日本語の崩れを抑えたい場合は、プレビューの余白設定や、ブラウザで GitHub の表示を開いてから印刷する方法もあります。

---

**注意**: `.gitignore` では **`docs/` ディレクトリ全体が無視**されています。Git で追跡する文書は **`documentation/`** を使い、`docs/` は別用途（ローカルのみ等）にしてください。
