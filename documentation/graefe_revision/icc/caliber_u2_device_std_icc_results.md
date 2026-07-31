# Caliber U2 — per-device (size_class) standardization ICC

**Date:** 2026-07-31  
**Set:** YY / Inoue / Osada · intersection **n = 46** · ICC(2,1) absolute agreement  
**Script:** `compute_caliber_u2_device_std_icc.py`

---

## 日本語サマリー

| 項目 | 結論 |
|------|------|
| (a) 理論的に中央値≈50にできるか | **PARTIAL** — 層（=機種/FOV）ごとに locked μ/σ＋piecewise（median→50）は PCA Caliber と同型で **可能**。ただしアプリ `stability_ref_*.json` に NV-CV / Dilated% の μ/σは **無い**（`stab_*` のみ）。原稿参照バッチ CSV から推定してロック。本 ICC は全例 `Angiography 3x3`＝`small_3mm` 単層のため、多機種での層内中央化は実証不可。ICC プール中央値≈50は保証されず（分布シフトで device_std 中央値≈64）。 |
| (b) 実装したか | **YES** — `caliber_U2_device_std` / `caliber_U2_device_soft`（75/25） |
| (c) ICC | 原 0.434 / C 0.765 / プール U2 0.838 / **device_std 0.770** / device_soft 0.751 |

---

## Theoretical verdict

**PARTIAL — yes within a device/size_class stratum; not a drop-in of locked app JSON for these axes.**

| Question | Answer |
|----------|--------|
| Can U2 use the same *style* as PCA Caliber (stratum μ/σ + median→50)? | **YES** |
| Do app `stability_ref_*.json` already lock μ/σ for NV CV / Dilated%? | **NO** (`stab_*` only) |
| What substitutes? | Manuscript reference batch CSVs per size_class (= device) |
| Does this ICC set span multiple devices? | **NO** — all 46 files are `Angiography 3x3 mm` → `small_3mm` |
| Therefore multi-device centering empirically? | **Not testable here** (single-stratum degenerate) |
| Missing vs original PCA | Frozen PCA loadings; `stab_*` features; locked JSON for these exact CSV columns; multi-stratum ICC sample |

### Device ↔ size_class (from `output/phase1_collect.log`)

| Stratum | Device | Training n |
|---------|--------|------------|
| `small` | Optovue Solix / AngioVue 6×6 mm | 33 |
| `large` | Zeiss PlexElite 9000 6×6 mm | 49 |
| `small_3mm` | Zeiss CIRRUS HD AngioPlex 3×3 mm (Angiography 3x3) | 30 |

### Locked cuts used for `small_3mm` (this ICC set)

```
{
  "device": "Zeiss CIRRUS HD AngioPlex 3\u00d73 mm (Angiography 3x3)",
  "n_cases": 30,
  "nv_cv": {
    "n": 30.0,
    "mean": 51.036101959,
    "std": 8.954431085607578,
    "min": 43.07717553,
    "median": 47.295175835,
    "max": 79.119217,
    "p05": 44.103906067000004,
    "p95": 72.77597075999999
  },
  "dilated_pct": {
    "n": 30.0,
    "mean": 0.0886819374666667,
    "std": 0.01979612073356121,
    "min": 0.04651911,
    "median": 0.0918942285,
    "max": 0.121717059,
    "p05": 0.0619303021,
    "p95": 0.11657747564999998
  },
  "neg_nv_cv_piecewise": {
    "min": -79.119217,
    "median": -47.295175835,
    "max": -43.07717553
  },
  "neg_dilated_piecewise": {
    "min": -0.121717059,
    "median": -0.0918942285,
    "max": -0.04651911
  }
}
```

### Scoring formulas

- **`caliber_U2_device_std`** (app-style): for each case’s stratum, `U_cv = piecewise(−NV_CV; locked min/median/max)`, `U_dil = piecewise(−Dilated%; locked min/median/max)`, **Score = 0.75·U_cv + 0.25·U_dil** (clip 0–100).
- **`caliber_U2_device_soft`**: `U_cv = 50 + 50·tanh((μ̃−NV_CV)/σ)` with locked stratum median/SD; same for Dilated%; same 75/25 blend.
- Contrast: pooled `caliber_U2_softcv_dil` re-estimates median/SD on the ICC 46×3 pool.

**Stratum assignment in this run:** {'small_3mm': 46}

---

## Empirical ICC(2,1)

| Metric | ICC(2,1) | 95% CI | Δ vs orig | Δ vs C | Score median | Score mean |
|--------|----------|--------|-----------|--------|--------------|------------|
| `Caliber Uniformity Score` | 0.434 | 0.260–0.610 | +0.000 | -0.331 | 51.5 | 50.3 |
| `caliber_C_winsor_inv_nv_cv` | 0.765 | 0.640–0.860 | +0.331 | +0.000 | 50.0 | 53.5 |
| `caliber_U2_softcv_dil` | 0.838 | 0.750–0.900 | +0.404 | +0.073 | 46.0 | 50.1 |
| `caliber_U2_device_std` | 0.770 | 0.660–0.860 | +0.336 | +0.005 | 64.1 | 67.2 |
| `caliber_U2_device_soft` | 0.751 | 0.630–0.840 | +0.317 | -0.013 | 55.6 | 57.2 |

### Interpretation

- Device-locked piecewise U2 ICC = **0.770** (soft twin **0.751**) vs pooled U2 **0.838** and original **0.434**.
- Score medians on ICC pool: device_std **64.1**, device_soft **55.6**, pooled U2 **46.0**, original Caliber **51.5**.
- Median≈50 is guaranteed **on the locking (training) cohort** at the feature piecewise / soft center; on a new cohort it is only approximate (distribution shift). Here ICC is all `small_3mm`, so multi-device re-centering cannot be shown.
- Prefer device-locked cuts for **transferability** (no ICC-pool re-fit); pooled U2 remains a strong within-study sensitivity score.

---

## Files

- `caliber_u2_device_std_ref.json` — locked stratum cuts
- `caliber_u2_device_std_long.csv` — per rating scores
- `caliber_u2_device_std_icc_stats.csv` — ICC table
- `caliber_u2_device_std_icc_results.md` — this report

