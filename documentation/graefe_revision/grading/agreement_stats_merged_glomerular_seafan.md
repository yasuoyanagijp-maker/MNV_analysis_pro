# Expert–automated agreement — sensitivity (Glomerular/Seafan merged)

Sensitivity analysis: collapse `Glomerular` and `Seafan` into one category
`Glomerular/Seafan` on **both** expert and automated labels before agreement.

Ordinal order for quadratic weighted κ (4 levels): Dead tree → Tree in bud → Glomerular/Seafan → Medusa.
Spelling normalized to `Tree in bud` (same as primary analysis).
Bootstrap 95% CI: 10000 resamples, seed `20260727` (same method as `compute_agreement.py`).

Source files: `expert_grades_locked.csv`, `automated_labels.csv`, joined via `grading_manifest.csv` / `grading_subset_meta.csv` (same as `compute_agreement.py`).

- n (subset): **54**
- Overall agreement: **75.9%** (41/54)
- Quadratic weighted κ: **0.682** (95% CI 0.400–0.852)
- Unweighted κ: **0.512** (95% CI 0.258–0.724)

## Comparison to primary 5-class analysis

| Metric | 5-class (primary) | 4-class (Glomerular/Seafan merged) | Δ |
|---|---|---|---|
| Overall agreement | 57.4% | 75.9% | +18.5 pp |
| Quadratic weighted κ | 0.507 | 0.682 | +0.175 |

## Confusion matrix (rows = expert, columns = automated)

| expert \ automated | Dead tree | Tree in bud | Glomerular/Seafan | Medusa |
|---|---|---|---|---|
| Dead tree | 2 | 0 | 1 | 0 |
| Tree in bud | 0 | 2 | 3 | 0 |
| Glomerular/Seafan | 0 | 0 | 30 | 6 |
| Medusa | 0 | 0 | 3 | 7 |
