# Reference JSON 整合性確認（mainstreamer / mnv_pipeline 向け）

## 参照元

- **complexity_ref_*.json** → `src/core/pattern_metrics.py` の `calculate_complexity_pca()`
- **mnv_classification_ref_*.json** → `src/core/pattern_classifier.py` の `classify_morphology_final()`, `classify_pathophysiology_final()`, `check_arteriolarized()` および `_ref_p()`

（mainstreamer.py は直接これらを読まず、`mnv_pipeline` 経由で上記を使用）

---

## 1. complexity_ref_*.json

### 期待されるキー

| キー | 用途 | 現状 |
|-----|------|------|
| `mu` | 各指標の平均（Z = (x - mu)/sigma） | 必須・存在 |
| `sigma` | 各指標の標準偏差 | 必須・存在 |
| `pc1_weights` | PC1 の重み（指標名 → 係数） | 必須・存在 |
| `pc2_weights` | PC2 の重み | 必須・存在 |
| `metrics` | 使用する指標名のリスト（`mu`/`sigma`/`pc1_weights`/`pc2_weights` に存在すること） | 任意・存在 |
| `score_min`, `score_max` | PC1_raw の min-max スケール用 | 必須・存在 |
| `PC2_min`, `PC2_max` | PC2_raw の min-max スケール用（参照群から算出） | 必須・存在 |
| `explained_variance_ratio` | 重み [PC1, PC2]、残りが Trunk | 必須・存在 |

### アプリ側の計算式（pattern_metrics）※CSV と同一

- Z = (value - mu) / sigma（各指標）
- PC1_raw = Σ(Z × pc1_weights), PC2_raw = Σ(Z × pc2_weights)
- **PC1_score = clip(100 × (PC1_raw - score_min) / (score_max - score_min), 0, 100)**（線形 min-max）
- **PC2_score = clip(100 × (PC2_raw - PC2_min) / (PC2_max - PC2_min), 0, 100)**（ref の PC2_min/PC2_max 使用）
- complexity_score = PC1_score×evr[0] + PC2_score×evr[1] + trunk_score×(1 - evr[0] - evr[1]) → clip(0, 100)
- 重みは `explained_variance_ratio` を使用

### 期待される値

- `mu`, `sigma`, `pc1_weights`, `pc2_weights`: 指標名（`metrics` の要素）をキーにした数値
- `final_weights`: `PC1`, `PC2`, `TrunkDist` は数値（float）

---

## 2. mnv_classification_ref_*.json

### 期待されるキー（パーセンタイルブロック）

各指標ごとに `P10`, `P25`, `P40`, `P50`, `P60`, `P65`, `P75`, `P90` のいずれも **数値** であること。

分類で参照される指標:

| 指標 | 使用箇所 | 使用パーセンタイル |
|------|----------|---------------------|
| `complexity_score` | Level1 形態分類 | P10, P30(補間), P40, P60, P65 |
| `maturity_index` | Level2 病態分類 | P25, P40, P75 |
| `stability_score` | Level2 病態分類 | P25, P40, P75 |
| `junction_density` | check_arteriolarized | P60 |
| `loop_total` | check_arteriolarized | P60 |
| `mean_diameter_um` | check_arteriolarized | P50 |
| `arteriolarization_segment_count` | check_arteriolarized | P50 |

P30 は `_ref_p()` 内で P25 と P40 の線形補間で算出される。

### 期待される値

- 各ブロックは `{"P10": number, "P25": number, ...}` の形式
- 数値は 0–100 や実測スケール（例: loop_total）など指標に応じた範囲

---

## 3. 静的结构チェック結果（実施済み）

- complexity_ref_large / small / small_3mm: 必須キー・metrics と mu/sigma/weights の対応を確認済み → **OK**
- mnv_classification_ref_large / small / small_3mm: 上記全指標で P10–P90 が存在し数値 → **OK**

---

## 4. 計算式（CSV とアプリは同一）

アプリ（pattern_metrics.calculate_complexity_pca）は CSV 用スクリプト（update_complexity_maturity_from_csv.py）と同じ式を使用しています。

- PC1/PC2: 線形 min-max（score_min/score_max, PC2_min/PC2_max）
- 重み: explained_variance_ratio（evr[0], evr[1], 残り Trunk）
- Trunk: 固定値 50

---

## 5. まとめ

- **構造・必須キー・型**: 現状の JSON は pattern_metrics / pattern_classifier の期待と整合しています。
- **値の意味**: complexity_score / maturity_index のパーセンタイルは CSV 用の計算式に基づいています。アプリは別式（sigmoid + final_weights）で complexity を計算しているため、数値の対応には上記の違いを考慮してください。
