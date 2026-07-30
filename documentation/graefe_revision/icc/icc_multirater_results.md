# Multi-rater ICC results (Graefe revision WS1)

**Date computed:** 2026-07-30  
**n (intersection of 3 observers):** 46  
**Observers:** Inoue, Osada, YY (YY = original analyst; Inoue = observer_A; Osada = observer_B)  
**Primary model:** ICC(2,1) — two-way random effects, absolute agreement, single measures (Shrout & Fleiss / McGraw & Wong)

## Data sources

| Observer | Folder | CSV | Rows (unique cases) |
|----------|--------|-----|---------------------|
| YY | `incoming/observer_YY/` | `MNV_batch_20260730_165332.csv` | 46 |
| Inoue | `incoming/observer_A/` (alias `observer_inoue/`) | `MNV_batch_20260729_180525_inoue.csv` | 46 |
| Osada | `incoming/observer_B/` (alias `observer_osada/`) | `MNV_batch_20260730_131130_osada.csv` | 46 |

Join key: `File` basename, lowercased, extension stripped.

## Case matching

- Union of case IDs: **46**
- Intersection (all 3 observers): **46**
- No observer-specific dropouts beyond intersection filter.

## Primary: 3-rater ICC(2,1)

| Metric | n | k | ICC(2,1) | 95% CI | Source |
|--------|---|---|----------|--------|--------|
| MNV Area (mm²) | 46 | 3 | 0.859 | 0.680–0.930 | pingouin |
| Network Complexity Score | 46 | 3 | 0.807 | 0.660–0.890 | pingouin |
| Caliber Uniformity Score | 46 | 3 | 0.434 | 0.260–0.610 | pingouin |
| Maturity Index | 46 | 3 | 0.659 | 0.510–0.780 | pingouin |

## Supplementary: pairwise ICC(2,1)

| Metric | Pair | n | ICC(2,1) | 95% CI | Source |
|--------|------|---|----------|--------|--------|
| MNV Area (mm²) | YY–Inoue | 46 | 0.844 | 0.180–0.950 | pingouin |
| MNV Area (mm²) | YY–Osada | 46 | 0.846 | 0.630–0.930 | pingouin |
| MNV Area (mm²) | Inoue–Osada | 46 | 0.897 | 0.810–0.940 | pingouin |
| Network Complexity Score | YY–Inoue | 46 | 0.800 | 0.460–0.910 | pingouin |
| Network Complexity Score | YY–Osada | 46 | 0.859 | 0.760–0.920 | pingouin |
| Network Complexity Score | Inoue–Osada | 46 | 0.754 | 0.400–0.890 | pingouin |
| Caliber Uniformity Score | YY–Inoue | 46 | 0.517 | 0.270–0.700 | pingouin |
| Caliber Uniformity Score | YY–Osada | 46 | 0.466 | 0.170–0.670 | pingouin |
| Caliber Uniformity Score | Inoue–Osada | 46 | 0.284 | -0.000–0.530 | pingouin |
| Maturity Index | YY–Inoue | 46 | 0.716 | 0.540–0.830 | pingouin |
| Maturity Index | YY–Osada | 46 | 0.679 | 0.440–0.820 | pingouin |
| Maturity Index | Inoue–Osada | 46 | 0.568 | 0.330–0.740 | pingouin |

## Multilevel / variance-component ICC

Two-way random ANOVA variance components:

$$\mathrm{ICC}_{\mathrm{case}} = \sigma^2_{\mathrm{case}} / (\sigma^2_{\mathrm{case}} + \sigma^2_{\mathrm{observer}} + \sigma^2_{\varepsilon})$$

| Metric | σ²_case | σ²_observer | σ²_error | ICC_case |
|--------|---------|-------------|---------|----------|
| MNV Area (mm²) | 1.096 | 0.06537 | 0.1143 | 0.859 |
| Network Complexity Score | 194.1 | 11.11 | 35.19 | 0.807 |
| Caliber Uniformity Score | 265.2 | 33.27 | 312.7 | 0.434 |
| Maturity Index | 208.8 | 10.27 | 97.75 | 0.659 |

## Interpretation notes

- Primary claim for the Response / Methods: **3-rater ICC(2,1)** with 95% CI.
- Pairwise ICCs are supplementary (YY–Inoue, YY–Osada, Inoue–Osada).
- Variance-component ICC_case is complementary (case vs observer vs residual).
- Intra-observer (same-operator test–retest) was not the primary analysis for this revision.

## Output files

- `icc_multirater_results.md` — this report
- `icc_multirater_stats.csv` — primary 3-rater ICC table
- `icc_multirater_pairwise.csv` — pairwise ICC table
- `icc_multirater_variance_components.csv` — variance components
- `icc_multirater_long.csv` — long-format matched ratings
- `icc_multirater_wide.csv` — wide-format matched ratings
