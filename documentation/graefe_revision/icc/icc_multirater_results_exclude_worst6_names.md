# Multi-rater ICC — exclude all files matching worst-6 patient names

**Date computed:** 2026-07-30  
**Primary analysis (unchanged):** 3-rater ICC(2,1) on **n = 46** (see `icc_multirater_results.md`).  
**This file:** sensitivity after excluding **all** matched-set files whose patient-name stem appears in the concordance-worst 6 cases (not only those 6 files).  
**Observers:** Inoue, Osada, YY  
**Model:** ICC(2,1) — two-way random effects, absolute agreement, single measures

## Exclusion rule

1. Take concordance ranks **41–46** from `icc_cases_ranked_by_concordance.csv` (highest discordance).
2. Extract unique **name stems** = `lastname_firstname` prefix before `__` in `File`.
3. Exclude **every** n=46 case whose `File` starts with any of those stems (both visits for that patient).

### Unique name stems (from worst-6 File names)

- `furukawa_hiroichi`
- `imazeki_humio`
- `kobayashi_isao`
- `matuzaki_mineo`
- `takako_fumiichi`

**Excluded files:** 10  
**Remaining n:** 36 (= 46 − 10)

### Excluded count per name

| Name stem | Files excluded | Concordance ranks of those files |
|-----------|----------------|----------------------------------|
| `furukawa_hiroichi` | 2 | 35, 45 |
| `imazeki_humio` | 2 | 6, 42 |
| `kobayashi_isao` | 2 | 40, 46 |
| `matuzaki_mineo` | 2 | 26, 44 |
| `takako_fumiichi` | 2 | 41, 43 |

Unlike excluding only ranks 41–46 (→ n=40), name-level exclusion also drops the **paired** visits of those patients that ranked higher on concordance (imazeki rank 6, matuzaki rank 26, furukawa rank 35, kobayashi rank 40). takako_fumiichi already contributed both visits to the worst-6.

## Primary: 3-rater ICC(2,1) on remaining cases

| Metric | n | k | ICC(2,1) | 95% CI | Source |
|--------|---|---|----------|--------|--------|
| MNV Area (mm²) | 36 | 3 | 0.788 | 0.54–0.90 | pingouin |
| Network Complexity Score | 36 | 3 | 0.845 | 0.69–0.92 | pingouin |
| Caliber Uniformity Score | 36 | 3 | 0.637 | 0.46–0.78 | pingouin |
| Maturity Index | 36 | 3 | 0.802 | 0.68–0.89 | pingouin |

## Comparison vs n=46 (primary) and vs concordance top-40

| Metric | n=46 ICC(2,1) | 95% CI | n=40 (excl. worst-6 *files*) | 95% CI | n=36 (excl. worst-6 *names*) | 95% CI | Δ vs n46 | Δ vs n40 |
|--------|---------------|--------|------------------------------|--------|--------------------------------|--------|----------|----------|
| MNV Area (mm²) | 0.859 | 0.68–0.93 | 0.847 | 0.67–0.93 | 0.788 | 0.54–0.90 | -0.071 | -0.059 |
| Network Complexity Score | 0.807 | 0.66–0.89 | 0.822 | 0.68–0.90 | 0.845 | 0.69–0.92 | +0.037 | +0.023 |
| Caliber Uniformity Score | 0.434 | 0.26–0.61 | 0.611 | 0.44–0.75 | 0.637 | 0.46–0.78 | +0.203 | +0.026 |
| Maturity Index | 0.659 | 0.51–0.78 | 0.777 | 0.65–0.87 | 0.802 | 0.68–0.89 | +0.143 | +0.025 |

## Interpretation

- Name-level exclusion removes **10** files (**5** unique patients) → **n = 36**, stricter than file-only exclusion of the worst 6 (n=40).
- This is a **sensitivity / exploratory** analysis; it does **not** replace the primary n=46 ICC.
- Compared with concordance top-40, results differ because additional mid-ranked paired visits of the same patients are removed.

## Output files

- `icc_excluded_by_worst6_names.csv` — all excluded files + name stem
- `icc_after_exclude_worst6_names_case_list.csv` — remaining case IDs
- `icc_multirater_results_exclude_worst6_names.md` — this report

