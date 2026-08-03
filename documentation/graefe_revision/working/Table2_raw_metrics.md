# Table 2 — Raw topological and morphometric parameters by acquisition protocol

Mean ± SD, n = 112 (large = 49, small_3mm = 30, small = 33). Total loop count and Euler number = Center + Periphery components. Device label for small = **Optovue Solix**.

Topological / morphometric rows (loop count through mean vessel diameter) remain from the **original submission tables** (`MNV_analysis_tables_original.docx`). Caliber uniformity rows were **replaced** (2026-08-01) with skeleton-derived inputs to the default Caliber Uniformity Score, recomputed from primary analysis batch CSVs under `documentation/graefe_revision/data/`.

| Parameter | Large PlexElite 6×6 mm (n = 49) | Small_3mm HD series 3×3 mm (n = 30) | Small Optovue Solix 6×6 mm (n = 33) |
|-----------|----------------------------------|--------------------------------------|--------------------------------------|
| Total loop count | 300.3 ± 199.2 | 165.2 ± 118.0 | 89.5 ± 53.4 |
| Euler number (total) | −168.4 ± 146.0 | −135.0 ± 98.4 | −61.6 ± 48.2 |
| Junction density (mm⁻²) | 25.85 ± 1.77 | 21.99 ± 3.51 | 15.89 ± 2.88 |
| Fractal dimension | 1.391 ± 0.081 | 1.378 ± 0.076 | 1.310 ± 0.110 |
| Mean vessel diameter (µm) | 16.0 ± 0.3 | 23.7 ± 2.0 | 32.3 ± 3.8 |
| NV Diameter CV (%) | 38.5 ± 1.1 | 51.0 ± 9.0 | 41.7 ± 2.5 |
| Dilated vessel (%) | 13.3 ± 2.5 | 8.9 ± 2.0 | 8.3 ± 3.2 |

**Source (caliber rows).** Columns `NV Diameter (CV)` and `Dilated vessel (%)` in:
- `MNV_batch_20260220_230245_large.csv` (n = 49)
- `MNV_batch_20260220_223647_small_3mm.csv` (n = 30)
- `MNV_batch_20260220_083448small.csv` (n = 33)

`NV Diameter (CV)` is already stored as percent. `Dilated vessel (%)` is stored as a fraction (0–1) and multiplied by 100 for the table. These two features are the inputs to the default Caliber Uniformity Score (Methods). Legacy radial-profile Diameter CV / diameter range/mean (14.7 ± 6.8 etc.) were removed from Table 2.
