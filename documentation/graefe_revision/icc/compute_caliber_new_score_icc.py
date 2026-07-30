#!/usr/bin/env python3
"""Recompute Caliber Uniformity ICC with CSV-only new scores (no re-ROI).

Constraint
----------
Use only columns already present in the 3-observer ImageJ-compatible batch CSVs.
Do NOT re-segment, re-skeletonize, or re-draw ROI.

Primary outputs (this directory)
--------------------------------
- caliber_new_score_long.csv
- caliber_new_score_wide.csv
- caliber_new_score_icc_stats.csv
- caliber_new_score_icc_results.md
"""

from __future__ import annotations

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
    icc_2_1_multirater,
    try_pingouin_icc,
    variance_components_anova,
)

OUT_DIR = Path(__file__).resolve().parent

FEATURE_ALIASES = {
    "caliber_uniformity": (
        "Caliber Uniformity Score",
        "caliber_uniformity",
    ),
    "complexity": (
        "Network Complexity Score",
        "complexity",
    ),
    "maturity": (
        "Maturity Index",
        "maturity",
    ),
    "area": (
        "MNV Area (mm2)",
        "MNV Area (mm²)",
        "area",
    ),
    "nv_diameter_cv": (
        "NV Diameter (CV)",
        "nv_diameter_cv",
        "cv_diameter",
    ),
    "local_max_cv": (
        "Local Diameter Variation (max CV%)",
        "local_max_cv",
        "localized_diameter_variation",
    ),
    "skel_diameter": (
        "(Skel) Vsl Diameter",
        "skel_diameter",
        "Skel Vsl Diameter",
    ),
    "raw_diameter": (
        "Raw Vsl Diameter",
        "raw_diameter",
    ),
    "vsl_branches": (
        "Vsl Branches",
        "vsl_branches",
    ),
    "vsl_length": (
        "Vsl Length (mm)",
        "vsl_length",
    ),
    "vsl_density": (
        "Vsl Density (Vessel Area/MNV (%))",
        "vsl_density",
    ),
    "dilated_pct": (
        "Dilated vessel (%)",
        "dilated_pct",
    ),
    "arteriol_n": (
        "Arteriolarization Segment Count",
        "arteriol_n",
    ),
}

CASE_ALIASES = ("case_id", "icc_id", "Case", "File", "file_name", "image_key")
DATE_ALIASES = ("date", "session_date", "analysis_date", "timestamp", "Started At")


def piecewise_scale(x: np.ndarray, x_min: float, x_med: float, x_max: float) -> np.ndarray:
    """Map values so median → 50, min → 0, max → 100 (clip)."""
    x = np.asarray(x, dtype=float)
    out = np.full_like(x, np.nan, dtype=float)
    low = np.isfinite(x) & (x <= x_med)
    high = np.isfinite(x) & (x > x_med)
    if x_med > x_min:
        out[low] = 50.0 * (x[low] - x_min) / (x_med - x_min)
    else:
        out[low] = 50.0
    if x_max > x_med:
        out[high] = 50.0 + 50.0 * (x[high] - x_med) / (x_max - x_med)
    else:
        out[high] = 50.0
    return np.clip(out, 0.0, 100.0)


def winsorize(x: np.ndarray, lo: float, hi: float) -> np.ndarray:
    return np.clip(np.asarray(x, dtype=float), lo, hi)


def load_features() -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    for name in OBSERVER_DIRS:
        folder = INCOMING_DIR / name
        raw = _load_observer_csvs(folder)
        if raw is None:
            raise FileNotFoundError(f"No CSV in {folder}")
        case_col = _first_present(raw.columns, CASE_ALIASES)
        if case_col is None:
            raise ValueError(f"No case column in {folder}")
        out = pd.DataFrame()
        out["case_id"] = raw[case_col].map(_normalize_case_id)
        out["case_id_raw"] = raw[case_col].astype(str).str.strip()
        out["observer"] = OBSERVER_ALIASES_DIRS[name]
        date_col = _first_present(raw.columns, DATE_ALIASES)
        out["date"] = raw[date_col] if date_col is not None else pd.NA
        for canon, aliases in FEATURE_ALIASES.items():
            col = _first_present(raw.columns, aliases)
            if col is None:
                raise ValueError(f"Missing column for {canon} in {folder}: tried {aliases}")
            out[canon] = pd.to_numeric(raw[col], errors="coerce")
        out = out[out["case_id"] != ""].drop_duplicates(subset=["case_id"], keep="first")
        parts.append(out)

    combined = pd.concat(parts, ignore_index=True)
    sets = {o: set(g["case_id"]) for o, g in combined.groupby("observer")}
    intersection = set.intersection(*sets.values())
    if len(intersection) != 46:
        print(f"WARNING: intersection n={len(intersection)} (expected 46)")
    return combined[combined["case_id"].isin(intersection)].copy()


def ref_cuts(values: np.ndarray) -> dict[str, float]:
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    return {
        "p05": float(np.percentile(v, 5)),
        "p95": float(np.percentile(v, 95)),
        "min": float(np.min(v)),
        "median": float(np.median(v)),
        "max": float(np.max(v)),
    }


def build_scores(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Add candidate new Caliber scores; return df + formula metadata."""
    nv = df["nv_diameter_cv"].to_numpy(float)
    loc = df["local_max_cv"].to_numpy(float)
    skel = df["skel_diameter"].to_numpy(float)
    cal0 = df["caliber_uniformity"].to_numpy(float)

    nv_cuts = ref_cuts(nv)
    loc_cuts = ref_cuts(loc)
    skel_cuts = ref_cuts(skel)
    cal0_cuts = ref_cuts(cal0)

    # --- Candidate C: Winsorize weak CV, map low CV → high uniformity (exclude Local) ---
    nv_w = winsorize(nv, nv_cuts["p05"], nv_cuts["p95"])
    # Stability direction: smaller CV is better → score on -CV
    neg_nv = -nv_w
    neg_cuts = ref_cuts(neg_nv)
    caliber_C = piecewise_scale(
        neg_nv, neg_cuts["min"], neg_cuts["median"], neg_cuts["max"]
    )

    # --- Intermediate: Winsorize both CVs; downweight Local (0.85 / 0.15) ---
    loc_w = winsorize(loc, loc_cuts["p05"], loc_cuts["p95"])
    neg_loc = -loc_w
    neg_loc_cuts = ref_cuts(neg_loc)
    u_nv = caliber_C
    u_loc = piecewise_scale(
        neg_loc, neg_loc_cuts["min"], neg_loc_cuts["median"], neg_loc_cuts["max"]
    )
    caliber_C_local = np.clip(0.85 * u_nv + 0.15 * u_loc, 0.0, 100.0)

    # --- Candidate A/B: robust CV + high-ICC mean diameter (construct hybrid) ---
    u_skel = piecewise_scale(
        skel, skel_cuts["min"], skel_cuts["median"], skel_cuts["max"]
    )
    caliber_AB = np.clip(0.70 * u_nv + 0.30 * u_skel, 0.0, 100.0)

    # --- Baseline: Winsorize original Caliber score only ---
    caliber_winsor_orig = winsorize(cal0, cal0_cuts["p05"], cal0_cuts["p95"])
    # Re-scale winsorized original onto 0–100 with median→50 for comparability
    caliber_W = piecewise_scale(
        caliber_winsor_orig,
        float(np.min(caliber_winsor_orig[np.isfinite(caliber_winsor_orig)])),
        float(np.median(caliber_winsor_orig[np.isfinite(caliber_winsor_orig)])),
        float(np.max(caliber_winsor_orig[np.isfinite(caliber_winsor_orig)])),
    )

    out = df.copy()
    out["caliber_C_winsor_inv_nv_cv"] = caliber_C
    out["caliber_C_local_downweight"] = caliber_C_local
    out["caliber_AB_cv70_skel30"] = caliber_AB
    out["caliber_W_winsor_orig"] = caliber_W

    # Maturity redefined with each new caliber (Complexity unchanged)
    cx = out["complexity"].to_numpy(float)
    out["maturity_from_C"] = 50.0 + (caliber_C - cx) / 2.0
    out["maturity_from_AB"] = 50.0 + (caliber_AB - cx) / 2.0

    meta = {
        "nv_cuts": nv_cuts,
        "loc_cuts": loc_cuts,
        "skel_cuts": skel_cuts,
        "cal0_cuts": cal0_cuts,
        "formulas": {
            "caliber_C_winsor_inv_nv_cv": (
                "Winsorize NV Diameter (CV) at pooled p05–p95; "
                "piecewise-scale (−CV) so median→50 (higher = more uniform). "
                "Local max CV excluded."
            ),
            "caliber_C_local_downweight": (
                "0.85 × U(winsor NV CV) + 0.15 × U(winsor Local max CV); "
                "each U is piecewise (−CV → 0–100)."
            ),
            "caliber_AB_cv70_skel30": (
                "0.70 × U(winsor NV CV) + 0.30 × U(skel mean diameter); "
                "U = piecewise median→50. Hybrid: uniformity + high-ICC mean caliber."
            ),
            "caliber_W_winsor_orig": (
                "Winsorize original Caliber Uniformity Score at pooled p05–p95, "
                "then piecewise re-scale median→50."
            ),
        },
    }
    return out, meta


def icc_table(long_df: pd.DataFrame, metrics: list[str]) -> pd.DataFrame:
    rows = []
    observers = sorted(long_df["observer"].unique())
    for metric in metrics:
        pg = try_pingouin_icc(long_df, metric)
        # wide matrix for numpy fallback / VC
        wide = long_df.pivot_table(
            index="case_id", columns="observer", values=metric, aggfunc="first"
        )
        wide = wide.reindex(columns=observers)
        arr = wide.to_numpy(dtype=float)
        fb = icc_2_1_multirater(arr)
        vc = variance_components_anova(arr)
        if pg is not None:
            icc, lo, hi, src = pg["icc"], pg["ci_low"], pg["ci_high"], "pingouin"
            n, k = pg["n"], pg["k"]
        else:
            icc, lo, hi, src = fb["icc"], fb["ci_low"], fb["ci_high"], "numpy"
            n, k = fb["n"], fb["k"]
        rows.append(
            {
                "metric": metric,
                "n": int(n),
                "k": int(k),
                "icc_2_1": icc,
                "ci_low": lo,
                "ci_high": hi,
                "source": src,
                "var_case": vc["var_case"],
                "var_observer": vc["var_observer"],
                "var_error": vc["var_error"],
                "icc_vc": vc["icc_vc"],
            }
        )
    return pd.DataFrame(rows)


def pairwise_icc(long_df: pd.DataFrame, metric: str) -> pd.DataFrame:
    pairs = [("YY", "Inoue"), ("YY", "Osada"), ("Inoue", "Osada")]
    rows = []
    for a, b in pairs:
        sub = long_df[long_df["observer"].isin([a, b])]
        pg = try_pingouin_icc(sub, metric)
        if pg is None:
            wide = sub.pivot_table(
                index="case_id", columns="observer", values=metric, aggfunc="first"
            )
            fb = icc_2_1_multirater(wide[[a, b]].to_numpy(float))
            icc, lo, hi, src = fb["icc"], fb["ci_low"], fb["ci_high"], "numpy"
        else:
            icc, lo, hi, src = pg["icc"], pg["ci_low"], pg["ci_high"], "pingouin"
        rows.append(
            {
                "metric": metric,
                "pair": f"{a}–{b}",
                "icc_2_1": icc,
                "ci_low": lo,
                "ci_high": hi,
                "source": src,
            }
        )
    return pd.DataFrame(rows)


def fmt_ci(lo: float, hi: float) -> str:
    if not (np.isfinite(lo) and np.isfinite(hi)):
        return "—"
    return f"{lo:.3f}–{hi:.3f}"


def write_results_md(
    stats: pd.DataFrame,
    pairwise: pd.DataFrame,
    meta: dict,
    primary: str,
    secondary: str,
) -> str:
    s = stats.set_index("metric")
    orig = "caliber_uniformity"
    lines = []
    lines.append("# New Caliber Uniformity Score — ICC comparison (CSV-only)")
    lines.append("")
    lines.append("**Date:** 2026-07-30  ")
    lines.append("**Set:** YY, Inoue, Osada · intersection **n = 46** · ICC(2,1) absolute agreement  ")
    lines.append("**Constraint:** existing batch CSV columns only — **no re-ROI / no re-segmentation**  ")
    lines.append("**Script:** `compute_caliber_new_score_icc.py`")
    lines.append("")
    lines.append("## Adopted formulas")
    lines.append("")
    lines.append(f"### Primary new score: `{primary}`")
    lines.append("")
    lines.append(meta["formulas"][primary])
    lines.append("")
    lines.append(
        "Explicit steps (pooled over all 138 ratings = 46×3 for reference cuts):"
    )
    lines.append("")
    nv = meta["nv_cuts"]
    lines.append(
        f"1. Let `CV` = `NV Diameter (CV)`. Winsorize to "
        f"[{nv['p05']:.4f}, {nv['p95']:.4f}] (pooled p05–p95)."
    )
    lines.append(
        "2. Score direction: lower CV → higher uniformity. Set `x = −CV_w`."
    )
    lines.append(
        "3. Piecewise linear map of `x` with min/median/max → 0 / 50 / 100 "
        "(same median-anchor style as pipeline Stability Score)."
    )
    lines.append("")
    lines.append(f"### Secondary (intermediate): `{secondary}`")
    lines.append("")
    lines.append(meta["formulas"][secondary])
    lines.append("")
    lines.append("### Other candidates evaluated")
    lines.append("")
    for k, v in meta["formulas"].items():
        if k in (primary, secondary):
            continue
        lines.append(f"- `{k}`: {v}")
    lines.append("")
    lines.append("### Maturity redefinition (secondary columns only)")
    lines.append("")
    lines.append(
        "`maturity_from_*` = `50 + (caliber_new − Network Complexity Score) / 2` "
        "(same algebra as original Maturity Index)."
    )
    lines.append("")
    lines.append("## Primary ICC(2,1) comparison (n=46, k=3)")
    lines.append("")
    lines.append("| Metric | ICC(2,1) | 95% CI | Δ vs original Caliber | Source |")
    lines.append("|--------|----------|--------|------------------------|--------|")
    base_icc = float(s.loc[orig, "icc_2_1"])
    order = [
        "area",
        "complexity",
        "caliber_uniformity",
        primary,
        secondary,
        "caliber_C_local_downweight",
        "caliber_W_winsor_orig",
        "maturity",
        "maturity_from_C",
        "maturity_from_AB",
    ]
    labels = {
        "area": "MNV Area (mm²) [ref]",
        "complexity": "Network Complexity [ref]",
        "caliber_uniformity": "Caliber Uniformity (original)",
        primary: f"**{primary} (PRIMARY new)**",
        secondary: f"{secondary} (secondary)",
        "caliber_C_local_downweight": "caliber_C_local_downweight",
        "caliber_W_winsor_orig": "caliber_W_winsor_orig",
        "maturity": "Maturity Index (original)",
        "maturity_from_C": "Maturity from primary new Caliber",
        "maturity_from_AB": "Maturity from AB hybrid",
    }
    for m in order:
        if m not in s.index:
            continue
        icc = float(s.loc[m, "icc_2_1"])
        lo = float(s.loc[m, "ci_low"])
        hi = float(s.loc[m, "ci_high"])
        if m in (
            "caliber_uniformity",
            primary,
            secondary,
            "caliber_C_local_downweight",
            "caliber_W_winsor_orig",
        ):
            delta = f"{icc - base_icc:+.3f}"
        elif m.startswith("maturity"):
            delta = "—"
        else:
            delta = "—"
        lines.append(
            f"| {labels.get(m, m)} | {icc:.3f} | {fmt_ci(lo, hi)} | {delta} | "
            f"{s.loc[m, 'source']} |"
        )
    lines.append("")
    lines.append("## Pairwise ICC(2,1) — original vs primary new")
    lines.append("")
    lines.append("| Metric | Pair | ICC(2,1) | 95% CI |")
    lines.append("|--------|------|----------|--------|")
    for _, r in pairwise.iterrows():
        lines.append(
            f"| {r['metric']} | {r['pair']} | {r['icc_2_1']:.3f} | "
            f"{fmt_ci(r['ci_low'], r['ci_high'])} |"
        )
    lines.append("")
    lines.append("## Variance components (primary new vs original Caliber)")
    lines.append("")
    lines.append("| Metric | σ²_case | σ²_observer | σ²_error | ICC_vc |")
    lines.append("|--------|---------|-------------|---------|--------|")
    for m in (orig, primary, secondary):
        lines.append(
            f"| {m} | {s.loc[m, 'var_case']:.4g} | {s.loc[m, 'var_observer']:.4g} | "
            f"{s.loc[m, 'var_error']:.4g} | {s.loc[m, 'icc_vc']:.3f} |"
        )
    lines.append("")
    lines.append("## Columns used (existing CSV only)")
    lines.append("")
    lines.append("| Role | Batch CSV column |")
    lines.append("|------|------------------|")
    lines.append("| Original Caliber | `Caliber Uniformity Score` |")
    lines.append("| Primary input | `NV Diameter (CV)` |")
    lines.append("| Secondary / downweight | `Local Diameter Variation (max CV%)` |")
    lines.append("| High-ICC blend | `(Skel) Vsl Diameter` |")
    lines.append("| Maturity partner | `Network Complexity Score` |")
    lines.append("| Matching | `File` (basename, lowercased, ext stripped) |")
    lines.append("")
    lines.append("**Not available in batch CSV (cannot use without recompute):** "
                 "`stab_cv`, `stab_mean_adjacent_change`, `stab_residual_cv`, "
                 "`stab_range_percent`, radial 10-bin diameter profile.")
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    p_icc = float(s.loc[primary, "icc_2_1"])
    ab_icc = float(s.loc[secondary, "icc_2_1"])
    improved = p_icc > base_icc
    lines.append(
        f"- Original Caliber ICC(2,1) = **{base_icc:.3f}**; "
        f"primary new (`{primary}`) = **{p_icc:.3f}** "
        f"({p_icc - base_icc:+.3f})."
    )
    lines.append(
        f"- Secondary hybrid (`{secondary}`) = **{ab_icc:.3f}** "
        f"({ab_icc - base_icc:+.3f})."
    )
    if improved:
        lines.append(
            "- **ICC improved** under a CSV-only redefinition that drops the "
            "lowest-ICC Local max CV channel and robustifies NV Diameter CV."
        )
    else:
        lines.append(
            "- Primary new score did **not** improve ICC vs original; see AB hybrid / other candidates."
        )
    lines.append(
        "- The AB hybrid can raise ICC further by mixing in skel mean diameter "
        "(high ICC), but that **shifts the construct** from pure caliber "
        "*uniformity/stability* toward a caliber-level hybrid — treat as exploratory."
    )
    lines.append("")
    lines.append("## Caveats (Graefe revision)")
    lines.append("")
    lines.append(
        "- This is a **sensitivity / exploratory** analysis. Do **not** replace "
        "the manuscript’s primary Caliber Uniformity definition mid-revision "
        "without explicit disclosure to reviewers."
    )
    lines.append(
        "- Reference cuts (p05/p95/min/median/max) are estimated on this n=46×3 "
        "pooled set (not the original stratum reference JSON)."
    )
    lines.append(
        "- No cherry-picking of cases: full intersection n=46 retained."
    )
    lines.append(
        "- Improving ICC by importing high-ICC non-uniformity features "
        "(mean diameter, branches) is methodologically different from "
        "strengthening the original Stability Score pipeline."
    )
    lines.append("")
    lines.append("## Output files")
    lines.append("")
    lines.append("- `caliber_new_score_long.csv`")
    lines.append("- `caliber_new_score_wide.csv`")
    lines.append("- `caliber_new_score_icc_stats.csv`")
    lines.append("- `caliber_new_score_icc_pairwise.csv`")
    lines.append("- `caliber_new_score_icc_results.md` (this file)")
    lines.append("- `compute_caliber_new_score_icc.py`")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    df = load_features()
    scored, meta = build_scores(df)

    metrics = [
        "area",
        "complexity",
        "caliber_uniformity",
        "caliber_C_winsor_inv_nv_cv",
        "caliber_C_local_downweight",
        "caliber_AB_cv70_skel30",
        "caliber_W_winsor_orig",
        "maturity",
        "maturity_from_C",
        "maturity_from_AB",
    ]
    stats = icc_table(scored, metrics)

    # Choose primary = best among CV-faithful candidates (C and C_local), not AB
    faithful = ["caliber_C_winsor_inv_nv_cv", "caliber_C_local_downweight", "caliber_W_winsor_orig"]
    faithful_icc = {
        m: float(stats.loc[stats["metric"] == m, "icc_2_1"].iloc[0]) for m in faithful
    }
    primary = max(faithful_icc, key=faithful_icc.get)
    secondary = "caliber_AB_cv70_skel30"

    # Long / wide exports
    long_cols = [
        "case_id",
        "case_id_raw",
        "observer",
        "date",
        "area",
        "complexity",
        "caliber_uniformity",
        "caliber_C_winsor_inv_nv_cv",
        "caliber_C_local_downweight",
        "caliber_AB_cv70_skel30",
        "caliber_W_winsor_orig",
        "maturity",
        "maturity_from_C",
        "maturity_from_AB",
        "nv_diameter_cv",
        "local_max_cv",
        "skel_diameter",
    ]
    long_path = OUT_DIR / "caliber_new_score_long.csv"
    scored[long_cols].sort_values(["case_id", "observer"]).to_csv(
        long_path, index=False
    )

    wide_metrics = [
        "caliber_uniformity",
        "caliber_C_winsor_inv_nv_cv",
        "caliber_C_local_downweight",
        "caliber_AB_cv70_skel30",
        "caliber_W_winsor_orig",
        "maturity",
        "maturity_from_C",
        "maturity_from_AB",
        "area",
        "complexity",
        "nv_diameter_cv",
        "local_max_cv",
        "skel_diameter",
    ]
    wide_parts = []
    for m in wide_metrics:
        w = scored.pivot_table(
            index="case_id", columns="observer", values=m, aggfunc="first"
        )
        w.columns = [f"{m}_{c}" for c in w.columns]
        wide_parts.append(w)
    wide = pd.concat(wide_parts, axis=1).reset_index()
    # attach one example raw file name
    raw_ex = (
        scored.sort_values("observer")
        .groupby("case_id", as_index=False)
        .first()[["case_id", "case_id_raw"]]
        .rename(columns={"case_id_raw": "file_example"})
    )
    wide = raw_ex.merge(wide, on="case_id", how="right")
    wide_path = OUT_DIR / "caliber_new_score_wide.csv"
    wide.to_csv(wide_path, index=False)

    stats_path = OUT_DIR / "caliber_new_score_icc_stats.csv"
    stats.to_csv(stats_path, index=False)

    pw = pd.concat(
        [
            pairwise_icc(scored, "caliber_uniformity"),
            pairwise_icc(scored, primary),
            pairwise_icc(scored, secondary),
        ],
        ignore_index=True,
    )
    pw_path = OUT_DIR / "caliber_new_score_icc_pairwise.csv"
    pw.to_csv(pw_path, index=False)

    md = write_results_md(stats, pw, meta, primary=primary, secondary=secondary)
    md_path = OUT_DIR / "caliber_new_score_icc_results.md"
    md_path.write_text(md, encoding="utf-8")

    # Also write a short proposals companion if missing / update pointer
    proposals = OUT_DIR / "caliber_cv_strengthening_proposals.md"
    if not proposals.exists():
        proposals.write_text(
            "# Caliber CV strengthening — CSV-only proposals\n\n"
            "See `caliber_new_score_icc_results.md` for the implemented new-score "
            "experiment (existing batch columns only; no re-ROI).\n",
            encoding="utf-8",
        )

    print("n cases:", scored["case_id"].nunique())
    print("observers:", sorted(scored["observer"].unique()))
    print(stats[["metric", "icc_2_1", "ci_low", "ci_high"]].to_string(index=False))
    print("PRIMARY:", primary, "ICC=", faithful_icc[primary])
    print("Wrote:", md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
