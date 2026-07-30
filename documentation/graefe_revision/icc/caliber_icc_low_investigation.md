# Why is Caliber Uniformity ICC low? (3-rater, n=46)

**Date:** 2026-07-30  
**Set:** YY, Inoue, Osada · intersection n=46 · ICC(2,1) absolute agreement  
**Primary ICCs (reference):** Area 0.859 · Complexity 0.807 · Maturity 0.659 · **Caliber 0.434**  
**Sources:** `icc_multirater_wide.csv`, `icc_multirater_long.csv`, `icc_multirater_variance_components.csv`, `icc_multirater_pairwise.csv`, `icc_cases_ranked_by_concordance.csv`, observer batch CSVs under `incoming/`

---

## 1. Variance components (already computed)

$$\mathrm{ICC}_{\mathrm{case}} = \sigma^2_{\mathrm{case}} / (\sigma^2_{\mathrm{case}} + \sigma^2_{\mathrm{observer}} + \sigma^2_{\varepsilon})$$

| Metric | σ²_case | σ²_observer | σ²_error | % case | % obs | % error | ICC |
|--------|---------|-------------|---------|--------|-------|---------|-----|
| Area | 1.096 | 0.0654 | 0.114 | 85.9% | 5.1% | 9.0% | 0.859 |
| Complexity | 194.1 | 11.11 | 35.19 | 80.7% | 4.6% | 14.6% | 0.807 |
| **Caliber** | **265.2** | **33.27** | **312.7** | **43.4%** | **5.4%** | **51.2%** | **0.434** |
| Maturity | 208.8 | 10.27 | 97.75 | 65.9% | 3.2% | 30.9% | 0.659 |

**Caliber interpretation**

- The observer main-effect share (~5%) is **similar** to Area/Complexity — Caliber is **not** low ICC primarily because one rater has a huge fixed offset in the ANOVA sense.
- What is distinctive is **σ²_error > σ²_case** (51% vs 43%): residual / case×observer interaction dominates. Same lesion → different Caliber depending on which observer drew the ROI, in a **non-systematic** (case-specific) way.
- Absolute σ²_observer for Caliber (33.3) is larger than Complexity (11.1) on the 0–100 scale, and paired biases are real (see §3), but residual noise is the larger share of the ICC penalty.

---

## 2. Per-case discordance and correlates

For each metric, 3-rater **range** = max − min and **SD** (ddof=1). Spearman correlations with **Caliber range**:

| Correlate | Spearman ρ | p | Note |
|-----------|------------|---|------|
| Maturity range | **0.799** | 2.8×10⁻¹¹ | Expected (Maturity formula) |
| Vessel density range | 0.301 | 0.042 | Mild |
| Vessel density mean | −0.339 | 0.021 | Lower density ↔ larger Caliber discordance |
| Caliber mean | −0.327 | 0.027 | Lower mean Caliber ↔ larger discordance |
| **Area range** | **0.077** | **0.61** | **No association** |
| **Area mean** | **−0.046** | **0.76** | **No association** |
| Complexity range | 0.036 | 0.81 | No association |
| Complexity mean | 0.204 | 0.18 | NS |
| Skel vessel diameter mean | −0.248 | 0.096 | NS trend |
| NV Diameter (CV) mean | −0.124 | 0.41 | NS |
| Local Diameter max CV% mean | −0.220 | 0.14 | NS |
| Vsl Branches / Length mean | −0.12 / −0.07 | >0.4 | NS |

**Pearson** Area mean vs Caliber range: r = 0.109, p = 0.47 (same null result).

Partial Spearman: Caliber range ~ Area mean | Area range → ρ = −0.11, p = 0.47; Caliber range ~ Area range | Area mean → ρ = 0.13, p = 0.41.

**Takeaway:** Case-level Caliber disagreement is **not** explained by lesion size or by Area disagreement. It tracks Maturity disagreement (by construction) and weakly tracks low vessel density / low Caliber level.

---

## 3. Which observers disagree (MAD and bias)

| Metric | Pair | MAD | Bias (A−B) | SD of diff |
|--------|------|-----|------------|------------|
| **Caliber** | YY−Inoue | **19.2** | **−7.7** | 24.5 |
| **Caliber** | YY−Osada | **20.4** | **−12.6** | 23.5 |
| **Caliber** | Inoue−Osada | **20.4** | −4.8 | 26.9 |
| Area | YY−Inoue | 0.53 | +0.51 | 0.44 |
| Area | YY−Osada | 0.54 | +0.34 | 0.55 |
| Area | Inoue−Osada | 0.35 | −0.17 | 0.44 |
| Complexity | YY−Inoue | 7.3 | −5.7 | 7.7 |
| Complexity | YY−Osada | 6.0 | +0.5 | 8.8 |
| Complexity | Inoue−Osada | 7.6 | +6.2 | 8.7 |
| Maturity | YY−Inoue | 10.9 | −1.0 | 13.6 |
| Maturity | YY−Osada | 11.9 | −6.5 | 13.6 |
| Maturity | Inoue−Osada | 12.0 | −5.5 | 14.7 |

Pairwise Caliber ICC(2,1) (from `icc_multirater_pairwise.csv`): YY–Inoue **0.517** · YY–Osada **0.466** · **Inoue–Osada 0.284**.

Paired t-tests on Caliber: YY < Inoue (p = 0.038), YY < Osada (p = 0.00074), Inoue vs Osada NS (p = 0.23).

**Takeaway:** All three pairs have ~20-point MAD. There is a **systematic scale shift** (YY lowest, Osada highest), but Inoue–Osada still have the **worst** pairwise ICC with large SD of differences → **noise / interaction**, not only bias.

---

## 4. Worst Caliber-discordance cases (top 10)

Ranked by 3-rater Caliber range. Overall concordance rank from `icc_cases_ranked_by_concordance.csv` (1 = best agreement across metrics; 46 = worst).

| # | File (basename) | Cal range | Overall rank | Area mean | Area range | Cx range | Mat range | Cal Inoue / Osada / YY |
|---|-----------------|-----------|--------------|-----------|------------|----------|-----------|-------------------------|
| 1 | kobayashi_isao…20240424…OD | 72.4 | **46** | 0.89 | 0.75 | 17.7 | 44.2 | 16.0 / 88.3 / 41.4 |
| 2 | furukawa_hiroichi…20240529…OD | 71.9 | **45** | **4.89** | 0.94 | 9.2 | 32.9 | 83.4 / 42.1 / 11.5 |
| 3 | takako_fumiichi…20230724…OD | 68.7 | 41 | 1.01 | 0.59 | 7.3 | 35.8 | 84.1 / 15.4 / 43.8 |
| 4 | matuzaki_mineo…20260422…OS | 66.6 | **44** | 1.13 | 0.34 | 13.8 | 40.2 | 46.0 / 86.2 / 19.6 |
| 5 | oouchi_tarou…20250819…OS | 61.3 | 36 | 0.66 | 0.38 | 6.2 | 28.3 | 61.3 / 37.5 / **0.0** |
| 6 | asai_haruo…20230802…OS | 60.4 | 39 | 1.09 | 0.92 | 4.0 | 30.9 | 8.3 / 68.3 / 7.9 |
| 7 | takako_fumiichi…20230329…OD | 59.3 | **43** | 2.18 | 1.71 | 11.6 | 25.9 | 64.2 / 67.1 / 7.8 |
| 8 | imazeki_humio…20260617…OS | 50.6 | **42** | 0.68 | 0.83 | 19.0 | 34.8 | 27.5 / 74.1 / 78.1 |
| 9 | furukawa_hiroichi…20231127…OD | 48.7 | 35 | **5.34** | 1.21 | 4.8 | 24.1 | 8.7 / 56.0 / 7.3 |
| 10 | yamamoto_masako…20220708…OD | 41.6 | 23 | 0.94 | 0.08 | 7.0 | 19.1 | 72.2 / 55.8 / 30.7 |

- **Overlap with overall concordance-worst 10:** **7 / 10**
- Extremes are **not** always the same observer; Osada or Inoue can be the high or low outlier. YY is often low but not always (#8).
- Two of the top-10 are **large** lesions (~5 mm²) with high branch counts (~2000) — Caliber can fail badly even when Area is large.

---

## 5. Score distributions per observer

| Metric | Observer | Mean | SD | Min–Max |
|--------|----------|------|-----|---------|
| **Caliber** | YY | **43.6** | 26.9 | 0.0–89.3 |
| | Inoue | **51.3** | 24.0 | 2.2–87.3 |
| | Osada | **56.1** | 20.9 | 15.4–88.3 |
| Complexity | YY | 60.1 | 16.4 | 21.5–95.6 |
| | Inoue | 65.8 | 12.3 | 39.2–88.7 |
| | Osada | 59.6 | 16.4 | 22.5–94.8 |
| Maturity | YY | 41.7 | 19.6 | 11.8–83.9 |
| | Inoue | 42.7 | 16.2 | 6.8–72.1 |
| | Osada | 48.3 | 16.5 | 14.7–80.1 |

**Systematic scale shift vs noise?** **Both.**

- Means differ in a consistent direction (YY < Inoue < Osada for Caliber) → absolute-agreement ICC is penalized.
- But σ²_error ≫ σ²_observer (§1) and MAD ~20 with SD of differences ~24–27 → **case-specific noise is the larger problem**. A pure fixed bias would inflate σ²_observer, not leave half the variance as residual.

Sentinel score 25.0: none. Extreme low (<5): YY 2, Inoue 1, Osada 0.

---

## 6. Maturity link

Exact formula (verified on all 138 ratings, MAE ≈ 0):

$$\mathrm{Maturity} = 50 + \frac{\mathrm{Caliber} - \mathrm{Complexity}}{2}$$

| Maturity range vs | Spearman ρ | p |
|-------------------|------------|---|
| **Caliber range** | **0.799** | 2.8×10⁻¹¹ |
| Complexity range | 0.428 | 0.003 |
| Area range | 0.324 | 0.028 |

**Does Caliber noise explain mid Maturity ICC?** **Yes, largely.**

- Complexity ICC is high (0.807); Caliber is low (0.434). Maturity averages both → lands in between (0.659).
- Maturity’s residual variance share (30.9%) sits between Complexity (14.6%) and Caliber (51.2%).
- Pairwise Maturity ICC pattern mirrors Caliber (Inoue–Osada worst).

---

## 7. Raw / intermediate features (batch CSV)

`stab_cv` and other radial-profile stability inputs are **not exported** in the ImageJ-compatible batch CSV. Proxies present:

| Feature | ICC(2,1) VC | σ²_error share | Means YY / Inoue / Osada |
|---------|-------------|----------------|---------------------------|
| Caliber Uniformity Score | **0.434** | 51% | 43.6 / 51.3 / 56.1 |
| **NV Diameter (CV)** | **0.259** | **72%** | 46.4 / 45.2 / 44.6 |
| **Local Diameter Variation (max CV%)** | **0.138** | **77%** | 4.0 / 5.6 / 7.6 |
| Raw Vsl Diameter | 0.385 | 47% | 20.7 / 21.7 / 23.0 |
| (Skel) Vsl Diameter | 0.760 | 19% | 22.9 / 23.4 / 23.5 |
| Vsl Density | 0.520 | 20% | 0.50 / 0.56 / 0.61 |
| Vsl Length | 0.882 | 8% | 39.8 / 30.7 / 36.8 |
| Vsl Branches | 0.813 | 13% | 916 / 688 / 865 |
| Vsl Junctions | 0.815 | 14% | 260 / 196 / 245 |
| End Pts | 0.855 | 10% | 116 / 89 / 112 |
| Arteriolarization Segment Count | 0.802 | 15% | 553 / 435 / 596 |
| Complexity Score | 0.807 | 15% | (scores) |
| Area | 0.859 | 9% | (mm²) |

**Takeaway:** Low ICC is **not unique to the composite Caliber score**. Diameter **variability / CV** features that feed stability show **even lower** ICC. Mean caliber (skel diameter) and topology counts (branches, length) remain **good–excellent** — consistent with Complexity/Area being robust while Caliber/stability is fragile.

---

## 8. User hypothesis: small MNV → unstable 10-bin Caliber → low ICC

**Hypothesis:** Smaller MNV → narrower radial bins / fewer vessels per bin → unstable stab/CV measures → larger inter-observer Caliber disagreement and low ICC.

### 8.1 Case-level: Area vs Caliber discordance

| Test | Result |
|------|--------|
| Spearman Area mean vs Caliber range | ρ = −0.046, p = 0.76 |
| Pearson Area mean vs Caliber range | r = 0.109, p = 0.47 |
| Area range vs Caliber range | ρ = 0.077, p = 0.61 |
| Quintile mean Caliber range (Q1→Q5 by Area) | 29.0, **41.2**, 23.9, 23.7, 32.1 — **non-monotonic** |

→ **Case-level discordance is not a simple “small Area → large Caliber range” relationship.**

### 8.2 Stratum ICC by Area tertile / quartile

**Tertile** (n ≈ 15–16; Area mean cuts ≈ 0.26–1.01 / 1.05–1.69 / 1.70–5.34 mm²):

| Stratum | Caliber ICC | mean Cal range | Complexity ICC | Maturity ICC |
|---------|-------------|----------------|----------------|--------------|
| Q1 small | **0.308** | 33.9 | 0.687 | 0.458 |
| Q2 mid | 0.378 | 27.1 | 0.764 | 0.619 |
| Q3 large | **0.562** | 28.5 | 0.804 | 0.759 |

**Quartile** (n ≈ 11–12; note unstable with small n):

| Stratum | Caliber ICC | mean Cal range | Complexity ICC | Maturity ICC |
|---------|-------------|----------------|----------------|--------------|
| Q1 small | 0.516 | 28.7 | 0.640 | 0.635 |
| Q2 | **0.000** | **39.9** | 0.587 | 0.020 |
| Q3 | 0.645 | 22.3 | 0.798 | 0.804 |
| Q4 large | 0.547 | 29.1 | 0.833 | 0.757 |

Tertile shows a **modest upward ICC gradient** with Area for Caliber (and Maturity). Quartile is **non-monotonic** (worst band is Q2, not the smallest). Stratum ICCs with n≈11–16 are noisy.

### 8.3 Are worst Caliber cases enriched for small Area?

| Check | Result |
|-------|--------|
| ≤ median Area among top-10 Caliber range | 7 / 10 |
| Smallest tertile among top-10 | 5 / 10 (expected ≈ 3.3) |
| Fisher exact (top-10 ∩ T1-small) | OR = 2.27, **p = 0.283** (NS) |
| Mann–Whitney Area mean: top-10 < rest (one-sided) | **p = 0.44** (NS) |
| Mean Area top-10 vs rest | **1.88 vs 1.46** (top-10 slightly *larger*) |

→ **No significant enrichment** of small lesions among Caliber-worst cases; two worst-ish cases are large (~5 mm²).

### 8.4 Intermediates vs Area (mechanism check)

Batch CSV has no `stab_cv` / segment-bin area. Available intermediates:

| Relation | Spearman ρ | p |
|----------|------------|---|
| Area mean vs Vsl Branches / Length / Junctions | 0.92 / 0.97 / 0.90 | ≪10⁻¹⁵ |
| Area mean vs **NV Diameter (CV) range** (3-rater) | **−0.557** | 5.9×10⁻⁵ |
| Area mean vs Local Diameter max CV range | −0.291 | 0.050 |
| Area mean vs Skel diameter range | −0.601 | 1.0×10⁻⁵ |

**NV Diameter (CV) ICC by Area tertile:** Q1 **0.049** · Q2 0.854 · Q3 **0.969**

→ **Supported mechanism fragment:** in small lesions, *raw diameter-CV disagreement* rises and *NV Diameter CV ICC collapses*. That is consistent with unstable sampling of caliber variability when the lesion (and vessel count) is small.

→ **But:** that raw-CV Area dependence **does not translate** into a clear case-level Area ↔ Caliber-**score** discordance correlation, and composite Caliber ICC remains only moderate even in the largest tertile (0.56).

### 8.5 Control: is Area dependence Caliber-specific?

| Metric | ICC small tertile | ICC large tertile | Δ |
|--------|-------------------|-------------------|---|
| Caliber | 0.308 | 0.562 | +0.25 |
| Maturity | 0.458 | 0.759 | +0.30 |
| Complexity | 0.687 | 0.804 | +0.12 |
| Area (within tertile; restricted range) | 0.108 | 0.811 | (stratum artifact) |

Complexity stays **good** even in small lesions. Maturity’s Area gradient largely **inherits Caliber**. So the small-Area vulnerability is **preferential for Caliber/stability-family metrics**, not a global “everything fails when small” effect — but Complexity is still somewhat lower in Q1.

### 8.6 Hypothesis verdict

| Claim | Verdict |
|-------|---------|
| Small Area → unstable raw diameter-CV / stability intermediates across observers | **Supported** |
| Small Area → higher Caliber **score** discordance at case level | **Not supported** (null correlation; non-monotonic bins) |
| Small Area → lower Caliber ICC in strata | **Partially supported** (tertile gradient; quartile messy; large tertile still only ICC 0.56) |
| Worst Caliber cases are mostly small MNVs | **Not supported** (NS enrichment; large lesions in top-10) |
| Effect is Caliber-specific vs Complexity | **Mostly yes** (Complexity remains ≥0.69 in small tertile) |

**Overall hypothesis: 部分支持 (partial support).**  
The mechanistic premise (unstable CV/stability sampling when Area/vessel count is small) is real for raw features. It is **not** a sufficient or primary explanation for the full-set Caliber ICC of 0.434, which remains limited even in larger lesions and is driven mainly by high residual score noise + Inoue–Osada disagreement + modest scale shift.

---

## Ranked likely causes of low Caliber ICC

1. **Dominant residual / case×observer noise in diameter-variability features** — NV Diameter (CV) ICC 0.259, Local max CV ICC 0.138; Caliber σ²_error = 51% of total. Composite score inherits fragile CV/stability inputs, not mean diameter (skel ICC 0.760).
2. **Large case-specific rater disagreement, worst between Inoue and Osada** — pairwise Caliber ICC 0.284; MAD ≈ 20 points all pairs; top-10 show alternating high/low outliers (not one fixed “bad” rater).
3. **Modest systematic scale shift (YY < Inoue < Osada)** — mean gaps −7.7 / −12.6 vs YY; contributes to absolute-agreement ICC but explains only ~5% of variance as observer main effect.
4. **Secondary: small-lesion instability of raw CV** — NV Diameter CV ICC collapses in smallest Area tertile; contributes to stratum ICC gradient but does **not** drive case-level Caliber-score discordance vs Area.
5. **Maturity mid-ICC is downstream of (1)** via Maturity = 50 + (Caliber − Complexity)/2.

### What is NOT the cause

- **Area-driven coupling:** Caliber discordance is **not** correlated with Area discordance or mean Area (ρ ≈ 0).
- **“Caliber fails only because ROI Area fails”:** Area ICC is excellent (0.859); topology/Complexity remain robust.
- **Pure fixed observer bias alone:** would appear as large σ²_observer; here σ²_error dominates.
- **Sentinel/default scores (e.g. 25.0):** not observed.
- **Hypothesis that small MNV fully explains low Caliber ICC:** only **partially** supported; rejected as primary/sole cause.

---

## Japanese-ready summary (for Response / internal note)

**結論:** Caliber Uniformity の ICC≈0.434 は、主に **径のばらつき（CV系）特徴量の観察者間ノイズ** と、それに伴う **症例ごとのスコア不一致（特に Inoue–Osada）** による。Area 不一致や「小さい病変だから」だけでは説明できない（部分支持）。

**上位3原因（証拠付き）**

1. **径変動・安定性系の生指標そのものの再現性が低い** — NV Diameter (CV) ICC 0.259、Local Diameter max CV ICC 0.138。Caliber の分散成分は σ²_error 51%（σ²_case 43%）。平均径（skel）や枝数・長さの ICC は高い（0.76–0.88）のに、CV系だけ崩れる。
2. **観察者ペア間の大きな絶対差＋症例依存の不一致** — 3ペアとも MAD≈19–20点。ペア ICC は YY–Inoue 0.52 / YY–Osada 0.47 / **Inoue–Osada 0.28**。Worst 10例の外れは観察者固定ではなく入れ替わる。
3. **系統的スケール差（副因）** — 平均 Caliber は YY 43.6 < Inoue 51.3 < Osada 56.1（YY vs Osada p&lt;0.001）。ただし分散成分上の観察者主効果は約5%にとどまり、主因ではない。

**仮説「小さい MNV → 10分割が不安定 → 低 ICC」:** **部分支持。** 小病変で NV Diameter CV の観察者間不一致は増え ICC も崩れるが、症例レベルの Area と Caliber スコア不一致の相関はなく（ρ≈0）、Worst 10への小病変偏りも有意でない。大病変でも Caliber が大きく割れる例がある。Complexity は小病変でも ICC≈0.69 を維持。

**原因でないもの**

- Area 不一致や Area そのものが Caliber 不一致を駆動しているわけではない（Area ICC 0.859、相関 NS）。
- Complexity からの波及でもない（Complexity range と Caliber range は無相関）。
- 固定バイアスのみ、でもない（残差分散が主）。

**Maturity が中間的な理由:** Maturity = 50 + (Caliber − Complexity)/2 のため、Caliber ノイズが Complexity の高 ICC で希釈され ICC≈0.659 になる。
