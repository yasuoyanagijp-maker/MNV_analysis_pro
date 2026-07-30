# ICC(2,1) — all numeric batch-CSV parameters (n=46, k=3)

**Date:** 2026-07-31  
**Observers:** YY / Inoue / Osada · matched `File` intersection **n = 46**  
**Model:** ICC(2,1) absolute agreement (Shrout & Fleiss / McGraw & Wong)  
**Script:** `compute_caliber_major_params_new_score.py`

## Scope

All mostly-numeric morphological / vessel / caliber-related (and other) columns
exported in the ImageJ-compatible batch CSVs. Meta/ID/FD-region QC flag columns excluded.

**Total metrics ranked:** 46  
**Caliber-/diameter-/dilated-/arteriolarization-tagged:** 11

## Top 20 by ICC(2,1)

| Rank | Metric | ICC(2,1) | 95% CI | Family |
|------|--------|----------|--------|--------|
| 1 | Branch Density (n/mm) | 0.911 | 0.850–0.950 | morphometry/topology |
| 2 | Junction Density (n/mm) | 0.911 | 0.850–0.950 | morphometry/topology |
| 3 | Multi-Branch Pts Density (n/mm) | 0.905 | 0.850–0.940 | morphometry/topology |
| 4 | Arteriolarization Connectivity Index (mm/segment) | 0.896 | 0.840–0.940 | caliber/diameter |
| 5 | Vsl Length (mm) | 0.882 | 0.760–0.940 | morphometry/topology |
| 6 | Raw Vsl Length | 0.878 | 0.750–0.940 | morphometry/topology |
| 7 | Arteriolarization Max Segment Length (mm) | 0.870 | 0.800–0.920 | caliber/diameter |
| 8 | Vsl Area (mm2) | 0.868 | 0.740–0.930 | morphometry/topology |
| 9 | MNV Area adjusted by signal intensity (aMNV) | 0.866 | 0.720–0.930 | morphometry/topology |
| 10 | MNV Area (mm2) | 0.859 | 0.680–0.930 | morphometry/topology |
| 11 | ROI coverage (%) | 0.859 | 0.680–0.930 | morphometry/topology |
| 12 | End Pts | 0.855 | 0.700–0.930 | morphometry/topology |
| 13 | Periphery Total Length (mm) | 0.825 | 0.630–0.910 | morphometry/topology |
| 14 | Triple Pts | 0.824 | 0.670–0.910 | morphometry/topology |
| 15 | Vsl Junctions | 0.815 | 0.660–0.900 | morphometry/topology |
| 16 | Vsl Branches | 0.813 | 0.650–0.900 | morphometry/topology |
| 17 | Network Complexity Score | 0.807 | 0.660–0.890 | score/composite |
| 18 | Arteriolarization Segment Count | 0.802 | 0.660–0.890 | caliber/diameter |
| 19 | Arteriolarization Total Length (mm) | 0.800 | 0.660–0.890 | caliber/diameter |
| 20 | End Pts Density (n/mm) | 0.796 | 0.690–0.870 | morphometry/topology |

## Caliber / diameter / uniformity–related raw params (ranked)

| Rank (global) | Metric | ICC(2,1) | 95% CI | High/Low |
|---------------|--------|----------|--------|----------|
| 4 | Arteriolarization Connectivity Index (mm/segment) | 0.896 | 0.840–0.940 | **HIGH (≥0.70)** |
| 7 | Arteriolarization Max Segment Length (mm) | 0.870 | 0.800–0.920 | **HIGH (≥0.70)** |
| 18 | Arteriolarization Segment Count | 0.802 | 0.660–0.890 | **HIGH (≥0.70)** |
| 19 | Arteriolarization Total Length (mm) | 0.800 | 0.660–0.890 | **HIGH (≥0.70)** |
| 25 | (Skel) Vsl Diameter | 0.760 | 0.610–0.860 | **HIGH (≥0.70)** |
| 34 | Arteriolarization Density (/mm²) | 0.558 | 0.310–0.730 | **MODERATE (0.50–0.70)** |
| 36 | Dilated vessel (%) | 0.522 | 0.320–0.690 | **MODERATE (0.50–0.70)** |
| 43 | Caliber Uniformity Score | 0.434 | 0.260–0.610 | **LOW (<0.50)** |
| 44 | Raw Vsl Diameter | 0.385 | 0.180–0.580 | **LOW (<0.50)** |
| 45 | NV Diameter (CV) | 0.259 | 0.080–0.450 | **LOW (<0.50)** |
| 46 | Local Diameter Variation (max CV%) | 0.138 | -0.020–0.330 | **LOW (<0.50)** |

### Highlight — high vs low among caliber family

**High / good–excellent ICC:** mean skeleton diameter `(Skel) Vsl Diameter`, arteriolarization counts/lengths (topology of thick vessels), and related densities when vessel-count based.

**Low / fragile ICC:** dispersion / variability features — especially `NV Diameter (CV)`, `Local Diameter Variation (max CV%)`, and the composite `Caliber Uniformity Score` (10-bin Stability PCA). `Raw Vsl Diameter` is only fair.

**Implication:** Reproducible information lives in **mean caliber level** and **thick-vessel topology counts**, not in raw CV / local max-CV / radial Stability composites — unless CV is robustly transformed (see new-score note).

## Full ranked table

| Rank | Metric | ICC(2,1) | 95% CI | Caliber-related | Family |
|------|--------|----------|--------|-----------------|--------|
| 1 | Branch Density (n/mm) | 0.911 | 0.850–0.950 |  | morphometry/topology |
| 2 | Junction Density (n/mm) | 0.911 | 0.850–0.950 |  | morphometry/topology |
| 3 | Multi-Branch Pts Density (n/mm) | 0.905 | 0.850–0.940 |  | morphometry/topology |
| 4 | Arteriolarization Connectivity Index (mm/segment) | 0.896 | 0.840–0.940 | Y | caliber/diameter |
| 5 | Vsl Length (mm) | 0.882 | 0.760–0.940 |  | morphometry/topology |
| 6 | Raw Vsl Length | 0.878 | 0.750–0.940 |  | morphometry/topology |
| 7 | Arteriolarization Max Segment Length (mm) | 0.870 | 0.800–0.920 | Y | caliber/diameter |
| 8 | Vsl Area (mm2) | 0.868 | 0.740–0.930 |  | morphometry/topology |
| 9 | MNV Area adjusted by signal intensity (aMNV) | 0.866 | 0.720–0.930 |  | morphometry/topology |
| 10 | MNV Area (mm2) | 0.859 | 0.680–0.930 |  | morphometry/topology |
| 11 | ROI coverage (%) | 0.859 | 0.680–0.930 |  | morphometry/topology |
| 12 | End Pts | 0.855 | 0.700–0.930 |  | morphometry/topology |
| 13 | Periphery Total Length (mm) | 0.825 | 0.630–0.910 |  | morphometry/topology |
| 14 | Triple Pts | 0.824 | 0.670–0.910 |  | morphometry/topology |
| 15 | Vsl Junctions | 0.815 | 0.660–0.900 |  | morphometry/topology |
| 16 | Vsl Branches | 0.813 | 0.650–0.900 |  | morphometry/topology |
| 17 | Network Complexity Score | 0.807 | 0.660–0.890 |  | score/composite |
| 18 | Arteriolarization Segment Count | 0.802 | 0.660–0.890 | Y | caliber/diameter |
| 19 | Arteriolarization Total Length (mm) | 0.800 | 0.660–0.890 | Y | caliber/diameter |
| 20 | End Pts Density (n/mm) | 0.796 | 0.690–0.870 |  | morphometry/topology |
| 21 | Periphery Loop Number | 0.781 | 0.590–0.880 |  | morphometry/topology |
| 22 | Periphery Branches | 0.778 | 0.570–0.880 |  | morphometry/topology |
| 23 | Quadruple Pts | 0.766 | 0.610–0.860 |  | morphometry/topology |
| 24 | Periphery Euler Number | 0.761 | 0.570–0.870 |  | morphometry/topology |
| 25 | (Skel) Vsl Diameter | 0.760 | 0.610–0.860 | Y | caliber/diameter |
| 26 | Fractal Dim | 0.671 | 0.480–0.800 |  | morphometry/topology |
| 27 | Periphery Tortuosity | 0.663 | 0.520–0.780 |  | morphometry/topology |
| 28 | MNV mean gray intensity (AU) | 0.660 | 0.260–0.840 |  | morphometry/topology |
| 29 | Maturity Index | 0.659 | 0.510–0.780 |  | score/composite |
| 30 | Tortuosity | 0.643 | 0.490–0.770 |  | morphometry/topology |
| 31 | Center FD (Box-Counting) | 0.639 | 0.490–0.760 |  | morphometry/topology |
| 32 | Center Total Length (mm) | 0.584 | 0.320–0.760 |  | morphometry/topology |
| 33 | Vessel density index adjusted by signal intensity (aVDI) | 0.574 | 0.180–0.790 |  | morphometry/topology |
| 34 | Arteriolarization Density (/mm²) | 0.558 | 0.310–0.730 | Y | caliber/diameter |
| 35 | Center Tortuosity | 0.540 | 0.370–0.690 |  | morphometry/topology |
| 36 | Dilated vessel (%) | 0.522 | 0.320–0.690 | Y | caliber/diameter |
| 37 | Vsl Density (Vessel Area/MNV (%)) | 0.520 | 0.130–0.750 |  | morphometry/topology |
| 38 | Center Branches | 0.494 | 0.230–0.690 |  | morphometry/topology |
| 39 | MNV intensity Variation (CV) | 0.488 | 0.110–0.730 |  | morphometry/topology |
| 40 | Periphery FD (Box-Counting) | 0.473 | 0.220–0.670 |  | morphometry/topology |
| 41 | Center Euler Number | 0.472 | 0.240–0.660 |  | morphometry/topology |
| 42 | Center Loop Number | 0.467 | 0.200–0.670 |  | morphometry/topology |
| 43 | Caliber Uniformity Score | 0.434 | 0.260–0.610 | Y | caliber/diameter |
| 44 | Raw Vsl Diameter | 0.385 | 0.180–0.580 | Y | caliber/diameter |
| 45 | NV Diameter (CV) | 0.259 | 0.080–0.450 | Y | caliber/diameter |
| 46 | Local Diameter Variation (max CV%) | 0.138 | -0.020–0.330 | Y | caliber/diameter |

## Output files

- `icc_all_numeric_params_n46.csv`
- `icc_all_numeric_params_n46.md` (this file)
