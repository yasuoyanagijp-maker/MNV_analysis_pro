# MNV_Analysis_YY_rev1 — CHANGELOG (mapped to Response)

Compares `MNV_Analysis_YY_rev1.md` to original `manuscript_text.txt` / `MNV_Analysis_YY.docx`.  
Sources for numbers: `Response_to_Reviewers.md`, `icc/icc_multirater_results.md`, `icc/icc_intra_YY_results.md`, `icc/caliber_u2_device_std_icc_results.md`, `grading/agreement_stats.md`, `stats/table3_effect_sizes.md`, `src/core/caliber_u2.py`, `resources/reference_metrics/caliber_u2_device_ref.json`.

| Reviewer / Editor item | Claimed in Response | Implemented in rev1? | Where in rev1 |
|------------------------|---------------------|----------------------|---------------|
| **Editor 1** Key Messages | What is known / What is new on Title Page | **Yes** | Key Messages (after affiliations) |
| **Editor 2** Accurate reporting / limitations | Soften overclaims; expand Limitations | **Yes** | Abstract, Results, Discussion, Limitations, Conclusion |
| **R1** Workflow figure | New schematic = Figure 2 | **Yes** | Methods + Figure 2 legend; Fig 3 also kept (see NOTES) |
| **R1** Phansalkar vs Otsu | Expanded Methods justification | **Yes** | Methods → Binarization subsection |
| **R2#1** Circularity of median≈50 | Rewrite; not biological equivalence | **Yes** | Abstract, Results (retitled section), Discussion |
| **R2#1** Drop “device-independent” / “statistically indistinguishable” | Removed | **Yes** | Throughout; aim → stratum-standardized reporting |
| **R2#2** Expert agreement κ | n=54; 57.4%; κ=0.507; merge sensitivity | **Yes** | Methods + Results; Suppl confusion matrix noted |
| **R2#2** Disclose thresholds | Methods / Suppl Table S1 | **Yes** | Rule table in Methods; Suppl Table S1 (`Supplementary_Table_S1.md`) with P10/P30/P40/P65 + Caliber locked cuts |
| **R2#2** Soften “validated classification” | → rule-based + agreement | **Yes** | Abstract, Methods, Results, Conclusion |
| **R2#3** Pathophysiological → morphology-derived | Throughout + title | **Yes** | Title + interpretive category naming |
| **R2#3** Soften clinical decision-making | Softened | **Yes** | Abstract Conclusion, Discussion, Conclusion |
| **R2#4** Inter-observer ICC n=46 | Area/Complexity/Caliber/Maturity | **Yes** | Methods + Results: **primary Caliber = Standardized Caliber Uniformity Score 0.770**; Maturity **0.593**; PCA Caliber 0.434 = legacy sensitivity |
| **R2#4** Caliber naming / framing | Default = device-locked score; no “U2” in prose | **Yes — 2026-07-31 terminology pass** | Manuscript + Response Comment 4/1/5 aligned; Response DRAFT synced |
| **R2#4** Intra YY n=46 | 0.925 / 0.917; same device-locked definition | **Yes** | Methods + Results |
| **R2#5** ε² for Table 3 KW | Default Caliber: all three NS | **Yes** | Table 3 default Caliber/Maturity (ε²≈0). Response Comment 5 updated to match |
| **R2#6** Baseline covariates unavailable | Methods + Limitations | **Yes** | Study Population; Limitations item 3 |
| **R2#7a** Terminology unify | Complexity / Caliber Uniformity / Maturity | **Yes** | Abstract onward; Stability only as synonym note |
| **R2#7b** Remove Pruned tree / Large vessels | Align Table 4/5 | **Yes** | **Table 5** restored without those rows; Methods + Discussion aligned |
| **R2#7c** Duplicate Tew refs | Deduplicate | **Yes** | Single Tew [8]; former #22 removed |
| **R2#7d** Heidelberg Solix → Optovue | Correct manufacturer | **Yes** | **Table 2** legend/headers + Methods + Figure 1 (Optovue Solix) |

## 2026-07-31 evening — Separate tables/legends packaging (original convention)

Original submission used a single tables Word file (`MNV_analysis_tables.docx`) and manuscript text that cites Tables/Figures without embedding grids. Rev1 now matches: `MNV_Analysis_YY_rev1_tables.md`/`.docx` (Tables 1–5), `MNV_Analysis_YY_rev1_figure_legends.md`/`.docx` (Fig 1–3); manuscript body cites only; synced to `submission_package_20260731/`.

## 2026-07-31 evening — Tables restored from `MNV_analysis_tables_original.docx`

Source: `documentation/graefe_revision/MNV_analysis_tables_original.docx` (local copy of original submission tables).

| Table | Rev1 body change |
|-------|------------------|
| **1** | Full Category/Parameter/Description inventory restored (replaced 2-col placeholder). Notation: Stability→Caliber Uniformity; pathophys→morphology-derived; default vs legacy Caliber described. |
| **2** | Original mean±SD restored (300.3… etc.); Optovue Solix; “Caliber uniformity metrics (pre-standardization)”. Results prose updated to match. |
| **3** | Revision primary = default Caliber + ε² columns (not original PCA Caliber medians). Titled; legacy note. |
| **4** | Full Medusa/Seafan splits restored (6/0/0 and 0/11/2); Pathophysiological State column removed; † residual closed. |
| **5** | Restored for five operational subtypes only; interpretive-category columns; Pruned tree / Large vessels removed. |

Response Comments 1/2/3/5/7 and Editor 2 updated with explicit “which table / what rewritten” bullets. Files: `MNV_Analysis_YY_rev1.md`/`.docx`, `Response_to_Reviewers.md`/`.docx` (+ DRAFT), `submission_package_20260731/` copies, `Table2_raw_metrics.md`, NOTES.

## 2026-07-31 — Terminology: no “U2” in reader-facing prose

**Canonical public name:** **Standardized Caliber Uniformity Score** (= default / primary).  
**Legacy contrast name:** **PCA-based Caliber Uniformity Score (legacy)**.  
**Internal alias (code/JSON only):** `caliber_u2` / `caliber_u2_device_ref.json` — not used in manuscript or Response letter body.

**What changed**
- Removed all reader-facing “U2” / “harmonized U2” / “device-locked U2” / “Caliber U2” from `MNV_Analysis_YY_rev1.md`, `Response_to_Reviewers.md`, and synced `Response_to_Reviewers_DRAFT.md`.
- Framing: default = device-locked NV-CV + Dilated% weighted score; PCA = sensitivity/legacy only.
- Intra: “same device-locked definition applied to both sessions.”
- Regenerated `MNV_Analysis_YY_rev1.docx` via pandoc.

## 2026-07-31 — Caliber Uniformity Methods → device-locked default (formula)

**What changed**
- Methods “Standardized Caliber Uniformity Score” rewritten from PCA Stability composite (0.7×(−PC1)+0.2×PC2+0.1×50) to device-/stratum-locked: `0.75·piecewise(−NV_CV) + 0.25·piecewise(−Dilated%)` with locked min/median/max cuts (`caliber_u2_device_ref.json`; internal name only).
- ICC Methods/Results: primary inter Caliber = **0.770** (0.660–0.860); Maturity = **0.593** (0.430–0.730); PCA Caliber **0.434** = legacy sensitivity.
- Abstract, Table 3, Discussion, Limitations item 4 realigned (Table 3 KW from manuscript reference batch CSVs + locked ref).

**Table 3 (default Caliber; n=112)**

| Metric | Medians (L / S / S3) | H | p | ε² (95% CI) |
|--------|----------------------|---|---|-------------|
| Complexity (unchanged PCA) | 48.7 / 50.7 / 47.8 | 1.712 | 0.425 | 0.000 (0.000–0.089) |
| Caliber Uniformity Score | 46.6 / 55.5 / 50.6 | 1.118 | 0.572 | 0.000 (0.000–0.082) |
| Maturity Index | 49.5 / 53.9 / 51.0 | 1.082 | 0.582 | 0.000 (0.000–0.077) |

Original `MNV_Analysis_YY.docx` was **not** overwritten.

## 2026-07-31 — Inter-observer Methods clarity + ICC citations [32–34]

- Inter-observer Methods use shorter sentences; default-Caliber-primary framing.
- Numbered refs: Shrout & Fleiss 1979 [32], McGraw & Wong 1996 [33], Koo & Li 2016 [34] (Crossref-verified; not in local Zotero sqlite; Zotero desktop API unavailable).
- [34] cited where Results/Limitations use conventional ICC bands.

## 2026-07-31 — Package sync (Suppl S1, Tables 1–2, Response, docx)

**Completed**
- `Supplementary_Table_S1.md` / `.docx` — Complexity percentiles (P30 interpolated), extended percentiles, default Caliber locked NV-CV / Dilated% cuts; small-stratum n=34 (ref) vs n=33 (analysis) disclosed.
- `Supplementary_expert_agreement.md` / `.docx` — κ + confusion matrix (n=54).
- **Table 1** embedded as pipeline metric inventory; original literature-comparison matrix **not recoverable** from OOXML (gap disclosed in table note).
- **Table 2** embedded from primary batch CSVs (mean±SD); narrative updated to match recomputed values (loops/Euler/junction/diameter differ slightly from original prose).
- Response: title = chosen rev1 title; Comment 4/5 = default Caliber primary + legacy PCA sensitivity; **poor-to-moderate** for PCA ICC 0.434; no `icc/` repo paths; no reader-facing “U2”; DRAFT synced.
- Regenerated `MNV_Analysis_YY_rev1.docx`, `Response_to_Reviewers.docx` (+ DRAFT), Suppl docx via pandoc.

## 2026-07-31 — Author decisions 1–6 applied

| Decision | Action |
|----------|--------|
| **1. Table 1** | **Deferred** — no resubmission/rework this round; keep pipeline-inventory Table 1 |
| **2. Figure 3** | **Replaced 2026-07-31** — freehand furukawa case `b3039a78` / `ee595b46` (see below); prior auto-ROI draft superseded |
| **3. Table 4** | **Locked** to original submission narrative % (`MNV_Analysis_YY.docx` / `manuscript_text.txt`); automated_labels refresh **reverted**; no computer-assigned labeling clutter; clinical subtype names only |
| **4. changes-marked** | **Superseded 2026-08-01** — journal File 2 created via Word Compare (see below); prior Cancelled decision withdrawn |
| **5. zip** | **Not built** — user will zip if needed; PHI audit kept as reference; no `submission_safe/` mass anonymization |
| **6. Corvi / Caliber** | **Confirmed** — Corvi year **2020** as cited, no extra prose; Caliber naming unchanged (device-locked default / PCA legacy / no “U2”) |

**Table 4 locked numbers (source: original Results narrative)**

| Subtype | large (n=49) | small_3mm (n=30) | small (n=33) |
|---------|--------------|------------------|--------------|
| Glomerular | 29 (59.2%) | 9 (30.0%) | 12 (36.4%) |
| Seafan | residual w/ Medusa | 11 (36.7%) | residual w/ Medusa |
| Tree in bud | 10 (20.4%) | 4 (13.3%) | 14 (42.4%) |
| Dead tree | 4 (8.2%) | 6 (20.0%) | 5 (15.2%) |
| Medusa | residual w/ Seafan | 0 (0%) | residual w/ Seafan |

Residuals: large Medusa+Seafan = 6 (12.2%); small = 2 (6.1%). Split within residual **not** stated in original prose (footnote † in rev1). Batch `Subtype` / `automated_labels.csv` counts were **not** used.

## 2026-07-31 — Safe-only pass (dialog-gated ambiguous items)

**Done without author-proxy**
- Methods: one sentence on small-stratum Complexity ref **n = 34** vs analysis batch **n = 33** (aligned with Suppl S1).
- PHI audit report: `PHI_AUDIT_rev1.md` (findings + remediation plan; `submission_safe/` deferred — zip not built per decision 5).
- Consistency re-check: reader-facing rev1 / Response / Suppl / Table2 — **zero** “U2”; title header matches rev1; default Caliber = device-locked formula; PCA = legacy.

**Superseded by later author action:** Table 1 restore deferred; **Fig 3 replaced 2026-07-31** (freehand); Table 4 lock / changes-marked / zip anonymization as above.

## 2026-07-31 — Figure 3 replaced (freehand ROI case)

**What changed**
- Rebuilt `figures/Figure3_processing_steps.png` / `.tiff` from freehand-ROI analysis matching ARIAKE report `…_b3039a78.pdf` (timestamp 2026-07-31 13:13) → `output/mnv/ee595b46-6521-41fe-9c7e-72f466482d33` (CIRRUS 3×3 mm ORCC en-face).
- Initial panels: ROI → LoG/mex-hat → binary → color viz. No patient name/ID/DOB on figure.
- Copied into `submission_package_20260731/figures/`.
- Working extract under `figures/_fig3_rebuild_furukawa/`; run archive `figures/_fig3_runs/ee595b46-furukawa-20260731`.

**Gap:** Report PDF page 2 embeds color viz + ROI mask only; enhancement/binary panels taken from matched `output/mnv` debug PNGs (not embedded in PDF).

## 2026-07-31 evening — Figure 3 panels → Frangi / binary / skeleton

**What changed**
- Same furukawa case (`b3039a78` / `ee595b46`). Rebuilt montage so B≠C: **(A)** ROI, **(B)** continuous Frangi grayscale, **(C)** binary vessel map, **(D)** 1-px skeleton.
- B: regenerated with `skimage.filters.frangi` (pipeline `debug_tubeness.png` is Sauvola-binarized only — not usable for continuous display). D: `skeletonize` of ROI-masked `debug_binary_combined.png` (not exported by default). Footer metadata blanked.
- Updated `Figure3_processing_steps_caption.md`, Figure 3 caption + Results cross-ref in `MNV_Analysis_YY_rev1.md` and submission-package md. Copied png/tiff to `submission_package_20260731/figures/`.
- **Limitation:** Panel D is raw skeletonize of the analysis binary, not the boundary-trimmed `refined_skeleton` used for scores. Panel C label follows Methods (Phansalkar); displayed map is the hybrid vessel binary from the matched run.
- NOTES + this CHANGELOG; docx caption sync may still be needed if Word is regenerated from md.

## Notable numeric replacements vs original manuscript

| Topic | Original claim | Rev1 (source) |
|-------|----------------|---------------|
| Table 3 KW (legacy PCA era) | All p≥0.276; medians≈50 = equivalence | Was Complexity NS; PCA Caliber/Maturity sig ε²≈0.24 |
| Table 3 (current default Caliber) | — | All three scores NS; Caliber medians 46.6/55.5/50.6 |
| Classification accuracy | None | κ / % agreement from `grading/agreement_stats.md` |
| Reproducibility (current) | None | Primary Caliber ICC **0.770**; Maturity **0.593**; legacy PCA Caliber **0.434** |
| Table 4 subtype % | Original narrative counts | **Locked back** to original narrative (not automated_labels) |

## Files produced

- `documentation/graefe_revision/MNV_Analysis_YY_rev1.md` — primary editable rev1
- `documentation/graefe_revision/MNV_Analysis_YY_rev1.docx` — pandoc export (= journal File 3 clean)
- `documentation/graefe_revision/MNV_Analysis_YY_rev1_manuscript_changes_marked.docx` — journal File 2 (Word Compare redline)
- `documentation/graefe_revision/MNV_Analysis_YY_rev1_NOTES.md` — decisions / remaining TODOs
- `documentation/graefe_revision/MNV_Analysis_YY_rev1_CHANGELOG.md` — this file
- `documentation/graefe_revision/Supplementary_Table_S1.md` / `.docx`
- `documentation/graefe_revision/Supplementary_expert_agreement.md` / `.docx`
- `documentation/graefe_revision/Table2_raw_metrics.md` — standalone Table 2 source mirror
- `documentation/graefe_revision/Response_to_Reviewers.md` / `.docx` (+ DRAFT copies)

**Not overwritten:** `MNV_Analysis_YY.docx`, `manuscript_text.txt` (now under `original_submission/`).

## 2026-08-01 — Journal File 2 (changes-marked) created

- Method: Microsoft Word **Compare** (AppleScript `compare` → `compare target new`), author `rev1`
- Original: `original_submission/MNV_Analysis_YY.docx`
- Revised (clean): `MNV_Analysis_YY_rev1.docx`
- Output: `MNV_Analysis_YY_rev1_manuscript_changes_marked.docx` (+ copy in `submission_package_20260731/`)
- Verified OOXML markup: ~470 `w:ins`, ~373 `w:del` (real track changes, not fake highlighting)
- Packaging map updated in `submission_package_20260731/README_提出内容.txt` (File 1/2/3)

## Remaining “U2” (internal only; not manuscript)

Analysis notes / scripts / CSVs under `documentation/graefe_revision/icc/` and `src/core/caliber_u2.py` still use the internal codename. Optional cleanup for submission packet clarity; not required for reader-facing prose.
