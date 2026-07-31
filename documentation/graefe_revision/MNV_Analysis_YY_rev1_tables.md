# Tables — MNV Analysis (revision 1)

Separate tables file matching the original submission packaging (`MNV_analysis_tables.docx`). The manuscript body cites Tables 1–5 in text only; grids are not embedded in the manuscript.

---

## Table 1. Quantitative parameters of the analysis pipeline.

| Category | Parameter | Description & definition |
|----------|-----------|--------------------------|
| Morphometry | Vessel Density (VD) | Proportion of perfused lesion area: (binarized vessel pixels inside refined ROI / total ROI pixels) × 100%. |
|  | Vessel Area (VA) | Absolute perfused area: binarized vessel pixels inside refined ROI × pixel area (mm²). |
|  | Total Vessel Length | Sum of all skeletonized centerline lengths: skeleton pixels × pixel size (mm). |
|  | Mean / Max Diameter | Local vessel diameter (2 × Euclidean distance from skeleton to background). Mean and max over all skeleton pixels in ROI. |
| Topology | Junction / Node Density | Total node count (branch/endpoints) divided by physical ROI area (nodes/mm²). |
|  | Loop Count | Total number of independent closed vascular loops (graph-based cycle detection after boundary-branch exclusion). |
|  | Euler Number | Global connectivity index: (connected components) − (loops). More negative = higher connectivity. |
| Complexity | Fractal Dimension (Df) | Box-counting dimension of the skeletonized MNV (slope of the log–log plot). |
|  | Tortuosity Index | Mean segment tortuosity: (path length along skeleton / straight-line distance) averaged over eligible branches. |
|  | Standardized Complexity Score (0–100) | Stratum-specific PCA latent score: 0.7 × PC1 + 0.2 × PC2 + 0.1 × TrunkDist; piecewise map so min/median/max → 0/50/100 within stratum. |
| Caliber Uniformity | Standardized Caliber Uniformity Score (0–100) | **Default:** device-/stratum-locked 0.75 × U(−NV Diameter CV) + 0.25 × U(−Dilated vessel %). **Legacy (sensitivity):** PCA of four radial-profile metrics. Formerly also called Vascular Stability Score. |
|  | Diameter CV / Dilated vessel % | Skeleton-derived NV Diameter CV and fraction of vessel length exceeding mean + 2.0 × SD (inputs to the default Caliber score). |
| Advanced | Intelligent ROI Refinement | 5-iteration vertex optimization (3-pixel search radius) to align the ROI boundary with non-perfused tissue. |
|  | Arteriolarization Detection | Branches with local diameter > mean + 2.0 × SD; reports count, length, and area density. |
|  | Rule-based morphological categorization | Five-class subtype labels (Medusa, Seafan, Glomerular, Tree in bud, Dead tree) plus separate morphology-derived interpretive categories (hypothesis-generating). |
| Multi-device | Stratum-locked score normalization | Within-stratum standardization / locked piecewise maps place scores on a common 0–100 **reporting** scale (not biological equivalence across devices). |
|  | Field-of-View Correction | Physical unit conversion using device-specific scaling across 3×3 mm and 6×6 mm scans. |
|  | Standardized Maturity Index (0–100) | clip(50 + (Caliber Uniformity Score − Complexity Score) / 2, 0, 100). Values > 50 indicate uniformity-dominant morphology; < 50 complexity-dominant. |

*Note.* Restored from the original submission tables file (`MNV_analysis_tables.docx`) with notation revised for this revision (Caliber Uniformity; morphology-derived categories; default vs legacy Caliber definition; no claim that Kruskal–Wallis non-significance equals cross-device equivalence).

---

## Table 2. Raw topological and morphometric parameters by acquisition protocol (mean ± SD).

| Parameter | Large PlexElite 6×6 mm (n = 49) | Small_3mm HD series 3×3 mm (n = 30) | Small Optovue Solix 6×6 mm (n = 33) |
|-----------|----------------------------------|--------------------------------------|--------------------------------------|
| **Topological metrics** |  |  |  |
| Total loop count | 300.3 ± 199.2 | 165.2 ± 118.0 | 89.5 ± 53.4 |
| Euler number (total) | −168.4 ± 146.0 | −135.0 ± 98.4 | −61.6 ± 48.2 |
| Junction density (mm⁻²) | 25.85 ± 1.77 | 21.99 ± 3.51 | 15.89 ± 2.88 |
| **Morphometric metrics** |  |  |  |
| Fractal dimension | 1.391 ± 0.081 | 1.378 ± 0.076 | 1.310 ± 0.110 |
| Mean vessel diameter (µm) | 16.0 ± 0.3 | 23.7 ± 2.0 | 32.3 ± 3.8 |
| **Caliber uniformity metrics (pre-standardization)** |  |  |  |
| Diameter CV (%) | 14.7 ± 6.8 | 16.8 ± 10.9 | 19.4 ± 10.3 |
| Diameter range / mean (%) | 50.4 ± 25.5 | 55.3 ± 35.1 | 65.9 ± 37.1 |

*Note.* Values are mean ± SD from the original submission tables. Protocols: Zeiss PlexElite 9000 6×6 mm (large); Zeiss CIRRUS HD / AngioPlex 3×3 mm (small_3mm); **Optovue Solix** 6×6 mm (small; corrected from the original “Heidelberg Solix” wording). Total loop count and Euler number include center and periphery zones. Pre-standardization Diameter CV and diameter range/mean are radial-profile features used in the **legacy** PCA Caliber Uniformity construct; the **default** Caliber Uniformity Score in this revision uses skeleton-derived NV Diameter CV and Dilated vessel % (Methods).

---

## Table 3. Standardized scores after stratum-locked normalization, by acquisition stratum (default Caliber Uniformity endpoint).

| Metric | Median (large / small / small_3mm) | H | p | ε² | 95% CI (ε²) |
|--------|-------------------------------------|---|---|-----|-------------|
| Network Complexity Score | 48.7 / 50.7 / 47.8 | 1.712 | 0.425 | 0.000 | 0.000–0.089 |
| Caliber Uniformity Score (default) | 46.6 / 55.5 / 50.6 | 1.118 | 0.572 | 0.000 | 0.000–0.082 |
| Maturity Index (from default Caliber) | 49.5 / 53.9 / 51.0 | 1.082 | 0.582 | 0.000 | 0.000–0.077 |

*Note.* ε² = (H − k + 1) / (n − k) with k = 3; bootstrap 95% CIs use 10 000 within-stratum resamples (seed `20260727`). Primary batch CSVs, n = 112 (large = 49, small = 33, small_3mm = 30). Network Complexity PC1 explained variance: 63.7% / 73.9% / 70.2% (large / small_3mm / small). The original submission Table 3 reported PCA-based Caliber Uniformity medians near 50 with Kruskal–Wallis p ≥ 0.276 and no effect sizes; those PCA Caliber/Maturity values are retained only as legacy sensitivity context (Results interpretation / Response Comment 5), not as the primary Table 3 endpoint. Median proximity to 50 after median-anchored piecewise scaling must not be interpreted as biological equivalence across devices.

---

## Table 4. Morphological subtype distribution by acquisition protocol.

| Morphological pattern | Large PlexElite 6×6 mm (n = 49) | Small_3mm HD series 3×3 mm (n = 30) | Small Optovue Solix 6×6 mm (n = 33) |
|-----------------------|----------------------------------|--------------------------------------|--------------------------------------|
| Glomerular | 29 (59.2%) | 9 (30.0%) | 12 (36.4%) |
| Medusa | 6 (12.2%) | 0 (0%) | 0 (0%) |
| Seafan | 0 (0%) | 11 (36.7%) | 2 (6.1%) |
| Tree in bud | 10 (20.4%) | 4 (13.3%) | 14 (42.4%) |
| Dead tree | 4 (8.2%) | 6 (20.0%) | 5 (15.2%) |

*Note.* Values are n (%) from the original submission tables. The original “Pathophysiological State” column has been removed (Reviewer 2 Comment 3); morphology-derived interpretive mapping is summarized separately in Table 5. Spelling standardized to **Tree in bud**. Device label for the small stratum is **Optovue Solix**.

---

## Table 5. Morphology-derived interpretive mapping for operational subtypes.

| Morphological pattern | Primary interpretive category | Secondary interpretive category | Key discriminating metrics |
|-----------------------|-------------------------------|---------------------------------|----------------------------|
| Medusa | Active-pattern | Transitional-pattern | Junction density, loop count, trunk distribution |
| Seafan | Active-pattern | Transitional-pattern | Peripheral arcade, trunk eccentricity |
| Glomerular | Active-pattern | — | High Complexity Score, low Caliber Uniformity Score |
| Tree in bud | Active-pattern | Transitional-pattern | High branching density, Euler number |
| Dead tree | Mature-quiescent-pattern | Arteriolarized-pattern | Mean diameter, Caliber Uniformity Score |

*Note.* Restored from original Table 5 with Reviewer 2 Comments 3 and 7b applied: “pathophysiological state” wording replaced by **morphology-derived interpretive categories**; “Pruned tree” and “Large vessels” rows removed (not part of the operational five-subtype scheme). Categories are hypothesis-generating and are **not** clinically validated disease-behavior classes.
