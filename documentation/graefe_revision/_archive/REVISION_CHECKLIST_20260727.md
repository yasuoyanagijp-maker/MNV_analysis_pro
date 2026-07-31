# Graefe Major Revision — Work Checklist (ARCHIVED 2026-07-31)

> **Superseded.** Use `documentation/graefe_revision/README.md` for current status.  
> This file is a 2026-07-27 WIP snapshot: intra was still “optional/not done,” primary Caliber ICC table still reflected the PCA-era numbers, and many manuscript TODOs were open. Kept for history only.

> **Do not push this branch to remote.**  
> Branch `graefe/major-revision-analyses` and all work under `documentation/graefe_revision/` stay **local only**. Never `git push` unless the user explicitly asks.

Submission ID: `d8450736-638d-47c9-991d-90d98396c381`  
Deadline: **24 Aug 2026**  
Branch: `graefe/major-revision-analyses` (from `docs/distribution-recipient-ops-20260714`) — **local only; do not push**

## Confirmed decisions (2026-07-27)

| Item | Decision |
|------|----------|
| ICC (primary) | **Multi-rater / multilevel ICC**: **3 observers** (YY + Inoue + Osada); **n = 46**; ICC(2,1) primary — **DONE** |
| ICC data | Incoming CSVs under `icc/incoming/observer_{YY,A,B}/` (+ aliases `observer_inoue`, `observer_osada`) |
| ICC (optional) | Same-operator Session1/Session2 Flet plan **deprioritized** — intra-observer not completed; limitation |
| Expert grading | **Subset** n=54 (24/16/14), seed `20260727` — not full cohort |
| Weighted κ order | Dead tree → Tree in bud → Glomerular → Seafan → Medusa |
| Subtype spelling | **`Tree in bud`** (match automated) |
| small Subtype GT | Classifier re-run (CSV scores + session trunk + ref JSON) |
| Table 3 / effect sizes | Primary source = git CSVs @ `1e5d202` |
| Effect size | ε² + bootstrap 95% CI |
| Figures | **Fig2 AND Fig3** (processing steps); Fig3 draft assembled from headless auto-ROI |
| Work order | Start **WS4 + WS2 prep** first |

## Files in `documentation/graefe_revision/`

| File | Role |
|------|------|
| `Response_to_Reviewers_DRAFT.md` / `.docx` | Point-by-point response (File 1) — fill placeholders after analyses |
| `MNV_Analysis_YY.docx` | Original manuscript |
| `Figure.tiff` / `Figure.png` | Existing multi-device examples → **Figure 1** |
| `Figure2_workflow_schematic.png` / `.tiff` | Workflow schematic → **Figure 2** (R1) |
| `figures/Figure3_processing_steps.png` / `.tiff` | Processing-step panels → **Figure 3** (draft; prefer Flet freehand for final) |
| `data/*.csv` | Recovered `1e5d202` batch CSVs (not under tracked `csv/`) |
| `stats/table3_effect_sizes.md` | WS4 ε² results |
| `grading/` | WS2 blind grading prep + agreement script |
| `icc/` | WS1 multi-rater ICC protocol + `incoming/` drop folders; legacy S1/S2 optional |

## Analyses

### WS4 — Effect sizes for Table 3 strata (R2#5) — **DONE (numbers available)**

- [x] Recover three CSVs from `1e5d202` → `data/`
- [x] Kruskal–Wallis + ε² + bootstrap 95% CI (`scripts/graefe_revision/table3_effect_sizes.py`)
- [x] Outputs: `stats/table3_effect_sizes.md`, `.csv`, `table3_per_case_scores.csv`
- [ ] Update Results/Discussion wording (remove “non-significant = comparable”; **note:** Caliber & Maturity **are** significant on these CSVs — Complexity is not)

**Key numbers (n=112):**

| Metric | H | p | ε² (display) | 95% CI |
|--------|---|---|--------------|--------|
| Network Complexity Score | 1.712 | 0.425 | 0.000 | 0.000–0.089 |
| Caliber Uniformity Score | 27.713 | 9.6e-07 | 0.236 | 0.112–0.396 |
| Maturity Index | 28.690 | 5.89e-07 | 0.245 | 0.122–0.408 |

### WS2 — Masked expert grading (R2#2) — **DONE (κ available)**

- [x] Build `grading/automated_labels.csv` (large/small_3mm from CSV; small = classifier re-run)
- [x] Stratified subset n=54 seed `20260727` → `grading_manifest.csv`
- [x] Blind template `expert_grades_blind.csv` (no automated labels)
- [x] Protocol README + `open_blind_cases.py` (paths; no full image copy)
- [x] `compute_agreement.py` ready (exits gracefully until grades locked; does not unblind)
- [x] YY grades all 54 `blind_id`s (post-regrade counts: Glomerular 33, Medusa 10, Tree in bud 5, Dead tree 3, Seafan 3)
- [x] Lock → `expert_grades_locked.csv` → agreement script → overall agreement + **weighted κ** + confusion matrix
- [x] Regrade pass (2026-07-27): **16/54** expert grades changed → recomputed κ; Response Comment 2 updated
- [x] Fill Response letter Comment 2 placeholders

**Key numbers (n=54, post-regrade):** overall agreement **57.4%** (31/54); quadratic weighted κ **0.507** (95% CI **0.222–0.714**). Sensitivity (Glomerular/Seafan merged, 4-class): agreement **75.9%** (41/54); κ **0.682** (95% CI **0.400–0.852**). Outputs: `grading/agreement_stats.md`, `confusion_matrix.csv`, `agreement_stats_merged_glomerular_seafan.md`.

### WS1 — Inter-observer multi-rater ICC (R2#4) — **DONE**

- [x] Design locked: **3 observers** (YY + Inoue + Osada), primary = multi-rater ICC(2,1) (+ multilevel VC ICC)
- [x] `icc/README.md` rewritten (incoming layout, columns, analysis options A/B, checklist)
- [x] `icc/incoming/{observer_YY,observer_A,observer_B}/` drop folders (+ aliases `observer_inoue`, `observer_osada`)
- [x] Receive score CSVs: YY `MNV_batch_20260730_165332.csv`; Inoue `…_inoue.csv`; Osada `…_osada.csv`
- [x] Run multi-rater ICC(2,1) + 95% CI per metric (`scripts/graefe_revision/compute_icc_multirater.py`)
- [x] Pairwise ICC + ANOVA variance-component ICC_case
- [x] Fill Response letter Comment 4 placeholders
- [ ] Optional only: legacy same-operator Session 2 / `compute_icc.py` if intra-observer supplement desired

**Key numbers (n=46, 3 observers, pingouin ICC2):**

| Metric | ICC(2,1) | 95% CI |
|--------|----------|--------|
| MNV Area (mm²) | 0.859 | 0.680–0.930 |
| Network Complexity Score | 0.807 | 0.660–0.890 |
| Caliber Uniformity Score | 0.434 | 0.260–0.610 |
| Maturity Index | 0.659 | 0.510–0.780 |

Outputs: `icc/icc_multirater_results.md`, `icc_multirater_stats.csv`, `icc_multirater_pairwise.csv`, `icc_multirater_variance_components.csv`, long/wide CSVs. No cases dropped (union = intersection = 46).

### Figures

- [x] Fig2 workflow schematic present
- [x] **Fig3 draft** processing-step montage (`figures/Figure3_processing_steps.png` / `.tiff` + caption)
  - Source: headless `CoreMNVPipeline` auto-ROI on cohort case `81224417_IVF_before_OD.jpg` (large)
  - Rebuild / replace with Flet freehand: `scripts/graefe_revision/assemble_figure3.py --from-dir output/mnv/<uuid> --original <path>`
  - [ ] YY: optionally re-run 1–3 cases in Flet for final freehand-ROI panels

## Manuscript text revisions (can start now; full rewrite not in this task)

- [ ] Title Page: Key Messages
- [ ] Unify terminology → Standardized Vascular Complexity / Caliber Uniformity / Maturity Index
- [ ] Soften Abstract/Results/Discussion on median≈50 (circularity)
- [ ] Replace “pathophysiological classification” → morphology-derived interpretive categories
- [ ] Soften clinical decision-making / prognostic claims
- [ ] Expand Limitations
- [ ] Phansalkar vs Otsu paragraph in Methods
- [ ] Disclose classification thresholds (Methods or Suppl Table)
- [ ] Fix duplicate Tew et al. (refs 8 & 22)
- [ ] Fix any “Heidelberg Solix” → Optovue Solix
- [ ] Clean “Pruned tree” / “Large vessels” if present in Table 5
- [ ] Consider title change removing “Pathophysiological”
- [ ] Update Table 3 / text to match WS4 ε² findings (Complexity NS; Caliber & Maturity significant)

## Submission package (when ready)

1. Response to reviewers (PDF)  
2. Revised manuscript – changes marked  
3. Revised manuscript – clean  
4. Figures, Tables, Supplementary  

## Suggested revised title

Novel Semi-Automated System for Multi-Dimensional Analysis of Macular Neovascularization: Quantitative Biomarkers and Rule-Based Morphological Categorization Across OCTA Platforms
