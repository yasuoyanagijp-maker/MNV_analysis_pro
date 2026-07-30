# Intra-observer ICC (YY test–retest) — Graefe Comment 4 supplement

## Status (2026-07-30)

| Item | Status |
|------|--------|
| Session 1 (YY) | **Done** — inter-observer batch `MNV_batch_20260730_165332.csv` (n=46) |
| Session 2 (YY re-ROI) | **Needed** — no second YY batch found for the same 46 Files |
| Intra ICC numbers | Not computed until Session 2 CSV arrives |

Legacy Flet `icc_session1.csv` / `icc_session2.csv` (n≈30, different image set) are **not** this cohort. Do not mix them with the n=46 inter set.

## Design

| Item | Decision |
|------|----------|
| Examiner | Same operator (YY) |
| Cases | **All 46** Files from the inter-observer set (default; matches Comment 4 primary n) |
| Interval | Re-analyze on a different sitting; **do not look at Session 1 scores** while drawing ROIs |
| Pipeline | Same freehand ROI → automated metrics (unchanged processing) |
| Metrics | MNV Area, Network Complexity, Caliber Uniformity, Maturity Index |
| Primary model | **ICC(2,1)** absolute agreement (two-way random; sessions as random) |
| Secondary | **ICC(3,1)** consistency (two-way mixed; sessions fixed) |

**n recommendation:** Prefer **all 46** so intra-observer reporting matches the inter-observer Comment 4 set. A stratified 20–30 subset is acceptable only if time is limiting; use the ordered case list and stop early only after documenting which orders were completed.

## Images

Use the same 46 JPGs already used for inter-observer:

- `/Users/yy/Desktop/octa_images_jpg` (working copy)
- Repo mirror: `documentation/graefe_revision/icc/_raw_from_downloads/octa_images_jpg`

Case order: `icc_intra_session1_case_list.csv` (column `order` 1–46 = Session 1 File order).

## Protocol (Session 2)

1. Open the interactive / Flet OCTA analysis UI **only when ready to re-ROI** (do not start it from this scaffold alone).
2. Load images from `octa_images_jpg` in the order of `icc_intra_session1_case_list.csv`.
3. Draw freehand ROI **without** opening Session 1 CSV scores or prior ROI overlays as a guide.
4. Export batch CSV (standard MNV batch schema with `File` + metric columns).
5. Drop the CSV here:

```
documentation/graefe_revision/icc/intra/incoming_session2/
  MNV_batch_YYYYMMDD_HHMMSS.csv
```

Preferred explicit path after export:

```
documentation/graefe_revision/icc/intra/incoming_session2/MNV_batch_<timestamp>_YY_session2.csv
```

6. Run:

```bash
.venv/bin/python scripts/graefe_revision/compute_icc_intra.py
```

Outputs (when Session 2 is present and Files match):

- `icc/icc_intra_YY_results.md`
- `icc/icc_intra_YY_stats.csv`

## Session 1 reference (locked)

| Field | Value |
|-------|--------|
| Canonical path | `icc/incoming/observer_YY/MNV_batch_20260730_165332.csv` |
| Local copy | `icc/intra/session1_YY_MNV_batch_20260730_165332.csv` |
| Session ID | `20260730_165332_530478` |
| Analyst | Yasuo Yanagi |
| n | 46 unique `File`s |

Do **not** overwrite Session 1. Session 2 must be a new batch export.

## After Session 2

1. Confirm `File` intersection = 46 (or documented subset).
2. Run `compute_icc_intra.py`.
3. Fill Response Comment 4 intra-observer paragraph with ICC(2,1) (+ CI) per metric; keep inter-observer n=46 table as primary.

## Checklist

- [x] Confirm only one YY batch for n=46 inter set
- [x] Case list + Session 1 copy under `icc/intra/`
- [x] `scripts/graefe_revision/compute_icc_intra.py`
- [ ] Session 2 re-ROI (n=46 preferred)
- [ ] Drop Session 2 CSV under `intra/incoming_session2/`
- [ ] Run compute script → `icc_intra_YY_results.md`
- [ ] Update Response Comment 4 intra paragraph
