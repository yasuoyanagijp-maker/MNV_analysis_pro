# Table 3 — Kruskal–Wallis effect sizes (ε²)

## Source

- Git commit `1e5d202` batch CSVs recovered to `documentation/graefe_revision/data/`
- Metrics: `Network Complexity Score`, `Caliber Uniformity Score`, `Maturity Index`
- Strata: large / small / small_3mm (device / FOV analysis strata)

## Method

- Omnibus test: Kruskal–Wallis across 3 strata
- Effect size: ε² = (H − k + 1) / (n − k), with k = 3 (display truncates negative ε² / CI lower bound to 0 when H < k−1)
- Bootstrap 95% CI: 10000 resamples within strata (with replacement), seed `20260727`
- Interpretation (common rule of thumb): ε² < 0.01 negligible; ~0.01–0.08 small; ~0.08–0.26 medium; ≥0.26 large

**N cases used:** 112 (large=49, small=33, small_3mm=30)

## Results

| Metric | H | p | ε² | 95% CI | medians (L / S / S3) |
|---|---:|---:|---:|---|---|
| Network Complexity Score | 1.712 | 0.425 | 0.0000 | 0.0000–0.0887 | 48.7 / 50.7 / 47.8 |
| Caliber Uniformity Score | 27.713 | 9.6e-07 | 0.2359 | 0.1121–0.3959 | 66.4 / 56.7 / 58.9 |
| Maturity Index | 28.690 | 5.89e-07 | 0.2449 | 0.1224–0.4078 | 57.5 / 52.4 / 52.8 |

## Notes for manuscript / response letter

- Medians near 50 after piecewise-linear normalization are **not** evidence of biological equivalence.
- On these 1e5d202 CSVs, **Network Complexity** does not differ across strata (p≈0.43; ε²≈0), but **Caliber Uniformity** and **Maturity Index** do (both p<0.001; ε²≈0.24). Do **not** reuse the original manuscript claim that all three Kruskal–Wallis tests were non-significant.
- Report ε² + bootstrap CI alongside Kruskal–Wallis p-values; soften any “comparable across devices” wording for Caliber/Maturity.
- Per-case scores: `table3_per_case_scores.csv`
- Machine-readable summary (raw ε², may be slightly negative): `table3_effect_sizes.csv`
