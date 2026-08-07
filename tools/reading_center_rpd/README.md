# Reading Center — Dual-CSV RPD Adoption

リーディングセンター向け：**施設CSV × 第2読影CSV** から採用値を作るツールです。

## 固定パイプライン

1. **U2 再計算（必須）** — Caliber / Maturity を standardized U2 に更新  
2. **突合** — Case + Visit（列指定 or ファイル名正規表現）  
3. **採用** — RPD ≤ 20%（既定）→ 算術平均、それ以外 → `NA`（再計測）

$$
\mathrm{RPD}=\frac{|A-B|}{(|A|+|B|)/2}\times 100
$$

**閾値の説明文（標準）:**  
「20%は測定誤差を許容しつつ、過度な除外を避けるために設定した。」

## マイクロン向け出力（3点セット）

| ファイル | 内容 |
|----------|------|
| `{prefix}_adopted_values.csv` | 元バッチ形式の採用値（乖離は NA） |
| `{prefix}_recheck_list.csv` | 主要指標の再計測一覧 |
| `{prefix}_summary.md` | RPD / ICC / Bland–Altman 要約＋根拠文 |

## 必要環境

リポジトリルートで、既存 `.venv`（numpy 入り）を使用:

```bash
cd /path/to/MNV_analysis_pro
.venv/bin/python tools/reading_center_rpd/compute_adopted_from_dual_csv.py --help
```

単独アプリ（PyInstaller）化は **入出力仕様固定後** に行う予定（現時点は CLI）。

## 実行例

```bash
.venv/bin/python tools/reading_center_rpd/compute_adopted_from_dual_csv.py \
  --site-csv path/to/site_reader.csv \
  --reader2-csv path/to/second_reader.csv \
  --out-dir path/to/out \
  --prefix STUDY_SITE01 \
  --rpd-threshold 20 \
  --size-class small_3mm \
  --site-label "SiteA" \
  --reader2-label "CentralReader2" \
  --keep-u2-csv
```

### 多施設でファイル名規則が違う場合

```bash
# Case 列・Visit 列があるとき
  --case-col CaseID --visit-col Visit

# ファイル名から抽出（例: ABC_00123_Week04_...）
  --case-regex '(?P<case>[A-Z]+_\d+)'
```

既定でも `102-001` 形式や `Baseline` / `Week12` をファイル名から推定します。

## 主要指標（RECHECK 判定・サマリー）

- MNV Area (mm2)
- Vsl Area (mm2)
- Vsl Density (Vessel Area/MNV (%))
- Caliber Uniformity Score (U2)
- Maturity Index (U2)
- Network Complexity Score
- Fractal Dim
- Tortuosity

## 関連ドキュメント

- 手順書: [`PROCEDURE_JA.md`](PROCEDURE_JA.md)
- 設定例: [`config_example.yaml`](config_example.yaml)
- トレーニング根拠: `documentation/micron_training_20260727/RPD20_根拠メモ_20260807.md`
- Cursor rule: `.cursor/rules/reading-center-rpd.mdc`

## 将来（仕様固定後）

- Mac / Windows スタンドアロン配布（`tools/caliber_u2` と同型）
- 複数ペア一括（manifest YAML）
- 第3読影（合議）入力の接続
