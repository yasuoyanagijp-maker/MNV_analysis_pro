# Blind expert grading (WS2 prep)

## Purpose

Masked morphological grading by YY for agreement vs automated rule-based subtypes (Reviewer 2 #2). Weighted Cohen’s κ after unblinding.

## Confirmed decisions

- Examiner: **YY**
- Spelling (match automated): **Dead tree / Tree in bud / Glomerular / Seafan / Medusa**
- Weighted κ ordinal order: Dead tree → Tree in bud → Glomerular → Seafan → Medusa
- Expert grading uses a **stratified subset**, not the full ~112–113 cohort

## Subset design

| Stratum | Cohort n | Graded n |
|---------|----------|----------|
| large | 49 | 24 |
| small | 33 | 16 |
| small_3mm | 30 | 14 |
| **Total** | **112** | **54** |

- Seed: `20260727`
- Why n=54: ~48% of the analysis cohort; large enough for weighted κ with five ordered categories while remaining feasible for single-reader grading; proportional by device/FOV stratum
- Cases without a readable image under the original_inputdata tree were excluded from the sampling pool (1 small CSV file name not present on disk)

## Files (blinding)

| File | Contents | Who may see |
|------|----------|-------------|
| `expert_grades_blind.csv` | `blind_id` + empty `expert_subtype` | **YY (grader)** |
| `grading_manifest.csv` | blind_id → real path/key/stratum | Operator / unblinding only |
| `automated_labels.csv` | full cohort automated subtypes | **Do not open while grading** |
| `grading_subset_meta.csv` | blind_id + automated subtype (subset) | Unblinding only |

## Automated label method

1. **large / small_3mm:** `Subtype` column from git commit `1e5d202` batch CSVs in `../data/`
2. **small:** CSV lacked Subtype → **classifier re-run** is paper ground truth:
   - Inputs: `Network Complexity Score` + `Caliber Uniformity Score` from the small batch CSV
   - Trunk pattern: `TrunkVesselClassifier` using `eccentricity`, `angular_cv`, `radial_uniformity` from `output/reference_build_session.json` raw
   - Session raw lacks `thick_vessel_center_ratio` / `diameter_ratio` → mid-tier defaults **7.5** and **1.1** (documented; see `trunk_method` column)
   - Rule set: `classify_morphology_final` + `resources/reference_metrics/mnv_classification_ref_small.json`
   - 1 CSV case not in session JSON used Intermediate trunk fallback (`label_method` flag)

Rebuild:

```bash
.venv/bin/python scripts/graefe_revision/build_automated_labels.py
.venv/bin/python scripts/graefe_revision/build_grading_subset.py
```

## Grading protocol (YY)

1. Open only `expert_grades_blind.csv`
2. For each `blind_id`, open the OCTA image **without** overlays/subtype text:
   ```bash
   .venv/bin/python scripts/graefe_revision/open_blind_cases.py --blind-id B001
   ```
   or `--print-only` for the path list. Images stay in  
   `/Users/yy/MNV_quantitatibe analysis_original_inputdata/{large,small,small_3mm}`  
   (no full blind copy; avoids large disk use).
3. Enter one of: `Dead tree` | `Tree in bud` | `Glomerular` | `Seafan` | `Medusa`
4. Do **not** open `automated_labels.csv` / `grading_subset_meta.csv` until all rows are locked
5. After lock: merge on `blind_id` and compute agreement + weighted κ:
   ```bash
   .venv/bin/python scripts/graefe_revision/compute_agreement.py
   ```
   Writes `agreement_stats.md` (+ CSV / confusion matrix). If grades are empty or incomplete, the script exits with a clear message and does **not** unblind.

## Status

- [x] Prep (labels, subset, blind template)
- [x] `compute_agreement.py` ready (graceful until grades locked)
- [x] YY grading complete (54/54) → `expert_grades_locked.csv`
- [x] Unblind + κ / confusion matrix (`agreement_stats.md`, `confusion_matrix.csv`)

**Results (n=54, post-regrade):** overall agreement 57.4% (31/54); quadratic weighted κ 0.507 (95% CI 0.222–0.714).
