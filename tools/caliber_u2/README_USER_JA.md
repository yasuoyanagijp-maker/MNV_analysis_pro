# ARIAKE OCTA — Caliber Uniformity CSV ツール

MNV バッチ CSV に **Standardized Caliber Uniformity Score** と **Standardized Maturity Index** を追加するスタンドアロンツールです（GUI 不要）。

## 必要列（CSV ヘッダー）
- `File`
- `NV Diameter (CV)`
- `Dilated vessel (%)`
- `Network Complexity Score`

任意: 既存の `Caliber Uniformity Score` / `Maturity Index` の右隣に Standardized 列を挿入します（旧 `… (U2)` 列がある場合は置き換え）。

## size_class（層）
ファイル名（`File` 列）から自動判定します。
- `3x3` など → `small_3mm`（CIRRUS 3×3）
- Optovue / AngioVue / Solix → `small`
- PlexElite など → `large`

上書き: `--size-class small|large|small_3mm`

## macOS（Apple Silicon arm64）
1. ZIP を展開
2. 初回は Gatekeeper で「開発元を確認できない」と出る場合あり → 右クリック → 開く、または `xattr -cr compute_caliber_u2_from_csv`
3. 実行例:

```bash
./compute_caliber_u2_from_csv INPUT.csv -o OUTPUT.csv
./compute_caliber_u2_from_csv INPUT.csv --inplace
./compute_caliber_u2_from_csv INPUT.csv --size-class small_3mm -o out.csv
```

**注意:** 本バイナリは **Apple Silicon (arm64)** 向けです。Intel Mac では動きません。

## Windows（x64）
1. ZIP を展開
2. PowerShell / コマンドプロンプト:

```bat
compute_caliber_u2_from_csv.exe INPUT.csv -o OUTPUT.csv
compute_caliber_u2_from_csv.exe INPUT.csv --inplace
```

SmartScreen が出た場合は「詳細情報」→「実行」。

## 同梱
実行ファイルに `caliber_u2_device_ref.json`（デバイス参照）が埋め込まれています。別途 JSON を置く必要はありません。
