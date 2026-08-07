# Dual-read adoption summary (2026-08-07)

- Site reader: **Inoda**
- 2nd reader: **Inoue**
- RPD threshold: **20%**
- Matched visits: **12**
- Unmatched (site only): 0
- Unmatched (2nd only): 0

## Rule

1. Recompute Caliber/Maturity **U2** on both CSVs (mandatory).
2. Match by Case + Visit (flexible filename / column rules).
3. If RPD ≤ 20% → adopted = mean; else **NA** (recheck).

**Justification:** 20%は測定誤差を許容しつつ、過度な除外を避けるために設定した。

## Exclusion at this threshold

- Major-metric cell exclusion: 6/96 (6.25%)
- Visits with any major RECHECK: 4/12 (33.33%)

### RECHECK by major metric

- MNV Area (mm2): 3
- Vsl Area (mm2): 2
- Caliber Uniformity Score (U2): 1

## Per-metric RPD / ICC / Bland–Altman

| Metric | n | RPD median | RPD P90 | ≤thr % | ICC(2,1) | BA bias | 95% LoA |
|--------|---|------------|---------|--------|----------|---------|---------|
| MNV Area (mm2) | 12 | 13.17% | 24.89% | 75.0% | 0.383 | -0.1462 | [-0.6914, 0.399] |
| Vsl Area (mm2) | 12 | 6.31% | 24.78% | 83.3% | 0.445 | -0.03259 | [-0.2865, 0.2213] |
| Vsl Density (Vessel Area/MNV (%)) | 12 | 4.11% | 14.81% | 100.0% | 0.439 | 0.02175 | [-0.04925, 0.09275] |
| Caliber Uniformity Score (U2) | 12 | 6.19% | 17.83% | 91.7% | 0.688 | -3.128 | [-15.76, 9.506] |
| Maturity Index (U2) | 12 | 3.54% | 7.66% | 100.0% | 0.639 | -1.712 | [-7.944, 4.521] |
| Network Complexity Score | 12 | 3.70% | 9.00% | 100.0% | 0.973 | 0.2951 | [-4.215, 4.805] |
| Fractal Dim | 12 | 1.60% | 3.87% | 100.0% | 0.757 | -0.01753 | [-0.07186, 0.03679] |
| Tortuosity | 12 | 0.99% | 2.00% | 100.0% | 0.762 | -0.002364 | [-0.03511, 0.03038] |
