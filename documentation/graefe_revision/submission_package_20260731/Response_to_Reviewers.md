# Point-by-Point Response to Reviewers

**Journal:** Graefe's Archive for Clinical and Experimental Ophthalmology  
**Submission ID:** d8450736-638d-47c9-991d-90d98396c381  
**Manuscript title:** Novel Semi-Automated System for Multi-Dimensional Analysis of Macular Neovascularization: Quantitative Biomarkers and Rule-Based Morphological Categorization Across OCTA Platforms  
**Corresponding author:** Yasuo Yanagi, M.D., Ph.D. (yanagi.yas.wu@yokohama-cu.ac.jp)

---

Dear Editor and Reviewers,

We thank the Editor and Reviewers for their careful evaluation of our manuscript and for the constructive comments. We have revised the manuscript accordingly. Below we provide a point-by-point response. Reviewer comments are reproduced in italics; our responses follow. Page/line numbers refer to the marked revised manuscript unless otherwise stated.

---

## Response to the Editor

### Editor comment 1 — Key Message

*Please note: The key messages should be placed on the Title Page. Please prepare as bullet points and ensure they are concise. Two–Four key messages are required, please place the heading “what is known” and note 1–2 key messages, then please note the heading “What is new” and place 2–3 key messages highlighting the new information in the paper.*

**Response:**  
We have added a Key Messages box on the Title Page, structured as requested.

**What is known**
- Quantitative OCTA analysis of macular neovascularization (MNV) is limited by device- and field-of-view–dependent scaling of raw topological metrics, hindering cross-platform comparison.
- Qualitative MNV pattern labels (e.g., Medusa, Seafan, Dead tree) remain inconsistently defined and are rarely linked to reproducible quantitative thresholds.

**What is new**
- We present a semi-automated pipeline (hybrid vessel enhancement, adaptive binarization, skeleton-based topology) that generates stratum-specific standardized Complexity and Caliber Uniformity scores (0–100) for cross-device reporting.
- We provide operational, rule-based morphological categories with disclosed decision thresholds and report agreement with masked expert grading.
- Morphology-derived interpretive categories are proposed as hypothesis-generating labels; clinical outcome validation was outside the scope of this anonymized, treatment-naïve cohort.

### Editor comment 2 — Accurate reporting, conclusions, and limitations

*Please ensure the results are accurately reported, any overstated conclusions are rewritten and the limitations of the work fully explained.*

**Response:**  
We agree. Throughout the Abstract, Results, Discussion, and Conclusion we have:
1. Removed claims that median score convergence near 50 constitutes evidence of biological equivalence across devices (see Reviewer 2, Comment 1).
2. Softened language regarding “pathophysiological classification” and clinical decision-making (see Reviewer 2, Comment 3); **Tables 4–5** rewritten accordingly.
3. Expanded the Limitations section to address circularity of median-anchored normalization, absence of longitudinal clinical anchors, anonymized cohort without detailed baseline demographics, reproducibility scope (multi-rater inter-observer primary, with same-operator intra-observer test–retest as a supplement; see Reviewer 2, Comment 4), and the need for multi-center external validation.
4. Restored and notation-revised **Tables 1–5** from the original submission tables file (see Reviewer 2 Comments 1, 3, 5, 7). Tables are provided as a **separate Word file** (`MNV_Analysis_YY_rev1_tables.docx`, corresponding to the original `MNV_analysis_tables.docx` packaging); the manuscript body cites Tables 1–5 in text only. Figure legends for Figures 1–3 are likewise in a separate file (`MNV_Analysis_YY_rev1_figure_legends.docx`).

---

## Response to Reviewer 1

We thank Reviewer 1 for the positive assessment and the focused methodological request.

### Comment #1 — Schematic workflow figure and rationale for Phansalkar binarization

*The authors should provide a schematic figure illustrating the image-processing workflow used in this study, including vessel enhancement (e.g., edge detection using Frangi and/or Laplacian filters), binarization of the OCTA images using the Phansalkar method, and skeletonization. Such a figure would greatly improve the clarity and reproducibility of the methodology.*

*In addition, the rationale for using the Phansalkar method for binarization should be clarified. Phansalkar thresholding is commonly applied in choriocapillaris analysis; however, in vascular imaging of the SCP, DCP, or avascular slab, Otsu thresholding is more commonly used. While I agree that the Frangi filter is appropriate and effective for vessel enhancement, the choice of binarization method requires further justification.*

**Response:**  
We fully agree.

1. **New schematic figure.** We have added a new figure (Figure 2 in the revised manuscript) illustrating the end-to-end processing workflow: freehand ROI → iterative ROI refinement → hybrid multiscale vessel enhancement (Frangi/tubeness + Laplacian of Gaussian) → Phansalkar adaptive binarization → morphological refinement → skeletonization → boundary-branch exclusion → quantitative metrics and standardized scores. The original multi-device segmentation examples remain as Figure 1.

2. **Rationale for Phansalkar rather than global Otsu.** We have expanded the Methods (Binarization subsection) as follows. After Frangi/LoG enhancement, MNV vessel maps retain spatially heterogeneous background intensity arising from projection artifacts, signal attenuation, and lesion-internal contrast variation. Global Otsu thresholding assumes a bimodal intensity histogram with a single global cut-point and therefore tends to erode fine peripheral capillaries or, conversely, to include background speckles when lesion and background overlap. Phansalkar adaptive local thresholding estimates a local mean/SD-based threshold within a resolution-calibrated window (radius corresponding to 24 µm; k = 0.1, R = 0), preserving locally contrasted fine vessels while suppressing regional background drift. Although Phansalkar thresholding is widely recognized in choriocapillaris flow-deficit analysis, the same property—robustness to local intensity non-uniformity—is advantageous for enhanced MNV vessel maps on the outer-retina/avascular complex slab. Our implementation follows the ImageJ Auto Local Threshold (Phansalkar) convention used in the original macro, facilitating reproducibility. We now explicitly acknowledge that Otsu remains common for relatively homogeneous SCP/DCP en-face slabs and state why we preferred a local adaptive method for this MNV application.

**Changes made:**
- New Figure 2 (workflow schematic) with legend.
- Expanded Methods justification for Phansalkar vs Otsu.
- Minor cross-references updated in Results.

---

## Response to Reviewer 2

We thank Reviewer 2 for the rigorous methodological critique. We agree that several interpretive claims in the original submission were stronger than the evidence allowed. We have undertaken additional analyses where feasible and have substantially tempered the conclusions.

### Comment 1 — Circularity of cross-device score “convergence”

*The demonstration of cross-device score convergence (Table 3) is circular. The piecewise-linear normalization maps each stratum’s median to 50 by design, so observing medians near 50 after normalization is a mathematical certainty rather than evidence of biological equivalence.*

**Response:**  
We agree without reservation. Mapping each stratum’s median to 50 is by construction; therefore median values near 50 after normalization cannot be interpreted as empirical proof of biological equivalence across devices. Under the **default Standardized Caliber Uniformity Score**, between-stratum Kruskal–Wallis tests for Complexity, Caliber, and Maturity are non-significant (ε² ≈ 0; see Comment 5)—but that pattern still does **not** establish biological equivalence, because median-anchored transforms and locked cuts can attenuate stratum-mean contrasts by design. Under the **PCA-based Caliber Uniformity Score (legacy)**, Caliber and Maturity had retained significant between-stratum differences (ε² ≈ 0.24); that legacy finding is reported only as sensitivity context. In all cases, medians near 50 are a mathematical consequence of the transform and do **not** imply that scores are biologically comparable across devices/FOV strata.

**Changes made:**
- Abstract, Results (“Stratum-Standardized Scores…”), and Discussion have been rewritten to state that piecewise-linear normalization is a **within-stratum scaling procedure** intended to place scores on a common 0–100 reporting scale for rule-based classification thresholds, **not** a demonstration of cross-device biological equivalence.
- We no longer describe median≈50 as “empirical evidence” that device-dependent scaling was removed while “preserving biological information,” and we no longer claim that standardized scores are statistically indistinguishable or biologically equivalent across strata.
- **Table 3** rewritten: primary endpoint is now the **default** Standardized Caliber Uniformity Score with Kruskal–Wallis H/p plus ε² and bootstrap 95% CIs (medians 46.6 / 55.5 / 50.6 for Caliber; Complexity PC1 explained variance retained in prose). Original PCA-Caliber Table 3 medians/p-values are no longer the primary table content.
- Retained and clarified the non-circular elements that remain informative: (i) large between-device differences in **raw** metrics (**Table 2**, restored from original submission numbers with Optovue labeling); (ii) consistency of PCA structure (PC1 loadings and explained variance) across strata; (iii) within-stratum score distributions by morphological category after expert comparison (revised analyses).
- Title/aim language adjusted from “device-independent quantification” toward “stratum-standardized scoring for cross-device reporting.”

### Comment 2 — Lack of accuracy assessment for automated morphological classification

*The automated morphological classification is presented without any accuracy assessment. Table 4 reports subtype distributions but no comparison against masked expert grading. Agreement statistics (e.g., weighted kappa) and full disclosure of decision thresholds are necessary for a methods paper claiming automated classification.*

**Response:**  
We agree that an agreement assessment against masked expert grading, with disclosed decision thresholds, is required. In the revised manuscript we report a **masked expert–automated agreement assessment** (not framed as definitive “validation”) as follows.

1. A retinal specialist (Y.Y.) performed **masked morphological grading** on a stratified subset of study OCTA images (**n = 54**), without access to automated subtype labels at the time of grading.
2. Expert grades were compared with rule-based automated labels. Overall agreement was **57.4%** (31/54); quadratic weighted Cohen’s κ was **0.507** (95% CI **0.222–0.714**; ordinal order Dead tree → Tree in bud → Glomerular → Seafan → Medusa). The confusion matrix is provided in Supplementary Material.
3. Decision thresholds (percentile cut-points and trunk-pattern rules for Dead tree, Tree in bud, Glomerular, Seafan, and Medusa) are fully disclosed in Methods and/or Supplementary Table S1.

We interpret this modest-to-moderate κ as partly reflecting **limitations of subjective, human categorical OCTA morphological grading**, rather than as solely indicating algorithmic failure. Qualitative pattern labels (e.g., Medusa, Seafan, tangled/medusa-like descriptors) are used clinically but remain partly descriptive and ambiguous in the OCTA literature (Tew et al., *Clin Experiment Ophthalmol* 2020; already cited in the manuscript). Related work similarly indicates that **qualitative** assessments can be less reliable across raters than **quantitative** OCTA metrics (Shah et al., *Transl Vis Sci Technol* 2023). Categorical MNV typing between fluorescein angiography– and OCT-based systems likewise shows only moderate agreement (Deák et al., *Sci Rep* 2025; κ approximately 0.46–0.58 for major type correspondences), underscoring the inherent subjectivity of morphology-based categorical labels even among trained readers. Quantitative OCTA biomarkers have accordingly been developed to objectify aspects of neovascular morphology and activity (Gan et al., *Transl Vis Sci Technol* 2026; Hsu et al., *Sci Rep* 2021).

Against this background, our rule-based quantitative operationalization—with disclosed thresholds and scores—is intended to **reduce rater-dependent ambiguity** inherent in purely descriptive human grading. In that sense, modest expert–algorithm agreement **motivates** rather than undermines the methodological rationale of the system: to make morphological categories reproducible and transparent relative to purely visual labels.

**Caveats (stated explicitly):** (a) the comparison contrasts full-image visual expert grades with ROI-metric–derived rule classes, so perfect concordance is not expected; (b) this analysis is expert–algorithm agreement, **not** multi-human inter-grader κ (a separate three-observer ICC for ROI-dependent score reproducibility is reported in Comment 4; n=46); (c) for the small-FOV stratum, some automated subtypes were score-rederived from disclosed classifier rules when the batch CSV lacked a Subtype column; (d) we do **not** claim that the algorithm replaces expert judgment—we report agreement, disclose thresholds, and claim only that quantitative operational definitions improve transparency and reproducibility *relative to purely descriptive labels*.

**Optional sensitivity:** when Glomerular and Seafan were merged into a single category on both expert and automated labels (4-class analysis), overall agreement rose to **75.9%** (41/54) and quadratic weighted κ to **0.682** (95% CI **0.400–0.852**), suggesting that a substantial fraction of discordance reflects adjacent descriptive subtypes that are difficult to separate visually.

We have also replaced wording such as “validated automated classification” with “rule-based morphological categorization with agreement against masked expert grading.”

**Changes made (tables):**
- **Table 4** restored from the original submission tables file with complete Medusa/Seafan splits (large Medusa 6 [12.2%]; small Seafan 2 [6.1%]; small_3mm Seafan 11 [36.7%]); expert–automated κ and Supplementary confusion matrix added in Results (not as a numbered main-text table).
- Decision thresholds disclosed in Methods / Supplementary Table S1.

**Selected references (Comment 2):**
- Tew TB et al. Comparison of different morphologies of choroidal neovascularization evaluated by ocular coherence tomography angiography in age-related macular degeneration. *Clin Experiment Ophthalmol*. 2020;48:927–937.
- Shah PN et al. Inter-rater reliability of proliferative diabetic retinopathy assessment on wide-field OCT-angiography and fluorescein angiography. *Transl Vis Sci Technol*. 2023;12(7):13.
- Deák GG et al. Comparison of optical coherence tomography vs. fluorescein angiography-based macular neovascularization classifications in age-related macular degeneration. *Sci Rep*. 2025;15:87576 (doi:10.1038/s41598-025-87576-6).
- Gan Y et al. Novel quantitative OCTA biomarkers of choroidal neovascularization and associations with disease activity and etiology. *Transl Vis Sci Technol*. 2026;15(3):10.
- Hsu CR et al. Combined quantitative and qualitative optical coherence tomography angiography biomarkers for predicting active neovascular age-related macular degeneration. *Sci Rep*. 2021;11:18068.

### Comment 3 — Pathophysiological labels not anchored to clinical data

*The mapping of morphological patterns to pathophysiological states is not anchored to clinical data. No fluid status, treatment response, or longitudinal outcome data are presented to confirm these labels reflect actual disease behavior. Without such evidence, these should be described as morphology-derived categories rather than pathophysiological classifications.*

**Response:**  
We agree. This anonymized, cross-sectional, treatment-naïve dataset does not contain fluid status, treatment response, or longitudinal outcomes; such data cannot be added for this revision.

**Changes made:**
- Replaced “pathophysiological classification/states” with **“morphology-derived interpretive categories”** (Active-pattern, Mature-quiescent-pattern, Transitional-pattern, Arteriolarized-pattern) throughout, including the title, Abstract, Methods, Results, Discussion, and Conclusion.
- **Table 4:** removed the original “Pathophysiological State” column; subtype counts/percentages restored from the original tables file (including Medusa/Seafan splits).
- **Table 5:** retitled/rewritten as a morphology-derived interpretive mapping (Primary/Secondary **interpretive category** columns); no pathophysiological-state wording.
- Explicitly state that these labels are **hypothesis-generating**, based on quantitative morphology and published morphological criteria, and are **not** clinically validated disease-behavior classes.
- Removed or softened statements implying improved clinical decision-making or prognostic stratification pending outcome-linked studies.

### Comment 4 — Missing inter- and intra-observer reproducibility

*Inter- and intra-observer reproducibility of the semi-automated pipeline is not reported. Since the system depends on manual ROI delineation, operator variability may substantially affect downstream scores.*

**Response:**
We agree that ROI-dependent variability must be quantified. For this revision we assessed **inter-observer reproducibility** with **three independent operators** (the original analyst [YY] plus two external examiners [Inoue, Osada]) who each performed freehand ROI delineation on the same set of lesions (**n = 46** complete cases matched across all three observers), with subsequent fully automated processing unchanged. We report **multi-rater ICCs** (two-way random-effects, absolute agreement, single measures — ICC(2,1); Shrout & Fleiss; McGraw & Wong) for lesion area and for Network Complexity Score, the **default Standardized Caliber Uniformity Score**, and Maturity Index recomputed from that Caliber score, with pairwise ICCs and a multilevel variance-component ICC as complementary summaries. Interpretive bands follow published guidance (poor <0.50; moderate 0.50–0.75; good 0.75–0.90; excellent >0.90; Koo & Li).

In the revised manuscript, the **default / primary Caliber Uniformity endpoint** is the device-/stratum-locked score based on NV Diameter CV and Dilated vessel % (weights 0.75 / 0.25; stratum-locked min/median/max piecewise maps; CIRRUS/`small_3mm` locked cuts on this ICC set). The **PCA-based Caliber Uniformity Score (legacy)** from the original submission is retained only as a sensitivity comparison.

**Primary results (3-rater ICC(2,1), n = 46; default Caliber definition):**

| Metric | ICC(2,1) | 95% CI |
|--------|----------|--------|
| MNV Area (mm²) | 0.859 | 0.680–0.930 |
| Network Complexity Score | 0.807 | 0.660–0.890 |
| Caliber Uniformity Score (default, device-locked) | 0.770 | 0.660–0.860 |
| Maturity Index (from default Caliber) | 0.593 | 0.430–0.730 |

Lesion area, Network Complexity, and the default Standardized Caliber Uniformity Score showed **good** inter-observer agreement on conventional ICC benchmarks; Maturity Index derived from that Caliber score was **moderate**. Variance-component ICC_case yielded the same point estimates for these primary endpoints.

We thank the Reviewer for prompting this closer examination of metric-specific reproducibility. Under the legacy PCA Caliber definition, concordance was poorer and more ROI-sensitive. Prior OCTA work has shown that quantitative vascular metrics are often **not interchangeable across OCTA devices/algorithms** without device-aware reporting (Corvi et al., *Am J Ophthalmol* 2018; Corvi et al., *Retina* 2020; consistent with Munk et al., *PLOS ONE* 2017, already cited). In the present manuscript, Caliber Uniformity is handled as a **stratum-/device-specific** construct (Zeiss PlexElite 6×6 mm; Zeiss CIRRUS AngioPlex 3×3 mm; Optovue Solix 6×6 mm), with locked reference cuts disclosed in Methods and Supplementary Table S1.

**Sensitivity (same n = 46; disclosed alternate Caliber scores):**

| Score | Definition (summary) | ICC(2,1) | 95% CI |
|-------|----------------------|----------|--------|
| PCA-based Caliber Uniformity Score (legacy) | Prior PCA Stability composite (original submission primary) | **0.434** | 0.260–0.610 |
| Robust CV proxy | Winsorized NV Diameter CV → inverted 0–100 | **0.765** | 0.640–0.860 |
| Pooled soft CV + Dilated% variant | 0.75·soft(−NV-CV) + 0.25·U(−Dilated%); re-estimated on ICC pool | **0.838** | 0.750–0.900 |
| Default device-locked Caliber Uniformity (primary) | Same 0.75/0.25 weights with CIRRUS/`small_3mm` locked piecewise cuts | **0.770** | 0.660–0.860 |

**Interpretation.** The legacy PCA Caliber ICC (0.434) falls in the **poor-to-moderate** range, whereas the default device-locked score (0.770) and other CV/Dilated%-based variants move into the **good** range—comparable in magnitude to Network Complexity (0.807) and approaching Area (0.859). These alternate scores are **not** monotonically aligned with the legacy PCA construct. The pooled soft variant remains a within-study sensitivity score that re-fits on the ICC pool and is therefore less transferable than the locked reference cuts used as the manuscript default. Maturity Index ICC was not improved by redefining Caliber relative to the legacy PCA-based Maturity Index (0.659) and remains moderate under the default definition (0.593). Multi-device ICC spanning all three platforms was not available for this revision (all 46 images were 3×3 mm).

As a further sensitivity analysis on the 20 most cross-observer–concordant cases (lowest mean z-scored rater range across metrics), ICC(2,1) was 0.864 / 0.950 / 0.852 / 0.924 for area / complexity / caliber uniformity / maturity; these do not replace the primary n=46 estimates above. Detailed numeric exports are available on request / as Supplementary Material.

**Intra-observer results (YY Session 1 vs Session 2, n = 46).** We additionally completed same-operator test–retest: the original analyst (YY) repeated freehand ROI delineation on the same **n = 46** lesions in a separate sitting, with automated processing unchanged. Session exports initially mixed legacy PCA and current default Caliber definitions across sittings; unharmonized default Caliber/Maturity columns are therefore **not** comparable and are **not** reported. For Caliber Uniformity and Maturity Index in this intra comparison, we report the **same device-locked default Standardized Caliber Uniformity Score applied to both sessions**—the primary inter-observer Caliber endpoint—alongside Area and Network Complexity (unchanged definitions).

| Metric | ICC(2,1) | 95% CI |
|--------|----------|--------|
| MNV Area (mm²) | 0.979 | 0.962–0.988 |
| Network Complexity Score | 0.950 | 0.913–0.973 |
| Caliber Uniformity Score (default, device-locked) | 0.925 | 0.871–0.959 |
| Maturity Index (from default Caliber) | 0.917 | 0.857–0.954 |

Within-rater agreement was excellent for Area, Network Complexity, and the default Caliber Uniformity and Maturity Index (all ICC(2,1) > 0.90). These intra-observer estimates support within-operator reproducibility under a fixed score definition; they supplement, and do **not** replace, the three-observer inter-observer ICCs as the primary multi-rater reproducibility claim.

### Comment 5 — Non-significant Kruskal–Wallis does not establish equivalence

*Non-significant Kruskal–Wallis p-values do not establish equivalence. A formal equivalence testing framework (e.g., TOST with pre-specified margins) or at minimum effect sizes with confidence intervals should replace the current “non-significant therefore comparable” interpretation.*

**Response:**  
We agree. Absence of a statistically significant Kruskal–Wallis test does not demonstrate equivalence. We now report Kruskal–Wallis H, p, and ε² with bootstrap 95% CIs (10 000 within-stratum resamples; seed `20260727`) for the **default** Standardized Caliber Uniformity Score used as the primary Caliber endpoint in the revised manuscript (device-/stratum-locked NV Diameter CV + Dilated vessel %; Maturity Index recomputed from that Caliber score; Network Complexity unchanged), on the primary batch CSVs (n = 112: large = 49, small = 33, small_3mm = 30):

| Metric | H | p | ε² | 95% CI | Medians (L / S / S3) |
|--------|---|---|-----|--------|----------------------|
| Network Complexity Score | 1.712 | 0.425 | 0.0000 | 0.0000–0.0887 | 48.7 / 50.7 / 47.8 |
| Caliber Uniformity Score (default) | 1.118 | 0.572 | 0.0000 | 0.0000–0.082 | 46.6 / 55.5 / 50.6 |
| Maturity Index (from default Caliber) | 1.082 | 0.582 | 0.0000 | 0.0000–0.077 | 49.5 / 53.9 / 51.0 |

**Interpretation (primary / default Caliber):** Under the default Standardized Caliber Uniformity Score, none of the three standardized scores differed significantly across strata (all p ≥ 0.425; ε² ≈ 0, negligible). This does **not** establish biological equivalence across devices: median-anchored piecewise mapping and locked reference cuts can attenuate stratum-mean contrasts by construction. The original “all Kruskal–Wallis non-significant → scores comparable across devices” framing remains withdrawn.

**Legacy sensitivity (PCA-based Caliber Uniformity on the same cases):** the prior PCA Stability Caliber composite showed significant between-stratum Caliber/Maturity differences (Caliber H = 27.713, p = 9.6×10⁻⁷, ε² = 0.2359 [0.1121–0.3959], medians 66.4 / 56.7 / 58.9; Maturity H = 28.690, p = 5.89×10⁻⁷, ε² = 0.2449 [0.1224–0.4078], medians 57.5 / 52.4 / 52.8), while Complexity remained NS. That legacy pattern is disclosed as sensitivity context and is **not** the primary endpoint narrative in this revision.

**Changes made:**
- Removed “statistically indistinguishable / therefore comparable” and “all KW non-significant therefore equivalent” language.
- **Table 3** now reports H, p, ε², and bootstrap 95% CIs under the **default** Caliber Uniformity definition (columns: Median [large/small/small_3mm], H, p, ε², 95% CI); Table note discloses that original PCA-Caliber Table 3 values are legacy sensitivity only.
- Explicitly state that non-significant KW under the default score still does not establish equivalence; disclose the legacy PCA between-stratum differences as sensitivity only.
- Formal TOST was considered; because clinically meaningful equivalence margins for these novel 0–100 scores were not pre-specified at study design, we prioritized effect sizes with CIs and cautious interpretation rather than post-hoc TOST with arbitrary margins. This rationale is stated in Methods/Limitations.

### Comment 6 — No baseline clinical characteristics for device groups

*No baseline clinical characteristics are provided for the three device groups. Given the marked differences in subtype distribution across platforms (Seafan only in the 3×3mm group, Medusa only in PlexElite), cohort composition likely differs. Without controlling for this, apparent score convergence may mask genuine biological heterogeneity.*

**Response:**  
We appreciate this important point. The analysis set consists of **anonymized, treatment-naïve** Type 1 or Type 2 MNV secondary to neovascular AMD. Detailed demographic and clinical covariates (age, sex, laterality, visual acuity, lesion type breakdown beyond Type 1/2, systemic factors) were **not retained** in the anonymized research archive and therefore cannot be tabulated by device group for this revision.

**Changes made:**
- Methods now state explicitly that all included eyes were treatment-naïve nAMD-related Type 1/2 MNV and that detailed baseline covariates were unavailable because of anonymization.
- Discussion/Limitations now acknowledge that between-platform differences in subtype prevalence (Table 4) may reflect sampling/case-mix and FOV-dependent lesion sampling rather than classifier instability alone, and that lack of covariate adjustment limits causal interpretation of cross-device score comparisons.
- In conjunction with Comment 1, we no longer interpret score medians near 50 as evidence that biological heterogeneity was removed.

### Comment 7 — Textual inconsistencies

*(a) The Abstract uses “Vascular Stability Score” while the Methods defines “Standardized Caliber Uniformity Score” for the same metric; “Vascular Complexity Score” and “Standardized Complexity Score” are likewise used interchangeably—terminology should be unified. (b) Table 5 includes “Pruned tree” and “Large vessels” categories that do not appear in Table 4 or anywhere in the Results; it is unclear whether these are theoretical subtypes with no observed cases or remnants from a different classification version. (c) References 8 and 22 cite the same paper (Tew et al., Clin Experiment Ophthalmol 2020). (d) The third device is called “Optovue Solix” in the text but “Heidelberg Solix” in the Table 2 legend—the correct manufacturer should be confirmed.*

**Response / Changes made:**

**(a)** Terminology has been unified throughout to:
- **Standardized Vascular Complexity Score** (Complexity Score)
- **Standardized Caliber Uniformity Score** (formerly also called Vascular Stability Score)
- **Standardized Maturity Index**

The Abstract, Introduction, Discussion, **Tables 1–5**, and figure legends now use these names consistently. Where “stability” appears conceptually, it is explicitly linked to caliber uniformity. **Table 1** Category “Stability” was renamed **Caliber Uniformity**; score descriptions distinguish default vs legacy Caliber definitions.

**(b)** We thank the Reviewer for catching this inconsistency. “Pruned tree” and “Large vessels” are **not** part of the operational five-subtype scheme used in this study (Dead tree, Tree in bud, Glomerular, Seafan, Medusa). They have been **removed from Table 5**. Table 5 now maps only the five operational subtypes to morphology-derived interpretive categories. **Table 4** and the classification Methods are fully aligned with that five-class scheme.

**(c)** Duplicate citation of Tew et al. (2020) has been removed; the reference list and in-text citations have been renumbered.

**(d)** The correct designation is **Optovue Solix** (Optovue/Visionix). The erroneous “Heidelberg Solix” wording in the original **Table 2** legend has been corrected; restored Table 2 column headers and note now read **Optovue Solix**.

---

## Summary of additional experiments / analyses performed for this revision

| Item | Status |
|------|--------|
| Workflow schematic figure (Frangi/LoG → Phansalkar → skeletonization) | Added (Figure 2) |
| Phansalkar vs Otsu methodological justification | Added in Methods |
| Masked expert morphological grading vs automated labels (weighted κ) | Done — agreement assessment (not “validation”); n=54; 57.4%; κ=0.507 (95% CI 0.222–0.714); Glomerular/Seafan merge 75.9%, κ=0.682; framed via Tew/Shah/Deák/Gan/Hsu as motivating quantitative operationalization (not undermining it); confusion matrix in Suppl |
| Inter-observer multi-rater ICC (3 operators, n=46; area + scores) | Done — ICC(2,1): area 0.859 (0.680–0.930); complexity 0.807 (0.660–0.890); **Caliber Uniformity (default) 0.770 (0.660–0.860)**; Maturity 0.593 (0.430–0.730); legacy PCA Caliber 0.434 as sensitivity |
| Effect sizes (+ CIs) for between-stratum standardized scores | Added — under **default** Caliber: all three scores NS (ε²≈0); legacy PCA Caliber/Maturity had ε²≈0.24 (sensitivity only); not “all KW NS → equivalent” |
| Softening of pathophysiology language; expanded Limitations | Completed |
| Terminology unification; reference deduplication; Optovue correction; Table cleanup | Completed |
| Intra-observer test–retest (YY Session1 vs Session2, n=46); longitudinal clinical anchors; full baseline demographics | Intra done — ICC(2,1): area 0.979 (0.962–0.988); complexity 0.950 (0.913–0.973); Caliber 0.925 (0.871–0.959); Maturity 0.917 (0.857–0.954) under **same device-locked definition applied to both sessions**. Clinical anchors / full demographics not feasible in this anonymized dataset — listed as Limitations |

---

We hope that these revisions satisfactorily address the Editor’s and Reviewers’ concerns.

Respectfully submitted,  
Yasuo Yanagi, on behalf of all co-authors
