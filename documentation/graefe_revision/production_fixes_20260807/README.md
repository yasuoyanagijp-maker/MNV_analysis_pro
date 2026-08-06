# Production fixes — 2026-08-07（再アップロード用）

Frozen snapshot `../submission_package_20260731/` は触らず、本番クエリ対応ファイルをここに集約。

## クエリ対応サマリ

| # | Query | Action |
|---|-------|--------|
| 1 | SI file format | Word → **PDF** as `si/ESM_1.pdf`（表タイトルは Supplementary Table S1 のまま）。第2 SI は `si/ESM_2.pdf`。 |
| 2 | Competing Interest（投稿システム） | **著者作業**：オンラインフォームへ下記文字列を貼付。MS 本文は既に一致（変更なし）。 |
| 3 | Figure 1 labelling | `figures/Figure1.tiff` / `Figure1.png` にリネーム（中身は提出済 Figure と同一）。レジェンドはもともと Figure 1。 |
| 4 | Table 5 citation | Table 5 は **存在**（tables ファイル）。本文に in-text 引用が無かったため Results（Table 4 段落末）へ追加。 |

## 再アップロード候補

```
MNV_Analysis_YY_rev1_production_fix.docx   ← File 3 clean に Table 5 引用 + Online Resource 表記を追加
figures/Figure1.tiff                         ← Figure 1（TIFF 主）
figures/Figure1.png                          ← プレビュー
si/ESM_1.pdf                                 ← Supplementary Table S1（推奨アップロード名）
si/ESM_2.pdf                                 ← Expert–algorithm agreement（第2 SI）
si/Supplementary_Table_S1.pdf                ← ESM_1 のエイリアス（同内容）
```

`submission_package_20260731/` 内の提出済 clean docx / `Figure.tiff` はスナップショットとして残置。

## Competing Interest（コピペ用・投稿システム）

```
Y. Yanagi - Consultant/Speaker for Astellas Pharmaceutical, Bayer Yakuhin Ltd, Roche/Chugai Pharmaceutical Co., Ltd., Novartis Pharma K.K., Boehringer Ingelheim Co., Ltd., Santen Pharmaceutical Co., Ltd., Senju Pharmaceutical Co.
```

MS Conflict of Interest セクションはこの文字列と一致済み。**投稿インターフェース側の Competing Interest 欄のみ著者更新が必要**（ガイドライン上、最終掲載はインターフェース入力が優先）。

## SI naming / numbering note

- Graefe SI: text は **PDF** 推奨（`.doc`/`.ppt` は長期保存に不適）。ファイル名は連番 `ESM_1.pdf`, `ESM_2.pdf`。本文では Online Resource として言及。
- SI **figures** は本文図と別番号。本件 S1 は **table** のため `Supplementary Table S1` が正しい（appendix 図の連続番号ルールとは別）。

## Japanese reply

`PRODUCTION_REPLY_JA.md` を参照。
