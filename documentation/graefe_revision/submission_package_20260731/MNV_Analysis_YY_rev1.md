# Novel Semi-Automated System for Multi-Dimensional Analysis of Macular Neovascularization: Quantitative Biomarkers and Rule-Based Morphological Categorization Across OCTA Platforms



Yasuo Yanagi, Maiko Maruyama-Inoue, Tatsuya Inoue and Kazuaki Kadonosono

Department of Ophthalmology and Micro-Technology, Yokohama City University, 4-57 Urafune, Minami-ku, Yokohama, Kanagawa, 232-0024, Japan.



Correspondence:

Yasuo Yanagi

yanagi.yas.wu@yokohama-cu.ac.jp

Department of Ophthalmology and Micro-technology, Graduate School of Medicine, Yokohama City University, Yokohama, Japan





Conflict of Interest: 

Y. Yanagi - Consultant/Speaker for Astellas Pharmaceutical, Bayer Yakuhin Ltd, Roche/Chugai Pharmaceutical Co., Ltd., Novartis Pharma K.K., Boehringer Ingelheim Co., Ltd., Santen Pharmaceutical Co., Ltd., Senju Pharmaceutical Co.



Funding Declaration:

Micron Co., Ltd. provided funding support to the development of the image analysis system.



Author contributions:

Y.Y. wrote the main manuscript text and T.I. and M.I. prepared figures. All authors reviewed the manuscript.



## Key Messages

What is known

Quantitative OCTA analysis of macular neovascularization (MNV) is limited by device- and field-of-view–dependent scaling of raw topological metrics, hindering cross-platform comparison.

Qualitative MNV pattern labels (e.g., Medusa, Seafan, Dead tree) remain inconsistently defined and are rarely linked to reproducible quantitative thresholds.

What is new

We present a semi-automated pipeline (hybrid vessel enhancement, adaptive binarization, skeleton-based topology) that generates stratum-specific standardized Vascular Complexity and Caliber Uniformity Scores (0–100) for cross-device reporting.

We provide operational, rule-based morphological categories with disclosed decision thresholds and report agreement with masked expert grading.

Morphology-derived interpretive categories are proposed as hypothesis-generating labels; clinical outcome validation was outside the scope of this anonymized, treatment-naïve cohort.



## Abstract

Purpose: To develop and validate a novel semi-automated Python-based pipeline for multi-dimensional analysis of macular neovascularization (MNV) on optical coherence tomography angiography (OCTA) images. The system provides standardized biomarkers, rule-based morphological categorization, and morphology-derived interpretive labels. It also incorporates an automated morphological classification scheme to objectively distinguish active, mature quiescent, transitional, and arteriolarized states.

Methods: We developed an advanced image-processing pipeline incorporating hybrid multiscale vessel enhancement using Frangi/tubeness and Laplacian of Gaussian filters, Phansalkar adaptive binarization, dynamic region-of-interest refinement, and boundary-branch exclusion. The system generates a Standardized Vascular Complexity Score, a Standardized Caliber Uniformity Score, and a Standardized Maturity Index on a 0–100 scale, and performs rule-based classification into Medusa, Seafan, Glomerular, Tree in bud, and Dead tree patterns using predefined percentile and trunk-pattern thresholds. Morphology-derived interpretive categories - Active-pattern, Mature-quiescent-pattern, Transitional-pattern, and Arteriolarized-pattern - were assigned using quantitative thresholds and published morphological criteria. A total of 112 MNV lesions acquired on three OCTA platforms (Zeiss PlexElite 6×6 mm, Zeiss CIRRUS AngioPlex HD 3×3 mm, and Optovue Solix 6×6 mm) were analyzed. Masked expert–automated morphological agreement was assessed in a stratified subset (n = 54). Inter-observer reproducibility was evaluated with three operators in 46 lesions using ICC(2,1), and same-operator intra-observer test–retest reproducibility was assessed as a supplement (n = 46). Between-stratum score differences were summarized using Kruskal–Wallis tests and ε² effect sizes with bootstrap 95% confidence intervals.

Results: Raw topological metrics differed substantially by device, precluding direct numerical comparison. Device-specific standardization using principal component analysis and piecewise-linear normalization yielded convergent standardized Complexity, Caliber Uniformity, and Maturity scores on a common 0–100 reporting scale across devices, with median values of approximately 50. Under this standardized framework, Complexity Score, Caliber Uniformity Score, and Maturity Index did not differ significantly across strata (Kruskal–Wallis p = 0.425, 0.572, and 0.582, respectively; ε² ≈ 0). Automated morphological classification identified the full spectrum of MNV subtypes across all platforms. Agreement with masked expert grading was modest to moderate, with an overall agreement of 57.4% and a quadratic weighted κ of 0.507. Inter-observer ICC(2,1) was good for lesion area (0.859), Complexity Score (0.807), and Standardized Caliber Uniformity Score (0.770), and moderate for the Maturity Index derived from the Caliber score (0.593).

Conclusion: This system provides a transparent and robust platform for quantification and rule-based morphological reporting of MNV architecture across OCTA platforms, establishing a common framework for comparative analysis. Future outcome-linked and multi-center evaluations will be required to establish clinical utility. By integrating morphological patterns with quantitative biomarkers and automated classification, the system enables objective differentiation of active angiogenesis from mature remodeling.



## Introduction

Optical Coherence Tomography Angiography (OCTA) has transformed visualization of macular neovascularization (MNV) [1]. Translating qualitative observations into objective quantitative metrics remains challenging. Although general-purpose tools such as AngioTool perform well with high-contrast immunofluorescence images [2], they often struggle when applied to OCTA data, which are typically low in contrast and prone to imaging artifacts [3–5]. Variations in image quality across acquisition protocols and devices hinder accurate delineation of fine capillaries within dense MNV networks and yield inconsistent quantitative parameters across machines [6].

Another hurdle is characterization of vascular remodeling and the distinction between patterns consistent with active neovascularization versus mature, quiescent-appearing networks. Patterns such as “Medusa” and “Seafan” are widely recognized, yet their quantitative definition and clinical interpretation often vary [7,8]. The term “mature” is used inconsistently: sometimes for a well-organized but still active lesion (morphological maturity), and other times for a pruned vascular tree (interpreted as pathophysiological maturity in the literature) [1,7,8]. This ambiguity impedes standardized assessment and cross-study comparison.

This paper presents a novel semi-automated framework designed to enhance the transparency and reproducibility of MNV quantification. We detail a robust rule-based morphological categorization that maps Medusa, Seafan, Glomerular, Tree in bud, and Dead tree patterns using disclosed quantitative thresholds. Furthermore, we assign morphology-derived interpretive categories (Active-pattern, Mature-quiescent-pattern, Transitional-pattern, Arteriolarized-pattern). These interpretive labels serve as a structured, hypothesis-generating taxonomy grounded in quantitative morphology. Our framework establishes standardized biomarkers (Standardized Vascular Complexity Score, Standardized Caliber Uniformity Score, Standardized Maturity Index) to facilitate consistent within-stratum reporting and rule-based thresholding, thereby providing a rigorous foundation for future biological validation.



Methods

### 

### Study Population and Acquisition Protocols

This study was approved by the Ethics Committee of the Yokohama City University Medical Center. The protocol adhered to the Declaration of Helsinki, and informed consent was obtained from all eligible patients. We included 112 MNV lesions imaged with three OCTA platforms and field-of-view configurations to establish a multi-device analysis framework for stratum-standardized scoring. The large group (n = 49) comprised 6×6 mm acquisitions on the Zeiss PlexElite 9000 (swept-source OCTA, 1060 nm). The small_3mm group (n = 30) comprised 3×3 mm acquisitions on the Zeiss CIRRUS HD-OCT with AngioPlex (spectral-domain OCTA, 840 nm). The small group (n = 33) comprised 6×6 mm acquisitions on the Optovue Solix (Optovue/Visionix; swept-source OCTA, 1060 nm).

All included eyes were treatment-naïve Type 1 or Type 2 MNV secondary to neovascular AMD, diagnosed by retinal specialists using structural OCT and multimodal imaging. To ensure patient privacy in the anonymized research archive, detailed demographic and clinical covariates (age, sex, laterality, visual acuity, finer lesion-type breakdown) were excluded from the dataset. The use of three hardware platforms - differing in manufacturer, OCTA modality, wavelength, scanning protocol, and field size - was intentional: it provides a multi-device setting in which to evaluate stratum-specific standardization for cross-device reporting.

### Analytical Framework

The analytical framework was initially implemented as a comprehensive ImageJ macro and later in Python.

The methodology comprised two parallel components: mapping quantitative biomarkers reported in the literature and developing a pipeline to compute and refine these metrics. A focused literature search identified studies reporting quantitative OCTA analyses of MNV; key parameters were extracted and several integrated scores were introduced, as described below.

The core pipeline operates after freehand delineation of the MNV lesion by the user. This input defines the ROI for subsequent automated processing (Figure 2; representative processing panels in Figure 3). The pipeline comprises the stages below.

### Artifact Mitigation and Spatial Organization

This stage addresses critical sources of error in existing analysis software.

ROI refinement. To reduce boundary artifacts, an iterative algorithm adjusts the user-drawn ROI. For five iterations, each vertex of the ROI polygon is evaluated within a 3-pixel radius and moved to the darkest pixel, pushing the boundary into non-perfused tissue so that the analytical boundary conforms more closely to the lesion edge.

Hybrid multiscale vessel enhancement. A combination of Frangi (tubeness) and Laplacian of Gaussian (LoG) filters accentuates vessels of varying calibers. Fusion of complementary filters can improve vessel detection relative to single-filter methods [9–11]. Frangi (scales 0.8–4.0) identifies tubular structures; LoG detects edges. Their combined use supports enhancement of complex, multi-scale MNV networks in low-contrast OCTA images.

Binarization Following Frangi/LoG enhancement, MNV vessel maps exhibit spatially heterogeneous background intensity due to projection artifacts, signal attenuation, and intra-lesional contrast variation. To address this, we employed Phansalkar adaptive local thresholding rather than global Otsu thresholding. While global Otsu assumes a bimodal intensity histogram with a single cut-point - often leading to the erosion of fine peripheral capillaries or the inclusion of background speckles in overlapping distributions - Phansalkar’s local mean/SD-based approach estimates thresholds within a resolution-calibrated window (local radius corresponding to approximately 24 µm; k = 0.1, R = 0). This method preserves locally contrasted fine vessels while effectively suppressing regional background drift, leveraging its robustness to local intensity non-uniformity. Although Phansalkar is widely recognized in choriocapillaris flow-deficit analysis, this property makes it particularly advantageous for enhanced MNV vessel maps on the outer-retina/avascular-complex slab. Our implementation adheres to the ImageJ Auto Local Threshold (Phansalkar) convention used in the original macro to ensure reproducibility. We selected this local adaptive method over Otsu to optimize vessel preservation in the heterogeneous MNV environment, acknowledging Otsu’s utility primarily in relatively homogeneous SCP/DCP en-face slabs.

Post-processing and skeletonization. The binary image is refined by morphological reconstitution and skeletonized to a one-pixel-wide centerline for topological analysis.

Boundary-branch exclusion. The refined ROI is divided into Center and Periphery zones. Branches existing solely within the Periphery or spanning both zones are flagged as boundary branches and excluded from calculations of average branch length, junction density, and tortuosity, limiting skew from incomplete peripheral vessels.



### Quantitative Analysis

This stage computes a comprehensive set of parameters, including major metrics identified in the literature review, and introduces integrated scores. Table 1 summarizes the quantitative parameters

obtained in this study; separate columns list inter-rater and intra-rater ICC(2,1) (or κ for morphological subtypes) for available lesion metrics. To identify objectively dilated segments, the system uses a statistical threshold of mean + 2.0 × SD of all vessel diameters. Contiguous segments exceeding this threshold are flagged, and their count, length, and density are reported as an adaptive measure of caliber remodeling.



### Standardized Score Computation

Standardized Vascular Complexity Score (0–100)

The score was derived using principal component analysis (PCA) of four topological metrics from the skeletonized MNV network: inverse Euler number (−Euler_total), total loop count, junction density, and global fractal dimension. Reference distributions were constructed independently for each acquisition stratum (large, small_3mm, small). Features were standardized using stratum-specific means and standard deviations prior to PCA. The dominant first principal component (PC1), with uniformly positive loadings across all four metrics, explained 63.7%, 73.9%, and 70.2% of total variance for the large, small_3mm, and small strata, respectively. A secondary component (PC2, loading primarily on junction density) captured residual variance (24.8%, 21.9%, and 22.3%). PC1 and PC2 scores were combined with a fixed trunk-distribution constant (TrunkDist = 50, used in the absence of device-specific calibration) using weights 0.7, 0.2, and 0.1. To place scores on a common 0–100 reporting scale within each stratum, PC1 and PC2 were independently subjected to piecewise-linear normalization in which the within-stratum median maps to 50, the stratum minimum to 0, and the stratum maximum to 100. This normalization ensures consistent within-stratum scaling for rule-based thresholds, establishing a standardized framework for comparative reporting across diverse acquisition settings.

Standardized Caliber Uniformity Score (0–100)

A PCA-based standardization scheme was also evaluated for vascular caliber uniformity, but the present score was adopted to improve interpretability and reproducibility. Vascular caliber uniformity was quantified using two skeleton-derived morphometric features already exported by the pipeline: (1) the coefficient of variation of neovascular vessel diameter (NV Diameter CV); and (2) the fraction of dilated vessel length (Dilated vessel %, defined as segments exceeding the mean + 2.0 × SD of vessel diameters). Each feature was transformed into a uniformity axis by piecewise-linear scaling of its negated value (NV Diameter CV; dilated vessel fraction), such that the stratum-specific minimum, median, and maximum mapped to 0, 50, and 100, respectively, with higher scores indicating greater caliber uniformity and fewer dilated extremes.

The Standardized Caliber Uniformity Score was then defined as

Score = clip(0.75 × U(−NV Diameter CV) + 0.25 × U(−Dilated vessel %), 0, 100),

where U(·) denotes the stratum-specific piecewise map.

Standardized Maturity Index (0–100)

The Standardized Maturity Index was defined as:

Maturity Index = clip(50 + (Caliber Uniformity Score − Complexity Score) / 2, 0, 100).

This formulation reflects the concept that greater vascular maturity is characterized by increasing caliber uniformity relative to network architectural complexity. Values above 50 indicate a uniformity-dominant, maturity-dominant pattern consistent with vascular remodeling or quiescence, whereas values below 50 indicate a complexity-dominant pattern. Taken together, these normalizations ensured consistent within-stratum scaling for rule-based thresholds across acquisition settings.

### 

### Rule-Based Morphological Categorization and Morphology-Derived Interpretive Categories

Using stratum-specific reference percentiles of the Standardized Vascular Complexity Score and trunk pattern assignments (Medusa, Seafan, or Intermediate) derived from the spatial organization of large-caliber segments, lesions were classified in priority order as follows. Lesions with a Complexity Score below the stratum-specific 10th percentile were labeled Dead tree. Among the remaining lesions, those with a Medusa trunk pattern and a Complexity Score at or above the 65th percentile were labeled Medusa. Those with a SEAFAN trunk pattern and a Complexity Score at or above the 40th percentile were labeled Seafan. Lesions with a Complexity Score at or above the 30th percentile were labeled Glomerular irrespective of trunk pattern. The remaining lesions were labeled Tree in bud, typically corresponding to an intermediate trunk pattern and mid-to-low complexity.

The percentile cut-points for each stratum were taken from the reference files used by the classifier and are summarized in Supplementary Table S1 (Online Resource 1). For the small (Optovue Solix) stratum, the reference cohort used to define the Complexity percentile cut-points included 34 lesions, whereas the primary analysis batch reported in Table 3 included 33 lesions.

Level 2 - morphology-derived interpretive categories. Separately, rule-based labels Active-pattern, Mature-quiescent-pattern, Transitional-pattern, and Arteriolarized-pattern are assigned from Maturity Index, Caliber Uniformity Score, and arteriolarization indicators (segment count, junction density, loop count, mean diameter relative to stratum percentiles), informed by published morphological criteria [12]. These labels were defined as morphology-derived interpretive categories based on quantitative morphological features.

### 

### Expert–Automated Agreement Assessment

A retinal specialist (Y.Y.) performed masked morphological grading on a stratified subset of study OCTA images (n = 54; stratum allocation 24 / 16 / 14 for large / small / small_3mm) without access to automated subtype labels at the time of grading. Expert grades were compared with rule-based automated labels. Overall percent agreement and quadratic weighted Cohen’s κ were computed using the ordinal ordering Dead tree, Tree in bud, Glomerular, Seafan, and Medusa; bootstrap 95% CIs were obtained from 10,000 resamples. The confusion matrix is provided in Online Resource 2. This analysis was presented as an expert–algorithm agreement assessment and was intended to describe concordance between masked expert grading and the automated labeling scheme.

### 

### Reproducibility: Inter- and Intra-Observer ICC

Inter-observer (primary multi-rater analysis). Three independent operators performed freehand ROI delineation. Complete three-observer data were available for n = 46 cases. Automated processing after ROI delineation was identical across observers. All images were Angiography 3×3 mm acquisitions on Zeiss CIRRUS AngioPlex (small_3mm stratum).

Intra-rater and inter-rater reliabilities were assessed using intraclass correlation coefficients (ICCs) [13,14]. For both designs, we report ICC(2,1) (two-way random-effects, absolute agreement, single measures). Inter-observer analyses treated three operators as random raters, while intra-observer test–retest treated the two YY sessions as random raters under the same absolute-agreement model (selecting ICC(2,1) over ICC(1,1) to appropriately account for the same rater contributing both sessions). Primary endpoints included MNV area, Standardized Vascular Complexity Score, the Caliber Uniformity Score, and Maturity Index derived from Caliber Uniformity Score. Pairwise ICCs and a multilevel variance-component ICC were reported as complementary summaries for the multi-rater set. Interpretive bands for continuous clinical measurements (poor <0.50; moderate 0.50–0.75; good 0.75–0.90; excellent >0.90) follow published guidance [15].

Intra-observer (supplemental analysis). The original analyst (YY) repeated freehand ROI delineation on the same n = 46 lesions in a separate sitting; ICC(2,1) was computed as above. To ensure comparability across sessions, Caliber Uniformity and Maturity Index were calculated using the same standardized definition applied to both sessions (the Standardized Caliber Uniformity Score used as the primary inter-observer endpoint), alongside Area and Complexity Score (unchanged definitions). Unharmonized Caliber/Maturity columns, which lacked cross-session standardization, were excluded from this comparison. Intra-observer estimates serve as a supplemental validation of the three-observer ICCs.



### Statistical Analysis

Between-stratum differences in standardized scores were assessed with the Kruskal–Wallis test. Effect size was summarized as ε² = (H − k + 1) / (n − k) with k = 3, and bootstrap 95% CIs (10,000 within-stratum resamples; fixed random seed for reproducibility). A non-significant Kruskal–Wallis test was interpreted cautiously, without inferring statistical equivalence. Although Formal TOST equivalence testing was considered, clinically meaningful equivalence margins for these novel 0–100 scores were not established at study design; therefore, we prioritized transparent reporting of effect sizes with CIs over post-hoc TOST with provisional margins. Agreement analyses and ICC methods are described above. Analyses were performed in Python 3.11 using standard scientific computing libraries for statistical modeling and hypothesis testing. A p-value < 0.05 was considered statistically significant for omnibus Kruskal–Wallis tests, with non-significant results (p ≥ 0.05) reported as absence of evidence for difference rather than evidence of equivalence.



## Results

### Robust Segmentation and Artifact Mitigation

Representative OCTA images indicate that the system provides consistent segmentation of MNV lesions, with the semi-automatically delineated lesion area highlighted and dilated neovascular segments marked (Figure 1). In these examples, the segmented neovascular network follows lesion architecture rather than spurious high-contrast boundaries. The ROI refinement algorithm reduces boundary artifacts by adjusting user-drawn ROIs toward the non-perfused tissue border. Boundary-branch exclusion further limits the contribution of incomplete peripheral vessel segments to topological and morphometric metrics. The processing workflow is summarized in Figure 2; representative intermediate panels (Frangi enhancement, Phansalkar binarization, skeletonization) are shown in Figure 3.



### Cross-Device Raw Metrics and the Necessity of Standardization

Table 2 presents raw topological and morphometric parameters across the three acquisition protocols (mean ± SD; n = 112). As expected from differences in imaged vascular territory and device-specific resolution, raw metrics differed substantially across platforms. Mean total loop count (center + periphery) ranged from 300.3 ± 199.2 in the large (PlexElite 6×6 mm) group to 165.2 ± 118.0 in the small_3mm (CIRRUS AngioPlex / HD series 3×3 mm) group and 89.5 ± 53.4 in the small (Optovue Solix 6×6 mm) group - a 3.4-fold difference between the highest and lowest values. Mean Euler number (center + periphery) ranged from −168.4 ± 146.0 to −61.6 ± 48.2, and mean junction density from 25.85 ± 1.77 to 15.89 ± 2.88 mm⁻². Mean skeleton-derived vessel diameter showed the reverse ordering (16.0, 23.7, and 32.3 µm for large, small_3mm, and small, respectively). These systematic differences confirm that direct cross-device comparison of raw parameters is not feasible and motivate stratum-specific standardization for a shared reporting scale.



### Stratum-Standardized Scores

Table 3 presents standardized scores after stratum-specific normalization, together with Kruskal–Wallis statistics and ε² effect sizes (primary analysis set, n = 112: large = 49, small = 33, small_3mm = 30). The Standardized Vascular Complexity Score uses stratum-specific PCA with piecewise-linear PC scaling (PC1 explained variance 63.7% / 73.9% / 70.2% for large / small_3mm / small). Caliber Uniformity uses the Standardized Caliber Uniformity Score; Maturity Index is recomputed from that Caliber score and Complexity. By design, the piecewise-linear normalization maps each stratum’s locking-cohort median to 50 on the scaled axes. Consequently, median values near 50 after normalization are a direct mathematical consequence of this scaling procedure. These scores serve as a standardized reporting scale for within-stratum assessment and for applying shared rule-based thresholds across acquisition strata, while maintaining stratum-specific reference frames.

Under the Standardized Caliber Uniformity Score, none of the three standardized scores differed significantly across strata (Complexity median 48.7 / 50.7 / 47.8, H = 1.712, p = 0.425, ε² = 0.000 [95% CI 0.000–0.089]; Caliber Uniformity 46.6 / 55.5 / 50.6, H = 1.118, p = 0.572, ε² = 0.000 [0.000–0.082]; Maturity Index 49.5 / 53.9 / 51.0, H = 1.082, p = 0.582, ε² = 0.000 [0.000–0.077]; medians ordered large / small / small_3mm). Median-anchored normalization places scores on a common 0–100 reporting scale for rule thresholds within each stratum. High PC1 explained-variance ratios for the Complexity Score (63.7–73.9%) indicate robust within-stratum latent topological structure.



### Rule-Based Morphological Categorization and Expert Agreement

Table 4 presents the distribution of morphological subtypes across acquisition platforms (n = 112). The spectrum of MNV subtypes was identified across the three devices. Glomerular pattern was the most prevalent subtype in the large group (n = 29, 59.2%) and was also well-represented in the small_3mm and small groups (30.0% and 36.4%, respectively). Medusa pattern was observed only in the large group (n = 6, 12.2%). Seafan pattern was more common in the small_3mm group (n = 11, 36.7%) than in the small group (n = 2, 6.1%) and was absent in the large group. Dead tree pattern was identified in all three groups (8.2%, 20.0%, and 15.2%). Tree in bud pattern was present in all groups (20.4%, 13.3%, 42.4%). Between-platform differences in subtype prevalence may reflect sampling, case-mix, and differences in scan area rather than classifier instability alone. Morphology-derived interpretive mapping of these five operational subtypes is summarized in Table 5.

On the masked expert subset (n = 54), overall agreement between expert and automated labels was 57.4% (31/54); quadratic weighted Cohen’s κ was 0.507 (95% CI 0.222–0.714). When Glomerular and Seafan were merged on both sides (4-class sensitivity), agreement rose to 75.9% (41/54) and κ to 0.682 (95% CI 0.400–0.852), indicating that discordance largely reflects adjacent descriptive subtypes that are challenging to separate visually. This level of agreement aligns with prior reports that qualitative OCTA morphological grading can show moderate reliability across raters. Our rule-based quantitative operationalization with disclosed thresholds aims to reduce rater-dependent ambiguity relative to purely descriptive labels, complementing expert judgment.



### Inter- and Intra-Observer Reproducibility

Inter-observer reproducibility was assessed in a three-rater subset of 46 lesions. Agreement was good for lesion area (ICC(2,1) = 0.859; 95% CI 0.680–0.930), the Standardized Vascular Complexity Score (ICC(2,1) = 0.807; 95% CI 0.660–0.890), and the Standardized Caliber Uniformity Score (ICC(2,1) = 0.770; 95% CI 0.660–0.860). In contrast, the Maturity Index showed only moderate agreement (ICC(2,1) = 0.593; 95% CI 0.430–0.730), consistent with the lower reproducibility of the composite measure derived from the Caliber Uniformity Score.

Intra-observer reproducibility was excellent in the same 46-lesion subset. For the second session of the same rater, ICC(2,1) values were 0.979 (95% CI 0.962–0.988) for lesion area, 0.950 (95% CI 0.913–0.973) for the Standardized Vascular Complexity Score, 0.925 (95% CI 0.871–0.959) for the Standardized Caliber Uniformity Score, and 0.917 (95% CI 0.857–0.954) for the Maturity Index. These findings indicate consistently high within-rater repeatability under the fixed score definition and complement the primary multi-rater reproducibility analysis.



## Discussion

This work advances quantitative MNV analysis by combining hybrid vessel enhancement, adaptive binarization, skeleton-based topology, and stratum-standardized multi-parameter scores with disclosed rule-based morphological categories. While existing tools and recent studies provide a foundational set of metrics, they often fail to capture the holistic nature of the neovascular complex and remain vulnerable to methodological artifacts.



A central feature of the present system is generation of stratum-standardized reporting scores across different acquisition conditions. In contrast to tools that report only raw, device-specific metrics unsuitable for shared numerical thresholds, the framework produces three standardized scores - Standardized Vascular Complexity Score (stratum-specific PCA), Standardized Caliber Uniformity Score (NV Diameter CV + Dilated vessel %), and Standardized Maturity Index (from Caliber − Complexity) - on a common 0–100 scale within each stratum. The median-anchored piecewise scaling is designed to place scores on a common reporting axis [6]. Informative aspects of the framework include: (i) large between-device differences in raw metrics (Table 2); (ii) consistency of Complexity PCA structure (PC1 loadings and explained variance) across strata; and (iii) within-stratum score distributions in relation to morphological categories and expert comparison. Under the Standardized Caliber Uniformity Score there are no significant between-stratum differences for Complexity, Caliber Uniformity, or Maturity Index (ε² ≈ 0) - reflecting the intended effect of the scaling procedure to attenuate stratum-mean contrasts by design. Prior work has shown that quantitative vascular metrics are often not interchangeable across OCTA devices/algorithms without device-aware reporting [16,17].



Several methodological aspects warrant consideration. The ROI refinement algorithm addresses a long-standing challenge in quantitative OCTA analysis [7,18–20] by encouraging the ROI boundary to lie in non-perfused tissue. The Euler number and loop count remain core elements of the Vascular Complexity construct because they quantify connectivity and mesh-like organization [21–23]. Immature, angiogenesis-dominant networks often appear as dense, highly interconnected plexuses [24]; markedly negative Euler numbers with elevated loop counts are therefore useful morphological biomarkers of complexity-dominant architecture. Terms such as “dead tree,” “tree in bud,” “medusa,” “sea fan,” and “glomerular” have previously been applied in a primarily descriptive manner [25,26]. The present framework supplies operational definitions with disclosed thresholds.



We also address terminological ambiguity around maturation, arterialization, and abnormalization [27–30]. Our morphology-derived interpretive categories map quantitative patterns onto labels informed by published criteria, including arteriolarization-segment detection and caliber-uniformity scores related to the unstable vascular state described by Spaide as abnormalization [30]. These categories provide a useful framework for future outcome-linked studies aimed at clarifying their role in clinical decision-making and prognostic stratification.

Masked expert–automated agreement (κ = 0.507) was modest-to-moderate. This level of agreement aligns with prior reports that qualitative OCTA pattern labels remain partly descriptive and ambiguous [8], and that qualitative assessments can be less reliable than quantitative metrics [31]. Categorical MNV classifications between imaging-based systems have likewise shown only moderate agreement [32]. Quantitative operationalization with disclosed rules offers a transparency and reproducibility aid relative to purely visual labels. Related quantitative OCTA biomarker work further supports objectifying morphology and activity descriptors [33,34].



## Limitations

Data and patient population. This anonymized, cross-sectional, treatment-naïve dataset lacks fluid status, treatment response, outcome data, and detailed baseline demographics and included only treatment-naïve Type 1 and Type 2 MNV secondary to neovascular AMD; therefore, morphology-derived interpretive categories require future outcome-linked studies for clinical validation, and applicability to other lesion types or post-treatment fibrotic lesions remains to be determined. Between-platform subtype prevalence differences may reflect case-mix and differences in scan area, which should be considered when interpreting cross-device score comparisons.

Standardization and validation. Piecewise-linear mapping of each stratum’s locking-cohort median toward 50 is designed to establish a common reporting scale, rather than to demonstrate biological equivalence across devices; absence of significant Kruskal–Wallis differences under the Standardized Caliber Uniformity Score should be interpreted as consistent with the scaling procedure, without establishing interchangeability of scores across platforms. Primary multi-rater reproducibility is the three-observer ICC on n = 46. Standardized Caliber Uniformity Score ICC (0.770) is good on conventional benchmarks; Maturity Index derived from that Caliber score was moderate (0.593). Intra-observer ICCs under the standardized definition are excellent and provide supplemental validation to inter-observer results. Multi-center external validation on independent cohorts and scanners will be required to establish broader generalizability, and the impact of standardized scores on clinical decision-making requires prospective validation in treatment-outcome studies.



## Conclusion

We have developed a semi-automated Python-based system for multi-dimensional analysis of macular neovascularization that addresses several methodological limitations of existing tools, incorporates established biomarkers from recent literature, and introduces integrated scores for complexity, caliber uniformity, and a morphology-derived maturity index. The system provides stratum-standardized scoring for reporting, disclosed rule-based morphological categorization with expert-agreement assessment, and hypothesis-generating morphology-derived interpretive labels. These standardized scores establish a common reporting framework for comparative analyses across diverse acquisition settings, while the rule-based morphological categorization offers a transparent and reproducible alternative to purely descriptive labels. Future outcome-linked and multi-center evaluations will further establish the clinical utility of these quantitative tools for advancing reproducible research on MNV architecture in neovascular AMD.





## References

Guo, J., Tang, W., Xu, S., Liu, W. & Xu, G. OCTA evaluation of treatment-naïve flat irregular PED (FIPED)-associated CNV in chronic central serous chorioretinopathy before and after half-dose PDT. Eye 35, 2871–2878 (2021).

Zudaire, E., Gambardella, L., Kurcz, C. & Vermeren, S. A Computational Tool for Quantitative Analysis of Vascular Networks. PLOS ONE 6, e27385 (2011).

Told, R. et al. Profiling neovascular age-related macular degeneration choroidal neovascularization lesion response to anti-vascular endothelial growth factor therapy using SSOCTA. Acta Ophthalmol. (Copenh.) 99, e240–e246 (2021).

Montesel, A. et al. Quantitative response of macular neovascularisation to loading phase of aflibercept in neovascular age-related macular degeneration. Eye 37, 3648–3655 (2023).

Carlà, M. M. et al. MORPHOMETRIC CHANGES IN MACULAR NEOVASCULARIZATION ARCHITECTURE AFTER FARICIMAB TREATMENT IN NEOVASCULAR AGE-RELATED MACULAR DEGENERATION: Comparison Between Naive and Switched Eyes. Retina 125–135 (2026) doi:10.1097/iae.0000000000004635.

Munk, M. R. et al. OCT-angiography: A qualitative and quantitative comparison of 4 OCT-A devices. PLOS ONE 12, e0177059 (2017).

Miere, A. et al. VASCULAR REMODELING OF CHOROIDAL NEOVASCULARIZATION AFTER ANTI-VASCULAR ENDOTHELIAL GROWTH FACTOR THERAPY VISUALIZED ON OPTICAL COHERENCE TOMOGRAPHY ANGIOGRAPHY. Retina 39, 548–557 (2019).

Tew, T. B. et al. Comparison of different morphologies of choroidal neovascularization evaluated by ocular coherence tomography angiography in age-related macular degeneration. Clin. Experiment. Ophthalmol. 48, 927–937 (2020).

Oliveira, W. S., Teixeira, J. V., Ren, T. I., Cavalcanti, G. D. C. & Sijbers, J. Unsupervised Retinal Vessel Segmentation Using Combined Filters. PLoS ONE 11, e0149943 (2016).

Ma, Y. et al. Multichannel Retinal Blood Vessel Segmentation Based on the Combination of Matched Filter and U-Net Network. BioMed Res. Int. 2021, 5561125 (2021).

Memari, N., Ramli, A. R., Bin Saripan, M. I., Mashohor, S. & Moghbel, M. Supervised retinal vessel segmentation from color fundus images based on matched filtering and AdaBoost classifier. PLoS ONE 12, e0188939 (2017).

Coscas, F. et al. Optical coherence tomography angiography in exudative age-related macular degeneration: A predictive model for treatment decisions. Br. J. Ophthalmol. 103, 1342–1356 (2019).

Shrout, P. E. & Fleiss, J. L. Intraclass correlations: uses in assessing rater reliability. Psychol. Bull. 86, 420–428 (1979).

McGraw, K. O. & Wong, S. P. Forming inferences about some intraclass correlation coefficients. Psychol. Methods 1, 30–46 (1996).

Koo, T. K. & Li, M. Y. A guideline of selecting and reporting intraclass correlation coefficients for reliability research. J. Chiropr. Med. 15, 155–163 (2016).

Corvi, F. et al. Reproducibility of vessel density, fractal dimension, and foveal avascular zone using 7 different optical coherence tomography angiography devices. Am. J. Ophthalmol. 186, 25–31 (2018).

Corvi, F. et al. Comparison between several optical coherence tomography angiography devices and indocyanine green angiography of choroidal neovascularization. Retina 40, 873–880 (2020).

Wang, M. et al. Evaluating Polypoidal Choroidal Vasculopathy With Optical Coherence Tomography Angiography. Investig. Opthalmology Vis. Sci. 57, OCT526-32 (2016).

Xue, J. et al. Automatic quantification of choroidal neovascularization lesion area on OCT angiography based on density cell-like P systems with active membranes. Biomed. Opt. Express 9, 3208–3219 (2018).

Babiuch, A. et al. IMPACT OF OPTICAL COHERENCE TOMOGRAPHY ANGIOGRAPHY REVIEW STRATEGY ON DETECTION OF CHOROIDAL NEOVASCULARIZATION. Retina 672–678 (2020) doi:10.1097/iae.0000000000002443.

Smith, A. & Zavala, V. The Euler characteristic: A general topological descriptor for complex data. Comput Chem Eng 154, 107463 (2021).

Willführ, A. et al. Estimation of the number of alveolar capillaries by the Euler number (Euler-Poincaré characteristic). Am. J. Physiol. Lung Cell. Mol. Physiol. 309, L1286-93 (2015).

Santos, F. et al. Topological phase transitions in functional brain networks. bioRxiv https://doi.org/10.1101/469478 (2018) doi:10.1101/469478.

Viallard, C. & Larrivée, B. Tumor angiogenesis and vascular normalization: alternative therapeutic targets. Angiogenesis 20, 409–426 (2017).

Goker, Y. S. & Demir, G. Comparison of optical coherence tomography angiography features in type 1 versus type 2 choroidal neovascular membranes secondary to age-related macular degeneration. Med. Hypothesis Discov. Innov. Ophthalmol. J. 10, 67–73 (2021).

Li, J. et al. Comparative quantitative analysis of optical coherence tomography angiography in varied morphologies of macular neovascularization following intravitreal conbercept and ranibizumab treatments for neovascular age‑related macular degeneration. Exp. Ther. Med. 27, 214 (2024).

Mettu, P. S., Allingham, M. J. & Cousins, S. W. Incomplete response to Anti-VEGF therapy in neovascular AMD: Exploring disease mechanisms and therapeutic opportunities. Prog. Retin. Eye Res. 82, 100906 (2021).

Attarde, A., Riad, T., Zhang, Z., Ahir, M. & Fu, Y. Characterization of Vascular Morphology of Neovascular Age-Related Macular Degeneration by Indocyanine Green Angiography. J. Vis. Exp. JoVE 198, (2023).

Fu, Y., Zhang, Z., Webster, K. & Paulus, Y. Treatment Strategies for Anti-VEGF Resistance in Neovascular Age-Related Macular Degeneration by Targeting Arteriolar Choroidal Neovascularization. Biomolecules 14, 252 (2024).

Spaide, R. Optical Coherence Tomography Angiography Signs of Vascular Abnormalization With Antiangiogenic Therapy for Choroidal Neovascularization. Am. J. Ophthalmol. 160, 6–16 (2015).

Shah, P. N. et al. Inter-rater reliability of proliferative diabetic retinopathy assessment on wide-field OCT-angiography and fluorescein angiography. Transl. Vis. Sci. Technol. 12(7), 13 (2023).

Deák, G. G. et al. Comparison of optical coherence tomography vs. fluorescein angiography-based macular neovascularization classifications in age-related macular degeneration. Sci. Rep. 15, 4303 (2025) doi:10.1038/s41598-025-87576-6.

Gan, Y. et al. Novel quantitative OCTA biomarkers of choroidal neovascularization and associations with disease activity and etiology. Transl. Vis. Sci. Technol. 15(3), 10 (2026).

Hsu, C. R. et al. Combined quantitative and qualitative optical coherence tomography angiography biomarkers for predicting active neovascular age-related macular degeneration. Sci. Rep. 11, 18068 (2021).



Figure legends



Figure 1. Representative OCTA images demonstrating consistent MNV segmentation across multiple platforms. 

Images were acquired using: (A) Zeiss PlexElite 9000 (6×6 mm), (B) Optovue Solix (6×6 mm), and (C) Zeiss CIRRUS / HD series (3×3 mm). Semi-automatically delineated lesion areas and dilated neovascular segments follow internal lesion architecture. The ROI is refined toward the non-perfused tissue border to minimize boundary artifacts, and incomplete peripheral vessel segments are excluded from quantitative analysis.



Figure 2. Schematic of the semi-automated image-processing workflow: freehand ROI → iterative ROI refinement → hybrid multiscale vessel enhancement (Frangi/tubeness + Laplacian of Gaussian) → Phansalkar adaptive binarization → morphological refinement → skeletonization → boundary-branch exclusion → quantitative metrics and standardized scores.



Figure 3. Representative OCTA en-face image of macular neovascularization illustrating the semi-automated processing pipeline. (A) Input angiogram with freehand / refined region of interest (ROI; green outline and tint). (B) Continuous multiscale Frangi vesselness (tubeness) enhancement within the ROI. (C) Adaptive Phansalkar / hybrid binarization vessel map within the ROI after morphological refinement. (D) One-pixel-wide skeleton (centerline) used for topological and morphometric metrics.
