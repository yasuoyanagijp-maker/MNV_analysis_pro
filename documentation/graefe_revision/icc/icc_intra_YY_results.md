# Intra-observer ICC — YY Session1 vs Session2

**Session1:** `documentation/graefe_revision/icc/intra/session1_YY_MNV_batch_20260730_165332.csv`
**Session2:** `documentation/graefe_revision/icc/intra/incoming_session2/MNV_batch_20260731_114427_YY_session2.csv`
**Matched n:** 46

## Primary — ICC(2,1) absolute agreement

| Metric | n | ICC(2,1) | 95% CI |
|--------|---|----------|--------|
| MNV Area (mm²) | 46 | 0.979 | 0.962–0.988 |
| Network Complexity Score | 46 | 0.950 | 0.913–0.973 |
| Caliber Uniformity Score | 46 | -0.107 | -0.201–0.083 |
| Maturity Index | 46 | 0.274 | 0.035–0.433 |
| Caliber Uniformity Score (U2) | 46 | 0.925 | 0.871–0.959 |
| Maturity Index (U2) | 46 | 0.917 | 0.857–0.954 |

## Secondary — ICC(3,1) consistency

| Metric | ICC(3,1) | 95% CI |
|--------|----------|--------|
| MNV Area (mm²) | 0.979 | 0.963–0.988 |
| Network Complexity Score | 0.949 | 0.910–0.972 |
| Caliber Uniformity Score | -0.155 | -0.424–0.138 |
| Maturity Index | 0.341 | 0.059–0.573 |
| Caliber Uniformity Score (U2) | 0.923 | 0.866–0.957 |
| Maturity Index (U2) | 0.915 | 0.852–0.952 |

## Notes

- Intra-observer = same examiner (YY), two sittings, freehand ROI each time.
- Primary reporting model matches inter-observer Comment 4: **ICC(2,1)**.
- U2 columns are sensitivity scores (device-locked Caliber U2).

Outputs: `icc_intra_YY_stats.csv`, `icc_intra_YY_long.csv`, `icc_intra_YY_results.md`
