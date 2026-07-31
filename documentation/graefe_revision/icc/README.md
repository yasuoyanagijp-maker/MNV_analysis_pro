# Multi-rater ICC (WS1) — inter- and intra-observer reproducibility — **COMPLETED**

Parent map: [`../README.md`](../README.md).

## Status (2026-07-31) — complete for Comment 4

| Workstream | Status |
|------------|--------|
| Inter-observer (3 raters × **n = 46**) | **Done** — `icc_multirater_results.md` |
| Intra-observer (YY Session1 vs Session2, **n = 46**) | **Done** — `icc_intra_YY_results.md` |
| Response Comment 4 | Filled (inter primary + intra supplement) |
| Caliber framing | **Default** = device-/stratum-locked Standardized Caliber Uniformity Score; **PCA** = legacy / sensitivity only |

Reader-facing prose uses **Standardized Caliber Uniformity Score** (default) and **PCA-based Caliber Uniformity Score (legacy)**. Internal code / paths may still say `caliber_u2_*` / `U2`; do not use “U2” in manuscript or Response summaries.

## Confirmed design

| Item | Decision |
|------|----------|
| Observers (inter) | **3 independent operators**: YY + Inoue + Osada |
| n (inter / intra) | **46** cases (complete intersection; same Files) |
| Primary analysis | **Multi-rater ICC(2,1)** (3 raters × 46); intra = same-operator supplement |
| Metrics | Lesion area, Network Complexity, **default** Caliber Uniformity, Maturity Index (from default Caliber) |
| Caliber default | Device-/stratum-locked: `0.75·piecewise(−NV_CV) + 0.25·piecewise(−Dilated%)` (`caliber_u2_device_ref.json`; internal name) |
| Caliber legacy | PCA Stability composite — sensitivity only (inter ICC 0.434) |

Legacy same-operator Session1/Session2 files (`icc_session1.csv`, `icc_session2*.csv`, `icc_case_list.csv`, `compute_icc.py`) remain on disk as optional older material (different image set). Do **not** mix with the n=46 cohort.

## Incoming data layout

```
documentation/graefe_revision/icc/incoming/
  README.md
  observer_YY/              ← YY Session 1 scores
  observer_A/ / observer_inoue/
  observer_B/ / observer_osada/
```

Intra Session 2:

```
documentation/graefe_revision/icc/intra/incoming_session2/
  MNV_batch_20260731_114427_YY_session2.csv
```

## Required CSV columns

| Column | Description |
|--------|-------------|
| `case_id` | Shared case identifier across observers (must match) |
| `area` | Lesion / MNV area |
| `complexity` | Network Complexity |
| `caliber_uniformity` | Caliber Uniformity score (see default vs PCA note above) |
| `maturity` | Maturity Index |
| `observer` | Observer id (`YY`, `A`, `B`, or folder name) |
| `date` | Analysis / ROI date (ISO `YYYY-MM-DD` preferred) |

Aliases: `MNV Area` → `area`; `Network Complexity` → `complexity`; `Caliber Uniformity` → `caliber_uniformity`; `Maturity` / `Maturity Index` → `maturity`; `icc_id` / `File` → `case_id`.

## Primary analysis — multi-rater ICC

**Primary (for paper):** classical **Shrout & Fleiss ICC(2,1)** — two-way **random** effects, **absolute agreement**, **single measures** — for **3 raters × 46 cases**, reported **per metric**, each with **95% CI**.

Also report ICC(2,k) and multilevel / ANOVA variance-component ICC as complementary.

**Primary inter numbers (default Caliber):** Area 0.859 · Complexity 0.807 · Caliber **0.770** · Maturity **0.593**.  
**Legacy PCA Caliber (sensitivity):** 0.434. Details: `icc_multirater_results.md`, `caliber_u2_device_std_icc_results.md`, Response Comment 4.

**Intra (YY, n=46; same device-locked Caliber on both sessions):** Area 0.979 · Complexity 0.950 · Caliber **0.925** · Maturity **0.917**. Details: `icc_intra_YY_results.md`.

## Compute

```bash
.venv/bin/python scripts/graefe_revision/compute_icc_multirater.py
.venv/bin/python scripts/graefe_revision/compute_icc_intra.py
```

Caliber default / device-locked ICC artifacts: `compute_caliber_u2_device_std_icc.py`, `caliber_u2_device_std_icc_results.md`. Changelog of score hunt: `caliber_cv_strengthening_changelog.md`.

## Checklist

- [x] Receive score CSVs from Inoue, Osada, YY
- [x] Drop files under `incoming/` (+ clear-name aliases)
- [x] Confirm shared `case_id` set (**n = 46**)
- [x] Run `compute_icc_multirater.py` → `icc_multirater_results.md`
- [x] Device-locked default Caliber ICC + PCA legacy sensitivity framed
- [x] YY intra Session 2 (n=46) → `icc_intra_YY_results.md`
- [x] Response letter Comment 4 filled (inter + intra; no reader-facing “U2”)
- [x] Methods: ICC(2,1) primary; multilevel VC ICC reported; Caliber default vs PCA legacy

## Sensitivity subset (n=20 most concordant)

Optional upper-bound ICC on nested concordance subsets (n=20/30/35/40). See `icc_cases_ranked_by_concordance.csv`, `icc_multirater_concordance_ladder.md`, and `icc_multirater_results_subset*.md`. Does **not** replace primary n=46 Comment 4 numbers.
