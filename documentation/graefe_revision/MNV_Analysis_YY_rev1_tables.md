# Tables — MNV Analysis

The manuscript body cites Tables 1–5 in text only; grids are provided in this separate tables file.

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
| Caliber Uniformity | Standardized Caliber Uniformity Score (0–100) | **Default:** device-/stratum-locked 0.75 × U(−NV Diameter CV) + 0.25 × U(−Dilated vessel %). **Legacy (sensitivity):** PCA of four radial-profile metrics. |
|  | Diameter CV / Dilated vessel % | Skeleton-derived NV Diameter CV and fraction of vessel length exceeding mean + 2.0 × SD (inputs to the default Caliber score). |
| Advanced | Intelligent ROI Refinement | 5-iteration vertex optimization (3-pixel search radius) to align the ROI boundary with non-perfused tissue. |
|  | Arteriolarization Detection | Branches with local diameter > mean + 2.0 × SD; reports count, length, and area density. |
|  | Rule-based morphological categorization | Five-class subtype labels (Medusa, Seafan, Glomerular, Tree in bud, Dead tree) plus separate morphology-derived interpretive categories (hypothesis-generating). |
| Multi-device | Stratum-locked score normalization | Within-stratum standardization / locked piecewise maps place scores on a common 0–100 **reporting** scale (not biological equivalence across devices). |
|  | Field-of-View Correction | Physical unit conversion using device-specific scaling across 3×3 mm and 6×6 mm scans. |
|  | Standardized Maturity Index (0–100) | clip(50 + (Caliber Uniformity Score − Complexity Score) / 2, 0, 100). Values > 50 indicate uniformity-dominant morphology; < 50 complexity-dominant. |

*Note.* Default Caliber Uniformity uses skeleton-derived NV Diameter CV and Dilated vessel %; a PCA-based Caliber Uniformity construct is retained only as a sensitivity comparison. Kruskal–Wallis non-significance of standardized scores must not be interpreted as cross-device biological equivalence.

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

*Note.* Values are mean ± SD. Protocols: Zeiss PlexElite 9000 6×6 mm (large); Zeiss CIRRUS HD / AngioPlex 3×3 mm (small_3mm); Optovue Solix 6×6 mm (small). Total loop count and Euler number include center and periphery zones. Pre-standardization Diameter CV and diameter range/mean are radial-profile features used in the **legacy** PCA Caliber Uniformity construct; the **default** Caliber Uniformity Score uses skeleton-derived NV Diameter CV and Dilated vessel % (Methods).

---

## Table 3. Standardized scores after stratum-locked normalization, by acquisition stratum (default Caliber Uniformity endpoint).

| Metric | Median (large / small / small_3mm) | H | p | ε² | 95% CI (ε²) |
|--------|-------------------------------------|---|---|-----|-------------|
| Network Complexity Score | 48.7 / 50.7 / 47.8 | 1.712 | 0.425 | 0.000 | 0.000–0.089 |
| Caliber Uniformity Score (default) | 46.6 / 55.5 / 50.6 | 1.118 | 0.572 | 0.000 | 0.000–0.082 |
| Maturity Index (from default Caliber) | 49.5 / 53.9 / 51.0 | 1.082 | 0.582 | 0.000 | 0.000–0.077 |

*Note.* ε² = (H − k + 1) / (n − k) with k = 3; bootstrap 95% CIs use 10 000 within-stratum resamples (seed 20260727). Primary analysis set, n = 112 (large = 49, small = 33, small_3mm = 30). Network Complexity PC1 explained variance: 63.7% / 73.9% / 70.2% (large / small_3mm / small). PCA-based Caliber/Maturity values are retained only as legacy sensitivity context in the Results and are not the primary Table 3 endpoint. Median proximity to 50 after median-anchored piecewise scaling must not be interpreted as biological equivalence across devices.

---

## Table 4. Morphological subtype distribution by acquisition protocol.

| Morphological pattern | Large PlexElite 6×6 mm (n = 49) | Small_3mm HD series 3×3 mm (n = 30) | Small Optovue Solix 6×6 mm (n = 33) |
|-----------------------|----------------------------------|--------------------------------------|--------------------------------------|
| Glomerular | 29 (59.2%) | 9 (30.0%) | 12 (36.4%) |
| Medusa | 6 (12.2%) | 0 (0%) | 0 (0%) |
| Seafan | 0 (0%) | 11 (36.7%) | 2 (6.1%) |
| Tree in bud | 10 (20.4%) | 4 (13.3%) | 14 (42.4%) |
| Dead tree | 4 (8.2%) | 6 (20.0%) | 5 (15.2%) |

*Note.* Values are n (%). Morphology-derived interpretive mapping is summarized separately in Table 5. Spelling is standardized to **Tree in bud**. Device label for the small stratum is **Optovue Solix**.

---

## Table 5. Morphology-derived interpretive mapping for operational subtypes.

| Morphological pattern | Primary interpretive category | Secondary interpretive category | Key discriminating metrics |
|-----------------------|-------------------------------|---------------------------------|----------------------------|
| Medusa | Active-pattern | Transitional-pattern | Junction density, loop count, trunk distribution |
| Seafan | Active-pattern | Transitional-pattern | Peripheral arcade, trunk eccentricity |
| Glomerular | Active-pattern | — | High Complexity Score, low Caliber Uniformity Score |
| Tree in bud | Active-pattern | Transitional-pattern | High branching density, Euler number |
| Dead tree | Mature-quiescent-pattern | Arteriolarized-pattern | Mean diameter, Caliber Uniformity Score |

*Note.* Categories are **morphology-derived interpretive categories** (hypothesis-generating) and are **not** clinically validated disease-behavior classes. Only the five operational subtypes are shown; labels outside this scheme (e.g., “Pruned tree,” “Large vessels”) are omitted.
