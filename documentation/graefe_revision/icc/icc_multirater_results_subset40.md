# Multi-rater ICC — sensitivity subset (n=40 most concordant)

**Date computed:** 2026-07-30  
**Primary analysis (unchanged):** 3-rater ICC(2,1) on **n = 46** (see `icc_multirater_results.md`).  
**This file:** optional sensitivity on the **40 cases** with highest cross-observer concordance (top-40 of `icc_cases_ranked_by_concordance.csv`).  
**Observers:** Inoue, Osada, YY  
**Model:** ICC(2,1) — two-way random effects, absolute agreement, single measures

## Case selection

From the locked n=46 matched set:

1. For each metric (area, complexity, caliber uniformity, maturity), z-score all 46×3 ratings using that metric’s pool mean and SD (sample SD, ddof=1).
2. Per case, compute the **range** (max − min) of the three observers’ z-scores for each metric.
3. **Discordance score** = mean of the four metric-specific z-ranges (lower = more aligned).
4. Select the **40 cases with the lowest discordance** (same ranking source as n=20/30/35/40).

Selection is **top-N by concordance only** (no stratified sampling).

- Discordance range among selected 40: 0.246–1.338
- Discordance range among remaining 6: 1.463–1.826

## Side-by-side: n=46 (primary) vs n=40 (sensitivity)

| Metric | n=46 ICC(2,1) | 95% CI | n=40 ICC(2,1) | 95% CI | Δ (n40−n46) |
|--------|---------------|--------|---------------|--------|-------------|
| MNV Area (mm²) | 0.859 | 0.68–0.93 | 0.847 | 0.67–0.93 | -0.012 |
| Network Complexity Score | 0.807 | 0.66–0.89 | 0.822 | 0.68–0.90 | +0.014 |
| Caliber Uniformity Score | 0.434 | 0.26–0.61 | 0.611 | 0.44–0.75 | +0.177 |
| Maturity Index | 0.659 | 0.51–0.78 | 0.777 | 0.65–0.87 | +0.118 |

## Interpretation

- This subset is a **sensitivity / upper-bound** analysis on cases where the three observers already agreed relatively well; it does **not** replace the primary n=46 ICC.
- Higher ICC on the concordant subset is expected by construction and should be interpreted as such.
- Primary Response Comment 4 numbers remain the n=46 estimates.

## Output files

- `icc_subset40_case_list.csv` — top-40 cases (rank, case_id, File, discordance_score)
- `icc_cases_ranked_by_concordance.csv` — full n=46 ranking (shared source)
- `icc_multirater_results_subset40.md` — this report
- `icc_multirater_concordance_ladder.md` — comparison across n=20/30/35/40/46
