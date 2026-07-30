# Multi-rater ICC — concordance ladder (n=20 → 46)

**Date computed:** 2026-07-30  
**Primary analysis (unchanged):** 3-rater ICC(2,1) on **n = 46** (`icc_multirater_results.md`).  
**Sensitivity:** nested top-N subsets by cross-observer concordance (same ranking for all N).  
**Observers:** Inoue, Osada, YY · **Model:** ICC(2,1)

## Ranking method

1. Z-score each metric across the full 46×3 rating pool (per-metric mean / sample SD, ddof=1).
2. Per case: 3-rater **z-range** (max − min) for Area, Complexity, Caliber Uniformity, Maturity.
3. **Discordance score** = mean of the four z-ranges (lowest = highest concordance).
4. Nested subsets: top-20 / 30 / 35 / 40 from `icc_cases_ranked_by_concordance.csv`; n=46 = all.

**n=20 consistency:** recomputed ranking matches existing `icc_subset20_case_list.csv` top-20 IDs and discordance scores (identical ranking source).

## Discordance cutoffs (selected subset)

| Subset | n | Discordance min | Discordance max (cutoff) |
|--------|---|-----------------|--------------------------|
| top-20 | 20 | 0.246 | 0.712 |
| top-30 | 30 | 0.246 | 0.986 |
| top-35 | 35 | 0.246 | 1.192 |
| top-40 | 40 | 0.246 | 1.338 |
| top-46 | 46 | 0.246 | 1.826 |

## ICC(2,1) by subset size

| Metric | n=20 | 95% CI | n=30 | 95% CI | n=35 | 95% CI | n=40 | 95% CI | n=46 (primary) | 95% CI |
|--------|------|--------|------|--------|------|--------|------|--------|----------------|--------|
| MNV Area (mm²) | 0.864 | 0.56–0.95 | 0.800 | 0.56–0.91 | 0.867 | 0.68–0.94 | 0.847 | 0.67–0.93 | 0.859 | 0.68–0.93 |
| Network Complexity Score | 0.950 | 0.90–0.98 | 0.896 | 0.80–0.95 | 0.867 | 0.74–0.93 | 0.822 | 0.68–0.90 | 0.807 | 0.66–0.89 |
| Caliber Uniformity Score | 0.852 | 0.72–0.93 | 0.713 | 0.55–0.84 | 0.670 | 0.50–0.80 | 0.611 | 0.44–0.75 | 0.434 | 0.26–0.61 |
| Maturity Index | 0.924 | 0.85–0.97 | 0.863 | 0.77–0.93 | 0.823 | 0.71–0.90 | 0.777 | 0.65–0.87 | 0.659 | 0.51–0.78 |

## Δ vs primary n=46

| Metric | Δ n20 | Δ n30 | Δ n35 | Δ n40 |
|--------|-------|-------|-------|-------|
| MNV Area (mm²) | +0.005 | -0.060 | +0.008 | -0.012 |
| Network Complexity Score | +0.143 | +0.088 | +0.059 | +0.014 |
| Caliber Uniformity Score | +0.418 | +0.280 | +0.236 | +0.177 |
| Maturity Index | +0.265 | +0.204 | +0.164 | +0.118 |

## Interpretation

- Nested concordant subsets are **sensitivity / upper-bound** analyses; they do **not** replace primary n=46 Comment 4 ICCs.
- ICC typically rises as more discordant cases are excluded (expected by construction).
- Caliber Uniformity shows the steepest drop when moving from highly concordant subsets toward the full n=46 set.

## Output files

- `icc_cases_ranked_by_concordance.csv` — full ranked ID list (canonical ranking source)
- `icc_subset20_case_list.csv` — n=20 list (consistent with ranking; includes audit columns)
- `icc_subset30_case_list.csv`, `icc_subset35_case_list.csv`, `icc_subset40_case_list.csv`
- `icc_multirater_results_subset20.md` … `_subset40.md`
- `icc_multirater_stats_concordance_ladder.csv` — numeric ICC rows for all N
- `icc_multirater_concordance_ladder.md` — this comparison
