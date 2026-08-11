# Dual-read adoption summary (2026-08-11)

- Site reader: **Inoue**
- 2nd reader: **Inoda_ARIAKE**
- RPD threshold: **20%**
- Matched visits: **11**
- Unmatched (site only): 0
- Unmatched (2nd only): 0

## Rule

1. Recompute Caliber/Maturity **U2** on both CSVs (mandatory).
2. Match by Case + Visit (flexible filename / column rules).
3. If RPD ≤ 20% → adopted = mean; else **NA** (recheck).

**Justification:** 20%は測定誤差を許容しつつ、過度な除外を避けるために設定した。

## Exclusion at this threshold

- Major-metric cell exclusion: 3/88 (3.41%)
- Visits with any major RECHECK: 2/11 (18.18%)

### RECHECK by major metric

- MNV Area (mm2): 1
- Vsl Area (mm2): 1
- Caliber Uniformity Score (U2): 1

## Per-metric RPD / ICC / Bland–Altman

| Metric | n | RPD median | RPD P90 | ≤thr % | ICC(2,1) | BA bias | 95% LoA |
|--------|---|------------|---------|--------|----------|---------|---------|
| MNV Area (mm2) | 11 | 5.63% | 14.69% | 90.9% | 0.151 | 0.04432 | [-0.3264, 0.415] |
| Vsl Area (mm2) | 11 | 3.64% | 11.63% | 90.9% | 0.597 | 0.04114 | [-0.1173, 0.1995] |
| Vsl Density (Vessel Area/MNV (%)) | 11 | 3.76% | 7.76% | 100.0% | 0.747 | 0.01565 | [-0.02444, 0.05573] |
| Caliber Uniformity Score (U2) | 11 | 3.05% | 13.76% | 90.9% | 0.761 | 3.118 | [-6.962, 13.2] |
| Maturity Index (U2) | 11 | 1.84% | 5.65% | 100.0% | 0.848 | 1.149 | [-4.062, 6.36] |
| Network Complexity Score | 11 | 2.46% | 9.55% | 100.0% | 0.978 | 0.8204 | [-2.575, 4.215] |
| Fractal Dim | 11 | 0.50% | 2.11% | 100.0% | 0.912 | -0.008381 | [-0.03973, 0.02297] |
| Tortuosity | 11 | 0.56% | 1.37% | 100.0% | 0.956 | -0.006303 | [-0.02399, 0.01138] |
