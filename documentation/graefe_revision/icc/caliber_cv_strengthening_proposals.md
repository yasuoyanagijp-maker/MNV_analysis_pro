# Caliber CV strengthening proposals (CSV-only / current parameters)

**Date:** 2026-07-30  
**Constraint:** Use **only existing batch CSV columns** under current pipeline parameters. No re-ROI, no re-segmentation, no new skeleton/diameter algorithm.  
**Implemented experiment:** `caliber_new_score_icc_results.md` + `compute_caliber_new_score_icc.py`

---

## Short diagnosis (from `caliber_icc_low_investigation.md`)

Fragile step is **diameter-variability / CV aggregation**, not mean caliber or topology:

| Feature | ICC(2,1) |
|---------|----------|
| Caliber Uniformity Score (composite) | 0.434 |
| NV Diameter (CV) | 0.259 |
| Local Diameter Variation (max CV%) | 0.138 |
| (Skel) Vsl Diameter | 0.760 |
| Vsl Branches / Length | 0.81–0.88 |

`stab_cv` / 10-bin radial profile are **not** in the ImageJ batch CSV → cannot retune PCA Stability weights without recompute from images.

---

## Top 5 proposals (existing CSV only; ranked)

| Rank | Proposal | Expected ICC gain | Cost | Manuscript risk |
|------|----------|-------------------|------|-----------------|
| 1 | **Robust NV-CV → new uniformity score** (Winsorize CV p05–p95; piecewise (−CV) → 0–100; drop Local max CV) | **Large** (observed **0.434 → 0.765**) | Low (offline) | High if silent replace — **sensitivity only** |
| 2 | Same + light Local max CV downweight (0.85/0.15) | Large (observed 0.761) | Low | Same |
| 3 | Area / branch-count **gate** for Caliber reporting (Caliber-only ICC when Area ≥ cut) | Modest stratum gain | Low | Low if labeled sensitivity |
| 4 | Winsorize **original** Caliber score only | Negligible (observed 0.446) | Trivial | Low / not worth it |
| 5 | Blend high-ICC skel diameter into score (70% CV / 30% skel) | Moderate (observed 0.615) but **construct shift** | Low | High (not pure uniformity) |

### Future / out of scope for this constraint

Re-binning (adaptive bin count), MAD/median on per-bin diameters, distance-transform changes, Phansalkar retune, ROI padding — need images / re-pipeline. Park for post-revision.

---

## What NOT to do (Graefe revision)

- Cherry-pick concordant cases as the primary ICC.
- Silently swap Caliber definition mid-revision.
- Claim the NV-CV proxy is the “same” Caliber Uniformity Score (Spearman with original ≈ 0).

---

## Recommended next experiment (done)

**Run:** `compute_caliber_new_score_icc.py` on YY/Inoue/Osada batch CSVs (n=46 matched `File`).  
**Primary adopted formula:** `caliber_C_winsor_inv_nv_cv` — Winsorize `NV Diameter (CV)` → piecewise scale of −CV (Local max CV excluded).  
**Result:** ICC(2,1) **0.434 → 0.765**; treat as **sensitivity / alternate proxy**, not manuscript definition change.
