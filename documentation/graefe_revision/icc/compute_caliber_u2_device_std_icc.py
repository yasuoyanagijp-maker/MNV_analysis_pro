#!/usr/bin/env python3
"""U2 with per-device (size_class / 機種層) locked μ/σ + median→50 scaling.

Context
-------
Original Caliber Uniformity (PCA Stability) locks stratum-wise μ/σ and
piecewise min/median/max in ``stability_ref_{small|large|small_3mm}.json``.
Those strata map 1:1 to manuscript devices (phase1_collect.log):

  small      → Optovue Solix / AngioVue 6×6 mm
  large      → Zeiss PlexElite 9000 6×6 mm
  small_3mm  → Zeiss CIRRUS HD AngioPlex 3×3 mm

U2 axes (``NV Diameter (CV)``, ``Dilated vessel (%)``) are **not** in
stability_ref JSON. This script:

1. Estimates locked per-stratum cuts from manuscript reference batch CSVs
   (same cohorts that built the app refs; prefer over ICC-pool re-fit).
2. Maps each ICC case to a stratum (filename / FOV heuristics).
3. Builds ``caliber_U2_device_std`` (piecewise, app-style) and
   ``caliber_U2_device_soft`` (soft tanh with locked median/SD).
4. Recomputes 3-rater ICC(2,1) vs original Caliber, C, and pooled U2.

Outputs (this directory)
------------------------
- caliber_u2_device_std_ref.json
- caliber_u2_device_std_long.csv
- caliber_u2_device_std_icc_stats.csv
- caliber_u2_device_std_icc_results.md
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = REPO_ROOT / "scripts" / "graefe_revision"
sys.path.insert(0, str(SCRIPTS))

from compute_icc_multirater import (  # noqa: E402
    INCOMING_DIR,
    OBSERVER_ALIASES_DIRS,
    OBSERVER_DIRS,
    _first_present,
    _load_observer_csvs,
    _normalize_case_id,
)

# Reuse helpers / loaders from the major-params script
sys.path.insert(0, str(Path(__file__).resolve().parent))
from compute_caliber_major_params_new_score import (  # noqa: E402
    CASE_ALIASES,
    DATE_ALIASES,
    icc_one,
    load_matched_long,
    piecewise_scale,
    soft_squash,
    spearman_vs_original,
)

OUT_DIR = Path(__file__).resolve().parent
DATA_DIR = REPO_ROOT / "documentation" / "graefe_revision" / "data"

# Manuscript reference batches (= device / size_class strata)
STRATUM_BATCHES = {
    "small": DATA_DIR / "MNV_batch_20260220_083448small.csv",
    "large": DATA_DIR / "MNV_batch_20260220_230245_large.csv",
    "small_3mm": DATA_DIR / "MNV_batch_20260220_223647_small_3mm.csv",
}

DEVICE_LABELS = {
    "small": "Optovue Solix / AngioVue 6×6 mm",
    "large": "Zeiss PlexElite 9000 6×6 mm",
    "small_3mm": "Zeiss CIRRUS HD AngioPlex 3×3 mm (Angiography 3x3)",
}

NV_COL = "NV Diameter (CV)"
DIL_COL = "Dilated vessel (%)"
W_CV, W_DIL = 0.75, 0.25


def _finite(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    return x[np.isfinite(x)]


def feature_cuts(values: np.ndarray) -> dict[str, float]:
    v = _finite(values)
    if len(v) < 2:
        raise ValueError("Need ≥2 finite values for stratum cuts")
    return {
        "n": float(len(v)),
        "mean": float(np.mean(v)),
        "std": float(np.std(v, ddof=1)),
        "min": float(np.min(v)),
        "median": float(np.median(v)),
        "max": float(np.max(v)),
        "p05": float(np.percentile(v, 5)),
        "p95": float(np.percentile(v, 95)),
    }


def build_locked_ref() -> dict:
    """Per-stratum locked μ/σ and piecewise anchors from manuscript batches."""
    ref: dict = {
        "description": (
            "Locked per-size_class (=device) cuts for U2 axes. "
            "Estimated from manuscript reference batch CSVs (not ICC pool). "
            "stability_ref_*.json has stab_* μ/σ only — NV CV / Dilated% absent."
        ),
        "source_batches": {k: str(v.relative_to(REPO_ROOT)) for k, v in STRATUM_BATCHES.items()},
        "device_labels": DEVICE_LABELS,
        "weights": {"U_cv": W_CV, "U_dil": W_DIL},
        "strata": {},
    }
    for stratum, path in STRATUM_BATCHES.items():
        df = pd.read_csv(path)
        nv = df[NV_COL].to_numpy(float)
        dil = df[DIL_COL].to_numpy(float)
        nv_c = feature_cuts(nv)
        dil_c = feature_cuts(dil)
        # Uniformity direction: lower raw → higher score → piecewise on (−x)
        neg_nv = feature_cuts(-_finite(nv))
        neg_dil = feature_cuts(-_finite(dil))
        ref["strata"][stratum] = {
            "device": DEVICE_LABELS[stratum],
            "n_cases": int(len(df)),
            "nv_cv": nv_c,
            "dilated_pct": dil_c,
            "neg_nv_cv_piecewise": {
                "min": neg_nv["min"],
                "median": neg_nv["median"],
                "max": neg_nv["max"],
            },
            "neg_dilated_piecewise": {
                "min": neg_dil["min"],
                "median": neg_dil["median"],
                "max": neg_dil["max"],
            },
        }
    return ref


def infer_stratum(file_name: str) -> str:
    """Map ICC File name → size_class / device stratum.

    The n=46 multi-rater set is entirely ``Angiography 3x3 mm`` → small_3mm.
    Heuristics retained for mixed-device future cohorts.
    """
    n = str(file_name).lower()
    if "3x3" in n or "3×3" in n or "3 x 3" in n:
        return "small_3mm"
    if "angiovue" in n or "optovue" in n or "solix" in n:
        return "small"
    if "plexelite" in n or "plex elite" in n or re.search(r"\bplex\b", n):
        return "large"
    if "cirrus" in n or "angioplex" in n:
        return "small_3mm" if ("3x3" in n or "3×3" in n) else "large"
    if "6x6" in n or "6×6" in n:
        # Ambiguous device without vendor token — default large (Zeiss 6×6 cohort)
        return "large"
    return "small_3mm"  # conservative default matching this ICC set


def u_piecewise_locked(x: np.ndarray, pw: dict[str, float]) -> np.ndarray:
    """App-style piecewise on (−x) with locked min/median/max (median→50)."""
    neg = -np.asarray(x, dtype=float)
    return piecewise_scale(neg, pw["min"], pw["median"], pw["max"])


def u_soft_locked(x: np.ndarray, cuts: dict[str, float]) -> np.ndarray:
    """Soft map with locked stratum median/SD (score=50 at median)."""
    return soft_squash(x, cuts["median"], max(cuts["std"], 1e-9))


def score_device_std(df: pd.DataFrame, locked: dict) -> pd.DataFrame:
    out = df.copy()
    strata = []
    u_cv_pw, u_dil_pw = [], []
    u_cv_soft, u_dil_soft = [], []

    for _, row in out.iterrows():
        raw = row.get("case_id_raw", row["case_id"])
        st = infer_stratum(str(raw))
        strata.append(st)
        sref = locked["strata"][st]
        nv = float(row[NV_COL])
        dil = float(row[DIL_COL])
        u_cv_pw.append(float(u_piecewise_locked(np.array([nv]), sref["neg_nv_cv_piecewise"])[0]))
        u_dil_pw.append(float(u_piecewise_locked(np.array([dil]), sref["neg_dilated_piecewise"])[0]))
        u_cv_soft.append(float(u_soft_locked(np.array([nv]), sref["nv_cv"])[0]))
        u_dil_soft.append(float(u_soft_locked(np.array([dil]), sref["dilated_pct"])[0]))

    out["stratum"] = strata
    out["device_label"] = out["stratum"].map(DEVICE_LABELS)
    out["U_cv_device_pw"] = u_cv_pw
    out["U_dil_device_pw"] = u_dil_pw
    out["U_cv_device_soft"] = u_cv_soft
    out["U_dil_device_soft"] = u_dil_soft
    out["caliber_U2_device_std"] = np.clip(
        W_CV * np.asarray(u_cv_pw) + W_DIL * np.asarray(u_dil_pw), 0, 100
    )
    out["caliber_U2_device_soft"] = np.clip(
        W_CV * np.asarray(u_cv_soft) + W_DIL * np.asarray(u_dil_soft), 0, 100
    )
    return out


def build_pooled_u2_and_c(df: pd.DataFrame) -> pd.DataFrame:
    """Recompute pooled C and U2 (ICC-pool cuts) for head-to-head."""
    from compute_caliber_major_params_new_score import ref_cuts, u_neg_winsor

    out = df.copy()
    nv = out[NV_COL].to_numpy(float)
    dil = out[DIL_COL].to_numpy(float)
    nv_c = ref_cuts(nv)
    out["caliber_C_winsor_inv_nv_cv"] = u_neg_winsor(nv, 5, 95)
    u_soft = soft_squash(nv, nv_c["median"], max(nv_c["std"], 1e-6))
    u_d = u_neg_winsor(dil, 5, 95)
    out["caliber_U2_softcv_dil"] = np.clip(0.75 * u_soft + 0.25 * u_d, 0, 100)
    return out


def evaluate_metrics(df: pd.DataFrame, metrics: list[str]) -> pd.DataFrame:
    rows = []
    base = icc_one(df, "Caliber Uniformity Score")["icc_2_1"]
    c_icc = icc_one(df, "caliber_C_winsor_inv_nv_cv")["icc_2_1"]
    for m in metrics:
        r = icc_one(df, m)
        sp = spearman_vs_original(df, m) if m != "Caliber Uniformity Score" else {
            "YY": 1.0, "Inoue": 1.0, "Osada": 1.0
        }
        r["delta_vs_original"] = r["icc_2_1"] - base
        r["delta_vs_C"] = r["icc_2_1"] - c_icc
        r["spearman_mean"] = float(np.nanmean(list(sp.values())))
        r["score_median"] = float(np.nanmedian(df[m].to_numpy(float)))
        r["score_mean"] = float(np.nanmean(df[m].to_numpy(float)))
        rows.append(r)
    return pd.DataFrame(rows)


def write_md(stats: pd.DataFrame, locked: dict, stratum_counts: dict, path: Path) -> None:
    def row(m: str) -> pd.Series:
        return stats.loc[stats["metric"] == m].iloc[0]

    o0, c0 = row("Caliber Uniformity Score"), row("caliber_C_winsor_inv_nv_cv")
    u2p0 = row("caliber_U2_softcv_dil")
    u2d0, u2s0 = row("caliber_U2_device_std"), row("caliber_U2_device_soft")

    lines = [
        "# Caliber U2 — per-device (size_class) standardization ICC",
        "",
        "**Date:** 2026-07-31  ",
        "**Set:** YY / Inoue / Osada · intersection **n = 46** · ICC(2,1) absolute agreement  ",
        "**Script:** `compute_caliber_u2_device_std_icc.py`",
        "",
        "---",
        "",
        "## 日本語サマリー",
        "",
        "| 項目 | 結論 |",
        "|------|------|",
        "| (a) 理論的に中央値≈50にできるか | **PARTIAL** — 層（=機種/FOV）ごとに locked μ/σ＋piecewise（median→50）は PCA と同型で可能。"
        "アプリ JSON に NV-CV/Dilated% の μ/σは無し（原稿バッチから推定）。本 ICC は単層 `small_3mm`。 |",
        "| (b) 実装したか | **YES** — `caliber_U2_device_std` / `caliber_U2_device_soft`（75/25） |",
        f"| (c) ICC | 原 {o0['icc_2_1']:.3f} / C {c0['icc_2_1']:.3f} / プール U2 {u2p0['icc_2_1']:.3f} / "
        f"**device_std {u2d0['icc_2_1']:.3f}** / device_soft {u2s0['icc_2_1']:.3f} |",
        "",
        "---",
        "",
        "## Theoretical verdict",
        "",
        "**PARTIAL — yes within a device/size_class stratum; not a drop-in of locked app JSON for these axes.**",
        "",
        "| Question | Answer |",
        "|----------|--------|",
        "| Can U2 use the same *style* as PCA Caliber (stratum μ/σ + median→50)? | **YES** |",
        "| Do app `stability_ref_*.json` already lock μ/σ for NV CV / Dilated%? | **NO** (`stab_*` only) |",
        "| What substitutes? | Manuscript reference batch CSVs per size_class (= device) |",
        "| Does this ICC set span multiple devices? | **NO** — all 46 files are `Angiography 3x3 mm` → `small_3mm` |",
        "| Therefore multi-device centering empirically? | **Not testable here** (single-stratum degenerate) |",
        "| Missing vs original PCA | Frozen PCA loadings; `stab_*` features; locked JSON for these exact CSV columns; multi-stratum ICC sample |",
        "",
        "### Device ↔ size_class (from `output/phase1_collect.log`)",
        "",
        "| Stratum | Device | Training n |",
        "|---------|--------|------------|",
    ]
    for st, info in locked["strata"].items():
        lines.append(
            f"| `{st}` | {info['device']} | {info['n_cases']} |"
        )

    lines += [
        "",
        "### Locked cuts used for `small_3mm` (this ICC set)",
        "",
        "```",
        json.dumps(locked["strata"]["small_3mm"], indent=2),
        "```",
        "",
        "### Scoring formulas",
        "",
        "- **`caliber_U2_device_std`** (app-style): "
        "for each case’s stratum, "
        "`U_cv = piecewise(−NV_CV; locked min/median/max)`, "
        "`U_dil = piecewise(−Dilated%; locked min/median/max)`, "
        f"**Score = {W_CV}·U_cv + {W_DIL}·U_dil** (clip 0–100).",
        "- **`caliber_U2_device_soft`**: "
        "`U_cv = 50 + 50·tanh((μ̃−NV_CV)/σ)` with locked stratum median/SD; "
        "same for Dilated%; same 75/25 blend.",
        "- Contrast: pooled `caliber_U2_softcv_dil` re-estimates median/SD on the ICC 46×3 pool.",
        "",
        f"**Stratum assignment in this run:** {stratum_counts}",
        "",
        "---",
        "",
        "## Empirical ICC(2,1)",
        "",
        "| Metric | ICC(2,1) | 95% CI | Δ vs orig | Δ vs C | Score median | Score mean |",
        "|--------|----------|--------|-----------|--------|--------------|------------|",
    ]
    order = [
        "Caliber Uniformity Score",
        "caliber_C_winsor_inv_nv_cv",
        "caliber_U2_softcv_dil",
        "caliber_U2_device_std",
        "caliber_U2_device_soft",
    ]
    for m in order:
        r = row(m)
        ci = f"{r['ci_low']:.3f}–{r['ci_high']:.3f}" if pd.notna(r.get("ci_low")) else "—"
        lines.append(
            f"| `{m}` | {r['icc_2_1']:.3f} | {ci} | "
            f"{r['delta_vs_original']:+.3f} | {r['delta_vs_C']:+.3f} | "
            f"{r['score_median']:.1f} | {r['score_mean']:.1f} |"
        )

    u2d = row("caliber_U2_device_std")
    u2s = row("caliber_U2_device_soft")
    u2p = row("caliber_U2_softcv_dil")
    lines += [
        "",
        "### Interpretation",
        "",
        f"- Device-locked piecewise U2 ICC = **{u2d['icc_2_1']:.3f}** "
        f"(soft twin **{u2s['icc_2_1']:.3f}**) vs pooled U2 **{u2p['icc_2_1']:.3f}** "
        f"and original **{row('Caliber Uniformity Score')['icc_2_1']:.3f}**.",
        f"- Score medians on ICC pool: device_std **{u2d['score_median']:.1f}**, "
        f"device_soft **{u2s['score_median']:.1f}**, pooled U2 **{u2p['score_median']:.1f}**, "
        f"original Caliber **{row('Caliber Uniformity Score')['score_median']:.1f}**.",
        "- Median≈50 is guaranteed **on the locking (training) cohort** at the feature "
        "piecewise / soft center; on a new cohort it is only approximate "
        "(distribution shift). Here ICC is all `small_3mm`, so multi-device "
        "re-centering cannot be shown.",
        "- Prefer device-locked cuts for **transferability** (no ICC-pool re-fit); "
        "pooled U2 remains a strong within-study sensitivity score.",
        "",
        "---",
        "",
        "## Files",
        "",
        "- `caliber_u2_device_std_ref.json` — locked stratum cuts",
        "- `caliber_u2_device_std_long.csv` — per rating scores",
        "- `caliber_u2_device_std_icc_stats.csv` — ICC table",
        "- `caliber_u2_device_std_icc_results.md` — this report",
        "",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    print("Building locked per-device (size_class) reference…")
    locked = build_locked_ref()
    ref_path = OUT_DIR / "caliber_u2_device_std_ref.json"
    ref_path.write_text(json.dumps(locked, indent=2), encoding="utf-8")
    print(f"  wrote {ref_path}")

    print("Loading matched n=46…")
    df0 = load_matched_long()
    need = [NV_COL, DIL_COL, "Caliber Uniformity Score"]
    missing = [c for c in need if c not in df0.columns]
    if missing:
        raise SystemExit(f"Missing columns: {missing}")

    df = score_device_std(df0, locked)
    df = build_pooled_u2_and_c(df)
    stratum_counts = df.groupby("stratum")["case_id"].nunique().to_dict()
    print("  stratum case counts:", stratum_counts)

    metrics = [
        "Caliber Uniformity Score",
        "caliber_C_winsor_inv_nv_cv",
        "caliber_U2_softcv_dil",
        "caliber_U2_device_std",
        "caliber_U2_device_soft",
    ]
    stats = evaluate_metrics(df, metrics)
    stats.to_csv(OUT_DIR / "caliber_u2_device_std_icc_stats.csv", index=False)

    keep = [
        "case_id",
        "case_id_raw",
        "observer",
        "stratum",
        "device_label",
        NV_COL,
        DIL_COL,
        "Caliber Uniformity Score",
        "caliber_C_winsor_inv_nv_cv",
        "caliber_U2_softcv_dil",
        "U_cv_device_pw",
        "U_dil_device_pw",
        "caliber_U2_device_std",
        "U_cv_device_soft",
        "U_dil_device_soft",
        "caliber_U2_device_soft",
    ]
    df[keep].to_csv(OUT_DIR / "caliber_u2_device_std_long.csv", index=False)

    write_md(stats, locked, stratum_counts, OUT_DIR / "caliber_u2_device_std_icc_results.md")
    print(stats[["metric", "icc_2_1", "score_median"]].to_string(index=False))
    print("Done.")


if __name__ == "__main__":
    main()
