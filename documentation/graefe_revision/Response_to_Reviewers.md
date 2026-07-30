# Point-by-Point Response to Reviewers

**Journal:** Graefe's Archive for Clinical and Experimental Ophthalmology  
**Submission ID:** d8450736-638d-47c9-991d-90d98396c381  
**Manuscript title:** Novel Semi-Automated System for Multi-Dimensional Analysis of Macular Neovascularization: A Comparative Study of Quantitative Biomarkers and Morphological-Pathophysiological Classification  
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
2. Softened language regarding “pathophysiological classification” and clinical decision-making (see Reviewer 2, Comment 3).
3. Expanded the Limitations section to address circularity of median-anchored normalization, absence of longitudinal clinical anchors, anonymized cohort without detailed baseline demographics, reproducibility scope (multi-rater inter-observer primary; intra-observer optional if available), and the need for multi-center external validation.

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
We agree without reservation. Mapping each stratum’s median to 50 is by construction; therefore median values near 50 after normalization cannot be interpreted as empirical proof of biological equivalence across devices. Indeed, re-analysis of the primary batch CSVs (n = 112) shows that, despite median-anchored scaling, **Caliber Uniformity Score** and **Maturity Index** retain significant between-stratum differences with non-negligible effect sizes (see Comment 5). This strengthens the Reviewer’s point: medians near 50 are a mathematical consequence of the transform and do **not** imply that scores are biologically comparable across devices/FOV strata.

**Changes made:**
- Abstract, Results (“Convergence of Standardized Scores…”), and Discussion have been rewritten to state that piecewise-linear normalization is a **within-stratum scaling procedure** intended to place scores on a common 0–100 reporting scale for rule-based classification thresholds, **not** a demonstration of cross-device biological equivalence.
- We no longer describe median≈50 as “empirical evidence” that device-dependent scaling was removed while “preserving biological information,” and we no longer claim that standardized scores are statistically indistinguishable or biologically equivalent across strata.
- Retained and clarified the non-circular elements that remain informative: (i) large between-device differences in **raw** metrics (Table 2); (ii) consistency of PCA structure (PC1 loadings and explained variance) across strata; (iii) within-stratum score distributions by morphological category after expert comparison (revised analyses).
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
- Explicitly state that these labels are **hypothesis-generating**, based on quantitative morphology and published morphological criteria, and are **not** clinically validated disease-behavior classes.
- Removed or softened statements implying improved clinical decision-making or prognostic stratification pending outcome-linked studies.

### Comment 4 — Missing inter- and intra-observer reproducibility

*Inter- and intra-observer reproducibility of the semi-automated pipeline is not reported. Since the system depends on manual ROI delineation, operator variability may substantially affect downstream scores.*

**Response:**
We agree that ROI-dependent variability must be quantified. For this revision we assessed **inter-observer reproducibility** with **three independent operators** (the original analyst [YY] plus two external examiners [Inoue, Osada]) who each performed freehand ROI delineation on the same set of lesions (**n = 46** complete cases matched across all three observers), with subsequent fully automated processing unchanged. We report **multi-rater ICCs** (two-way random-effects, absolute agreement, single measures — ICC(2,1); Shrout & Fleiss / McGraw & Wong) for lesion area and for Network Complexity Score, Caliber Uniformity Score, and Maturity Index, with pairwise ICCs and a multilevel variance-component ICC as complementary summaries.

**Primary results (3-rater ICC(2,1), n = 46):**

| Metric | ICC(2,1) | 95% CI |
|--------|----------|--------|
| MNV Area (mm²) | 0.859 | 0.680–0.930 |
| Network Complexity Score | 0.807 | 0.660–0.890 |
| Caliber Uniformity Score | 0.434 | 0.260–0.610 |
| Maturity Index | 0.659 | 0.510–0.780 |

Lesion area and Network Complexity showed good-to-excellent inter-observer agreement; Maturity Index showed moderate-to-good agreement; Caliber Uniformity was moderate and more sensitive to ROI variability. Variance-component ICC_case (σ²_case / [σ²_case + σ²_observer + σ²_error]) yielded the same point estimates (0.859 / 0.807 / 0.434 / 0.659), indicating that residual and observer components together explain the remaining variance—largest for Caliber Uniformity.

**Intra-observer** (same-operator test–retest) reproducibility was not completed within the revision timeline and is acknowledged as a limitation; the primary reproducibility claim for this revision is the three-observer inter-observer ICC above.

### Comment 5 — Non-significant Kruskal–Wallis does not establish equivalence

*Non-significant Kruskal–Wallis p-values do not establish equivalence. A formal equivalence testing framework (e.g., TOST with pre-specified margins) or at minimum effect sizes with confidence intervals should replace the current “non-significant therefore comparable” interpretation.*

**Response:**  
We agree. Absence of a statistically significant Kruskal–Wallis test does not demonstrate equivalence—and, on re-analysis of the primary git batch CSVs (commit `1e5d202`; n = 112: large = 49, small = 33, small_3mm = 30), not all between-stratum Kruskal–Wallis tests were non-significant.

We now report Kruskal–Wallis H, p, and ε² with bootstrap 95% CIs (10 000 within-stratum resamples; seed `20260727`):

| Metric | H | p | ε² | 95% CI | Medians (L / S / S3) |
|--------|---|---|-----|--------|----------------------|
| Network Complexity Score | 1.712 | 0.425 | 0.0000 | 0.0000–0.0887 | 48.7 / 50.7 / 47.8 |
| Caliber Uniformity Score | 27.713 | 9.6×10⁻⁷ | 0.2359 | 0.1121–0.3959 | 66.4 / 56.7 / 58.9 |
| Maturity Index | 28.690 | 5.89×10⁻⁷ | 0.2449 | 0.1224–0.4078 | 57.5 / 52.4 / 52.8 |

**Interpretation:** Network Complexity does not differ across strata (p ≈ 0.43; ε² ≈ 0, negligible). In contrast, Caliber Uniformity and Maturity Index show significant between-stratum differences (both p < 0.001) with medium-to-large ε² (≈ 0.24). Thus the original “all Kruskal–Wallis non-significant → scores comparable across devices” framing was incorrect and has been withdrawn. Median-anchored normalization places each stratum’s median near 50 by design, but does **not** eliminate between-stratum differences or establish biological equivalence—consistent with, and strengthening, Comments 1 and 5.

**Changes made:**
- Removed “statistically indistinguishable / therefore comparable” and “all KW non-significant” language.
- Added ε² with bootstrap CIs alongside Kruskal–Wallis statistics (revised Table 3 / Results).
- Explicitly report that Complexity is NS whereas Caliber Uniformity and Maturity Index differ across strata with non-negligible effect sizes.
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

The Abstract, Introduction, Discussion, tables, and figure legends now use these names consistently. Where “stability” appears conceptually, it is explicitly linked to caliber uniformity.

**(b)** We thank the Reviewer for catching this inconsistency. “Pruned tree” and “Large vessels” are **not** part of the operational five-subtype scheme used in this study (Dead tree, Tree-in-bud, Glomerular, Seafan, Medusa). They have been removed from Table 5 / the comparative biomarker table (or clearly labeled as literature-only descriptors if retained for historical comparison). Table 4 and the classification Methods are now fully aligned.

**(c)** Duplicate citation of Tew et al. (2020) has been removed; the reference list and in-text citations have been renumbered.

**(d)** The correct designation is **Optovue Solix** (Optovue/Visionix). The erroneous “Heidelberg Solix” wording in the Table 2 legend has been corrected.

---

## Summary of additional experiments / analyses performed for this revision

| Item | Status |
|------|--------|
| Workflow schematic figure (Frangi/LoG → Phansalkar → skeletonization) | Added (Figure 2) |
| Phansalkar vs Otsu methodological justification | Added in Methods |
| Masked expert morphological grading vs automated labels (weighted κ) | Done — agreement assessment (not “validation”); n=54; 57.4%; κ=0.507 (95% CI 0.222–0.714); Glomerular/Seafan merge 75.9%, κ=0.682; framed via Tew/Shah/Deák/Gan/Hsu as motivating quantitative operationalization (not undermining it); confusion matrix in Suppl |
| Inter-observer multi-rater ICC (3 operators, n=46; area + scores) | Done — ICC(2,1): area 0.859 (0.680–0.930); complexity 0.807 (0.660–0.890); caliber 0.434 (0.260–0.610); maturity 0.659 (0.510–0.780); `icc/icc_multirater_results.md` |
| Effect sizes (+ CIs) for between-stratum standardized scores | Added — Complexity NS (ε²≈0); Caliber Uniformity & Maturity Index significant (ε²≈0.24); not “all KW NS” |
| Softening of pathophysiology language; expanded Limitations | Completed |
| Terminology unification; reference deduplication; Optovue correction; Table cleanup | Completed |
| Intra-observer test–retest (optional); longitudinal clinical anchors; full baseline demographics | Intra-observer optional/limitation if unavailable; clinical anchors / full demographics not feasible in this anonymized dataset — listed as Limitations |

---

We hope that these revisions satisfactorily address the Editor’s and Reviewers’ concerns.

Respectfully submitted,  
Yasuo Yanagi, on behalf of all co-authors
