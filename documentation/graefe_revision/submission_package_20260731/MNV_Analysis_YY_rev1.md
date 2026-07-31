<!--
Revised manuscript (rev1) for Graefe's Archive major revision.
Do NOT overwrite MNV_Analysis_YY.docx / manuscript_text.txt.
Title choice, figure scheme, and TODOs: see MNV_Analysis_YY_rev1_NOTES.md
Change map vs Response letter: see MNV_Analysis_YY_rev1_CHANGELOG.md
-->

# Novel Semi-Automated System for Multi-Dimensional Analysis of Macular Neovascularization: Quantitative Biomarkers and Rule-Based Morphological Categorization Across OCTA Platforms

Yasuo Yanagi, Maiko Maruyama-Inoue, Tatsuya Inoue and Kazuaki Kadonosono

Department of Ophthalmology and Micro-Technology, Yokohama City University, 4-57 Urafune, Minami-ku, Yokohama, Kanagawa, 232-0024, Japan.

**Correspondence:** Yasuo Yanagi  
yanagi.yas.wu@yokohama-cu.ac.jp  
Department of Ophthalmology and Micro-technology, Graduate School of Medicine, Yokohama City University, Yokohama, Japan

**Conflict of Interest:** Y. Yanagi — Consultant/Speaker for Astellas Pharmaceutical, Bayer Yakuhin Ltd, Roche/Chugai Pharmaceutical Co., Ltd., Novartis Pharma K.K., Boehringer Ingelheim Co., Ltd., Santen Pharmaceutical Co., Ltd., Senju Pharmaceutical Co.

**Funding Declaration:** Micron Co., Ltd. provided funding support to the development of the image analysis system.

**Author contributions:** Y.Y. wrote the main manuscript text and T.I. and M.I. prepared figures. All authors reviewed the manuscript.

---

## Key Messages

**What is known**
- Quantitative OCTA analysis of macular neovascularization (MNV) is limited by device- and field-of-view–dependent scaling of raw topological metrics, hindering cross-platform comparison.
- Qualitative MNV pattern labels (e.g., Medusa, Seafan, Dead tree) remain inconsistently defined and are rarely linked to reproducible quantitative thresholds.

**What is new**
- We present a semi-automated pipeline (hybrid vessel enhancement, adaptive binarization, skeleton-based topology) that generates stratum-specific standardized Vascular Complexity and Caliber Uniformity scores (0–100) for cross-device reporting.
- We provide operational, rule-based morphological categories with disclosed decision thresholds and report agreement with masked expert grading.
- Morphology-derived interpretive categories are proposed as hypothesis-generating labels; clinical outcome validation was outside the scope of this anonymized, treatment-naïve cohort.

---

## Abstract

**Purpose:**  
To introduce a novel semi-automated ImageJ-/Python-based pipeline for multi-dimensional analysis of macular neovascularization (MNV) on OCTA. The system is benchmarked against quantitative parameters from recent literature and provides standardized biomarkers together with rule-based morphological categorization and morphology-derived interpretive labels (hypothesis-generating; not clinically validated disease-behavior classes).

**Methods:**  
We developed an image-processing pipeline incorporating hybrid multiscale vessel enhancement (Frangi/tubeness and Laplacian of Gaussian filters), Phansalkar adaptive binarization, dynamic region-of-interest (ROI) refinement, and boundary-branch exclusion. The system generates a Standardized Vascular Complexity Score and a Standardized Caliber Uniformity Score (0–100), a Standardized Maturity Index, and rule-based labels for Medusa, Seafan, Glomerular, Tree in bud, and Dead tree patterns, with disclosed percentile and trunk-pattern thresholds. Morphology-derived interpretive categories (Active-pattern, Mature-quiescent-pattern, Transitional-pattern, Arteriolarized-pattern) are assigned from quantitative rules and published morphological criteria, without longitudinal clinical anchors. A total of 112 MNV lesions imaged on three OCTA platforms (Zeiss PlexElite 6×6 mm, Zeiss CIRRUS AngioPlex 3×3 mm, Optovue Solix 6×6 mm) were analyzed. Masked expert–automated morphological agreement was assessed on a stratified subset (n = 54). Inter-observer reproducibility was assessed with three operators on n = 46 lesions (ICC(2,1)); same-operator intra-observer test–retest was assessed as a supplement (n = 46). Between-stratum score differences were summarized with Kruskal–Wallis tests and ε² effect sizes with bootstrap 95% confidence intervals.

**Results:**  
Raw topological metrics differed substantially by device, precluding direct numerical comparison. Stratum-locked standardization (PCA for Network Complexity; device-/stratum-locked NV Diameter CV + Dilated vessel % for Caliber Uniformity) placed scores on a common 0–100 reporting scale for rule-based thresholds; because median-anchored piecewise mapping targets 50 by construction, median proximity to 50 is not evidence of biological equivalence across devices. Under the default Standardized Caliber Uniformity Score, Network Complexity, Caliber Uniformity, and Maturity Index did not differ significantly across strata (Kruskal–Wallis p = 0.425 / 0.572 / 0.582; ε² ≈ 0). Rule-based morphological categorization identified the spectrum of MNV subtypes across platforms. Agreement with masked expert grading was modest-to-moderate (overall agreement 57.4%; quadratic weighted κ = 0.507). Inter-observer ICC(2,1) was good for lesion area (0.859), Network Complexity (0.807), and Standardized Caliber Uniformity Score (0.770), and moderate for Maturity Index derived from that Caliber score (0.593). A legacy PCA-based Caliber Uniformity Score showed poorer concordance (ICC 0.434) and is retained only as a sensitivity comparison. Intra-observer agreement under the same device-locked Caliber/Maturity definition applied to both sessions was excellent (ICC ≥ 0.917).

**Conclusion:**  
This system provides a transparent platform for stratum-standardized quantification and rule-based morphological reporting of MNV architecture across OCTA platforms. Morphology-derived interpretive categories are hypothesis-generating. External, outcome-linked, and multi-center validation will be required before clinical decision-support claims are warranted.

---

## Introduction

Optical Coherence Tomography Angiography (OCTA) has transformed visualization of macular neovascularization (MNV) [1]. Translating qualitative observations into objective quantitative metrics remains challenging. Although general-purpose tools such as AngioTool perform well with high-contrast immunofluorescence images [2], they often struggle when applied to OCTA data, which are typically low in contrast and prone to imaging artifacts [3–5]. Variations in image quality across acquisition protocols and devices hinder accurate delineation of fine capillaries within dense MNV networks and yield inconsistent quantitative parameters across machines [6].

Another hurdle is characterization of vascular remodeling and the distinction between patterns consistent with active neovascularization versus mature, quiescent-appearing networks. Patterns such as “Medusa” and “Seafan” are widely recognized, yet their quantitative definition and clinical interpretation often vary [7,8]. The term “mature” is used inconsistently: sometimes for a well-organized but still active lesion (morphological maturity), and other times for a pruned vascular tree (interpreted as pathophysiological maturity in the literature) [1,7,8]. This ambiguity impedes standardized assessment and cross-study comparison.

This paper introduces a semi-automated system designed to improve transparency and reproducibility of MNV quantification. We compare our parameters with recent literature and detail a **rule-based morphological categorization** that maps Medusa, Seafan, Glomerular, Tree in bud, and Dead tree patterns using disclosed quantitative thresholds. Separately, we assign **morphology-derived interpretive categories** (Active-pattern, Mature-quiescent-pattern, Transitional-pattern, Arteriolarized-pattern). These interpretive labels are hypothesis-generating, based on quantitative morphology and published criteria [9]; they are **not** clinically validated disease-behavior classes in this anonymized, cross-sectional, treatment-naïve cohort. The framework uses standardized biomarkers (Standardized Vascular Complexity Score, Standardized Caliber Uniformity Score, Standardized Maturity Index) for within-stratum reporting and rule thresholds, rather than claiming device-independent biological equivalence.

---

## Methods

### Study Population and Acquisition Protocols

This study was approved by the Ethics Committee of the Yokohama City University Medical Center. The protocol adhered to the Declaration of Helsinki, and informed consent was obtained from all eligible patients. We included 112 MNV lesions imaged with three OCTA platforms and field-of-view configurations to establish a multi-device analysis framework for stratum-standardized scoring. The **large** group (n = 49) comprised 6×6 mm acquisitions on the Zeiss PlexElite 9000 (swept-source OCTA, 1060 nm). The **small_3mm** group (n = 30) comprised 3×3 mm acquisitions on the Zeiss CIRRUS HD-OCT with AngioPlex (spectral-domain OCTA, 840 nm). The **small** group (n = 33) comprised 6×6 mm acquisitions on the **Optovue Solix** (Optovue/Visionix; swept-source OCTA, 1060 nm).

All included eyes were **treatment-naïve** Type 1 or Type 2 MNV secondary to neovascular AMD, diagnosed by retinal specialists using structural OCT and multimodal imaging. Detailed demographic and clinical covariates (age, sex, laterality, visual acuity, finer lesion-type breakdown beyond Type 1/2, systemic factors) were **not retained** in the anonymized research archive and therefore cannot be tabulated by device group. The use of three hardware platforms—differing in manufacturer, OCTA modality, wavelength, scanning protocol, and field size—was intentional: it provides a multi-device setting in which to evaluate stratum-locked standardization for cross-device **reporting**, not a claim of biological interchangeability of raw metrics.

### Analytical Framework

The analytical framework was initially implemented as a comprehensive ImageJ macro and later in Python. The methodology comprised two parallel components: mapping quantitative biomarkers reported in the literature and developing a pipeline to compute and refine these metrics. A focused literature search identified studies reporting quantitative OCTA analyses of MNV; key parameters were extracted and several integrated scores were introduced, as described below.

The core pipeline operates after freehand delineation of the MNV lesion by the user. This input defines the ROI for subsequent automated processing (Figure 2; representative processing panels in Figure 3). The pipeline comprises the stages below.

### Artifact Mitigation and Spatial Organization

This stage addresses critical sources of error in existing analysis software.

1. **ROI refinement.** To reduce boundary artifacts, an iterative algorithm adjusts the user-drawn ROI. For five iterations, each vertex of the ROI polygon is evaluated within a 3-pixel radius and moved to the darkest pixel, pushing the boundary into non-perfused tissue so that the analytical boundary conforms more closely to the lesion edge.

2. **Hybrid multiscale vessel enhancement.** A combination of Frangi (tubeness) and Laplacian of Gaussian (LoG) filters accentuates vessels of varying calibers. Fusion of complementary filters can improve vessel detection relative to single-filter methods [10–12]. Frangi (scales 0.8–4.0) identifies tubular structures; LoG detects edges. Their combined use supports enhancement of complex, multi-scale MNV networks in low-contrast OCTA images.

3. **Binarization (Phansalkar vs global Otsu).** After Frangi/LoG enhancement, MNV vessel maps retain spatially heterogeneous background intensity arising from projection artifacts, signal attenuation, and lesion-internal contrast variation. **Global Otsu** thresholding assumes a bimodal intensity histogram with a single global cut-point and therefore tends to erode fine peripheral capillaries or, conversely, to include background speckles when lesion and background intensity distributions overlap. **Phansalkar** adaptive local thresholding estimates a local mean/SD-based threshold within a resolution-calibrated window (radius corresponding to 24 µm; k = 0.1, R = 0), preserving locally contrasted fine vessels while suppressing regional background drift. Although Phansalkar thresholding is widely recognized in choriocapillaris flow-deficit analysis, the same property—robustness to local intensity non-uniformity—is advantageous for enhanced MNV vessel maps on the outer-retina/avascular-complex slab. Our implementation follows the ImageJ Auto Local Threshold (Phansalkar) convention used in the original macro, facilitating reproducibility. We acknowledge that Otsu remains common for relatively homogeneous SCP/DCP en-face slabs; we preferred a local adaptive method for this MNV application.

4. **Post-processing and skeletonization.** The binary image is refined by morphological reconstitution and skeletonized to a one-pixel-wide centerline for topological analysis.

5. **Boundary-branch exclusion.** The refined ROI is divided into Center and Periphery zones. Branches existing solely within the Periphery or spanning both zones are flagged as boundary branches and excluded from calculations of average branch length, junction density, and tortuosity, limiting skew from incomplete peripheral vessels.

### Quantitative Analysis

This stage computes a comprehensive set of parameters, including major metrics identified in the literature review, and introduces integrated scores. Table 1 summarizes the quantitative parameters obtained in this study. To identify objectively dilated segments, the system uses a statistical threshold of mean + 2.0 × SD of all vessel diameters. Contiguous segments exceeding this threshold are flagged, and their count, length, and density are reported as an adaptive measure of caliber remodeling.

### Standardized Score Computation

#### Standardized Vascular Complexity Score (0–100)

The score was derived using principal component analysis (PCA) of four topological metrics from the skeletonized MNV network: inverse Euler number (−Euler_total), total loop count, junction density, and global fractal dimension. Reference distributions were constructed independently for each acquisition stratum (large, small_3mm, small). Features were standardized using stratum-specific means and standard deviations prior to PCA. The dominant first principal component (PC1), with uniformly positive loadings across all four metrics, explained 63.7%, 73.9%, and 70.2% of total variance for the large, small_3mm, and small strata, respectively. A secondary component (PC2, loading primarily on junction density) captured residual variance (24.8%, 21.9%, and 22.3%). PC1 and PC2 scores were combined with a trunk-distribution placeholder (TrunkDist; fixed at 50 in the absence of device-specific calibration) using weights 0.7, 0.2, and 0.1. To place scores on a common 0–100 **reporting** scale within each stratum, PC1 and PC2 were independently subjected to piecewise-linear normalization in which the within-stratum median maps to 50, the stratum minimum to 0, and the stratum maximum to 100. This procedure is a within-stratum scaling step for rule-based thresholds; it is **not** a demonstration of cross-device biological equivalence.

#### Standardized Caliber Uniformity Score (0–100)

*(Default / primary Caliber Uniformity endpoint in this revision; formerly also referred to as Vascular Stability Score.)*  
Vascular caliber uniformity was quantified from two skeleton-derived morphometric features already exported by the pipeline: (1) the coefficient of variation of neovascular vessel diameter (**NV Diameter CV**); and (2) the fraction of dilated vessel length (**Dilated vessel %**; segments exceeding mean + 2.0 × SD of vessel diameters). For each acquisition stratum (`large`, `small`, `small_3mm` — corresponding to Zeiss PlexElite 6×6 mm, Optovue Solix 6×6 mm, and Zeiss CIRRUS AngioPlex 3×3 mm), reference min/median/max cuts for both features were locked from the manuscript reference cohorts and were not re-estimated on analysis batches or on the ICC pool. Each feature was converted to a uniformity axis by piecewise-linear scaling of its negated value (−NV Diameter CV; −Dilated vessel fraction) so that the stratum minimum, median, and maximum map to 0, 50, and 100, respectively (higher score = more uniform caliber / fewer dilated extremes as operationalized). The Standardized Caliber Uniformity Score was then defined as

Score = clip(0.75 × U(−NV Diameter CV) + 0.25 × U(−Dilated vessel %), 0, 100),

where U(·) denotes the stratum-locked piecewise map. Weights (0.75 / 0.25) emphasize global diameter dispersion while retaining an independent dilated-fraction axis. Where the manuscript refers conceptually to “stability,” this denotes caliber uniformity as operationalized by this default score. A **PCA-based Caliber Uniformity Score (legacy)** based on four radial-profile metrics is retained only as a sensitivity comparison for inter-observer concordance (Results) and is **not** the default Caliber Uniformity endpoint in this revision.

#### Standardized Maturity Index (0–100)

The Standardized Maturity Index was defined as:

Maturity Index = clip(50 + (Caliber Uniformity Score − Complexity Score) / 2, 0, 100).

This formulation encodes the morphological notion that higher caliber uniformity relative to network complexity yields higher index values; values above 50 indicate a uniformity-dominant pattern and values below 50 a complexity-dominant pattern. In this revision these are treated as **morphology-derived** descriptors, not as confirmed clinical maturity or quiescence.

### Rule-Based Morphological Categorization and Morphology-Derived Interpretive Categories

**Level 1 — morphological subtypes (operational five-class scheme).**  
Using stratum-specific reference percentiles of the Standardized Vascular Complexity Score and the trunk pattern (MEDUSA / SEAFAN / INTERMEDIATE) derived from spatial organization of large-caliber segments, lesions are labeled in priority order as:

| Subtype | Decision rule (summary) |
|---------|-------------------------|
| Dead tree | Complexity Score &lt; stratum P10 |
| Medusa | Trunk pattern MEDUSA and Complexity Score ≥ stratum P65 |
| Seafan | Trunk pattern SEAFAN and Complexity Score ≥ stratum P40 |
| Glomerular | Complexity Score ≥ stratum P30 (trunk-independent) |
| Tree in bud | Remainder (typically intermediate trunk / mid-low complexity) |

Exact stratum percentile cut-points are taken from the locked reference files used by the classifier and are summarized in Supplementary Table S1. For the small (Optovue Solix) stratum, the Complexity percentile locking cohort has n = 34, whereas the primary analysis batch used for Table 3 has n = 33; locked cut-points were not re-estimated on the analysis batch. Spelling is standardized to **Tree in bud**. Categories such as “Pruned tree” or “Large vessels” are **not** part of this operational scheme.

**Level 2 — morphology-derived interpretive categories (hypothesis-generating).**  
Separately, rule-based labels Active-pattern, Mature-quiescent-pattern, Transitional-pattern, and Arteriolarized-pattern are assigned from Maturity Index, Caliber Uniformity Score, and arteriolarization indicators (segment count, junction density, loop count, mean diameter relative to stratum percentiles), informed by published morphological criteria [9]. These labels are **not** anchored to fluid status, treatment response, or longitudinal outcomes in this dataset and must not be interpreted as validated pathophysiological disease states.

### Expert–Automated Agreement Assessment

A retinal specialist (Y.Y.) performed **masked morphological grading** on a stratified subset of study OCTA images (**n = 54**; stratum allocation 24 / 16 / 14 for large / small / small_3mm; random seed `20260727`), without access to automated subtype labels at the time of grading. Expert grades were compared with rule-based automated labels. Overall percent agreement and quadratic weighted Cohen’s κ were computed with ordinal order Dead tree → Tree in bud → Glomerular → Seafan → Medusa; bootstrap 95% CIs used 10 000 resamples (seed `20260727`). The confusion matrix is provided in Supplementary Material. For the small stratum, some automated subtypes were score-rederived from disclosed classifier rules when the batch CSV lacked a Subtype column. This analysis is expert–algorithm agreement, **not** multi-human inter-grader κ, and is framed as an agreement assessment rather than definitive validation.

### Reproducibility: Inter- and Intra-Observer ICC

Because the pipeline depends on freehand ROI delineation, operator variability was quantified.

**Inter-observer (primary multi-rater claim).** Three independent operators—the original analyst (YY) and two external examiners (Inoue and Osada)—each performed freehand ROI delineation on the same lesions. Complete three-observer data were available for **n = 46** cases. Automated processing after ROI delineation was identical across observers. All images were Angiography 3×3 mm acquisitions on Zeiss CIRRUS AngioPlex (`small_3mm` stratum).

We quantified reproducibility with multi-rater **ICC(2,1)** under a two-way random-effects model for absolute agreement, single measures [32,33]. Primary endpoints were MNV area, Network Complexity Score, the default Standardized Caliber Uniformity Score (CIRRUS/`small_3mm` locked piecewise cuts), and Maturity Index recomputed from that Caliber score. Pairwise ICCs and a multilevel variance-component ICC were reported as complementary summaries. Interpretive bands for continuous clinical measurements (poor &lt;0.50; moderate 0.50–0.75; good 0.75–0.90; excellent &gt;0.90) follow published guidance [34].

As methodological **sensitivity analyses**, we additionally evaluated (i) the **PCA-based Caliber Uniformity Score (legacy)** (primary in the original submission), (ii) a robust Winsorized NV-CV proxy, and (iii) a pooled soft CV+Dilated% variant re-estimated on the ICC pool. These alternate scores contextualize concordance under different operationalizations and do **not** replace the default device-locked Standardized Caliber Uniformity Score.

**Intra-observer (supplement).** The original analyst (YY) repeated freehand ROI delineation on the same **n = 46** lesions in a separate sitting. Session exports initially mixed legacy PCA and current default Caliber definitions across sittings; unharmonized default Caliber/Maturity columns are therefore not comparable and are **not** reported. For Caliber Uniformity and Maturity Index in this intra comparison, we report the **same device-locked definition applied to both sessions** (the default Standardized Caliber Uniformity Score used as the primary inter-observer Caliber endpoint), alongside Area and Network Complexity (unchanged definitions). Intra-observer estimates supplement, and do not replace, the three-observer ICCs.

### Statistical Analysis

Between-stratum differences in standardized scores were assessed with the Kruskal–Wallis test. Effect size was summarized as ε² = (H − k + 1) / (n − k) with k = 3, and bootstrap 95% CIs (10 000 within-stratum resamples; seed `20260727`). Absence of a statistically significant Kruskal–Wallis test was **not** interpreted as equivalence. Formal TOST equivalence testing was considered; because clinically meaningful equivalence margins for these novel 0–100 scores were not pre-specified at study design, we prioritized effect sizes with CIs and cautious interpretation rather than post-hoc TOST with arbitrary margins. Agreement analyses and ICC methods are described above. Analyses were performed in Python 3.11 (scikit-learn for PCA; SciPy / pingouin for tests and ICC). A p-value &lt; 0.05 was considered statistically significant for omnibus Kruskal–Wallis tests, without claiming equivalence when p ≥ 0.05.

---

## Results

### Robust Segmentation and Artifact Mitigation

Representative OCTA images indicate that the system provides consistent segmentation of MNV lesions, with the semi-automatically delineated lesion area highlighted and dilated neovascular segments marked (Figure 1). In these examples, the segmented neovascular network follows lesion architecture rather than spurious high-contrast boundaries. The ROI refinement algorithm reduces boundary artifacts by adjusting user-drawn ROIs toward the non-perfused tissue border. Boundary-branch exclusion further limits the contribution of incomplete peripheral vessel segments to topological and morphometric metrics. The end-to-end processing workflow is summarized in Figure 2; representative intermediate panels (Frangi enhancement, Phansalkar binarization, skeletonization) are shown in Figure 3.

### Cross-Device Raw Metrics and the Necessity of Standardization

Table 2 presents raw topological and morphometric parameters across the three acquisition protocols (mean ± SD; original submission cohort, n = 112). As expected from differences in imaged vascular territory and device-specific resolution, raw metrics differed substantially across platforms. Mean total loop count (center + periphery) ranged from 300.3 ± 199.2 in the large (PlexElite 6×6 mm) group to 165.2 ± 118.0 in the small_3mm (CIRRUS AngioPlex / HD series 3×3 mm) group and 89.5 ± 53.4 in the small (Optovue Solix 6×6 mm) group—a 3.4-fold difference between the highest and lowest values. Mean Euler number (center + periphery) ranged from −168.4 ± 146.0 to −61.6 ± 48.2, and mean junction density from 25.85 ± 1.77 to 15.89 ± 2.88 mm⁻². Mean skeleton-derived vessel diameter showed the reverse ordering (16.0, 23.7, and 32.3 µm for large, small_3mm, and small, respectively). These systematic differences confirm that direct cross-device comparison of raw parameters is not feasible and motivate stratum-locked standardization for a shared reporting scale.

### Stratum-Standardized Scores: Reporting Scale, Not Biological Equivalence

Table 3 presents standardized scores after stratum-locked normalization, together with Kruskal–Wallis statistics and ε² effect sizes (primary batch CSVs, n = 112: large = 49, small = 33, small_3mm = 30). Network Complexity uses stratum-specific PCA with piecewise-linear PC scaling (PC1 explained variance 63.7% / 73.9% / 70.2% for large / small_3mm / small). Caliber Uniformity uses the **default** Standardized Caliber Uniformity Score (device-/stratum-locked NV Diameter CV + Dilated vessel %); Maturity Index is recomputed from that Caliber score and Complexity. Piecewise-linear normalization maps each stratum’s locking-cohort median toward 50 **by design** on the scaled axes; therefore median values near 50 after normalization are a mathematical consequence of the transform and **must not** be interpreted as empirical proof that device-dependent scaling was removed while “preserving biological information,” nor as evidence that scores are biologically equivalent or statistically indistinguishable across strata.

**Interpretation.** Under the default Standardized Caliber Uniformity Score, none of the three standardized scores differed significantly across strata (Complexity median 48.7 / 50.7 / 47.8, H = 1.712, p = 0.425, ε² = 0.000 [95% CI 0.000–0.089]; Caliber Uniformity 46.6 / 55.5 / 50.6, H = 1.118, p = 0.572, ε² = 0.000 [0.000–0.082]; Maturity Index 49.5 / 53.9 / 51.0, H = 1.082, p = 0.582, ε² = 0.000 [0.000–0.077]; medians ordered large / small / small_3mm). This pattern differs from the **PCA-based Caliber Uniformity Score (legacy)**, which had shown significant between-stratum Caliber/Maturity differences on the same cases; that legacy finding is not used as the primary endpoint here. Median-anchored normalization still places scores on a common 0–100 scale for rule thresholds and **must not** be read as biological equivalence across devices. High and consistent PC1 explained-variance ratios for Network Complexity (63.7–73.9%) remain informative regarding within-stratum latent topological structure.

### Rule-Based Morphological Categorization and Expert Agreement

Table 4 presents the distribution of morphological subtypes across acquisition platforms (original submission tables, n = 112). The spectrum of MNV subtypes was identified across the three devices. Glomerular pattern was the most prevalent subtype in the large group (n = 29, 59.2%) and was also well-represented in the small_3mm and small groups (30.0% and 36.4%, respectively). Medusa pattern was observed only in the large group (n = 6, 12.2%). Seafan pattern was more common in the small_3mm group (n = 11, 36.7%) than in the small group (n = 2, 6.1%) and was absent in the large group. Dead tree pattern was identified in all three groups (8.2%, 20.0%, and 15.2%). Tree in bud pattern was present in all groups (20.4%, 13.3%, 42.4%). Between-platform differences in subtype prevalence may reflect sampling, case-mix, and FOV-dependent lesion sampling rather than classifier instability alone. Table 5 summarizes the morphology-derived interpretive mapping for the five operational subtypes (hypothesis-generating; not clinically validated disease-behavior classes).

On the masked expert subset (n = 54), overall agreement between expert and automated labels was **57.4%** (31/54); quadratic weighted Cohen’s κ was **0.507** (95% CI **0.222–0.714**). When Glomerular and Seafan were merged on both sides (4-class sensitivity), agreement rose to **75.9%** (41/54) and κ to **0.682** (95% CI **0.400–0.852**), suggesting that a substantial fraction of discordance reflects adjacent descriptive subtypes that are difficult to separate visually. We interpret modest-to-moderate κ as partly reflecting limitations of subjective categorical OCTA morphological grading [8], rather than solely algorithmic failure; related work indicates that qualitative assessments can be less reliable across raters than quantitative OCTA metrics [26], and categorical MNV typing between angiography- and OCT-based systems may show only moderate agreement [27]. Rule-based quantitative operationalization with disclosed thresholds is intended to reduce rater-dependent ambiguity relative to purely descriptive labels; we do **not** claim that the algorithm replaces expert judgment.

### Inter- and Intra-Observer Reproducibility

**Primary inter-observer ICC(2,1) (3 raters, n = 46):**

| Metric | ICC(2,1) | 95% CI |
|--------|----------|--------|
| MNV Area (mm²) | 0.859 | 0.680–0.930 |
| Network Complexity Score | 0.807 | 0.660–0.890 |
| Caliber Uniformity Score | 0.770 | 0.660–0.860 |
| Maturity Index | 0.593 | 0.430–0.730 |

Lesion area, Network Complexity, and the default Standardized Caliber Uniformity Score showed good inter-observer agreement on conventional ICC benchmarks [34]; Maturity Index derived from that Caliber score was moderate. Adopting the device-locked Caliber definition improved Caliber concordance relative to the legacy PCA composite but did not improve Maturity ICC relative to the legacy PCA-based Maturity Index (0.659), consistent with imperfect alignment between the default and prior Caliber constructs.

**Sensitivity (inter-observer, disclosed alternate Caliber scores, n = 46):** PCA-based Caliber Uniformity Score (legacy) ICC 0.434 (0.260–0.610; **poor-to-moderate** on conventional benchmarks [34]); robust CV proxy 0.765 (0.640–0.860); pooled soft CV+Dilated% variant 0.838 (0.750–0.900). The poorer PCA concordance motivated adoption of the device-locked Standardized Caliber Uniformity Score as the default operational definition in this revision; the pooled soft variant remains a within-study sensitivity score that re-fits on the ICC pool and is therefore less transferable than the locked reference cuts.

**Intra-observer (YY Session 1 vs Session 2, n = 46; same device-locked Caliber/Maturity definition applied to both sessions):**

| Metric | ICC(2,1) | 95% CI |
|--------|----------|--------|
| MNV Area (mm²) | 0.979 | 0.962–0.988 |
| Network Complexity Score | 0.950 | 0.913–0.973 |
| Caliber Uniformity Score | 0.925 | 0.871–0.959 |
| Maturity Index | 0.917 | 0.857–0.954 |

Within-rater agreement was excellent under this fixed score definition; these estimates supplement the primary multi-rater claim.

---

## Discussion

This work advances quantitative MNV analysis by combining hybrid vessel enhancement, adaptive binarization, skeleton-based topology, and stratum-standardized multi-parameter scores with disclosed rule-based morphological categories. Our metric inventory (Table 1) illustrates that while existing tools and recent studies provide a foundational set of metrics, they often fail to capture the holistic nature of the neovascular complex and remain vulnerable to methodological artifacts.

A central feature of the present system is generation of **stratum-standardized reporting scores** across different acquisition conditions. In contrast to tools that report only raw, device-specific metrics unsuitable for shared numerical thresholds, the framework produces three standardized scores—Standardized Vascular Complexity Score (stratum-specific PCA), Standardized Caliber Uniformity Score (device-/stratum-locked NV Diameter CV + Dilated vessel %), and Standardized Maturity Index (from Caliber − Complexity)—on a common 0–100 scale **within each stratum**. We emphasize, correcting an overstatement in the original submission, that median proximity to 50 after median-anchored piecewise scaling is **circular** with respect to biological equivalence across devices [6]. Non-circular elements that remain informative include: (i) large between-device differences in raw metrics (Table 2); (ii) consistency of Complexity PCA structure (PC1 loadings and explained variance) across strata; and (iii) within-stratum score distributions in relation to morphological categories and expert comparison. Re-analysis under the default Standardized Caliber Uniformity Score shows no significant between-stratum differences for Complexity, Caliber Uniformity, or Maturity Index (ε² ≈ 0)—a pattern that must still not be conflated with proven biological equivalence, because median-anchored transforms and locked reference cuts can attenuate stratum-mean contrasts by construction. Prior work has shown that quantitative vascular metrics are often not interchangeable across OCTA devices/algorithms without device-aware reporting [6,28,29]. The poorer inter-observer concordance of the **PCA-based Caliber Uniformity Score (legacy)** (ICC 0.434; poor-to-moderate) further motivated adopting the more ROI-stable device-locked Standardized Caliber Uniformity Score as the default Caliber endpoint in this revision.

Several methodological aspects merit emphasis. The ROI refinement algorithm addresses a long-standing challenge in quantitative OCTA analysis [7,13–15] by encouraging the ROI boundary to lie in non-perfused tissue. The Euler number and loop count remain core elements of the Vascular Complexity construct because they quantify connectivity and mesh-like organization [16–18]. Immature, angiogenesis-dominant networks often appear as dense, highly interconnected plexuses [19]; markedly negative Euler numbers with elevated loop counts are therefore useful morphological biomarkers of complexity-dominant architecture. Terms such as “dead tree,” “tree in bud,” “medusa,” “sea fan,” and “glomerular” have previously been applied in a primarily descriptive manner [8,20,21]. The present framework supplies operational definitions with disclosed thresholds. We have removed inconsistent literature-only labels (e.g., “Pruned tree,” “Large vessels”) from Table 5 so that Table 4, Table 5, and the classification Methods remain aligned on the five-subtype operational scheme.

We also address terminological ambiguity around maturation, arterialization, and abnormalization [22–25]. Our morphology-derived interpretive categories map quantitative patterns onto labels informed by published criteria, including arteriolarization-segment detection and caliber-uniformity scores related to the unstable vascular state described by Spaide as abnormalization [25]. In this revision these are explicitly **hypothesis-generating** and are not claimed to improve clinical decision-making or prognostic stratification pending outcome-linked studies.

Masked expert–automated agreement (κ = 0.507) was modest-to-moderate. Rather than framing this solely as algorithmic failure, we note that qualitative OCTA pattern labels remain partly descriptive and ambiguous [8], that qualitative assessments can be less reliable than quantitative metrics [26], and that categorical MNV typing across imaging systems may show only moderate agreement [27]. Quantitative operationalization with disclosed rules is therefore motivated as a transparency and reproducibility aid relative to purely visual labels. Related quantitative OCTA biomarker work further supports objectifying morphology and activity descriptors [30,31].

### Limitations

Several limitations warrant explicit statement.

1. **Circularity of median-anchored normalization.** Piecewise-linear mapping of each stratum’s locking-cohort median toward 50 cannot demonstrate biological equivalence across devices; absence of significant Kruskal–Wallis differences under the default Standardized Caliber Uniformity Score likewise does not establish interchangeability of scores across platforms.

2. **Absence of longitudinal clinical anchors.** This anonymized, cross-sectional, treatment-naïve dataset lacks fluid status, treatment response, and outcome data; morphology-derived interpretive categories are not clinically validated.

3. **Anonymized cohort without detailed baseline demographics.** Covariates cannot be tabulated by device group; between-platform subtype prevalence differences (Table 4) may reflect case-mix and FOV sampling, limiting causal interpretation of cross-device score comparisons.

4. **Reproducibility scope.** Primary multi-rater reproducibility is the three-observer ICC on n = 46 (single FOV stratum). Default Standardized Caliber Uniformity Score ICC (0.770) is good on conventional benchmarks [34]; Maturity Index derived from that Caliber score remains moderate (0.593) and was not improved relative to the legacy PCA-based Maturity Index. The **PCA-based Caliber Uniformity Score (legacy)** (ICC 0.434; poor-to-moderate) is retained only as a sensitivity comparison. Intra-observer Caliber/Maturity ICCs under the same device-locked definition applied to both sessions are excellent but supplement rather than replace inter-observer results. Multi-device ICC spanning all three platforms was not available for this revision.

5. **Expert–algorithm agreement caveats.** Comparison contrasts full-image visual grades with ROI-metric–derived rule classes; perfect concordance is not expected. This is not multi-human inter-grader κ.

6. **External validation.** Multi-center external validation on independent cohorts and scanners is needed before broader generalizability claims.

7. **Equivalence testing.** Formal TOST was not performed because clinically meaningful margins for these novel scores were not pre-specified.

---

## Conclusion

We have developed a semi-automated ImageJ-/Python-based system for multi-dimensional analysis of macular neovascularization that addresses several methodological limitations of existing tools, incorporates established biomarkers from recent literature, and introduces integrated scores for complexity, caliber uniformity, and a morphology-derived maturity index. The system provides stratum-standardized scoring for cross-device **reporting**, disclosed rule-based morphological categorization with expert-agreement assessment, and hypothesis-generating morphology-derived interpretive labels. It does **not** establish device-independent biological equivalence of standardized scores, nor clinically validated pathophysiological disease states. With further outcome-linked and multi-center evaluation, these quantitative tools may support more reproducible research on MNV architecture in neovascular AMD.

---

## References

1. Guo, J., Tang, W., Xu, S., Liu, W. & Xu, G. OCTA evaluation of treatment-naïve flat irregular PED (FIPED)-associated CNV in chronic central serous chorioretinopathy before and after half-dose PDT. *Eye* 35, 2871–2878 (2021).
2. Zudaire, E., Gambardella, L., Kurcz, C. & Vermeren, S. A Computational Tool for Quantitative Analysis of Vascular Networks. *PLOS ONE* 6, e27385 (2011).
3. Told, R. et al. Profiling neovascular age-related macular degeneration choroidal neovascularization lesion response to anti-vascular endothelial growth factor therapy using SSOCTA. *Acta Ophthalmol. (Copenh.)* 99, e240–e246 (2021).
4. Montesel, A. et al. Quantitative response of macular neovascularisation to loading phase of aflibercept in neovascular age-related macular degeneration. *Eye* 37, 3648–3655 (2023).
5. Carlà, M. M. et al. MORPHOMETRIC CHANGES IN MACULAR NEOVASCULARIZATION ARCHITECTURE AFTER FARICIMAB TREATMENT IN NEOVASCULAR AGE-RELATED MACULAR DEGENERATION: Comparison Between Naive and Switched Eyes. *Retina* 125–135 (2026) doi:10.1097/iae.0000000000004635.
6. Munk, M. R. et al. OCT-angiography: A qualitative and quantitative comparison of 4 OCT-A devices. *PLOS ONE* 12, e0177059 (2017).
7. Miere, A. et al. VASCULAR REMODELING OF CHOROIDAL NEOVASCULARIZATION AFTER ANTI-VASCULAR ENDOTHELIAL GROWTH FACTOR THERAPY VISUALIZED ON OPTICAL COHERENCE TOMOGRAPHY ANGIOGRAPHY. *Retina* 39, 548–557 (2019).
8. Tew, T. B. et al. Comparison of different morphologies of choroidal neovascularization evaluated by ocular coherence tomography angiography in age-related macular degeneration. *Clin. Experiment. Ophthalmol.* 48, 927–937 (2020).
9. Coscas, F. et al. Optical coherence tomography angiography in exudative age-related macular degeneration: A predictive model for treatment decisions. *Br. J. Ophthalmol.* 103, 1342–1356 (2019).
10. Oliveira, W. S., Teixeira, J. V., Ren, T. I., Cavalcanti, G. D. C. & Sijbers, J. Unsupervised Retinal Vessel Segmentation Using Combined Filters. *PLoS ONE* 11, e0149943 (2016).
11. Ma, Y. et al. Multichannel Retinal Blood Vessel Segmentation Based on the Combination of Matched Filter and U-Net Network. *BioMed Res. Int.* 2021, 5561125 (2021).
12. Memari, N., Ramli, A. R., Bin Saripan, M. I., Mashohor, S. & Moghbel, M. Supervised retinal vessel segmentation from color fundus images based on matched filtering and AdaBoost classifier. *PLoS ONE* 12, e0188939 (2017).
13. Wang, M. et al. Evaluating Polypoidal Choroidal Vasculopathy With Optical Coherence Tomography Angiography. *Investig. Opthalmology Vis. Sci.* 57, OCT526-32 (2016).
14. Xue, J. et al. Automatic quantification of choroidal neovascularization lesion area on OCT angiography based on density cell-like P systems with active membranes. *Biomed. Opt. Express* 9, 3208–3219 (2018).
15. Babiuch, A. et al. IMPACT OF OPTICAL COHERENCE TOMOGRAPHY ANGIOGRAPHY REVIEW STRATEGY ON DETECTION OF CHOROIDAL NEOVASCULARIZATION. *Retina* 672–678 (2020) doi:10.1097/iae.0000000000002443.
16. Smith, A. & Zavala, V. The Euler characteristic: A general topological descriptor for complex data. *Comput Chem Eng* 154, 107463 (2021).
17. Willführ, A. et al. Estimation of the number of alveolar capillaries by the Euler number (Euler-Poincaré characteristic). *Am. J. Physiol. Lung Cell. Mol. Physiol.* 309, L1286-93 (2015).
18. Santos, F. et al. Topological phase transitions in functional brain networks. *bioRxiv* https://doi.org/10.1101/469478 (2018) doi:10.1101/469478.
19. Viallard, C. & Larrivée, B. Tumor angiogenesis and vascular normalization: alternative therapeutic targets. *Angiogenesis* 20, 409–426 (2017).
20. Goker, Y. S. & Demir, G. Comparison of optical coherence tomography angiography features in type 1 versus type 2 choroidal neovascular membranes secondary to age-related macular degeneration. *Med. Hypothesis Discov. Innov. Ophthalmol. J.* 10, 67–73 (2021).
21. Li, J. et al. Comparative quantitative analysis of optical coherence tomography angiography in varied morphologies of macular neovascularization following intravitreal conbercept and ranibizumab treatments for neovascular age‑related macular degeneration. *Exp. Ther. Med.* 27, 214 (2024).
22. Mettu, P. S., Allingham, M. J. & Cousins, S. W. Incomplete response to Anti-VEGF therapy in neovascular AMD: Exploring disease mechanisms and therapeutic opportunities. *Prog. Retin. Eye Res.* 82, 100906 (2021).
23. Attarde, A., Riad, T., Zhang, Z., Ahir, M. & Fu, Y. Characterization of Vascular Morphology of Neovascular Age-Related Macular Degeneration by Indocyanine Green Angiography. *J. Vis. Exp. JoVE* 198, (2023).
24. Fu, Y., Zhang, Z., Webster, K. & Paulus, Y. Treatment Strategies for Anti-VEGF Resistance in Neovascular Age-Related Macular Degeneration by Targeting Arteriolar Choroidal Neovascularization. *Biomolecules* 14, 252 (2024).
25. Spaide, R. Optical Coherence Tomography Angiography Signs of Vascular Abnormalization With Antiangiogenic Therapy for Choroidal Neovascularization. *Am. J. Ophthalmol.* 160, 6–16 (2015).
26. Shah, P. N. et al. Inter-rater reliability of proliferative diabetic retinopathy assessment on wide-field OCT-angiography and fluorescein angiography. *Transl. Vis. Sci. Technol.* 12(7), 13 (2023).
27. Deák, G. G. et al. Comparison of optical coherence tomography vs. fluorescein angiography-based macular neovascularization classifications in age-related macular degeneration. *Sci. Rep.* 15, 87576 (2025) doi:10.1038/s41598-025-87576-6.
28. Corvi, F. et al. Reproducibility of vessel density, fractal dimension, and foveal avascular zone using 7 different optical coherence tomography angiography devices. *Am. J. Ophthalmol.* 186, 25–31 (2018).
29. Corvi, F. et al. Comparison between several optical coherence tomography angiography devices and indocyanine green angiography of choroidal neovascularization. *Retina* 40, 873–880 (2020).
30. Gan, Y. et al. Novel quantitative OCTA biomarkers of choroidal neovascularization and associations with disease activity and etiology. *Transl. Vis. Sci. Technol.* 15(3), 10 (2026).
31. Hsu, C. R. et al. Combined quantitative and qualitative optical coherence tomography angiography biomarkers for predicting active neovascular age-related macular degeneration. *Sci. Rep.* 11, 18068 (2021).
32. Shrout, P. E. & Fleiss, J. L. Intraclass correlations: uses in assessing rater reliability. *Psychol. Bull.* 86, 420–428 (1979).
33. McGraw, K. O. & Wong, S. P. Forming inferences about some intraclass correlation coefficients. *Psychol. Methods* 1, 30–46 (1996).
34. Koo, T. K. & Li, M. Y. A guideline of selecting and reporting intraclass correlation coefficients for reliability research. *J. Chiropr. Med.* 15, 155–163 (2016).

<!-- Author note: Duplicate Tew et al. 2020 (former refs 8 and 22) removed; list renumbered. Shah/Deák/Corvi/Gan/Hsu added per Response. Corvi CNV device comparison: 2019 epub / 2020 print (Retina 40:873–880). ICC typology/forms [32,33] and interpretation bands [34] added for inter-observer Methods (Crossref-verified; not present in local Zotero library at edit time). Tables 1–5 and Figure 1–3 legends are provided as separate submission files (original packaging convention), not embedded in this manuscript body. -->
