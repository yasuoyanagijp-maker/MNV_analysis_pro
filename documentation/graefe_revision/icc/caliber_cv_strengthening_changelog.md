# Caliber CV／生指標強化 — 経緯と変更ログ

**Date:** 2026-07-31  
**Scope:** Graefe 改訂向け・3観察者 ICC（YY / Inoue / Osada, intersection **n = 46**, ICC(2,1) absolute agreement）  
**制約:** 既存バッチ CSV 列のみ。再ROI・再セグメンテーション・本解析定義の差し替えは行わない。  
**扱い:** 感度分析／代替プロキシ。原稿の主定義（Caliber Uniformity Score）は変更しない。

---

## 1. 経緯（タイムライン）

| 段階 | 内容 | 主成果物 |
|------|------|----------|
| **① 低 ICC 発見** | 3観察者 ICC で Area 0.859・Complexity 0.807・Maturity 0.659 に対し、**Caliber Uniformity のみ 0.434**。分散成分では σ²_error 51% が支配（観察者主効果は約5%）。 | `icc_multirater_*.csv` / Response 草稿 |
| **② 原因調査** | 複合スコア自体より、径ばらつき系の生指標が脆弱：`NV Diameter (CV)` ICC **0.259**、`Local Diameter Variation (max CV%)` ICC **0.138**。平均径（skel）や枝数・長さは高 ICC（0.76–0.88）。症例レベルの Caliber 不一致は Area と無相関（ρ≈0）。仮説「小 Area → 10-bin 不安定 → 低 ICC」は **部分支持**（生 CV は小病変で崩れるが、スコア不一致の主因ではない）。 | [`caliber_icc_low_investigation.md`](caliber_icc_low_investigation.md) |
| **③ 既存パラメータのみで強化案** | `stab_cv` 等の放射プロファイル入力はバッチ CSV に無い → PCA Stability の重み再調整は不可。CSV 列だけで Winsorize／(−CV)→0–100／Local 除外／skel ブレンド等を候補化。 | [`caliber_cv_strengthening_proposals.md`](caliber_cv_strengthening_proposals.md) |
| **④ 新スコア実装・ICC 再計算** | `compute_caliber_new_score_icc.py` で候補を実装。Primary: `caliber_C_winsor_inv_nv_cv` → ICC **0.434 → 0.765**（+0.331）。Spearman(原 Caliber, 新) ≈ 0 → **同一構成概念の強化ではなく定義置換**。sensitivity 扱いを明記。 | [`caliber_new_score_icc_results.md`](caliber_new_score_icc_results.md) |

---

## 2. 変更前（原定義）

### 2.1 パイプライン上の Caliber Uniformity Score

バッチ CSV の **`Caliber Uniformity Score`** は内部名 `stability_score`（Stability / Caliber Uniformity）のエクスポート名。

**入力（放射径プロファイル由来・バッチ CSV には非出力）:**

| 内部キー | 意味 |
|----------|------|
| `stab_cv` | 径プロファイルの CV |
| `stab_mean_adjacent_change` | 隣接 bin 変化率の平均 |
| `stab_residual_cv` | 線形トレンド除去後の残差 CV |
| `stab_range_percent` | レンジ／平均の百分率 |

**合成手順（method v3: サイズ別独立 PCA）** — `src/core/pattern_metrics.py` の `calculate_stability_score` + `resources/reference_metrics/stability_ref_*.json`:

1. 参照コホートの μ/σ で Z スコア化  
2. PC1・PC2 の線形結合（サイズ別 `pc1_weights` / `pc2_weights`）  
3. PC1 を反転（不安定性 → 安定性）: `pc1_inv = −pc1_raw`  
4. 各 PC を区分線形スケール（median → 50, min→0, max→100）  
5. 最終合成（参照 JSON の `final_weights`）:

\[
\mathrm{Stability} = 0.7\,\mathrm{PC1_{score}} + 0.2\,\mathrm{PC2_{score}} + 0.1\,\mathrm{TrunkDist}
\]

（0–100 clip。高いほど径が均一／安定。）

### 2.2 バッチ CSV に出る関連生指標（PCA 入力ではないが同族）

| CSV 列 | 算出の概要 | 3観察者 ICC(2,1) | 解釈 |
|--------|------------|------------------|------|
| `Caliber Uniformity Score` | 上記 PCA 複合 | **0.434** | 複合スコア |
| **`NV Diameter (CV)`** | skeleton 平均径の CV = \(100 \times \mathrm{SD}/\mathrm{mean}\) | **0.259** | **弱い成分**（σ²_error 72%） |
| **`Local Diameter Variation (max CV%)`** | セグメント平均ブランチ長の CV% | **0.138** | **最弱成分**（σ²_error 77%） |
| `(Skel) Vsl Diameter` | 平均径 | 0.760 | 強い（平均レベル） |
| `Vsl Branches` / `Vsl Length (mm)` | 位相・長さ | 0.81–0.88 | 強い |

**重要な区別:** 原 Caliber の PCA 入力は `stab_*`（CSV 非出力）。調査で「脆弱」と特定されたのは、CSV 上で観測できる **径変動／CV 族**（特に NV Diameter CV・Local max CV）であり、複合スコアがそれらと同族のノイズを引き継いでいる、という診断。

### 2.3 Maturity（下流）

\[
\mathrm{Maturity} = 50 + \frac{\mathrm{Caliber} - \mathrm{Complexity}}{2}
\]

Caliber 低 ICC が Maturity の中間的 ICC（0.659）の主因（Complexity ICC 0.807 で希釈）。

---

## 3. 検討した改善案と採否

制約: **現 CSV のみ**（再ROI・画像再計算なし）。

| 案 | 内容 | 観測 ICC | 採否 | 理由 |
|----|------|----------|------|------|
| **C（Primary）** | Winsorize `NV Diameter (CV)` p05–p95 → (−CV) を piecewise 0–100。**Local max CV 除外** | **0.765** | **採用（感度）** | CV 忠実・最大 ICC。Local の低 ICC チャネルを切る |
| C + Local 軽量 | 0.85×U(NV CV) + 0.15×U(Local max CV) | 0.761 | 不採用（Primary） | C とほぼ同等だが、より弱い Local を再混入 |
| AB ハイブリッド | 0.70×U(NV CV) + 0.30×U(skel diameter) | 0.615 | 副次のみ | 原より改善するが C より劣る。**平均径混入で構成概念がずれる** |
| W（原スコア Winsorize） | 原 `Caliber Uniformity Score` を p05–p95 Winsorize → 再スケール | 0.446 | 不採用 | ほぼ無改善。問題は裾切りではなく複合定義側 |
| Area／枝数ゲート | 小病変で Caliber を報告しない／層別 ICC | （層別で中程度の見込み） | 未実装・将来 | 層別感度としては低コストだが、本件の主実験は定義置換 |
| PCA 重み再調整 | `stab_*` の final_weights 変更 | — | **不可（本件）** | `stab_cv` 等がバッチ CSV に無い |
| 再ビン／MAD／再セグ | 適応 bin・距離変換・Phansalkar 等 | — | **スコープ外** | 画像再パイプラインが必要 |

**やらない方針（Graefe 改訂）:** 一致症例の cherry-pick を主 ICC にする／原稿定義を黙って差し替える／新スコアを「同一 Caliber Uniformity の強化版」と主張する。

---

## 4. 実際にどこをどう変えたか（差分）

### 4.1 対照表

| 項目 | 変更前（原） | 変更後（Primary: `caliber_C_winsor_inv_nv_cv`） |
|------|--------------|--------------------------------------------------|
| **入力列** | `stab_cv`, `stab_mean_adjacent_change`, `stab_residual_cv`, `stab_range_percent` + TrunkDist（＋参照 JSON） | **`NV Diameter (CV)` のみ** |
| **除外** | — | **`Local Diameter Variation (max CV%)` を使わない**；`stab_*`・Trunk・PCA も使わない |
| **前処理** | 参照 μ/σ による Z 化 | プール（46×3=138）の **p05–p95 Winsorize**: CV ∈ **[41.4989, 50.2788]** |
| **方向** | −PC1（不安定 → 安定） | **`x = −CV_w`**（低 CV → 高均一） |
| **スケーリング** | PC ごとの piecewise（median→50） | `x` の min/median/max → **0 / 50 / 100**（パイプラインと同型の piecewise） |
| **複合重み** | 0.7 PC1 + 0.2 PC2 + 0.1 Trunk | **単一チャネル**（重み付け合成なし） |
| **参照カット** | 層別 `stability_ref_*.json` | 本 n=46×3 プール推定（原 JSON ではない） |
| **出力列名** | `Caliber Uniformity Score` | オフライン列 `caliber_C_winsor_inv_nv_cv`（原稿主列は据え置き） |

### 4.2 Primary 式（スクリプト／結果 md と同一）

出典: [`compute_caliber_new_score_icc.py`](compute_caliber_new_score_icc.py) / [`caliber_new_score_icc_results.md`](caliber_new_score_icc_results.md)

1. `CV` = `NV Diameter (CV)` をプール p05–p95 で Winsorize → `CV_w`  
2. `x = −CV_w`  
3. `caliber_C_winsor_inv_nv_cv = piecewise_scale(x; min, median, max → 0, 50, 100)`（clip 0–100）

`piecewise_scale` は「中央値→50」の区分線形（原 Stability の `_piecewise_scale` と同型）。

### 4.3 評価したが Primary にしなかった式

- `caliber_C_local_downweight` = `0.85 × U(winsor NV CV) + 0.15 × U(winsor Local max CV)`  
- `caliber_AB_cv70_skel30` = `0.70 × U(winsor NV CV) + 0.30 × U(skel mean diameter)`  
- `caliber_W_winsor_orig` = 原 Caliber の Winsorize → piecewise 再スケール  

副次 Maturity: `maturity_from_* = 50 + (caliber_new − Network Complexity Score) / 2`（代数は原と同じ）。

### 4.4 やらなかったこと

- 再 ROI / 再セグメンテーション / 再スケルトン  
- 本解析・原稿の Caliber Uniformity **定義差し替え**  
- `stab_*` や PCA 重みのパイプライン変更（アプリ変更なし）  
- 最悪一致症例の除外を主結果にする  

---

## 5. 結果

### 5.1 主比較（n=46, k=3）

| Metric | ICC(2,1) | 95% CI | Δ vs 原 Caliber |
|--------|----------|--------|-----------------|
| Caliber Uniformity（原） | **0.434** | 0.260–0.610 | — |
| **`caliber_C_winsor_inv_nv_cv`（Primary）** | **0.765** | 0.640–0.860 | **+0.331** |
| `caliber_C_local_downweight` | 0.761 | 0.640–0.850 | +0.327 |
| `caliber_AB_cv70_skel30` | 0.615 | 0.400–0.770 | +0.181 |
| `caliber_W_winsor_orig` | 0.446 | 0.270–0.620 | +0.012 |
| Maturity（原） | 0.659 | 0.510–0.780 | — |
| Maturity from primary new | 0.622 | 0.440–0.760 | （改善せず） |

### 5.2 ペア ICC（原 vs Primary）

| Pair | 原 Caliber | Primary new |
|------|------------|-------------|
| YY–Inoue | 0.517 | 0.695 |
| YY–Osada | 0.466 | 0.725 |
| **Inoue–Osada** | **0.284** | **0.883** |

最大の改善は Inoue–Osada。分散成分では原 σ²_error 312.7 → Primary 147.4、σ²_case 265.2 → 554.7。

### 5.3 Caveat（必須）

- **Spearman(原 Caliber, Primary new) ≈ 0.00 / −0.25 / −0.16**（YY / Inoue / Osada）。近零〜負 → **同じ構成概念の単調強化ではない**（CSV のみの代替プロキシ／定義置換）。  
- 原スコアを Winsorize してもほぼ効かない（0.446）→ 利得は **Stability/PCA 複合を robust NV-CV 変換に置き換えたこと**から来る。  
- 新 Caliber で Maturity を組み直しても Maturity ICC は上がらない（0.622 < 0.659）。  
- 参照カットは本セットプール推定。  
- **推奨扱い:** sensitivity / exploratory。原稿の主 Caliber 定義は維持。使う場合は「alternate CSV-only proxy」と明示。

---

## 6. ファイル一覧（相対リンク）

### 調査・提案・結果（markdown）

- [`caliber_icc_low_investigation.md`](caliber_icc_low_investigation.md) — 低 ICC の原因調査  
- [`caliber_cv_strengthening_proposals.md`](caliber_cv_strengthening_proposals.md) — CSV のみ強化案と採否整理  
- [`caliber_new_score_icc_results.md`](caliber_new_score_icc_results.md) — 新スコア式・ICC 結果・caveat  
- [`caliber_cv_strengthening_changelog.md`](caliber_cv_strengthening_changelog.md) — 本ファイル（経緯＋差分ログ）

### スクリプト・出力 CSV

- [`compute_caliber_new_score_icc.py`](compute_caliber_new_score_icc.py) — 実装・ICC 再計算  
- [`caliber_new_score_long.csv`](caliber_new_score_long.csv)  
- [`caliber_new_score_wide.csv`](caliber_new_score_wide.csv)  
- [`caliber_new_score_icc_stats.csv`](caliber_new_score_icc_stats.csv)  
- [`caliber_new_score_icc_pairwise.csv`](caliber_new_score_icc_pairwise.csv)

### 参照（原 ICC・原定義コード）

- 原多者 ICC: `icc_multirater_wide.csv`, `icc_multirater_long.csv`, `icc_multirater_variance_components.csv`, `icc_multirater_pairwise.csv`  
- 原スコア実装: `src/core/pattern_metrics.py`（`calculate_stability_score`）  
- 参照 JSON: `resources/reference_metrics/stability_ref_*.json`  
- CSV 列マッピング: `src/utils/mnv_imagej_csv.py`（`stability_score` → `Caliber Uniformity Score`）

---

## Addendum 2026-07-31 — major-param sweep & new score hunt

- Full numeric ICC table: [`icc_all_numeric_params_n46.md`](icc_all_numeric_params_n46.md)
- Logical majors + candidate scores: [`caliber_major_params_new_score.md`](caliber_major_params_new_score.md)
- Recommended transferable score: `caliber_U2_softcv_dil` (ICC(2,1) **0.838**) vs original Caliber **0.434** and `caliber_C_winsor_inv_nv_cv` **0.765**.
- Negative controls: residualized CV (ICC collapsed); inverse absolute SD / rank-harmonized scores (higher ICC but wrong construct or non-transferable).
- Script: `compute_caliber_major_params_new_score.py`
