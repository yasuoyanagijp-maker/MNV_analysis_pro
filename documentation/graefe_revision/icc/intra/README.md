# Intra-observer ICC (YY test–retest) — Graefe Comment 4 supplement

## Status (2026-07-31) — **DONE**

| Item | Status |
|------|--------|
| Session 1 (YY) | **Done** — `session1_YY_MNV_batch_20260730_165332.csv` (n=46) |
| Session 2 (YY re-ROI) | **Done** — `incoming_session2/MNV_batch_20260731_114427_YY_session2.csv` (n=46) |
| Intra ICC numbers | **Done** — `icc/icc_intra_YY_results.md` (+ `icc_intra_YY_stats.csv`, `icc_intra_YY_long.csv`) |
| Matched n | **46/46** Files |

Legacy Flet `icc_session1.csv` / `icc_session2.csv` (n≈30, different image set) are **not** this cohort. Do not mix them with the n=46 inter set.

## Key ICC(2,1) results (reader-facing defaults)

| Metric | ICC(2,1) | 95% CI |
|--------|----------|--------|
| MNV Area (mm²) | 0.979 | 0.962–0.988 |
| Network Complexity | 0.950 | 0.913–0.973 |
| Caliber Uniformity (device-locked / harmonized definition) | 0.925 | 0.871–0.959 |
| Maturity Index (with device-locked Caliber) | 0.917 | 0.857–0.954 |

**Default Caliber** for reporting = device-locked NV-CV + Dilated% (harmonized definition). Do not present the pre-harmonization CSV column as the primary Caliber ICC.

Full tables (including secondary ICC(3,1) and legacy column sensitivity): `../icc_intra_YY_results.md`.

## Design

| Item | Decision |
|------|----------|
| Examiner | Same operator (YY) |
| Cases | **All 46** Files from the inter-observer set |
| Interval | Re-analyze on a different sitting; Session 2 drawn without Session 1 scores as a guide |
| Pipeline | Same freehand ROI → automated metrics |
| Metrics | MNV Area, Network Complexity, Caliber Uniformity, Maturity Index |
| Primary model | **ICC(2,1)** absolute agreement (two-way random; sessions as random) |
| Secondary | **ICC(3,1)** consistency (two-way mixed; sessions fixed) |

## Images

Same 46 JPGs as inter-observer:

- `/Users/yy/Desktop/octa_images_jpg` (working copy)
- Repo mirror: `documentation/graefe_revision/icc/_raw_from_downloads/octa_images_jpg`

Case order: `icc_intra_session1_case_list.csv` (column `order` 1–46 = Session 1 File order).

## Session paths (locked)

| Field | Value |
|-------|--------|
| Session 1 (local copy) | `icc/intra/session1_YY_MNV_batch_20260730_165332.csv` |
| Session 1 (canonical inter batch) | `icc/incoming/observer_YY/MNV_batch_20260730_165332.csv` |
| Session 1 ID | `20260730_165332_530478` |
| Session 2 | `icc/intra/incoming_session2/MNV_batch_20260731_114427_YY_session2.csv` |
| Analyst | Yasuo Yanagi |
| n | 46 unique `File`s (intersection = 46) |

Do **not** overwrite Session 1 or Session 2 CSVs.

## Recompute (if needed)

```bash
.venv/bin/python scripts/graefe_revision/compute_icc_intra.py
```

Outputs:

- `icc/icc_intra_YY_results.md`
- `icc/icc_intra_YY_stats.csv`
- `icc/icc_intra_YY_long.csv`

## After Session 2 (paper / Response) — all done

1. ~~Confirm `File` intersection = 46~~ — done.
2. ~~Run `compute_icc_intra.py`~~ — done.
3. ~~Fill Response Comment 4 intra-observer paragraph~~ — done (ICC(2,1) + CI; default device-locked Caliber; inter n=46 remains primary).

## Checklist

- [x] Confirm only one YY batch for n=46 inter set
- [x] Case list + Session 1 copy under `icc/intra/`
- [x] `scripts/graefe_revision/compute_icc_intra.py`
- [x] Session 2 re-ROI (n=46)
- [x] Drop Session 2 CSV under `intra/incoming_session2/`
- [x] Run compute script → `icc_intra_YY_results.md`
- [x] Update Response Comment 4 intra paragraph
