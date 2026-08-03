# Table 1 ICC supplement — full inter / intra inventory

**Date:** 2026-08-01
**Purpose:** Fill Table 1 Inter-rater / Intra-rater ICC(2,1) columns for all lesion metrics with Session1/Session2 data (n = 46).

## Model

ICC(2,1) absolute agreement (Shrout & Fleiss), via `try_pingouin_icc` → pingouin Type **ICC2** (fallback `icc_2_1_multirater`). Same model for inter (k=3 observers) and intra (k=2 sessions). ICC(1,1) was **not** used for intra/test–retest.

| Analysis | Sources | n | k |
|----------|---------|---|---|
| Inter | YY / Inoue / Osada matched batch CSVs | 46 | 3 |
| Intra | `intra/session1_YY_…` vs `intra/incoming_session2/MNV_batch_20260731_114427_YY_session2.csv` | 46 | 2 (sessions) |

## Table 1 results (separate columns)

| Variable | Inter ICC(2,1) | Intra ICC(2,1) | Table 1 inter | Table 1 intra |
|----------|----------------|----------------|---------------|---------------|
| MNV Area | 0.859 (0.680–0.930) | 0.979 (0.960–0.990) | **0.859** | **0.979** |
| Vessel Density | 0.520 (0.130–0.750) | 0.988 (0.980–0.990) | **0.520** | **0.988** |
| Vessel Area | 0.868 (0.740–0.930) | 0.973 (0.950–0.990) | **0.868** | **0.973** |
| Total Vessel Length | 0.882 (0.760–0.940) | 0.967 (0.940–0.980) | **0.882** | **0.967** |
| Mean Diameter (skel) | 0.760 (0.610–0.860) | 0.969 (0.950–0.980) | **0.760** | **0.969** |
| Junction Density | 0.911 (0.850–0.950) | 0.977 (0.960–0.990) | **0.911** | **0.977** |
| Loop Count (total) | 0.800 (0.640–0.890) | 0.949 (0.910–0.970) | **0.800** | **0.949** |
| Euler Number (total) | 0.788 (0.630–0.880) | 0.940 (0.890–0.970) | **0.788** | **0.940** |
| Fractal Dimension | 0.671 (0.480–0.800) | 0.853 (0.750–0.920) | **0.671** | **0.853** |
| Tortuosity | 0.643 (0.490–0.770) | 0.819 (0.700–0.900) | **0.643** | **0.819** |
| Complexity Score | 0.807 (0.660–0.890) | 0.950 (0.910–0.970) | **0.807** | **0.950** |
| Caliber (default) | 0.770 (0.660–0.860) | 0.925 (0.870–0.960) | **0.770** | **0.925** |
| Caliber (PCA legacy) | 0.434 (0.260–0.610) | 0.795 (0.660–0.880) | **0.434** | **0.795** |
| NV Diameter CV | 0.259 (0.080–0.450) | 0.952 (0.920–0.970) | **0.259** (with Dilated in cell) | **0.952** |
| Dilated vessel % | 0.522 (0.320–0.690) | 0.875 (0.780–0.930) | **0.522** | **0.875** |
| Arteriolarization count | 0.802 (0.660–0.890) | 0.928 (0.870–0.960) | **0.802** | **0.928** |
| Arteriolarization length | 0.800 (0.660–0.890) | 0.926 (0.870–0.960) | **0.800** | **0.926** |
| Arteriolarization density | 0.558 (0.310–0.730) | 0.912 (0.850–0.950) | **0.558** | **0.912** |
| Maturity (default) | 0.593 (0.430–0.730) | 0.917 (0.850–0.950) | **0.593** | **0.917** |
| Maturity (PCA legacy) | 0.659 (0.510–0.780) | 0.875 (0.780–0.930) | **0.659** | **0.875** |
| Morphological κ | expert–auto 0.507 (0.222–0.714), n=54 | YY intra 0.950 (0.893–0.988), n=46 | **κ = 0.507** | **κ = 0.950** |

## Process rows (remain `—`)

| Row | Reason |
|-----|--------|
| Intelligent ROI Refinement | Process step — no lesion-metric ICC |
| Stratum-locked score normalization | Reporting-scale step — not a per-lesion measurand |
| Field-of-View Correction | Device scaling step — not a per-lesion measurand |

## Notes

- Default Caliber/Maturity intra uses the same device-locked definition applied to both sessions (Session exports were otherwise definition-mismatched).
- Legacy PCA Caliber/Maturity intra: Session1 PCA-era `Caliber Uniformity Score` / `Maturity Index` vs Session2 explicit `(PCA)` columns.
- Morphological κ: inter column = expert vs automated (n=54); intra column = YY Session1 vs Session2 subtype labels (n=46); footnote clarifies these are κ, not ICC.
- Max diameter not exported in ICC batch CSVs; Mean/Max Diameter cell uses mean skeleton diameter only.

## Artifacts

| File | Content |
|------|---------|
| `icc_table1_supplement_stats.csv` | Inter + intra ICC rows (+ κ) |
| `icc_table1_supplement_inter_long.csv` | Inter long (totals; prior) |
| `icc_table1_supplement_intra_wide.csv` | Session1/Session2 side-by-side for Table 1 metrics |
| `icc_table1_supplement_stats.md` | This note |

