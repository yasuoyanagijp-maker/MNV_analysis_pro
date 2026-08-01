# Tables — MNV Analysis


---

## Table 1. Quantitative parameters of the analysis pipeline.

| Variable | Description | Inter-rater ICC(2,1) | Intra-rater ICC(2,1) |
|----------|-------------|---------------------:|---------------------:|
| MNV Area (lesion area) | Physical area of the freehand / refined ROI (mm²). | 0.859 | 0.979 |
| Vessel Density (VD) | Proportion of perfused lesion area: (binarized vessel pixels inside refined ROI / total ROI pixels) × 100%. | 0.520 | 0.988 |
| Vessel Area (VA) | Absolute perfused area: binarized vessel pixels inside refined ROI × pixel area (mm²). | 0.868 | 0.973 |
| Total Vessel Length | Sum of all skeletonized centerline lengths: skeleton pixels × pixel size (mm). | 0.882 | 0.967 |
| Mean / Max Diameter | Local vessel diameter (2 × Euclidean distance from skeleton to background). Mean and max over all skeleton pixels in ROI. | 0.760 | 0.969 |
| Junction / Node Density | Total node count (branch/endpoints) divided by physical ROI area (nodes/mm²). | 0.911 | 0.977 |
| Loop Count | Total number of independent closed vascular loops (graph-based cycle detection after boundary-branch exclusion). | 0.800 | 0.949 |
| Euler Number | Global connectivity index: (connected components) − (loops). More negative = higher connectivity. | 0.788 | 0.940 |
| Fractal Dimension (Df) | Box-counting dimension of the skeletonized MNV (slope of the log–log plot). | 0.671 | 0.853 |
| Tortuosity Index | Mean segment tortuosity: (path length along skeleton / straight-line distance) averaged over eligible branches. | 0.643 | 0.819 |
| Standardized Vascular Complexity Score (0–100) | Stratum-specific PCA latent score: 0.7 × PC1 + 0.2 × PC2 + 0.1 × TrunkDist; piecewise map so min/median/max → 0/50/100 within stratum. | 0.807 | 0.950 |
| Standardized Caliber Uniformity Score (0–100) | 0.75 × U(−NV Diameter CV) + 0.25 × U(−Dilated vessel %), with stratum-specific piecewise maps. | 0.770 | 0.925 |
| Diameter CV / Dilated vessel % | Skeleton-derived NV Diameter CV and fraction of vessel length exceeding mean + 2.0 × SD (inputs to the Caliber score). | 0.259; 0.522 | 0.952; 0.875 |
| Intelligent ROI Refinement | 5-iteration vertex optimization (3-pixel search radius) to align the ROI boundary with non-perfused tissue. | — | — |
| Arteriolarization Detection | Branches with local diameter > mean + 2.0 × SD; reports count, length, and area density. | 0.802; 0.800; 0.558 | 0.928; 0.926; 0.912 |
| Rule-based morphological categorization | Five-class subtype labels (Medusa, Seafan, Glomerular, Tree in bud, Dead tree) plus separate morphology-derived interpretive categories (hypothesis-generating). | κ = 0.507 | κ = 0.950 |
| Stratum-specific score normalization | Within-stratum standardization / locked piecewise maps place scores on a common 0–100 **reporting** scale (not biological equivalence across devices). | — | — |
| Field-of-View Correction | Physical unit conversion using device-specific scaling across 3×3 mm and 6×6 mm scans. | — | — |
| Standardized Maturity Index (0–100) | clip(50 + (Caliber Uniformity Score − Complexity Score) / 2, 0, 100) using the Caliber score. Values > 50 indicate uniformity-dominant morphology; < 50 complexity-dominant. | 0.593 | 0.917 |


*Note.* Kruskal–Wallis non-significance of standardized scores should be interpreted as consistent with the scaling procedure, without establishing cross-device biological equivalence. Inter-rater and intra-rater columns report ICC(2,1) (two-way random-effects, absolute agreement, single measures; n = 46) unless marked κ. Morphological agreement cells report quadratic weighted Cohen's κ: inter-rater (expert–algorithm, n = 54) and intra-rater (test–retest, same observer, n = 46). Arteriolarization lists count; length; density. Loop Count and Euler Number ICCs use totals (center + periphery), matching Table 2. Diameter CV / Dilated vessel % shows ICCs for each component (CV and Dilated%). Arteriolarization reports count, length, and density. Process rows (ROI refinement, stratum normalization, field-of-view correction) do not have corresponding lesion-metric ICCs. Mean / Max Diameter ICC reflects mean skeleton diameter only.

---

## Table 2. Raw topological and morphometric parameters by acquisition protocol (mean ± SD).

| Parameter | Zeiss PlexElite (6×6 mm) (n = 49) | Zeiss CIRRUS HD-OCT with AngioPlex (3×3 mm) (n = 30) | Optovue Solix (6×6 mm) (n = 33) |
|-----------|----------------------------------|--------------------------------------|--------------------------------------|
| **Topological metrics** | | | |
| Total loop count | 300.3 ± 199.2 | 165.2 ± 118.0 | 89.5 ± 53.4 |
| Euler number (total) | −168.4 ± 146.0 | −135.0 ± 98.4 | −61.6 ± 48.2 |
| Junction density (mm⁻²) | 25.85 ± 1.77 | 21.99 ± 3.51 | 15.89 ± 2.88 |
| **Morphometric metrics** | | | |
| Fractal dimension | 1.391 ± 0.081 | 1.378 ± 0.076 | 1.310 ± 0.110 |
| Mean vessel diameter (µm) | 16.0 ± 0.3 | 23.7 ± 2.0 | 32.3 ± 3.8 |
| **Caliber uniformity metrics (pre-standardization)** | | | |
| NV Diameter CV (%) | 38.5 ± 1.1 | 51.0 ± 9.0 | 41.7 ± 2.5 |
| Dilated vessel (%) | 13.3 ± 2.5 | 8.9 ± 2.0 | 8.3 ± 3.2 |

*Note.* Values are mean ± SD. Protocols: Zeiss PlexElite (6×6 mm) (large); Zeiss CIRRUS HD-OCT with AngioPlex (3×3 mm) (small_3mm); Optovue Solix (6×6 mm) (small). Skeleton-derived NV Diameter CV and Dilated vessel % are component metrics for the Standardized Caliber Uniformity Score (Methods).

---

## Table 3. Standardized scores after stratum-specific normalization, by acquisition stratum (Standardized Caliber Uniformity Score).

| Metric | Median (large / small / small_3mm) | H | p | ε² | 95% CI (ε²) |
|--------|-------------------------------------|---|---|-----|-------------|
| Standardized Vascular Complexity Score | 48.7 / 50.7 / 47.8 | 1.712 | 0.425 | 0.000 | 0.000–0.089 |
| Caliber Uniformity Score | 46.6 / 55.5 / 50.6 | 1.118 | 0.572 | 0.000 | 0.000–0.082 |
| Maturity Index (from Caliber) | 49.5 / 53.9 / 51.0 | 1.082 | 0.582 | 0.000 | 0.000–0.077 |

*Note.* ε² = (H − k + 1) / (n − k) with k = 3; bootstrap 95% CIs use 10,000 within-stratum resamples (fixed random seed for reproducibility). Primary analysis set, n = 112 (large = 49, small = 33, small_3mm = 30). Complexity Score PC1 explained variance: 63.7% / 73.9% / 70.2% (large / small_3mm / small). Median values near 50 reflect the mathematical definition of the median-anchored piecewise scaling procedure, rather than biological equivalence across devices.

---

## Table 4. Morphological subtype distribution by acquisition protocol.

| Morphological pattern | Zeiss PlexElite (6×6 mm) (n = 49) | Zeiss CIRRUS HD-OCT with AngioPlex (3×3 mm) (n = 30) | Optovue Solix (6×6 mm) (n = 33) |
|-----------------------|----------------------------------|--------------------------------------|--------------------------------------|
| Glomerular | 29 (59.2%) | 9 (30.0%) | 12 (36.4%) |
| Medusa | 6 (12.2%) | 0 (0%) | 0 (0%) |
| Seafan | 0 (0%) | 11 (36.7%) | 2 (6.1%) |
| Tree in bud | 10 (20.4%) | 4 (13.3%) | 14 (42.4%) |
| Dead tree | 4 (8.2%) | 6 (20.0%) | 5 (15.2%) |

*Note.* Values are n (%). Morphology-derived interpretive mapping is summarized separately in Table 5. 

---

## Table 5. Morphology-derived interpretive mapping for operational subtypes.

| Morphological pattern | Primary interpretive category | Secondary interpretive category | Key discriminating metrics |
|-----------------------|-------------------------------|---------------------------------|----------------------------|
| Medusa | Active-pattern | Transitional-pattern | Junction density, loop count, trunk distribution |
| Seafan | Active-pattern | Transitional-pattern | Peripheral arcade, trunk eccentricity |
| Glomerular | Active-pattern | — | High Complexity Score, low Caliber Uniformity Score |
| Tree in bud | Active-pattern | Transitional-pattern | High branching density, Euler number |
| Dead tree | Mature-quiescent-pattern | Arteriolarized-pattern | Mean diameter, Caliber Uniformity Score |

*Note.* Categories are morphology-derived interpretive categories intended for hypothesis generation. Clinical validation of these categories requires future outcome-linked studies. Only the five operational subtypes are shown; labels outside this scheme (e.g., "Pruned tree," "Large vessels") are omitted.
