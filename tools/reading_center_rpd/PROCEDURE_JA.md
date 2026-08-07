# 手順書：施設CSV × 第2読影CSV → 採用値（RPD 20%）

対象: マイクロン／リーディングセンター／エージェント再現用

## 前提

- 入力は常に **2本**（施設側読影 CSV と 第2読影 CSV）
- 採用前に **U2 再計算は必須**
- 出力はマイクロン向け **3点セット**
- 単独アプリ化は仕様固定後（現在は本 CLI）

## 手順

### 1. CSV を用意

両ファイルとも ARIAKE OCTA バッチ CSV（`File` 列、数値指標列あり）。  
Analyst 名は異なってよい。

### 2. 突合キーを確認

優先順:

1. `--case-col` / `--visit-col` があればそれを使用  
2. なければ `File` / `ID` から  
   - Case: `102-001` 形式など（`--case-regex` で上書き可）  
   - Visit: `Baseline` / `Week12` など  

同じ Case+Visit が両CSVに1行ずつあることを確認する。

### 3. コマンド実行

```bash
cd /path/to/MNV_analysis_pro

.venv/bin/python tools/reading_center_rpd/compute_adopted_from_dual_csv.py \
  --site-csv SITE.csv \
  --reader2-csv READER2.csv \
  --out-dir ./out_rc \
  --prefix TRIAL_SITE \
  --rpd-threshold 20 \
  --size-class small_3mm \
  --site-label "Facility" \
  --reader2-label "Reader2" \
  --keep-u2-csv
```

### 4. 成果物を確認・送付

| 成果物 | 用途 |
|--------|------|
| `*_adopted_values.csv` | 採用値（正式提出用・元形式） |
| `*_recheck_list.csv` | NA になった主要指標の一覧 |
| `*_summary.md` | 根拠サマリー（RPD/ICC/BA＋説明文） |

### 5. 再計測

`recheck_list` の Visit を再読影 or 合議し、新しい CSV ペアで再実行する。

## コード上の採用ロジック（要約）

```text
for each matched (Case, Visit):
  for each numeric metric:
    RPD = |A-B| / mean(|A|,|B|) * 100
    if both finite and RPD <= 20:
      adopted = (A+B)/2
    else:
      adopted = NA
```

実装: `compute_adopted_from_dual_csv.py`  
U2: `tools/caliber_u2/compute_caliber_u2_from_csv.py` → `src/core/caliber_u2.py`

## 検証用（トレーニングデータ）

```bash
.venv/bin/python tools/reading_center_rpd/compute_adopted_from_dual_csv.py \
  --site-csv documentation/micron_training_20260727/mnv_batch_20260726_145327_3c94f5.csv \
  --reader2-csv documentation/micron_training_20260727/mnv_batch_20260731_162922_e4fae1.csv \
  --out-dir documentation/micron_training_20260727/rc_tool_smoke_102-001 \
  --prefix 102-001 \
  --rpd-threshold 20 \
  --size-class small_3mm \
  --site-label Inoda \
  --reader2-label Inoue
```

102-002 も同様（site=`...644ccd.csv`, reader2=`...5d7ec1.csv`）。
