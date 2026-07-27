# Figure 3 — Processing steps (draft caption)

**Figure 3.** Representative OCTA en-face image of macular neovascularization illustrating the semi-automated processing pipeline. **(A)** Input angiogram with freehand / refined region of interest (ROI; green outline and tint). **(B)** Hybrid multiscale vessel enhancement (Mexican-hat / Laplacian-of-Gaussian component shown; Frangi/tubeness is combined in the full pipeline). **(C)** Adaptive Phansalkar binarization within the ROI after morphological refinement. **(D)** Color-coded vessel visualization used for qualitative review alongside quantitative skeleton-derived metrics (Network Complexity Score, Caliber Uniformity Score, Maturity Index).

*Draft assembly note:* Panels from `documentation/graefe_revision/figures/_fig3_runs/838a095e-b730-4446-a23d-a6e4509326d0` with original `/Users/yy/MNV_quantitatibe analysis_original_inputdata/large/81224417_IVF_before_OD.jpg`

Final panels for submission should preferably come from 1–3 cohort cases processed in Flet with the same freehand ROI workflow used clinically (see `scripts/graefe_revision/assemble_figure3.py --from-dir`). Auto-ROI headless frames are acceptable only as interim drafts.
