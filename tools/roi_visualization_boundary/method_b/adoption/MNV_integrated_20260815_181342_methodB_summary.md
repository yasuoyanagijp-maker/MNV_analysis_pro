# 統合解析データ (dual-read adoption) — 2026-08-15

- 第1グレーダー CSV: `MNV_batch_methodB_g1.csv`
- 第2リーダー CSV: `MNV_batch_methodB_g2.csv`
- RPD 閾値: **20%**
- 突合成功: **3** 行（第1のみ: 0 / 第2のみ: 0）

## ルール

1. 両CSVで Caliber/Maturity **U2** を再計算。
2. ファイル名（stem）で行を突合。
3. RPD ≤ 20% → 採用値 = 算術平均、超過 → **NA**（再計測）。

**根拠:** 20%は測定誤差を許容しつつ、過度な除外を避けるために設定した。

## RECHECK

- 主要指標セル: 5 件（対象ファイル 2 件）
  - MNV Area (mm2): 2
  - Vsl Area (mm2): 2
  - Fractal Dim: 1
