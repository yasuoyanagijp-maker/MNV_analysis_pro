# New Caliber Uniformity Score — ICC comparison (CSV-only)

**Date:** 2026-07-30  
**Set:** YY, Inoue, Osada · intersection **n = 46** · ICC(2,1) absolute agreement  
**Constraint:** existing batch CSV columns only — **no re-ROI / no re-segmentation**  
**Script:** `compute_caliber_new_score_icc.py`

## Adopted formulas

### Primary new score: `caliber_C_winsor_inv_nv_cv`

Winsorize NV Diameter (CV) at pooled p05–p95; piecewise-scale (−CV) so median→50 (higher = more uniform). Local max CV excluded.

Explicit steps (pooled over all 138 ratings = 46×3 for reference cuts):

1. Let `CV` = `NV Diameter (CV)`. Winsorize to [41.4989, 50.2788] (pooled p05–p95).
2. Score direction: lower CV → higher uniformity. Set `x = −CV_w`.
3. Piecewise linear map of `x` with min/median/max → 0 / 50 / 100 (same median-anchor style as pipeline Stability Score).

### Secondary (intermediate): `caliber_AB_cv70_skel30`

0.70 × U(winsor NV CV) + 0.30 × U(skel mean diameter); U = piecewise median→50. Hybrid: uniformity + high-ICC mean caliber.

### Other candidates evaluated

- `caliber_C_local_downweight`: 0.85 × U(winsor NV CV) + 0.15 × U(winsor Local max CV); each U is piecewise (−CV → 0–100).
- `caliber_W_winsor_orig`: Winsorize original Caliber Uniformity Score at pooled p05–p95, then piecewise re-scale median→50.

### Maturity redefinition (secondary columns only)

`maturity_from_*` = `50 + (caliber_new − Network Complexity Score) / 2` (same algebra as original Maturity Index).

## Primary ICC(2,1) comparison (n=46, k=3)

| Metric | ICC(2,1) | 95% CI | Δ vs original Caliber | Source |
|--------|----------|--------|------------------------|--------|
| MNV Area (mm²) [ref] | 0.859 | 0.680–0.930 | — | pingouin |
| Network Complexity [ref] | 0.807 | 0.660–0.890 | — | pingouin |
| Caliber Uniformity (original) | 0.434 | 0.260–0.610 | +0.000 | pingouin |
| **caliber_C_winsor_inv_nv_cv (PRIMARY new)** | 0.765 | 0.640–0.860 | +0.331 | pingouin |
| caliber_AB_cv70_skel30 (secondary) | 0.615 | 0.400–0.770 | +0.181 | pingouin |
| caliber_C_local_downweight | 0.761 | 0.640–0.850 | +0.327 | pingouin |
| caliber_W_winsor_orig | 0.446 | 0.270–0.620 | +0.012 | pingouin |
| Maturity Index (original) | 0.659 | 0.510–0.780 | — | pingouin |
| Maturity from primary new Caliber | 0.622 | 0.440–0.760 | — | pingouin |
| Maturity from AB hybrid | 0.536 | 0.310–0.710 | — | pingouin |

## Pairwise ICC(2,1) — original vs primary new

| Metric | Pair | ICC(2,1) | 95% CI |
|--------|------|----------|--------|
| caliber_uniformity | YY–Inoue | 0.517 | 0.270–0.700 |
| caliber_uniformity | YY–Osada | 0.466 | 0.170–0.670 |
| caliber_uniformity | Inoue–Osada | 0.284 | -0.000–0.530 |
| caliber_C_winsor_inv_nv_cv | YY–Inoue | 0.695 | 0.510–0.820 |
| caliber_C_winsor_inv_nv_cv | YY–Osada | 0.725 | 0.470–0.860 |
| caliber_C_winsor_inv_nv_cv | Inoue–Osada | 0.883 | 0.690–0.950 |
| caliber_AB_cv70_skel30 | YY–Inoue | 0.587 | 0.350–0.750 |
| caliber_AB_cv70_skel30 | YY–Osada | 0.557 | 0.070–0.790 |
| caliber_AB_cv70_skel30 | Inoue–Osada | 0.711 | 0.440–0.850 |

## Variance components (primary new vs original Caliber)

| Metric | σ²_case | σ²_observer | σ²_error | ICC_vc |
|--------|---------|-------------|---------|--------|
| caliber_uniformity | 265.2 | 33.27 | 312.7 | 0.434 |
| caliber_C_winsor_inv_nv_cv | 554.7 | 23.2 | 147.4 | 0.765 |
| caliber_AB_cv70_skel30 | 137.5 | 23.3 | 62.75 | 0.615 |

## Columns used (existing CSV only)

| Role | Batch CSV column |
|------|------------------|
| Original Caliber | `Caliber Uniformity Score` |
| Primary input | `NV Diameter (CV)` |
| Secondary / downweight | `Local Diameter Variation (max CV%)` |
| High-ICC blend | `(Skel) Vsl Diameter` |
| Maturity partner | `Network Complexity Score` |
| Matching | `File` (basename, lowercased, ext stripped) |

**Not available in batch CSV (cannot use without recompute):** `stab_cv`, `stab_mean_adjacent_change`, `stab_residual_cv`, `stab_range_percent`, radial 10-bin diameter profile.

## Interpretation

- Original Caliber ICC(2,1) = **0.434**; primary new (`caliber_C_winsor_inv_nv_cv`) = **0.765** (**+0.331**).
- Secondary hybrid (`caliber_AB_cv70_skel30`) = **0.615** (+0.181) — better than original, but **worse than** primary C (skel blend diluted the CV signal).
- Winsorizing the **original** Caliber score alone barely helps (`caliber_W` = 0.446). The gain comes from **replacing** the Stability/PCA composite with a robust transform of `NV Diameter (CV)`, not from trimming the old score.
- Pairwise: Inoue–Osada Caliber ICC rises from **0.284 → 0.883** under primary new (largest fix).
- **Construct check:** Spearman(original Caliber, primary new) ≈ **0.00 / −0.25 / −0.16** (YY / Inoue / Osada). Near-zero / negative → this is a **definition replacement**, not a monotonic “strengthening” of the same Stability Score.
- Maturity rebuilt as `50 + (newCaliber − Complexity)/2` does **not** improve (0.622 vs original Maturity 0.659): higher Caliber ICC does not automatically lift Maturity when the new Caliber is weakly related to the old one.

## Caveats (Graefe revision)

- This is a **sensitivity / exploratory** analysis. Do **not** replace the manuscript’s primary Caliber Uniformity definition mid-revision without explicit disclosure to reviewers.
- Empirically, the new score is **not the same construct** as the published Stability/Caliber Uniformity Score (near-zero Spearman). Report as an alternate CSV-only proxy if used at all.
- Reference cuts (p05/p95/min/median/max) are estimated on this n=46×3 pooled set (not the original stratum reference JSON).
- No cherry-picking of cases: full intersection n=46 retained.
- Mixing high-ICC mean diameter (`caliber_AB`) raised ICC vs original but underperformed pure robust NV-CV; it also shifts meaning toward caliber *level*.

## Output files

- `caliber_new_score_long.csv`
- `caliber_new_score_wide.csv`
- `caliber_new_score_icc_stats.csv`
- `caliber_new_score_icc_pairwise.csv`
- `caliber_new_score_icc_results.md` (this file)
- `compute_caliber_new_score_icc.py`
