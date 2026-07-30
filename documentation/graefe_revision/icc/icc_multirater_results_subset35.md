# Multi-rater ICC — sensitivity subset (n=35 most concordant)

**Date computed:** 2026-07-30  
**Primary analysis (unchanged):** 3-rater ICC(2,1) on **n = 46** (see `icc_multirater_results.md`).  
**This file:** optional sensitivity on the **35 cases** with highest cross-observer concordance (top-35 of `icc_cases_ranked_by_concordance.csv`).  
**Observers:** Inoue, Osada, YY  
**Model:** ICC(2,1) — two-way random effects, absolute agreement, single measures

## Case selection

From the locked n=46 matched set:

1. For each metric (area, complexity, caliber uniformity, maturity), z-score all 46×3 ratings using that metric’s pool mean and SD (sample SD, ddof=1).
2. Per case, compute the **range** (max − min) of the three observers’ z-scores for each metric.
3. **Discordance score** = mean of the four metric-specific z-ranges (lower = more aligned).
4. Select the **35 cases with the lowest discordance** (same ranking source as n=20/30/35/40).

Selection is **top-N by concordance only** (no stratified sampling).

- Discordance range among selected 35: 0.246–1.192
- Discordance range among remaining 11: 1.216–1.826

## Side-by-side: n=46 (primary) vs n=35 (sensitivity)

| Metric | n=46 ICC(2,1) | 95% CI | n=35 ICC(2,1) | 95% CI | Δ (n35−n46) |
|--------|---------------|--------|---------------|--------|-------------|
| MNV Area (mm²) | 0.859 | 0.68–0.93 | 0.867 | 0.68–0.94 | +0.008 |
| Network Complexity Score | 0.807 | 0.66–0.89 | 0.867 | 0.74–0.93 | +0.059 |
| Caliber Uniformity Score | 0.434 | 0.26–0.61 | 0.670 | 0.50–0.80 | +0.236 |
| Maturity Index | 0.659 | 0.51–0.78 | 0.823 | 0.71–0.90 | +0.164 |

## Interpretation

- This subset is a **sensitivity / upper-bound** analysis on cases where the three observers already agreed relatively well; it does **not** replace the primary n=46 ICC.
- Higher ICC on the concordant subset is expected by construction and should be interpreted as such.
- Primary Response Comment 4 numbers remain the n=46 estimates.

## Output files

- `icc_subset35_case_list.csv` — top-35 cases (rank, case_id, File, discordance_score)
- `icc_cases_ranked_by_concordance.csv` — full n=46 ranking (shared source)
- `icc_multirater_results_subset35.md` — this report
- `icc_multirater_concordance_ladder.md` — comparison across n=20/30/35/40/46
