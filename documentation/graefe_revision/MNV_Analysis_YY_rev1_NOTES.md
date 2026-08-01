# MNV_Analysis_YY_rev1 — Author NOTES

Companion to `MNV_Analysis_YY_rev1.md` / `.docx`. Original files left untouched:
`MNV_Analysis_YY.docx`, `manuscript_text.txt`.

## Title chosen

**Chosen (rev1):**  
Novel Semi-Automated System for Multi-Dimensional Analysis of Macular Neovascularization: Quantitative Biomarkers and Rule-Based Morphological Categorization Across OCTA Platforms

**Rationale:** Response to Reviewers Comment 3 requires removing “pathophysiological classification” from the title/aim language. `REVISION_CHECKLIST.md` already suggested this morphology/rule-based wording. **Response letter header now matches** this chosen title (synced 2026-07-31).

**Rejected alternative:** keep “Morphological-Pathophysiological Classification” (inconsistent with Comment 3 “Changes made”).

## Figure numbering decision

| Number | Content | Asset |
|--------|---------|-------|
| **Figure 1** | Multi-device segmentation examples | `Figure.tiff` / `Figure.png` |
| **Figure 2** | Workflow schematic (R1 request) | `Figure2_workflow_schematic.*` |
| **Figure 3** | Processing-step panels | `figures/Figure3_processing_steps.*` |

**Letter vs assets:** Response R1 says the new workflow schematic is “Figure 2” (adopted). Checklist and disk assets also include Figure 3 processing steps; rev1 keeps **both** Fig 2 and Fig 3 so filenames and in-text citations stay consistent. If the journal prefers a single combined Methods figure, merge Fig 2+3 later and update cross-references.

### Figure 3 — rebuilt (2026-07-31 evening: Frangi / binary / skeleton)

**Response (R1) intent:** Fig 2 = end-to-end schematic (ROI → enhancement → Phansalkar → skeleton → scores). Fig 3 = representative **panel sequence** of the same pipeline on a real OCTA case (not another schematic).

**Current on-disk asset:** `figures/Figure3_processing_steps.png` / `.tiff` (+ `Figure3_processing_steps_caption.md`); also copied to `submission_package_20260731/figures/`. Four panels (A–D): (A) en-face OCTA with green freehand/refined ROI; (B) **continuous Frangi vesselness** (grayscale tubeness) within ROI; (C) hybrid / Phansalkar-path **binary** vessel map; (D) **1-pixel skeleton** (centerline). Prior LoG+color-viz layout superseded (B≈C redundancy).

**Source:** Same freehand furukawa case — ARIAKE report `…_b3039a78.pdf` / `output/mnv/ee595b46-6521-41fe-9c7e-72f466482d33` (CIRRUS 3×3 mm ORCC). A/C from saved ROI + `debug_binary_combined.png`; B regenerated with `skimage.filters.frangi` (pipeline `debug_tubeness.png` is post-Sauvola binary only); D = `skeletonize` of ROI-masked binary. Footer strip blanked; labels A–D only (no patient name/ID/DOB). Caption updated in rev1 / submission md.

## Key terminology (reader-facing)

| Term | Meaning in this revision |
|------|--------------------------|
| **Standardized Caliber Uniformity Score (default)** | Device-/stratum-locked `0.75·U(−NV Diameter CV) + 0.25·U(−Dilated vessel %)` with locked min/median/max → 0/50/100 |
| **PCA-based Caliber Uniformity Score (legacy)** | Prior PCA Stability composite; sensitivity / original-submission primary only |
| **Standardized Vascular Complexity Score** | Stratum-specific PCA of topological metrics |
| **Standardized Maturity Index** | `clip(50 + (Caliber − Complexity)/2, 0, 100)` using the **default** Caliber score in primary analyses |

Do **not** use the internal alias “U2” in manuscript or Response prose.

## Primary Caliber claims (updated 2026-08-01)

- **Primary Caliber Uniformity** = default device-locked score → inter ICC **0.770** (0.660–0.860)
- **Primary Maturity Index (inter)** = Maturity from default Caliber → ICC **0.593** (0.430–0.730)
- **Intra Caliber/Maturity** = same device-locked default (0.925 / 0.917); supplements multi-rater claim
- Alternate Winsorized / pooled-soft Caliber ICCs and legacy PCA Caliber are **not** reported in manuscript or Response (removed 2026-08-01 per author).

**Table 3 (default Caliber primary):** Caliber medians 46.6 / 55.5 / 50.6 (p = 0.572); Maturity 49.5 / 53.9 / 51.0 (p = 0.582); Complexity unchanged.

## Author decisions applied (2026-07-31 afternoon / evening)

1. **Table 1** — **Restored 2026-07-31 evening** from `MNV_analysis_tables_original.docx` (Category / Parameter / Description) with notation revised (Caliber Uniformity; morphology-derived categories; default vs legacy Caliber). Not a multi-tool literature matrix — original Table 1 was already a pipeline parameter inventory.
2. **Figure 3** — freehand furukawa case (`b3039a78` / `ee595b46`); **panels rebuilt 2026-07-31 evening** to A ROI / B Frangi / C binary / D skeleton (see section above).
3. **Table 4** — Restored from `MNV_analysis_tables_original.docx` with full Medusa/Seafan splits (large Medusa 6/12.2%, Seafan 0; small Medusa 0, Seafan 2/6.1%). Pathophysiological State column removed. Not from `grading/automated_labels.csv`.
4. **changes-marked / redline** — **Cancelled.** Do not create `_changes_marked` Word Track Changes. Working file = `MNV_Analysis_YY_rev1.docx`. Optional `MNV_Analysis_YY_rev1_clean.docx` may remain as a duplicate snapshot only.
5. **Submission zip** — **Not built** (user will zip if needed). `PHI_AUDIT_rev1.md` kept as reference; no `submission_safe/` mass anonymization.
6. **Corvi / Caliber naming (confirmed はい)** — Corvi cite year stays **2020** print as already cited; **no extra Corvi discussion** this round. Caliber naming stays as-is: **device-locked default** / **PCA legacy** / **no reader-facing “U2”**; no further rename.

## Packaging (2026-07-31) — match original separate tables/legends

Original: one `MNV_analysis_tables.docx` + manuscript cites Tables/Figures in prose; figure legend at end of MS text. Rev1: `MNV_Analysis_YY_rev1_tables.docx` (Tables 1–5), `MNV_Analysis_YY_rev1_figure_legends.docx` (Fig 1–3), manuscript body without embedded Table 1–5 grids or figure-legend section.

## Tables restore (2026-07-31 evening) — source `MNV_analysis_tables_original.docx`

| Table | Action |
|-------|--------|
| **1** | Restored 3-column inventory; Stability → Caliber Uniformity; pathophys → morphology-derived; default Caliber formula in description |
| **2** | Restored original mean±SD; Heidelberg → Optovue; “Caliber stability” → “Caliber uniformity (pre-standardization)” |
| **3** | Kept revision ε² table under **default** Caliber (not original PCA Caliber medians/p); titled; legacy note |
| **4** | Restored full % including Medusa/Seafan; removed Pathophysiological State column |
| **5** | Restored mapping for five subtypes only; Pruned tree / Large vessels removed; states → interpretive categories |

## Table 4 lock — resolved

**Source (locked):** `MNV_analysis_tables_original.docx` Table 4:

| Subtype | large (n=49) | small_3mm (n=30) | small (n=33) |
|---------|--------------|------------------|--------------|
| Glomerular | 29 (59.2%) | 9 (30.0%) | 12 (36.4%) |
| Medusa | 6 (12.2%) | 0 (0%) | 0 (0%) |
| Seafan | 0 (0%) | 11 (36.7%) | 2 (6.1%) |
| Tree in bud | 10 (20.4%) | 4 (13.3%) | 14 (42.4%) |
| Dead tree | 4 (8.2%) | 6 (20.0%) | 5 (15.2%) |

Sums: 49 / 30 / 33. Residual † gap closed. Batch `Subtype` columns still unused.

## Completed earlier (still valid)

1. Suppl Table S1 + expert agreement Suppl.
2. Response title synced; no reader-facing “U2”; default Caliber = device-locked.
3. Methods one-liner: small-stratum Complexity locking n = 34 vs Table 3 analysis batch n = 33.
4. PHI audit listing: `PHI_AUDIT_rev1.md`.

## Still open (minimal)

1. **Figure 3** — done (freehand case + Frangi/binary/skeleton rebuild 2026-07-31).
2. Optional: author visual check of regenerated `.docx` table formatting in Word.
