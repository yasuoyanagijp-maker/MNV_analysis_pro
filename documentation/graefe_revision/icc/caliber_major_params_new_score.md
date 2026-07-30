# Caliber uniformity — major parameters & new score (n=46)

**Date:** 2026-07-31  
**Set:** YY / Inoue / Osada · intersection **n = 46** · ICC(2,1) absolute agreement  
**Script:** `compute_caliber_major_params_new_score.py`  
**Companion:** [`icc_all_numeric_params_n46.md`](icc_all_numeric_params_n46.md)

---

## Part 1 — Top high-ICC picks (caliber-related)

From full numeric sweep (`icc_all_numeric_params_n46.*`):

| Metric | ICC(2,1) | 95% CI | Note |
|--------|----------|--------|------|
| Arteriolarization Connectivity Index (mm/segment) | 0.896 | 0.840–0.940 | Thick-vessel connectivity |
| Arteriolarization Max Segment Length (mm) | 0.870 | 0.800–0.920 | Longest thick segment |
| Arteriolarization Segment Count | 0.802 | 0.660–0.890 | Thick-vessel topology count |
| Arteriolarization Total Length (mm) | 0.800 | 0.660–0.890 | Thick-vessel length |
| (Skel) Vsl Diameter | 0.760 | 0.610–0.860 | Mean caliber level — high ICC but **not** uniformity |
| Arteriolarization Density (/mm²) | 0.558 | 0.310–0.730 | Thick-vessel spatial density |
| Dilated vessel (%) | 0.522 | 0.320–0.690 | Fraction dilated — **heterogeneity axis**, moderate ICC |
| Caliber Uniformity Score | 0.434 | 0.260–0.610 | Published Stability/PCA composite — low |
| NV Diameter (CV) | 0.259 | 0.080–0.450 | Global diameter CV — raw ICC low; robust transform rescues |
| Local Diameter Variation (max CV%) | 0.138 | -0.020–0.330 | Local max CV — poorest |
| Raw Vsl Diameter | 0.385 | 0.180–0.580 | Alternate mean diameter — only fair ICC |

**Takeaway:** High-ICC caliber-*family* columns are mostly **mean level** or **arteriolarization counts**, not dispersion. True uniformity proxies (`NV Diameter (CV)`, `Local Diameter Variation`, original Caliber) are the **low-ICC** ones unless transformed.

---

## Part 2 — Logical major parameters for caliber uniformity

Goal: quantify **caliber uniformity** (homogeneity of vessel diameters) **without** fragile 10-bin `stab_*` radial partitions.

| # | Logical parameter | Why (pathophysiology / morphometry) | In batch CSV? | ICC hint |
|---|-------------------|--------------------------------------|---------------|----------|
| 1 | **Global diameter CV** (or robust CV / MAD/median) | Scale-free dispersion of lumen width across the lesion | `NV Diameter (CV)` only (mean/SD-based CV; **no MAD/percentiles**) | Raw low; Winsor+map high |
| 2 | **Mean-caliber–orthogonal residual CV** | CV correlates with mean diameter (ρ≈0.75); residual = uniformity *net of thickness* | **Derived** from `NV Diameter (CV)` + `(Skel) Vsl Diameter` | Tried — **ICC collapsed** (negative control) |
| 3 | **Dilated-vessel fraction** | Focal ectasia / arteriolarization → morphological *non*-uniformity, largely independent of global CV (ρ≈0.15) | `Dilated vessel (%)` | Moderate (~0.52) |
| 4 | **Local diameter variation** | Focal beading / segmental irregularity | `Local Diameter Variation (max CV%)` | **Very low** — avoid as primary |
| 5 | **Trunk vs periphery diameter ratio** | Normal taper vs chaotic calibers | Internal `diameter_ratio` / TrunkDist — **NOT in CSV** | Need extraction |
| 6 | **Radial profile residual CV / range CV** | Spatial caliber organization | Internal `stab_*` — **NOT in CSV** | Fragile 10-bin; avoid as sole definition |
| 7 | **Skeleton diameter percentiles (p25/p50/p75, IQR)** | Distribution shape without radial bins | **NOT in CSV** (only mean + CV) | Need pipeline export |
| 8 | **Branch-order / generation taper** | Orderly thinning along branching | **NOT computed** in current pipeline | Future |
| 9 | **Mean diameter (skel)** | Caliber *level*, not uniformity — confounder / optional covariate | `(Skel) Vsl Diameter` | High ICC — do **not** stuff into uniformity without disclosure |
| 10 | **Vessel density × CV interaction** | Sparse skeletons → unstable CV | Density in CSV; interaction derived | Caveat, not primary score |

### Independence (Spearman, pooled 138 ratings)

- NV CV vs Skel mean diameter: **ρ = 0.748** (collinear — residualization motivated)
- NV CV vs Dilated %: **ρ = 0.145** (near-independent — good second axis)
- Residual CV vs Dilated %: **ρ = -0.291**
- NV CV vs Local max CV: **ρ = -0.326**

### Shortlist adopted for scoring

1. **Primary uniformity axis:** robust transform of global NV CV (soft tanh or Winsor+piecewise). **Residualization on mean diameter looked elegant but ICC collapsed** — dropped from winner.
2. **Secondary independent axis:** inverse `Dilated vessel (%)` (ρ≈0.15 with NV CV).
3. **Explicitly excluded as primary:** Local max CV; mean skel diameter as “uniformity”; 10-bin `stab_*`; absolute diameter SD; within-observer rank harmonization.

### Internal extraction (if pursued later)

No saved masks/ROI intermediates for the n=46 ICC set → **cannot** offline-recompute `stab_*`, diameter percentiles, or `diameter_ratio` without re-ROI. Pipeline already computes `std_diameter_um`, `max_diameter_um`, `diameter_ratio`, `radial_profile`, `stab_*` in `skeleton_analysis` / `mnv_analysis` / `pattern_metrics` but **does not export** them to ImageJ CSV. Feasible next step: extend `mnv_imagej_csv.py` export + re-batch.

Derived today without re-run: `std ≈ (CV/100)×mean_skel` from existing columns.

---

## Part 3 — New score(s) vs 0.434 and 0.765

### Winning formula

**Winner by ICC(2,1):** `caliber_U2_softcv_dil`

**U2 (recommended):** `U_cv = 50 + 50·tanh((median_CV − NV_CV) / SD_CV)` (pooled median/SD); `U_dil = piecewise(−winsor(Dilated%, p05–p95))`; **Score = 0.75·U_cv + 0.25·U_dil** (clip 0–100). Higher = more uniform (lower relative dispersion + less dilated fraction).

- OLS used for residualization (if applicable): slope=1.6852, intercept=6.1975

### Head-to-head ICC(2,1)

| Metric | ICC(2,1) | 95% CI | Δ vs original | Δ vs C(0.765) | Spearman vs orig (mean YY/Inoue/Osada) |
|--------|----------|--------|---------------|---------------|----------------------------------------|
| Caliber Uniformity (original) | 0.434 | — | 0 | -0.331 | 1 |
| `caliber_C_winsor_inv_nv_cv` | 0.765 | 0.640–0.860 | +0.331 | +0.000 | -0.14 |
| `caliber_U2_softcv_dil` **← winner** | 0.838 | 0.750–0.900 | +0.404 | +0.073 | -0.21 |
| `caliber_U2_winsorcv_dil` | 0.834 | 0.750–0.900 | +0.401 | +0.070 | -0.22 |
| `caliber_M_cv70_dil30` | 0.834 | 0.750–0.900 | +0.401 | +0.070 | -0.22 |
| `caliber_M_soft75_dil25` | 0.838 | 0.750–0.900 | +0.404 | +0.073 | -0.21 |
| `caliber_H_rank70_dil30` | 0.842 | 0.760–0.900 | +0.408 | +0.077 | -0.22 |
| `caliber_S_inv_std` | 0.865 | 0.790–0.920 | +0.432 | +0.101 | -0.15 |
| `caliber_R_resid_cv` | 0.355 | 0.110–0.570 | -0.079 | -0.410 | 0.17 |
| `caliber_M_resid70_dil30` | 0.501 | 0.270–0.680 | +0.067 | -0.264 | 0.01 |
| `caliber_D_inv_dilated` | 0.555 | 0.360–0.710 | +0.121 | -0.210 | -0.30 |
| `caliber_AB_cv70_skel30` | 0.533 | 0.300–0.710 | +0.099 | -0.232 | -0.06 |

### What was tried and rejected

| Idea | Result | Why rejected / kept as control |
|------|--------|--------------------------------|
| Residualize NV CV on skel mean diameter (± Dilated) | ICC **~0.35–0.50** | Face-valid orthogonality **destroyed** reproducible CV signal |
| Inverse absolute diameter SD | ICC **0.865** | Construct shift toward mean caliber / absolute spread |
| Within-observer rank(−CV)+Dilated | ICC **0.842** | Non-transferable cohort score; calibration artifact |
| Blend skel mean into score | ICC ≤ prior hybrids | Wrong construct (level ≠ uniformity) |
| Local max CV axis | ICC ~0.14–0.23 | Too noisy |

### Full candidate ranking (top 15)

| Rank | Metric | ICC(2,1) | Δ vs C | Spearman mean vs orig |
|------|--------|----------|--------|------------------------|
| 1 | `caliber_S_inv_std` | 0.865 | +0.101 | -0.15 |
| 2 | `caliber_M_cv70_art30` | 0.848 | +0.083 | -0.22 |
| 3 | `caliber_H_rank70_dil30` | 0.842 | +0.077 | -0.22 |
| 4 | `caliber_H_rank85_dil15` | 0.841 | +0.076 | -0.16 |
| 5 | `caliber_U2_softcv_dil` | 0.838 | +0.073 | -0.21 |
| 6 | `caliber_M_soft75_dil25` | 0.838 | +0.073 | -0.21 |
| 7 | `caliber_U2_winsorcv_dil` | 0.834 | +0.070 | -0.22 |
| 8 | `caliber_M_cv70_dil30` | 0.834 | +0.070 | -0.22 |
| 9 | `caliber_H_locshift70_dil30` | 0.824 | +0.059 | -0.22 |
| 10 | `caliber_M_cv80_dil20` | 0.823 | +0.058 | -0.19 |
| 11 | `caliber_H_obsrank_inv_cv` | 0.817 | +0.053 | -0.14 |
| 12 | `caliber_M_cv70_std30` | 0.814 | +0.049 | -0.14 |
| 13 | `caliber_M_cv85_dil15` | 0.811 | +0.046 | -0.17 |
| 14 | `caliber_M_cv90_dil10` | 0.797 | +0.032 | -0.15 |
| 15 | `caliber_C_winsor_p25_75` | 0.790 | +0.025 | -0.16 |

### Independence rationale

- Avoided stuffing **Skel mean diameter** into the primary uniformity definition (high ICC but wrong construct); kept only as residualization covariate or disclosed hybrid.
- **Dilated %** added only at modest weight because Spearman with NV CV is low (0.15) — second major axis, not a correlated copy.
- **Local max CV** excluded from winning blends (ICC ~0.14).
- Residual CV addresses collinearity of raw CV with mean caliber (ρ=0.75).

### Spearman vs original Caliber (disclosure)

Winner `caliber_U2_softcv_dil`: YY=-0.10, Inoue=-0.28, Osada=-0.24 (mean -0.21).

Prior `caliber_C_winsor_inv_nv_cv`: YY=0.00, Inoue=-0.25, Osada=-0.16 (mean -0.14).

Near-zero / negative Spearman ⇒ **definition replacement**, not monotonic strengthening of the published Stability/Caliber score. Expect this in rebuttal wording.

### Recommendation (rebuttal / sensitivity)

1. Keep manuscript **primary** Caliber Uniformity = existing Stability/PCA score; report ICC **0.434** honestly.
2. Sensitivity / alternate CSV proxy for **caliber homogeneity** (not 10-bin Stability):
   **`caliber_U2_softcv_dil`** — ICC(2,1) **0.838** (Δ vs original **+0.404**; Δ vs prior C **+0.073**).
3. Two major, weakly correlated axes: robust **global NV Diameter CV** + **Dilated vessel %** (avoid Local max CV; avoid stuffing mean skel diameter).
4. Disclose: Spearman vs original Caliber is near-zero/negative → **definition replacement**, not a monotonic strengthening of the published score.
5. Do **not** adopt inverse-SD or within-observer rank scores as primary (ICC inflation / wrong construct).
6. Residualizing CV on mean diameter looked elegant but **failed empirically** — mention as negative control if useful.
7. Internal percentiles / `diameter_ratio` / `stab_*` remain future export work (no saved ROI for offline recompute).

---

## Output files

- `icc_all_numeric_params_n46.md` / `.csv`
- `caliber_major_params_new_score_icc_stats.csv`
- `caliber_major_params_candidates.csv`
- `caliber_major_params_new_score_long.csv`
- `caliber_major_params_new_score.md` (this file)
- `compute_caliber_major_params_new_score.py`
