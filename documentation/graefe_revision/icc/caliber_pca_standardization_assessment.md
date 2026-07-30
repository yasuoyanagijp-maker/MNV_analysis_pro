# Caliber Uniformity — PCA utilization & standardization assessment

**Date:** 2026-07-31  
**Scope:** App pipeline Caliber Uniformity Score (`stability_score`) vs offline proxy `caliber_C_winsor_inv_nv_cv`  
**Sources:** `src/core/pattern_metrics.py`, `src/core/mnv_pipeline.py`, `src/core/mnv_analysis.py`, `src/core/skeleton_analysis.py`, `resources/reference_metrics/stability_ref_*.json`, `documentation/graefe_revision/icc/caliber_*`

---

## Verdict（日本語・要約）

### (1) PCA 重みはどのくらい使われているか？

- **推論時に PCA は毎回“適用”されるが、再フィットはされない。** 学習済みの `pc1_weights` / `pc2_weights` が固定線形結合として JSON から読まれる。
- **最終スコアの約 90% が PCA 由来**（PC1 70% + PC2 20%）、残 10% が TrunkDist。
- ただし **PC1 の 4 特徴ローディングはほぼ均等（≈0.49–0.52）** で、PC1 は「不等重みの特徴選択」というより **高相関 4 指標の等重み合成に近い**。学習分散説明率は層別で PC1 **76–93%**（JSON の `explained_variance_ratio`）だが、**最終合成重みは EVR ではなく固定 0.7/0.2/0.1**。
- 結論: **「PCA ベース」は実装どおり凍結適用されている**が、**単一 CV との差は“PCA の不等重み”より“放射プロファイル 4 指標＋Trunk＋区分線形”の複合定義側**にある。

### (2) 標準化はどのくらい保証されているか？

- **強い（ロック）:** 層別参照コホートの **μ/σ（Z 化）・PC ローディング・piecewise min/median/max・final_weights** は JSON 固定。バッチ／症例ごとに再推定しない。
- **弱い:** 入力の `stab_*` 自体が ROI 依存の 10-bin 放射径に依存。層間の生物学的同等性は median→50 では保証されない（改訂 Response でも撤回済み）。Trunk 正規化はパイプライン上 **complexity_ref** の `trunk_scale_correction` を共有使用。
- 新スコア `caliber_C_winsor_inv_nv_cv` は **PCA 完全バイパス**。代わりに ICC プール（46×3）で Winsorize／piecewise を **オフライン再推定**しており、アプリ参照 JSON とは別系統。

---

## 1. 原定義：このアプリにおける “caliber uniformity”

| 項目 | 内容 |
|------|------|
| 表示名（CSV） | `Caliber Uniformity Score` |
| 内部名 | `stability_score`（Stability / Caliber Uniformity） |
| マッピング | `src/utils/mnv_imagej_csv.py`: `stability_score` → `Caliber Uniformity Score` |
| 方式 | method v3: **サイズ別独立 PCA** + piecewise 補正（2026-05-28 再構築） |

### 1.1 入力特徴（PCA に入るもの）

放射径プロファイル（**10 bins**、中心→辺縁の層別平均径 μm）から `_compute_stability_raw` が算出:

| 内部キー | 意味 |
|----------|------|
| `stab_cv` | 10-bin 径の CV（%） |
| `stab_mean_adjacent_change` | 隣接 bin 相対変化率の平均（上限クリップあり） |
| `stab_residual_cv` | 線形トレンド除去後の残差 CV |
| `stab_range_percent` | (max−min)/mean × 100 |

**重要:** これら `stab_*` はバッチ CSV に **出力されない**。CSV の `NV Diameter (CV)` は **別物**（skeleton 距離マップ上の全有効点の径 CV）。

### 1.2 推論式（凍結 PCA 線形結合）

実装: `calculate_stability_score` in `src/core/pattern_metrics.py`

1. \(Z_m = (x_m - \mu_m) / \sigma_m\)（参照 JSON の μ/σ）
2. \(\mathrm{PC1_{raw}} = \sum_m Z_m w^{(1)}_m\)，\(\mathrm{PC2_{raw}} = \sum_m Z_m w^{(2)}_m\)
3. \(\mathrm{PC1_{inv}} = -\mathrm{PC1_{raw}}\)（PC1＝不安定性方向）
4. 各 PC を piecewise（min→0, median→50, max→100）
5. \[
   \mathrm{Score} = 0.7\,\mathrm{PC1_{score}} + 0.2\,\mathrm{PC2_{score}} + 0.1\,\mathrm{TrunkDist}
   \]
   （0–100 clip。高いほど均一／安定）

参照 JSON:  
`resources/reference_metrics/stability_ref_{small|small_3mm|large}.json`

### 1.3 TrunkDist（PCA 外・10%）

`calculate_trunk_distribution_score`（偏心・角度 CV・中心太血管比・中心/辺縁径比）→ raw 0–100 →  
パイプラインでは `apply_trunk_scale_correction(..., complexity_ref)` で層別 piecewise 後、stability にも同じ正規化 Trunk を渡す（`mnv_pipeline.py` Phase 2）。

---

## 2. PCA: どこにあり、推論でどう効くか

### 2.1 ローディングの所在（凍結）

| 層 | n_cases | PC1 EVR | PC2 EVR | PC1 各特徴重み（概略） |
|----|---------|---------|---------|------------------------|
| `small` | 34 | **0.934** | 0.047 | 0.507 / 0.491 / 0.501 / 0.501 |
| `small_3mm` | 30 | **0.842** | 0.126 | 0.513 / 0.497 / 0.489 / 0.501 |
| `large` | 49 | **0.759** | 0.191 | 0.515 / 0.500 / 0.460 / 0.524 |

- `explained_variance_ratio` は JSON に保存されるが、**Stability の最終合成は `final_weights` 固定（0.7/0.2/0.1）**。Complexity 側のように EVR で重み付けする実装ではない。
- 推論で `sklearn.PCA` 等を走らせない。**学習済み重みのドット積のみ。**

### 2.2 「PCA がどれだけ効いているか」の定量イメージ

| 観点 | 評価 |
|------|------|
| 推論時に PCA ローディング適用？ | **Yes（毎回）** |
| バッチ／画像ごとに PCA 再学習？ | **No** |
| 最終スコアに占める PCA チャネル | **90%**（Trunk 10% を除く） |
| PC1 内の特徴間の不等重み | **弱い**（ほぼ等重み；4 指標が 1 潜在次元） |
| 学習 PC1 分散説明 | **76–93%**（層依存）→ 4 指標は強く共線 |
| 単一 `stab_cv` だけとの差 | PC1 内では CV ≈ ¼；加えて adjacent / residual / range / PC2 / Trunk |

**正直な言い方:**  
「PCA ベース」は **手続きとして正しく凍結適用**されている。一方で PC1 ローディングがほぼ均等なので、**“PCA が特定特徴を強く選んだ”わけではない**。定量的 caliber uniformity の本体は **放射プロファイル由来の不安定性合成（−PC1）を 70%** とし、残りを PC2・Trunk で補正する設計。

### 2.3 バッチ CSV との関係

- エクスポートされるのは **最終 `Caliber Uniformity Score` のみ**（＋別系統の `NV Diameter (CV)` 等）。
- CSV から原スコアを「同じ PCA で再計算」することは **不可**（`stab_*` 非出力）。
- したがって ICC 強化実験で PCA 重み再調整ができなかったのは実装制約として妥当（`caliber_cv_strengthening_*.md` と一致）。

---

## 3. 標準化（standardization）の保証範囲

### 3.1 ロックされているもの（強い）

| 要素 | ロック先 | 再フィット？ |
|------|----------|--------------|
| 特徴 Z 化の μ, σ | `stability_ref_*.json` | 推論では **しない** |
| PC1/PC2 loadings | 同上 | **しない** |
| PC の piecewise min/median/max | `scale_correction` | **しない** |
| 最終重み 0.7/0.2/0.1 | `final_weights` | **しない** |
| 層選択 | `size_class` ∈ {small_3mm, small, large} | 画像幅／ユーザー 3mm スケールで決定 |

→ **同一 size_class・同一アプリ参照 JSON なら、同じ `stab_*` 入力に対しスコアは決定的。**  
バッチ CSV 間で「別の μ/σ を推定し直す」経路はない。

### 3.2 ロックされていない／弱いもの

| 要素 | 実態 |
|------|------|
| ROI → 10-bin 径 | 観察者 ROI で `stab_*` が動く（ICC 低の主因はここ＋径変動族） |
| 層間比較 | median→50 は **層内アンカー**。層間差は残存（KW 有意・ε²≈0.24；Response で「同等の証拠」を撤回） |
| Trunk 補正の参照 | Stability JSON にも `trunk_scale_correction` があるが、パイプラインは **complexity_ref** を使用（小_3mm では値が一致；意図的共有の可能性） |
| JSON 欠落時 | legacy 複合スコア（固定係数・参照 μ/σ なし）へフォールバック |
| 完全定数配列 | sd=0 のとき **100** を返す特例（テスト互換） |

### 3.3 「標準化が保証する／しないこと」

- **保証:** 参照コホート基準の Z 化と 0–100 写像の **再現性（同一入力→同一スコア）**、層内中央付近への配置。
- **非保証:** 観察者間の入力特徴安定性、層間の生物学的同等性、単一の「真の口径均一性」への単調対応。

---

## 4. 新スコア `caliber_C_winsor_inv_nv_cv` との関係

| 項目 | 原 Caliber（Stability/PCA） | Primary new |
|------|-----------------------------|-------------|
| 入力 | `stab_*`（放射 10-bin）+ Trunk | **`NV Diameter (CV)` のみ** |
| PCA | **使用（凍結）** | **不使用（完全バイパス）** |
| 標準化 | アプリ JSON μ/σ + piecewise | ICC プール p05–p95 Winsorize + (−CV) piecewise |
| 参照カット | 層別訓練コホート（n=30–49） | **46×3 プールで再推定**（オフライン） |
| 構成概念 | 放射プロファイル安定性複合 | skeleton 全体径 CV の頑健逆写像 |
| 原との Spearman | — | ≈ 0 / −0.25 / −0.16（観察者別）→ **同一構成の強化ではない** |
| ICC(2,1) | 0.434 | **0.765**（感度／代替プロキシ） |

**結論:** 新スコアは「PCA 重みを調整した改良版」ではなく、**CSV で見える別定義の均一性プロキシ**。PCA・`stab_*`・Trunk は一切使わない。

---

## 5. 「意図どおり定量できているか」— 正直評価

### 強い点

- 口径均一性を **径プロファイルの変動族**として定義し、参照コホートで Z→PCA→0–100 まで **文書化可能な決定的パイプライン**になっている。
- PCA は訓練時に「4 指標≒1 次元の不安定性」を確認し、推論ではその方向（−PC1）を主軸にする、という使い方として一貫。
- 標準化定数は **凍結**されており、バッチ再推定によるドリフトはない。

### 弱い点

- PC1 が等重みに近いため、**PCA の“重み付けの独自性”は小さい**；実質は高相関 CV 族の合成。
- 入力が ROI 敏感な 10-bin 放射サンプリングに依存し、**観察者再現性（ICC 0.434）が弱い** — 「均一性を測る意図」と「測度の安定性」が乖離。
- CSV の `NV Diameter (CV)` は同族ノイズを示すが PCA 入力ではなく、原スコアとの単調一致も弱い（新プロキシで顕在化）。
- 層間標準化は **数学的中央合わせ**であり、装置横断の同等性は保証しない。

### 総合判定

| 問い | 判定 |
|------|------|
| (1) PCA 重みの実効 | **推論で凍結適用あり（最終の ~90%）。ただし PC1 内はほぼ等重みで、“強い特徴選択 PCA”ではない。学習 EVR は高いが最終重みは固定 0.7/0.2/0.1。** |
| (2) 標準化の保証 | **参照 μ/σ・ローディング・piecewise はロックされ、バッチ再フィットなし → 再現性は強い。ROI／層間同等性までは保証しない。** |
| 意図どおりの定量か | **定義どおりの複合 Stability としては実装一貫。ただし“単純な口径 CV 均一性”としては過剰複合かつ再現性脆弱。新スコアは意図の別解釈（頑健 NV-CV）で ICC は改善するが PCA 定義とは別物。** |

---

## 6. 主要ファイル索引

| パス | 役割 |
|------|------|
| `src/core/pattern_metrics.py` | `calculate_stability_score` / `_compute_stability_raw` / piecewise |
| `src/core/mnv_analysis.py` | 10-bin `radial_profile` |
| `src/core/mnv_pipeline.py` | Trunk 正規化後に stability 再計算 |
| `src/core/skeleton_analysis.py` | `cv_diameter` → CSV `NV Diameter (CV)` |
| `resources/reference_metrics/stability_ref_*.json` | μ/σ, loadings, EVR, scale_correction, final_weights |
| `documentation/graefe_revision/icc/compute_caliber_new_score_icc.py` | 新スコア（PCA なし） |
| `documentation/graefe_revision/icc/caliber_cv_strengthening_changelog.md` | 変更経緯 |

---

*No app restart. No commit/push.*
