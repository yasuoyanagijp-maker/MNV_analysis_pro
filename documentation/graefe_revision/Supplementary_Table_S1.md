# Supplementary Table S1 — Locked reference cut-points for rule-based morphological categorization and default Caliber Uniformity Score

Source: locked reference files used by the classifier and the default Standardized Caliber Uniformity Score (Complexity Score percentiles per acquisition stratum; device-/stratum-locked NV Diameter CV and Dilated vessel % cuts). Values are reporting-scale reference cuts, not claims of biological equivalence across devices. Classification-reference n for the small stratum is 34 in the locked Complexity percentile file; the primary analysis batch used for Tables 2–3 has n = 33 for that stratum.

## A. Complexity Score percentile cut-points used in Level-1 subtype rules

P30 is not stored in the locked JSON and is linearly interpolated between P25 and P40 (same rule as the classifier).

| Stratum (device) | n | P10 (Dead tree <) | P30 (Glomerular ≥; interpolated) | P40 (Seafan ≥ with SEAFAN trunk) | P65 (Medusa ≥ with MEDUSA trunk) |
|------------------|---|-------------------|-----------------------------------|----------------------------------|----------------------------------|
| large (Zeiss PlexElite 6×6 mm) | 49 | 24.29 | 38.36 | 43.21 | 55.00 |
| small_3mm (Zeiss CIRRUS AngioPlex 3×3 mm) | 30 | 44.77 | 67.93 | 69.36 | 72.85 |
| small (Optovue Solix 6×6 mm) | 34 | 34.20 | 41.21 | 44.93 | 53.77 |

**Operational priority order:** Dead tree → Medusa → Seafan → Glomerular → Tree in bud (remainder). Trunk pattern (MEDUSA / SEAFAN / INTERMEDIATE) is derived from spatial organization of large-caliber segments.

## B. Extended Complexity Score percentiles (locked reference cohort)

| Stratum | P10 | P25 | P40 | P50 | P60 | P65 | P75 | P90 |
|---------|-----|-----|-----|-----|-----|-----|-----|-----|
| large | 24.29 | 35.93 | 43.21 | 48.81 | 53.32 | 55.00 | 57.57 | 71.61 |
| small_3mm | 44.77 | 67.21 | 69.36 | 71.03 | 72.29 | 72.85 | 74.31 | 77.74 |
| small | 34.20 | 39.34 | 44.93 | 48.71 | 51.06 | 53.77 | 55.65 | 65.22 |

## C. Default Standardized Caliber Uniformity Score — locked feature cuts (NV Diameter CV; Dilated vessel fraction)

Score = clip(0.75·U(−NV Diameter CV) + 0.25·U(−Dilated vessel %), 0, 100), where U maps stratum min/median/max of the negated feature to 0/50/100.

| Stratum (device) | n | NV-CV min | NV-CV median | NV-CV max | Dilated% min | Dilated% median | Dilated% max |
|------------------|---|-----------|--------------|-----------|--------------|-----------------|--------------|
| large (Zeiss PlexElite 9000 6×6 mm) | 49 | 36.5120 | 38.4867 | 40.9939 | 0.076141 | 0.130156 | 0.183429 |
| small_3mm (Zeiss CIRRUS HD AngioPlex 3×3 mm (Angiography 3x3)) | 30 | 43.0772 | 47.2952 | 79.1192 | 0.046519 | 0.091894 | 0.121717 |
| small (Optovue Solix / AngioVue 6×6 mm) | 33 | 37.0858 | 41.3097 | 48.8622 | 0.041908 | 0.076640 | 0.163276 |

## D. Note on legacy PCA-based Caliber Uniformity Score

The PCA Stability Caliber composite (four radial-profile metrics) is retained only as a sensitivity / legacy comparison for inter-observer concordance and is **not** the default Caliber Uniformity endpoint in this revision.

