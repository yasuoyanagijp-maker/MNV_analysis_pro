# Multi-rater ICC — sensitivity subset (n=20 most concordant)

**Date computed:** 2026-07-30  
**Primary analysis (unchanged):** 3-rater ICC(2,1) on **n = 46** (see `icc_multirater_results.md`).  
**This file:** optional sensitivity on the **20 cases** with highest cross-observer concordance.  
**Observers:** Inoue, Osada, YY  
**Model:** ICC(2,1) — two-way random effects, absolute agreement, single measures

## Case selection

From the locked n=46 matched set:

1. For each metric (area, complexity, caliber uniformity, maturity), z-score all 46×3 ratings using that metric’s pool mean and SD.
2. Per case, compute the **range** (max − min) of the three observers’ z-scores for each metric.
3. **Discordance score** = mean of the four metric-specific z-ranges (equivalently: lower score = more aligned).
4. Select the **20 cases with the lowest discordance**.

Filenames encode FOV (`Angiography 3x3 mm`) but not a reliable device stratum for balancing; therefore selection is **top-20 by concordance only** (no stratified sampling).

Secondary columns in `icc_subset20_case_list.csv`: mean pairwise |Δ| on the z-scale and per-metric coefficient of variation (CV) across raters (audit only; not used for ranking).

- Discordance range among selected 20: 0.246–0.712
- Discordance range among remaining 26: 0.792–1.826

## Side-by-side: n=46 (primary) vs n=20 (sensitivity)

| Metric | n=46 ICC(2,1) | 95% CI | n=20 ICC(2,1) | 95% CI | Δ (n20−n46) |
|--------|---------------|--------|---------------|--------|-------------|
| MNV Area (mm²) | 0.859 | 0.680–0.930 | 0.864 | 0.560–0.950 | +0.005 |
| Network Complexity Score | 0.807 | 0.660–0.890 | 0.950 | 0.900–0.980 | +0.143 |
| Caliber Uniformity Score | 0.434 | 0.260–0.610 | 0.852 | 0.720–0.930 | +0.418 |
| Maturity Index | 0.659 | 0.510–0.780 | 0.924 | 0.850–0.970 | +0.265 |

## Interpretation

- This subset is a **sensitivity / upper-bound** analysis on cases where the three observers already agreed relatively well; it does **not** replace the primary n=46 ICC.
- Higher ICC on the concordant subset is expected by construction and should be interpreted as such.
- Primary Response Comment 4 numbers remain the n=46 estimates.


See also the concordance ladder (`icc_multirater_concordance_ladder.md`) for nested n=20/30/35/40/46 comparisons from the same ranking (`icc_cases_ranked_by_concordance.csv`).
## Output files

- `icc_subset20_case_list.csv` — all 46 cases ranked; `selected_subset20` flag + scores
- `icc_multirater_stats_subset20.csv` — ICC rows for n46 and n20
- `icc_multirater_comparison_n46_vs_n20.csv` — side-by-side table
- `icc_multirater_results_subset20.md` — this report

