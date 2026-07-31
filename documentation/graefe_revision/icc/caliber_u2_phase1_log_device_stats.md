# Caliber U2 — phase1 log vs device-locked refs

**Date:** 2026-07-31  
**Inputs:** `output/phase1_collect.log`, `resources/reference_metrics/stability_ref_*.json`, `documentation/graefe_revision/icc/caliber_u2_device_std_ref.json`, manuscript batch CSVs  
**Candidate JSON:** `caliber_u2_device_ref_from_phase1.json` (CSV-derived; not wired to production)

## Executive verdict (YES/NO)

| Question | Answer |
|---|---|
| App JSON still lacks NV-CV / Dilated% (only `stab_*`)? | **YES** — still true |
| Can `phase1_collect.log` supply per-device NV-CV / Dilated%? | **NO** — not logged |
| Can manuscript batch CSVs (phase1 cohort) supply them? | **YES** — n=33/49/30, full coverage |
| Are manuscript-batch locked U2 cuts correct vs those CSVs? | **YES** — exact mean/std/min/median/max match |
| Create candidate app JSON now? | **YES** — written (CSV source); do not wire yet |
| Wire into production app now? | **NO** — needs new scorer + product decision |

## 1. Log structure

`phase1_collect.log` is a dry-run of the MNV reference builder on the manuscript cohort.

- Header: `n=112` — small 33 / large 49 / small_3mm 30
- Device mapping:
  - `small` → Optovue Solix 6×6 mm
  - `large` → Zeiss PlexElite 9000 6×6 mm
  - `small_3mm` → Zeiss CIRRUS HD AngioPlex 3×3 mm
- Per successful case line: `✓ stab_cv=… loops=… junction=…` only
- **Absent:** `NV Diameter (CV)`, `Dilated vessel (%)`, diameter CV synonyms, caliber scores
- Cohort summary reports trunk_scale_correction only; dry-run would write stability/complexity/classification refs

### Images processed in log vs header

| size_class | Header n | Log images processed | Device |
|---|---:|---:|---|
| `small` | 33 | 11 | Optovue Solix / AngioVue 6×6 mm |
| `large` | 49 | 49 | Zeiss PlexElite 9000 6×6 mm |
| `small_3mm` | 30 | 30 | Zeiss CIRRUS HD AngioPlex 3×3 mm (Angiography 3x3) |

**Note:** `small` run in this log is incomplete (11/33). Even a complete log would still lack NV-CV / Dilated%.

## 2. What the log *can* yield (stab_cv only)

| size_class | n | stab_cv mean | stab_cv σ | median | min | max |
|---|---:|---:|---:|---:|---:|---:|
| `small` | 11 | 5.300 | 1.855 | 5.400 | 3.0 | 8.9 |
| `large` | 49 | 6.788 | 3.366 | 5.800 | 2.3 | 18.8 |
| `small_3mm` | 30 | 19.647 | 14.444 | 14.600 | 5.9 | 62.4 |

These are **not** NV Diameter (CV). `stab_cv` is a stability-profile CV used by PCA Caliber.

### Log stab_cv vs app `stability_ref_*.json` μ/σ

| size_class | ref n | ref μ(stab_cv) | log n | log mean | Δ mean |
|---|---:|---:|---:|---:|---:|
| `small` | 34 | 14.6278 | 11 | 5.3000 | -9.3278 |
| `large` | 49 | 15.1209 | 49 | 6.7878 | -8.3331 |
| `small_3mm` | 30 | 12.4731 | 30 | 19.6467 | 7.1736 |

Log one-liners are truncated progress markers, not the full 4-metric stability vector used to fit `stability_ref_*.json`. Do not rebuild stability μ/σ from this log.

## 3. App stability JSON — prior claim check

Files: `resources/reference_metrics/stability_ref_{small,large,small_3mm}.json`

- Metrics locked: `stab_cv`, `stab_mean_adjacent_change`, `stab_residual_cv`, `stab_range_percent`
- **No** `nv_cv` / `NV Diameter (CV)` / `dilated_pct` / `Dilated vessel (%)`
- Prior claim **“app JSON only has stab_* μ/σ”** → **still TRUE**

## 4. Manuscript-batch locked U2 cuts — verification

Source of `caliber_u2_device_std_ref.json`: the three manuscript batch CSVs (not the log text).

Recompute from CSVs (sample SD, ddof=1):

### NV Diameter (CV)

| size_class | n | locked μ | CSV μ | Δ | locked σ | CSV σ | Δ | locked median | CSV median |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `small` | 33 | 41.684309 | 41.684309 | -7.11e-15 | 2.452432 | 2.452432 | 0.00e+00 | 41.309692 | 41.309692 |
| `large` | 49 | 38.470361 | 38.470361 | 0.00e+00 | 1.086278 | 1.086278 | -2.22e-16 | 38.486699 | 38.486699 |
| `small_3mm` | 30 | 51.036102 | 51.036102 | 0.00e+00 | 8.954431 | 8.954431 | 0.00e+00 | 47.295176 | 47.295176 |

### Dilated vessel (%)

| size_class | n | locked μ | CSV μ | Δ | locked σ | CSV σ | Δ | locked median | CSV median |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `small` | 33 | 0.08310722 | 0.08310722 | 0.00e+00 | 0.03153273 | 0.03153273 | 0.00e+00 | 0.07664047 | 0.07664047 |
| `large` | 49 | 0.13256407 | 0.13256407 | 0.00e+00 | 0.02474087 | 0.02474087 | 0.00e+00 | 0.13015625 | 0.13015625 |
| `small_3mm` | 30 | 0.08868194 | 0.08868194 | 2.78e-17 | 0.01979612 | 0.01979612 | 3.47e-18 | 0.09189423 | 0.09189423 |

**Result:** all compared fields match within numerical noise (`matches_caliber_u2_device_std_ref_json` = `True`). Locked estimates are **correct**.

### Per-device summary (CSV / locked)

| Device (size_class) | n | NV-CV μ±σ | Dilated% μ±σ |
|---|---:|---|---|
| Optovue Solix / AngioVue 6×6 mm (`small`) | 33 | 41.684 ± 2.452 | 0.0831 ± 0.0315 |
| Zeiss PlexElite 9000 6×6 mm (`large`) | 49 | 38.470 ± 1.086 | 0.1326 ± 0.0247 |
| Zeiss CIRRUS HD AngioPlex 3×3 mm (Angiography 3x3) (`small_3mm`) | 30 | 51.036 ± 8.954 | 0.0887 ± 0.0198 |

## 5. Candidate app JSON

- Path: `documentation/graefe_revision/icc/caliber_u2_device_ref_from_phase1.json`
- Content: per-`size_class` `mu`/`sigma`, full distribution, negated piecewise anchors, 75/25 weights
- Numerically identical to `caliber_u2_device_std_ref.json` strata cuts
- Filename says “from_phase1” for cohort labeling; **source is CSVs**, not log parsing

## 6. App implementation feasibility

### Can implement? **YES (JSON ready) / NO (not wired)**

| Item | Status |
|---|---|
| Features already computed in pipeline | YES — `cv_diameter` → NV Diameter (CV); `high_skew_percentage` → Dilated vessel (%) |
| Existing ref loader pattern | YES — `pattern_metrics._load_reference_json` for `stability_ref_*.json` |
| U2 device_std scorer in production | NO |
| Production copy under `resources/reference_metrics/` | NO (candidate only under `documentation/.../icc/`) |
| Log as rebuild source | NO — missing axes; incomplete small |

### Suggested wiring (when product asks)

1. Copy candidate (or `caliber_u2_device_std_ref.json`) → `resources/reference_metrics/caliber_u2_device_ref.json`.
2. Add `_load_caliber_u2_device_ref()` next to stability loaders in `src/core/pattern_metrics.py`.
3. Add `calculate_caliber_u2_device_score(cv_diameter, high_skew_percentage, size_class)` using piecewise or soft formula + 0.75/0.25.
4. Decide CSV/UI column: replace vs dual-export alongside PCA `Caliber Uniformity Score`.
5. Do **not** regenerate locks from `phase1_collect.log`.

## 7. Japanese-ready summary

1. **ログから各機種の NV-CV / Dilated% が取れるか → NO**（ログは `stab_cv`/`loops`/`junction` のみ。原稿バッチ CSV なら YES）。
2. **原稿バッチロックは正しいか → YES**（CSV再計算と mean/std/median 等一致）。
3. **アプリ用 JSON を作って実装できるか → JSON: YES / 本番配線: NO（未実装・要意思決定）**。候補は `caliber_u2_device_ref_from_phase1.json`。

