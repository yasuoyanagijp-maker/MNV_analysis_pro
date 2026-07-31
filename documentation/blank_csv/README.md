# ブランク CSV（マニュアル添付用）

マイクロン社マニュアル添付向け。ヘッダ行のみ（データ行なし）。UTF-8 BOM。

| ファイル | 解析 | 備考 |
|----------|------|------|
| `cvi_results.csv` | CVI（自動解析・既定） | ARIAKE_CVI |
| `実施時期_Parameter.csv` | CVI 実行ログ | Parameter / Value の2列。実ファイル名は `{入力フォルダ名}_Parameter.csv` |
| `MNV_batch_YYYYMMDD_HHMMSS.csv` | MNV | ARIAKE OCTA Flet 版 |
| `VD_batch_YYYYMMDD_HHMMSS.csv` | VD（full SCP/DCP） | ARIAKE OCTA Flet 版 |

## 注意

- **CVI マニュアル解析**では `cvi_results.csv` に 1.5mm / 3.0mm ROI 列などが追加されます。
- **VD single**（浅層のみ）は列セットが異なります（`Vsl Density` 等）。
- MNV / VD の実ファイル名は単一症例時に `MNV_{画像名}_…` / `VD_{患者ID}_…` となる場合があります。

生成日: 2026-07-13

## 追加（2026-07-13・マイクロン依頼）

| ファイル | 内容 |
|----------|------|
| `cvi_results_manual.csv` | CVI **マニュアル解析**（Fovea指定）の列構成 |
| `FolderName_Parameter.csv` | 実行ログ。実ファイル名は `{入力フォルダ名}_Parameter.csv`。Parameter列に項目名あり |

※ 以前の `実施時期_Parameter.csv` はマニュアル文言の仮称であり、実アプリのファイル名ではありません（日本語ファイル名は環境により文字化けすることがあります）。
