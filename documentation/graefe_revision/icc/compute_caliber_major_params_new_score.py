#!/usr/bin/env python3
"""All-numeric ICC (n=46) + caliber-uniformity major-param shortlist + new scores.

Parts
-----
1. ICC(2,1) for every usable numeric batch-CSV column (matched File IDs, k=3).
2. Logical major parameters for caliber uniformity (documented in markdown).
3. Candidate scores preferring existing CSV columns; compare vs original Caliber
   (ICC≈0.434) and caliber_C_winsor_inv_nv_cv (ICC≈0.765).

Outputs (this directory)
------------------------
- icc_all_numeric_params_n46.md / .csv
- caliber_major_params_new_score.md
- caliber_major_params_new_score_icc_stats.csv
- caliber_major_params_new_score_long.csv
- caliber_major_params_candidates.csv
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

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

CASE_ALIASES = ("case_id", "icc_id", "Case", "File", "file_name", "image_key")
DATE_ALIASES = ("date", "session_date", "analysis_date", "timestamp", "Started At")

# Meta / ID / QC flags — exclude from "morphological" ICC ranking
EXCLUDE_COLS = {
    "ID",
    "Duration Sec",
    "FD quality flag (0=OK 1=abnormal)",
    "Exclude from FD analysis",
    "FD quality reason",
    "ROI coverage low quality (0=OK 1=low)",
    "N FD box sizes",
    "FD scale insufficient (0=OK 1=insufficient)",
    "FD% (R1)",
    "FD Avg Area µm² (R1)",
    "FD number (R1)",
    "FD density /mm² (R1)",
    "FD% (R2)",
    "FD Avg Area µm² (R2)",
    "FD number (R2)",
    "FD density /mm² (R2)",
    "FD% (R3)",
    "FD Avg Area µm² (R3)",
    "FD number (R3)",
    "FD density /mm² (R3)",
}

CALIBER_RELATED_KEYWORDS = (
    "diameter",
    "caliber",
    "dilated",
    "arteriol",
    "local diameter",
    "nv diameter",
    "skel) vsl diameter",
    "raw vsl diameter",
)


def piecewise_scale(x: np.ndarray, x_min: float, x_med: float, x_max: float) -> np.ndarray:
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


def ref_cuts(values: np.ndarray) -> dict[str, float]:
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    return {
        "p05": float(np.percentile(v, 5)),
        "p95": float(np.percentile(v, 95)),
        "p10": float(np.percentile(v, 10)),
        "p90": float(np.percentile(v, 90)),
        "p25": float(np.percentile(v, 25)),
        "p75": float(np.percentile(v, 75)),
        "min": float(np.min(v)),
        "median": float(np.median(v)),
        "max": float(np.max(v)),
        "mean": float(np.mean(v)),
        "std": float(np.std(v, ddof=1)) if len(v) > 1 else 0.0,
    }


def u_neg_winsor(x: np.ndarray, lo_pct: float = 5, hi_pct: float = 95) -> np.ndarray:
    """Winsorize x, then piecewise-scale (−x) so lower x → higher score."""
    cuts = ref_cuts(x)
    lo = float(np.percentile(x[np.isfinite(x)], lo_pct))
    hi = float(np.percentile(x[np.isfinite(x)], hi_pct))
    xw = winsorize(x, lo, hi)
    neg = -xw
    nc = ref_cuts(neg)
    return piecewise_scale(neg, nc["min"], nc["median"], nc["max"])


def u_pos_winsor(x: np.ndarray, lo_pct: float = 5, hi_pct: float = 95) -> np.ndarray:
    """Winsorize x, then piecewise-scale (+x) so higher x → higher score."""
    lo = float(np.percentile(x[np.isfinite(x)], lo_pct))
    hi = float(np.percentile(x[np.isfinite(x)], hi_pct))
    xw = winsorize(x, lo, hi)
    c = ref_cuts(xw)
    return piecewise_scale(xw, c["min"], c["median"], c["max"])


def soft_squash(x: np.ndarray, center: float, scale: float) -> np.ndarray:
    """Smooth robust map: 50 + 50*tanh((center−x)/scale), higher when x smaller."""
    z = (center - np.asarray(x, dtype=float)) / max(scale, 1e-9)
    return np.clip(50.0 + 50.0 * np.tanh(z), 0.0, 100.0)


def load_matched_long() -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    for name in OBSERVER_DIRS:
        raw = _load_observer_csvs(INCOMING_DIR / name)
        if raw is None:
            raise FileNotFoundError(f"No CSV in {INCOMING_DIR / name}")
        case_col = _first_present(raw.columns, CASE_ALIASES)
        if case_col is None:
            raise ValueError(f"No case column in {name}")
        out = pd.DataFrame()
        out["case_id"] = raw[case_col].map(_normalize_case_id)
        out["case_id_raw"] = raw[case_col].astype(str).str.strip()
        out["observer"] = OBSERVER_ALIASES_DIRS[name]
        date_col = _first_present(raw.columns, DATE_ALIASES)
        out["date"] = raw[date_col] if date_col is not None else pd.NA
        for c in raw.columns:
            if c == case_col:
                continue
            s = pd.to_numeric(raw[c], errors="coerce")
            # keep columns that are mostly numeric
            if s.notna().sum() >= max(3, int(0.5 * len(s))):
                out[c] = s
        out = out[out["case_id"] != ""].drop_duplicates(subset=["case_id"], keep="first")
        parts.append(out)

    combined = pd.concat(parts, ignore_index=True)
    sets = {o: set(g["case_id"]) for o, g in combined.groupby("observer")}
    intersection = set.intersection(*sets.values())
    if len(intersection) != 46:
        print(f"WARNING: intersection n={len(intersection)} (expected 46)")
    return combined[combined["case_id"].isin(intersection)].copy()


def icc_one(long_df: pd.DataFrame, metric: str) -> dict:
    observers = sorted(long_df["observer"].unique())
    pg = try_pingouin_icc(long_df, metric)
    wide = long_df.pivot_table(
        index="case_id", columns="observer", values=metric, aggfunc="first"
    ).reindex(columns=observers)
    arr = wide.to_numpy(dtype=float)
    fb = icc_2_1_multirater(arr)
    vc = variance_components_anova(arr)
    if pg is not None:
        icc, lo, hi, src = pg["icc"], pg["ci_low"], pg["ci_high"], "pingouin"
        n, k = pg["n"], pg["k"]
    else:
        icc, lo, hi, src = fb["icc"], fb["ci_low"], fb["ci_high"], "numpy"
        n, k = fb["n"], fb["k"]
    return {
        "metric": metric,
        "n": int(n),
        "k": int(k),
        "icc_2_1": float(icc) if icc is not None and np.isfinite(icc) else np.nan,
        "ci_low": float(lo) if lo is not None and np.isfinite(lo) else np.nan,
        "ci_high": float(hi) if hi is not None and np.isfinite(hi) else np.nan,
        "source": src,
        "var_case": vc["var_case"],
        "var_observer": vc["var_observer"],
        "var_error": vc["var_error"],
        "icc_vc": vc["icc_vc"],
    }


def is_caliber_related(col: str) -> bool:
    cl = col.lower()
    return any(k in cl for k in CALIBER_RELATED_KEYWORDS)


def part1_all_numeric_icc(df: pd.DataFrame) -> pd.DataFrame:
    skip = {"case_id", "case_id_raw", "observer", "date"}
    metrics = [
        c
        for c in df.columns
        if c not in skip and c not in EXCLUDE_COLS and pd.api.types.is_numeric_dtype(df[c])
    ]
    rows = []
    for m in metrics:
        sub = df[["case_id", "observer", m]].dropna()
        if sub["case_id"].nunique() < 10 or sub["observer"].nunique() < 3:
            continue
        r = icc_one(df[["case_id", "observer", m]].copy(), m)
        r["caliber_related"] = is_caliber_related(m)
        r["family"] = (
            "caliber/diameter"
            if is_caliber_related(m)
            else (
                "score/composite"
                if m
                in (
                    "Maturity Index",
                    "Caliber Uniformity Score",
                    "Network Complexity Score",
                )
                else "morphometry/topology"
            )
        )
        rows.append(r)
    out = pd.DataFrame(rows).sort_values("icc_2_1", ascending=False).reset_index(drop=True)
    out["rank"] = np.arange(1, len(out) + 1)
    return out


def spearman_vs_original(df: pd.DataFrame, score_col: str) -> dict[str, float]:
    out = {}
    for obs, g in df.groupby("observer"):
        a = g["Caliber Uniformity Score"].to_numpy(float)
        b = g[score_col].to_numpy(float)
        mask = np.isfinite(a) & np.isfinite(b)
        if mask.sum() < 5:
            out[obs] = np.nan
            continue
        rho, _ = stats.spearmanr(a[mask], b[mask])
        out[obs] = float(rho)
    return out


def pairwise_corr_matrix(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    return df[cols].corr(method="spearman")


def build_candidates(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Build many candidate uniformity scores; return enriched df + meta."""
    nv = df["NV Diameter (CV)"].to_numpy(float)
    loc = df["Local Diameter Variation (max CV%)"].to_numpy(float)
    skel = df["(Skel) Vsl Diameter"].to_numpy(float)
    rawd = df["Raw Vsl Diameter"].to_numpy(float)
    dil = df["Dilated vessel (%)"].to_numpy(float)
    cal0 = df["Caliber Uniformity Score"].to_numpy(float)
    dens = df["Vsl Density (Vessel Area/MNV (%))"].to_numpy(float)
    art_n = df["Arteriolarization Segment Count"].to_numpy(float)

    # Derived: SD from mean×CV; Raw/Skel ratio; residual CV vs mean diameter
    std_um = (nv / 100.0) * skel
    raw_skel_ratio = np.where(skel > 0, rawd / skel, np.nan)
    # pooled OLS residual: CV ~ skel
    mask = np.isfinite(nv) & np.isfinite(skel)
    coef = np.polyfit(skel[mask], nv[mask], 1)
    nv_hat = coef[0] * skel + coef[1]
    nv_resid = nv - nv_hat

    # density interaction caveat proxy: CV × density (not used as score alone)
    nv_x_dens = nv * dens

    out = df.copy()
    out["derived_std_diameter_um"] = std_um
    out["derived_raw_skel_ratio"] = raw_skel_ratio
    out["derived_nv_cv_resid_skel"] = nv_resid
    out["derived_nv_x_density"] = nv_x_dens

    # --- baselines ---
    out["caliber_C_winsor_inv_nv_cv"] = u_neg_winsor(nv, 5, 95)
    out["caliber_W_winsor_orig"] = u_pos_winsor(cal0, 5, 95)

    # --- stronger robust CV transforms ---
    out["caliber_C_winsor_p10_90"] = u_neg_winsor(nv, 10, 90)
    out["caliber_C_winsor_p25_75"] = u_neg_winsor(nv, 25, 75)
    nv_c = ref_cuts(nv)
    out["caliber_C_soft_tanh"] = soft_squash(nv, nv_c["median"], max(nv_c["std"], 1e-6))

    # residual CV (mean-caliber–orthogonal uniformity)
    out["caliber_R_resid_cv"] = u_neg_winsor(nv_resid, 5, 95)
    out["caliber_R_resid_soft"] = soft_squash(
        nv_resid, float(np.nanmedian(nv_resid)), float(np.nanstd(nv_resid) + 1e-9)
    )

    # dilated vessel as independent non-uniformity axis
    out["caliber_D_inv_dilated"] = u_neg_winsor(dil, 5, 95)

    # local (known fragile) — for comparison only
    out["caliber_L_inv_local"] = u_neg_winsor(loc, 5, 95)

    # std diameter (absolute dispersion) — construct shift toward thickness spread
    out["caliber_S_inv_std"] = u_neg_winsor(std_um, 5, 95)

    # raw/skel ratio near 1 → more consistent measurement; not pure uniformity
    # score higher when ratio closer to 1
    ratio_dev = np.abs(raw_skel_ratio - 1.0)
    out["caliber_Q_rawskel_agreement"] = u_neg_winsor(ratio_dev, 5, 95)

    # --- multi-parameter blends (prefer low collinearity) ---
    u_c = out["caliber_C_winsor_inv_nv_cv"].to_numpy(float)
    u_r = out["caliber_R_resid_cv"].to_numpy(float)
    u_d = out["caliber_D_inv_dilated"].to_numpy(float)
    u_s = out["caliber_S_inv_std"].to_numpy(float)
    u_skel = u_pos_winsor(skel, 5, 95)
    u_soft = out["caliber_C_soft_tanh"].to_numpy(float)

    blends = {
        # Primary conceptual: residual CV (level-independent) + dilated fraction
        "caliber_M_resid70_dil30": np.clip(0.70 * u_r + 0.30 * u_d, 0, 100),
        "caliber_M_resid80_dil20": np.clip(0.80 * u_r + 0.20 * u_d, 0, 100),
        "caliber_M_resid60_dil40": np.clip(0.60 * u_r + 0.40 * u_d, 0, 100),
        # Global CV + dilated (accept partial mean-caliber confound in CV)
        "caliber_M_cv70_dil30": np.clip(0.70 * u_c + 0.30 * u_d, 0, 100),
        "caliber_M_cv80_dil20": np.clip(0.80 * u_c + 0.20 * u_d, 0, 100),
        "caliber_M_cv85_dil15": np.clip(0.85 * u_c + 0.15 * u_d, 0, 100),
        "caliber_M_cv90_dil10": np.clip(0.90 * u_c + 0.10 * u_d, 0, 100),
        # Soft CV + dilated
        "caliber_M_soft75_dil25": np.clip(0.75 * u_soft + 0.25 * u_d, 0, 100),
        # Residual + soft CV consensus (same family — collinear check needed)
        "caliber_M_cv50_resid50": np.clip(0.50 * u_c + 0.50 * u_r, 0, 100),
        # CV + inverse std (related; collinear with mean)
        "caliber_M_cv70_std30": np.clip(0.70 * u_c + 0.30 * u_s, 0, 100),
        # Geometric-style: geometric mean of U_cv and U_dil (independent axes)
        "caliber_M_geom_cv_dil": np.clip(np.sqrt(np.maximum(u_c, 0) * np.maximum(u_d, 0)), 0, 100),
        "caliber_M_geom_resid_dil": np.clip(
            np.sqrt(np.maximum(u_r, 0) * np.maximum(u_d, 0)), 0, 100
        ),
        # Prior hybrid (known)
        "caliber_AB_cv70_skel30": np.clip(0.70 * u_c + 0.30 * u_skel, 0, 100),
        # Triple: resid + dil + light skel (risk construct shift) — keep weight on uniformity
        "caliber_M_resid55_dil25_skel20": np.clip(0.55 * u_r + 0.25 * u_d + 0.20 * u_skel, 0, 100),
        "caliber_M_cv55_dil25_skel20": np.clip(0.55 * u_c + 0.25 * u_d + 0.20 * u_skel, 0, 100),
        # Arteriolarization density of thick vessels as third axis (related to dilated)
        "caliber_M_cv70_art30": np.clip(0.70 * u_c + 0.30 * u_neg_winsor(art_n, 5, 95), 0, 100),
        # Rank-harmonized NV CV: within-observer percentile → pooled piecewise
        # (reduces observer location/scale; disclose as harmonization)
    }

    # Within-observer rank → 0–100 (percentile), then average with dilated
    rank_u = np.full_like(nv, np.nan, dtype=float)
    for obs in out["observer"].unique():
        idx = out["observer"].to_numpy() == obs
        x = nv[idx]
        # higher uniformity = lower CV → invert ranks
        r = stats.rankdata(-x, method="average")
        rank_u[idx] = 100.0 * (r - 1) / max(len(r) - 1, 1)
    out["caliber_H_obsrank_inv_cv"] = rank_u
    blends["caliber_H_rank70_dil30"] = np.clip(0.70 * rank_u + 0.30 * u_d, 0, 100)
    blends["caliber_H_rank85_dil15"] = np.clip(0.85 * rank_u + 0.15 * u_d, 0, 100)

    # Observer location harmonization of NV CV then U
    nv_h = nv.copy()
    grand_med = float(np.nanmedian(nv))
    for obs in out["observer"].unique():
        idx = out["observer"].to_numpy() == obs
        nv_h[idx] = nv[idx] - np.nanmedian(nv[idx]) + grand_med
    out["caliber_H_locshift_inv_cv"] = u_neg_winsor(nv_h, 5, 95)
    blends["caliber_H_locshift70_dil30"] = np.clip(
        0.70 * out["caliber_H_locshift_inv_cv"].to_numpy(float) + 0.30 * u_d, 0, 100
    )

    for k, v in blends.items():
        out[k] = v

    # Named flagship (transferable 0–100 score; no within-observer rank game):
    # soft robust map of global NV CV + independent dilated-vessel axis
    out["caliber_U2_softcv_dil"] = out["caliber_M_soft75_dil25"]
    # CSV-faithful winsor twin (same axes, hard winsor like prior C)
    out["caliber_U2_winsorcv_dil"] = out["caliber_M_cv70_dil30"]

    meta = {
        "nv_skel_ols": {"slope": float(coef[0]), "intercept": float(coef[1])},
        "spearman_inputs": {
            "NV_CV_vs_Skel": float(stats.spearmanr(nv[mask], skel[mask]).correlation),
            "NV_CV_vs_Dilated": float(
                stats.spearmanr(
                    nv[np.isfinite(nv) & np.isfinite(dil)],
                    dil[np.isfinite(nv) & np.isfinite(dil)],
                ).correlation
            ),
            "NV_resid_vs_Dilated": float(
                stats.spearmanr(
                    nv_resid[np.isfinite(nv_resid) & np.isfinite(dil)],
                    dil[np.isfinite(nv_resid) & np.isfinite(dil)],
                ).correlation
            ),
            "NV_CV_vs_Local": float(
                stats.spearmanr(
                    nv[np.isfinite(nv) & np.isfinite(loc)],
                    loc[np.isfinite(nv) & np.isfinite(loc)],
                ).correlation
            ),
        },
    }
    return out, meta


def score_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c.startswith("caliber_")]


def evaluate_scores(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    base_icc = icc_one(df, "Caliber Uniformity Score")["icc_2_1"]
    c_icc = icc_one(df, "caliber_C_winsor_inv_nv_cv")["icc_2_1"]
    for m in score_columns(df):
        r = icc_one(df, m)
        sp = spearman_vs_original(df, m)
        r["delta_vs_original"] = r["icc_2_1"] - base_icc
        r["delta_vs_C"] = r["icc_2_1"] - c_icc
        r["spearman_YY"] = sp.get("YY", np.nan)
        r["spearman_Inoue"] = sp.get("Inoue", np.nan)
        r["spearman_Osada"] = sp.get("Osada", np.nan)
        r["spearman_mean"] = float(np.nanmean(list(sp.values())))
        rows.append(r)
    return pd.DataFrame(rows).sort_values("icc_2_1", ascending=False).reset_index(drop=True)


def write_all_numeric_md(icc_df: pd.DataFrame, path: Path) -> None:
    cal = icc_df[icc_df["caliber_related"]].copy()
    lines = [
        "# ICC(2,1) — all numeric batch-CSV parameters (n=46, k=3)",
        "",
        "**Date:** 2026-07-31  ",
        "**Observers:** YY / Inoue / Osada · matched `File` intersection **n = 46**  ",
        "**Model:** ICC(2,1) absolute agreement (Shrout & Fleiss / McGraw & Wong)  ",
        "**Script:** `compute_caliber_major_params_new_score.py`",
        "",
        "## Scope",
        "",
        "All mostly-numeric morphological / vessel / caliber-related (and other) columns",
        "exported in the ImageJ-compatible batch CSVs. Meta/ID/FD-region QC flag columns excluded.",
        "",
        f"**Total metrics ranked:** {len(icc_df)}  ",
        f"**Caliber-/diameter-/dilated-/arteriolarization-tagged:** {len(cal)}",
        "",
        "## Top 20 by ICC(2,1)",
        "",
        "| Rank | Metric | ICC(2,1) | 95% CI | Family |",
        "|------|--------|----------|--------|--------|",
    ]
    for _, r in icc_df.head(20).iterrows():
        lines.append(
            f"| {int(r['rank'])} | {r['metric']} | {r['icc_2_1']:.3f} | "
            f"{r['ci_low']:.3f}–{r['ci_high']:.3f} | {r['family']} |"
        )

    lines += [
        "",
        "## Caliber / diameter / uniformity–related raw params (ranked)",
        "",
        "| Rank (global) | Metric | ICC(2,1) | 95% CI | High/Low |",
        "|---------------|--------|----------|--------|----------|",
    ]
    for _, r in cal.sort_values("icc_2_1", ascending=False).iterrows():
        tag = (
            "HIGH (≥0.70)"
            if r["icc_2_1"] >= 0.70
            else (
                "MODERATE (0.50–0.70)"
                if r["icc_2_1"] >= 0.50
                else "LOW (<0.50)"
            )
        )
        lines.append(
            f"| {int(r['rank'])} | {r['metric']} | {r['icc_2_1']:.3f} | "
            f"{r['ci_low']:.3f}–{r['ci_high']:.3f} | **{tag}** |"
        )

    lines += [
        "",
        "### Highlight — high vs low among caliber family",
        "",
        "**High / good–excellent ICC:** mean skeleton diameter `(Skel) Vsl Diameter`, "
        "arteriolarization counts/lengths (topology of thick vessels), and related densities "
        "when vessel-count based.",
        "",
        "**Low / fragile ICC:** dispersion / variability features — especially "
        "`NV Diameter (CV)`, `Local Diameter Variation (max CV%)`, and the composite "
        "`Caliber Uniformity Score` (10-bin Stability PCA). `Raw Vsl Diameter` is only fair.",
        "",
        "**Implication:** Reproducible information lives in **mean caliber level** and "
        "**thick-vessel topology counts**, not in raw CV / local max-CV / radial Stability "
        "composites — unless CV is robustly transformed (see new-score note).",
        "",
        "## Full ranked table",
        "",
        "| Rank | Metric | ICC(2,1) | 95% CI | Caliber-related | Family |",
        "|------|--------|----------|--------|-----------------|--------|",
    ]
    for _, r in icc_df.iterrows():
        lines.append(
            f"| {int(r['rank'])} | {r['metric']} | {r['icc_2_1']:.3f} | "
            f"{r['ci_low']:.3f}–{r['ci_high']:.3f} | "
            f"{'Y' if r['caliber_related'] else ''} | {r['family']} |"
        )
    lines += [
        "",
        "## Output files",
        "",
        "- `icc_all_numeric_params_n46.csv`",
        "- `icc_all_numeric_params_n46.md` (this file)",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_main_md(
    icc_all: pd.DataFrame,
    cand_icc: pd.DataFrame,
    meta: dict,
    corr: pd.DataFrame,
    winner: str,
    path: Path,
) -> None:
    cal = icc_all[icc_all["caliber_related"]].sort_values("icc_2_1", ascending=False)
    top_cal = cal.head(8)
    base = cand_icc[cand_icc["metric"] == "Caliber Uniformity Score"]
    # original may not be in score list — pull from icc_all
    orig_icc = float(
        icc_all.loc[icc_all["metric"] == "Caliber Uniformity Score", "icc_2_1"].iloc[0]
    )
    c_row = cand_icc[cand_icc["metric"] == "caliber_C_winsor_inv_nv_cv"].iloc[0]
    w_row = cand_icc[cand_icc["metric"] == winner].iloc[0]

    lines = [
        "# Caliber uniformity — major parameters & new score (n=46)",
        "",
        "**Date:** 2026-07-31  ",
        "**Set:** YY / Inoue / Osada · intersection **n = 46** · ICC(2,1) absolute agreement  ",
        "**Script:** `compute_caliber_major_params_new_score.py`  ",
        "**Companion:** [`icc_all_numeric_params_n46.md`](icc_all_numeric_params_n46.md)",
        "",
        "---",
        "",
        "## Part 1 — Top high-ICC picks (caliber-related)",
        "",
        "From full numeric sweep (`icc_all_numeric_params_n46.*`):",
        "",
        "| Metric | ICC(2,1) | 95% CI | Note |",
        "|--------|----------|--------|------|",
    ]
    notes = {
        "(Skel) Vsl Diameter": "Mean caliber level — high ICC but **not** uniformity",
        "Arteriolarization Segment Count": "Thick-vessel topology count",
        "Arteriolarization Total Length (mm)": "Thick-vessel length",
        "Arteriolarization Max Segment Length (mm)": "Longest thick segment",
        "Arteriolarization Density (/mm²)": "Thick-vessel spatial density",
        "Arteriolarization Connectivity Index (mm/segment)": "Thick-vessel connectivity",
        "Dilated vessel (%)": "Fraction dilated — **heterogeneity axis**, moderate ICC",
        "Caliber Uniformity Score": "Published Stability/PCA composite — low",
        "NV Diameter (CV)": "Global diameter CV — raw ICC low; robust transform rescues",
        "Local Diameter Variation (max CV%)": "Local max CV — poorest",
        "Raw Vsl Diameter": "Alternate mean diameter — only fair ICC",
    }
    for _, r in top_cal.iterrows():
        note = notes.get(r["metric"], "")
        lines.append(
            f"| {r['metric']} | {r['icc_2_1']:.3f} | {r['ci_low']:.3f}–{r['ci_high']:.3f} | {note} |"
        )
    # force-include key low ones
    for key in (
        "Dilated vessel (%)",
        "Caliber Uniformity Score",
        "NV Diameter (CV)",
        "Local Diameter Variation (max CV%)",
        "Raw Vsl Diameter",
    ):
        if key not in set(top_cal["metric"]):
            r = cal[cal["metric"] == key]
            if len(r):
                r = r.iloc[0]
                lines.append(
                    f"| {r['metric']} | {r['icc_2_1']:.3f} | {r['ci_low']:.3f}–{r['ci_high']:.3f} | "
                    f"{notes.get(key, '')} |"
                )

    lines += [
        "",
        "**Takeaway:** High-ICC caliber-*family* columns are mostly **mean level** or "
        "**arteriolarization counts**, not dispersion. True uniformity proxies (`NV Diameter (CV)`, "
        "`Local Diameter Variation`, original Caliber) are the **low-ICC** ones unless transformed.",
        "",
        "---",
        "",
        "## Part 2 — Logical major parameters for caliber uniformity",
        "",
        "Goal: quantify **caliber uniformity** (homogeneity of vessel diameters) **without** "
        "fragile 10-bin `stab_*` radial partitions.",
        "",
        "| # | Logical parameter | Why (pathophysiology / morphometry) | In batch CSV? | ICC hint |",
        "|---|-------------------|--------------------------------------|---------------|----------|",
        "| 1 | **Global diameter CV** (or robust CV / MAD/median) | Scale-free dispersion of lumen width across the lesion | `NV Diameter (CV)` only (mean/SD-based CV; **no MAD/percentiles**) | Raw low; Winsor+map high |",
        "| 2 | **Mean-caliber–orthogonal residual CV** | CV correlates with mean diameter (ρ≈{:.2f}); residual = uniformity *net of thickness* | **Derived** from `NV Diameter (CV)` + `(Skel) Vsl Diameter` | Tried — **ICC collapsed** (negative control) |".format(
            meta["spearman_inputs"]["NV_CV_vs_Skel"]
        ),
        "| 3 | **Dilated-vessel fraction** | Focal ectasia / arteriolarization → morphological *non*-uniformity, largely independent of global CV (ρ≈{:.2f}) | `Dilated vessel (%)` | Moderate (~0.52) |".format(
            meta["spearman_inputs"]["NV_CV_vs_Dilated"]
        ),
        "| 4 | **Local diameter variation** | Focal beading / segmental irregularity | `Local Diameter Variation (max CV%)` | **Very low** — avoid as primary |",
        "| 5 | **Trunk vs periphery diameter ratio** | Normal taper vs chaotic calibers | Internal `diameter_ratio` / TrunkDist — **NOT in CSV** | Need extraction |",
        "| 6 | **Radial profile residual CV / range CV** | Spatial caliber organization | Internal `stab_*` — **NOT in CSV** | Fragile 10-bin; avoid as sole definition |",
        "| 7 | **Skeleton diameter percentiles (p25/p50/p75, IQR)** | Distribution shape without radial bins | **NOT in CSV** (only mean + CV) | Need pipeline export |",
        "| 8 | **Branch-order / generation taper** | Orderly thinning along branching | **NOT computed** in current pipeline | Future |",
        "| 9 | **Mean diameter (skel)** | Caliber *level*, not uniformity — confounder / optional covariate | `(Skel) Vsl Diameter` | High ICC — do **not** stuff into uniformity without disclosure |",
        "| 10 | **Vessel density × CV interaction** | Sparse skeletons → unstable CV | Density in CSV; interaction derived | Caveat, not primary score |",
        "",
        "### Independence (Spearman, pooled 138 ratings)",
        "",
        f"- NV CV vs Skel mean diameter: **ρ = {meta['spearman_inputs']['NV_CV_vs_Skel']:.3f}** (collinear — residualization motivated)",
        f"- NV CV vs Dilated %: **ρ = {meta['spearman_inputs']['NV_CV_vs_Dilated']:.3f}** (near-independent — good second axis)",
        f"- Residual CV vs Dilated %: **ρ = {meta['spearman_inputs']['NV_resid_vs_Dilated']:.3f}**",
        f"- NV CV vs Local max CV: **ρ = {meta['spearman_inputs']['NV_CV_vs_Local']:.3f}**",
        "",
        "### Shortlist adopted for scoring",
        "",
        "1. **Primary uniformity axis:** robust transform of global NV CV "
        "(soft tanh or Winsor+piecewise). "
        "**Residualization on mean diameter looked elegant but ICC collapsed** — dropped from winner.",
        "2. **Secondary independent axis:** inverse `Dilated vessel (%)` (ρ≈0.15 with NV CV).",
        "3. **Explicitly excluded as primary:** Local max CV; mean skel diameter as “uniformity”; "
        "10-bin `stab_*`; absolute diameter SD; within-observer rank harmonization.",
        "",
        "### Internal extraction (if pursued later)",
        "",
        "No saved masks/ROI intermediates for the n=46 ICC set → **cannot** offline-recompute "
        "`stab_*`, diameter percentiles, or `diameter_ratio` without re-ROI. Pipeline already "
        "computes `std_diameter_um`, `max_diameter_um`, `diameter_ratio`, `radial_profile`, `stab_*` "
        "in `skeleton_analysis` / `mnv_analysis` / `pattern_metrics` but **does not export** them "
        "to ImageJ CSV. Feasible next step: extend `mnv_imagej_csv.py` export + re-batch.",
        "",
        "Derived today without re-run: `std ≈ (CV/100)×mean_skel` from existing columns.",
        "",
        "---",
        "",
        "## Part 3 — New score(s) vs 0.434 and 0.765",
        "",
        "### Winning formula",
        "",
        f"**Winner by ICC(2,1):** `{winner}`",
        "",
    ]

    formulas_text = {
        "caliber_U2_softcv_dil": (
            "**U2 (recommended):** "
            "`U_cv = 50 + 50·tanh((median_CV − NV_CV) / SD_CV)` (pooled median/SD); "
            "`U_dil = piecewise(−winsor(Dilated%, p05–p95))`; "
            "**Score = 0.75·U_cv + 0.25·U_dil** (clip 0–100). "
            "Higher = more uniform (lower relative dispersion + less dilated fraction)."
        ),
        "caliber_U2_winsorcv_dil": (
            "**U2 winsor twin:** `U_c = piecewise(−winsor(NV_CV))`; "
            "`U_d = piecewise(−winsor(Dilated%))`; **0.70·U_c + 0.30·U_d**."
        ),
        "caliber_C_winsor_inv_nv_cv": (
            "Winsorize `NV Diameter (CV)` at pooled p05–p95; piecewise-scale (−CV) "
            "(median→50). Prior primary."
        ),
        "caliber_M_resid70_dil30": (
            "Let `CV_resid = NV_CV − (a·SkelDiam + b)` with pooled OLS; "
            "U_r = piecewise(−winsor(CV_resid)); U_d = piecewise(−winsor(Dilated%)); "
            "**0.70·U_r + 0.30·U_d** — *face-valid but ICC collapsed* (negative control)."
        ),
        "caliber_M_cv70_dil30": (
            "U_c = piecewise(−winsor(NV_CV)); U_d = piecewise(−winsor(Dilated%)); "
            "**0.70·U_c + 0.30·U_d** (alias of U2 winsor twin)."
        ),
        "caliber_M_soft75_dil25": (
            "Same as `caliber_U2_softcv_dil` (implementation alias)."
        ),
        "caliber_M_cv80_dil20": (
            "Same axes as cv70_dil30 with weights **0.80 / 0.20**."
        ),
        "caliber_M_cv85_dil15": (
            "Same axes with weights **0.85 / 0.15**."
        ),
        "caliber_M_cv90_dil10": (
            "Same axes with weights **0.90 / 0.10**."
        ),
        "caliber_H_rank70_dil30": (
            "Within-observer percentile rank of (−NV_CV) → 0–100; blend **0.70** with U(−Dilated%). "
            "High ICC but **non-transferable** across cohorts (disclose / do not adopt as primary)."
        ),
        "caliber_H_locshift_inv_cv": (
            "Subtract observer median NV_CV, add grand median; then U(−winsor). Bias correction."
        ),
        "caliber_M_geom_cv_dil": (
            "Geometric mean of U(−winsor NV_CV) and U(−winsor Dilated%)."
        ),
        "caliber_R_resid_cv": (
            "U(−winsor(CV residualized on skel mean diameter)) alone — ICC collapsed."
        ),
        "caliber_C_soft_tanh": (
            "50 + 50·tanh((median−CV)/SD) — soft robust map without Dilated axis."
        ),
        "caliber_S_inv_std": (
            "U(−winsor(std_um)) with std=(CV/100)×skel mean — **highest raw ICC but construct shift** "
            "toward absolute spread / mean caliber; rejected as uniformity definition."
        ),
    }
    # generic fallback
    desc = formulas_text.get(winner, "See script `build_candidates()`.")
    lines += [
        desc,
        "",
        f"- OLS used for residualization (if applicable): "
        f"slope={meta['nv_skel_ols']['slope']:.4f}, "
        f"intercept={meta['nv_skel_ols']['intercept']:.4f}",
        "",
        "### Head-to-head ICC(2,1)",
        "",
        "| Metric | ICC(2,1) | 95% CI | Δ vs original | Δ vs C(0.765) | Spearman vs orig (mean YY/Inoue/Osada) |",
        "|--------|----------|--------|---------------|---------------|----------------------------------------|",
        f"| Caliber Uniformity (original) | {orig_icc:.3f} | — | 0 | {orig_icc - c_row['icc_2_1']:.3f} | 1 |",
    ]
    for key in [
        "caliber_C_winsor_inv_nv_cv",
        winner,
        "caliber_U2_winsorcv_dil",
        "caliber_M_cv70_dil30",
        "caliber_M_soft75_dil25",
        "caliber_H_rank70_dil30",
        "caliber_S_inv_std",
        "caliber_R_resid_cv",
        "caliber_M_resid70_dil30",
        "caliber_D_inv_dilated",
        "caliber_AB_cv70_skel30",
    ]:
        rows = cand_icc[cand_icc["metric"] == key]
        if len(rows) == 0:
            continue
        r = rows.iloc[0]
        mark = " **← winner**" if key == winner else ""
        lines.append(
            f"| `{key}`{mark} | {r['icc_2_1']:.3f} | {r['ci_low']:.3f}–{r['ci_high']:.3f} | "
            f"{r['delta_vs_original']:+.3f} | {r['delta_vs_C']:+.3f} | {r['spearman_mean']:.2f} |"
        )

    lines += [
        "",
        "### What was tried and rejected",
        "",
        "| Idea | Result | Why rejected / kept as control |",
        "|------|--------|--------------------------------|",
        "| Residualize NV CV on skel mean diameter (± Dilated) | ICC **~0.35–0.50** | Face-valid orthogonality **destroyed** reproducible CV signal |",
        "| Inverse absolute diameter SD | ICC **0.865** | Construct shift toward mean caliber / absolute spread |",
        "| Within-observer rank(−CV)+Dilated | ICC **0.842** | Non-transferable cohort score; calibration artifact |",
        "| Blend skel mean into score | ICC ≤ prior hybrids | Wrong construct (level ≠ uniformity) |",
        "| Local max CV axis | ICC ~0.14–0.23 | Too noisy |",
        "",
        "### Full candidate ranking (top 15)",
        "",
        "| Rank | Metric | ICC(2,1) | Δ vs C | Spearman mean vs orig |",
        "|------|--------|----------|--------|------------------------|",
    ]
    for i, r in cand_icc.head(15).iterrows():
        lines.append(
            f"| {i+1} | `{r['metric']}` | {r['icc_2_1']:.3f} | {r['delta_vs_C']:+.3f} | {r['spearman_mean']:.2f} |"
        )

    lines += [
        "",
        "### Independence rationale",
        "",
        "- Avoided stuffing **Skel mean diameter** into the primary uniformity definition "
        "(high ICC but wrong construct); kept only as residualization covariate or disclosed hybrid.",
        "- **Dilated %** added only at modest weight because Spearman with NV CV is low "
        f"({meta['spearman_inputs']['NV_CV_vs_Dilated']:.2f}) — second major axis, not a correlated copy.",
        "- **Local max CV** excluded from winning blends (ICC ~0.14).",
        "- Residual CV addresses collinearity of raw CV with mean caliber "
        f"(ρ={meta['spearman_inputs']['NV_CV_vs_Skel']:.2f}).",
        "",
        "### Spearman vs original Caliber (disclosure)",
        "",
        f"Winner `{winner}`: YY={w_row['spearman_YY']:.2f}, Inoue={w_row['spearman_Inoue']:.2f}, "
        f"Osada={w_row['spearman_Osada']:.2f} (mean {w_row['spearman_mean']:.2f}).",
        "",
        "Prior `caliber_C_winsor_inv_nv_cv`: "
        f"YY={c_row['spearman_YY']:.2f}, Inoue={c_row['spearman_Inoue']:.2f}, "
        f"Osada={c_row['spearman_Osada']:.2f} (mean {c_row['spearman_mean']:.2f}).",
        "",
        "Near-zero / negative Spearman ⇒ **definition replacement**, not monotonic strengthening "
        "of the published Stability/Caliber score. Expect this in rebuttal wording.",
        "",
        "### Recommendation (rebuttal / sensitivity)",
        "",
        "1. Keep manuscript **primary** Caliber Uniformity = existing Stability/PCA score; report ICC **0.434** honestly.",
        "2. Sensitivity / alternate CSV proxy for **caliber homogeneity** (not 10-bin Stability):",
        f"   **`{winner}`** — ICC(2,1) **{w_row['icc_2_1']:.3f}** "
        f"(Δ vs original **{w_row['delta_vs_original']:+.3f}**; Δ vs prior C **{w_row['delta_vs_C']:+.3f}**).",
        "3. Two major, weakly correlated axes: robust **global NV Diameter CV** + **Dilated vessel %** "
        "(avoid Local max CV; avoid stuffing mean skel diameter).",
        "4. Disclose: Spearman vs original Caliber is near-zero/negative → **definition replacement**, "
        "not a monotonic strengthening of the published score.",
        "5. Do **not** adopt inverse-SD or within-observer rank scores as primary (ICC inflation / wrong construct).",
        "6. Residualizing CV on mean diameter looked elegant but **failed empirically** — mention as negative control if useful.",
        "7. Internal percentiles / `diameter_ratio` / `stab_*` remain future export work (no saved ROI for offline recompute).",
        "",
        "---",
        "",
        "## Output files",
        "",
        "- `icc_all_numeric_params_n46.md` / `.csv`",
        "- `caliber_major_params_new_score_icc_stats.csv`",
        "- `caliber_major_params_candidates.csv`",
        "- `caliber_major_params_new_score_long.csv`",
        "- `caliber_major_params_new_score.md` (this file)",
        "- `compute_caliber_major_params_new_score.py`",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def update_changelog(winner: str, winner_icc: float) -> None:
    path = OUT_DIR / "caliber_cv_strengthening_changelog.md"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    marker = "## Addendum 2026-07-31 — major-param sweep & new score hunt"
    note = (
        "---\n\n"
        f"{marker}\n\n"
        "- Full numeric ICC table: [`icc_all_numeric_params_n46.md`](icc_all_numeric_params_n46.md)\n"
        "- Logical majors + candidate scores: [`caliber_major_params_new_score.md`](caliber_major_params_new_score.md)\n"
        f"- Recommended transferable score: `{winner}` (ICC(2,1) **{winner_icc:.3f}**) "
        "vs original Caliber **0.434** and `caliber_C_winsor_inv_nv_cv` **0.765**.\n"
        "- Negative controls: residualized CV (ICC collapsed); inverse absolute SD / rank-harmonized "
        "scores (higher ICC but wrong construct or non-transferable).\n"
        "- Script: `compute_caliber_major_params_new_score.py`\n"
    )
    if marker in text:
        pre = text.split(marker)[0].rstrip()
        # drop trailing --- from pre if present
        if pre.endswith("---"):
            pre = pre[: -len("---")].rstrip()
        path.write_text(pre + "\n\n" + note, encoding="utf-8")
    else:
        path.write_text(text.rstrip() + "\n\n" + note, encoding="utf-8")


def main() -> None:
    print("Loading matched n=46 long table…")
    df0 = load_matched_long()
    print(f"  rows={len(df0)}, cases={df0['case_id'].nunique()}, observers={sorted(df0['observer'].unique())}")

    print("Part 1: ICC for all numeric columns…")
    icc_all = part1_all_numeric_icc(df0)
    icc_all.to_csv(OUT_DIR / "icc_all_numeric_params_n46.csv", index=False)
    write_all_numeric_md(icc_all, OUT_DIR / "icc_all_numeric_params_n46.md")
    print(f"  wrote {len(icc_all)} metrics")

    print("Part 3: building candidate scores…")
    df, meta = build_candidates(df0)
    # also need original score column name preserved
    cand_icc = evaluate_scores(df)
    # prepend original for convenience in CSV
    orig_row = icc_one(df, "Caliber Uniformity Score")
    orig_row.update(
        {
            "delta_vs_original": 0.0,
            "delta_vs_C": orig_row["icc_2_1"]
            - float(cand_icc.loc[cand_icc["metric"] == "caliber_C_winsor_inv_nv_cv", "icc_2_1"].iloc[0]),
            "spearman_YY": 1.0,
            "spearman_Inoue": 1.0,
            "spearman_Osada": 1.0,
            "spearman_mean": 1.0,
        }
    )
    cand_icc = pd.concat([pd.DataFrame([orig_row]), cand_icc], ignore_index=True)
    cand_icc = cand_icc.sort_values("icc_2_1", ascending=False).reset_index(drop=True)

    # Winner policy (face validity > raw max ICC):
    # - Must target *relative* caliber homogeneity + optional independent dilated axis
    # - Exclude absolute SD (proxy for mean caliber), arteriolarization counts,
    #   within-observer rank harmonization (non-transferable), and skel-stuffed hybrids
    # - Prefer named U2 softcv+dil; fall back to best transferable M_cv*_dil* / soft*
    banned = (
        "rawskel",
        "W_winsor",
        "L_inv_local",
        "art30",
        "S_inv_std",
        "cv70_std",
        "skel20",
        "AB_cv",
        "H_rank",
        "H_obsrank",
        "H_locshift",
        "resid",  # residualization destroyed ICC — keep as negative control only
        "geom_",
        "R_resid",
        "D_inv_dilated",  # single axis, weaker than blends
        "primary_proposal",
    )
    face2 = cand_icc[
        cand_icc["metric"].str.startswith(("caliber_U2_", "caliber_M_", "caliber_C_"))
        & ~cand_icc["metric"].str.contains("|".join(banned), regex=True)
    ].copy()
    # Prefer named soft U2 if within 0.01 of empirical best in face2
    best_icc = float(face2["icc_2_1"].max())
    named = "caliber_U2_softcv_dil"
    if named in set(face2["metric"]):
        named_icc = float(face2.loc[face2["metric"] == named, "icc_2_1"].iloc[0])
        winner = named if best_icc - named_icc <= 0.01 else str(face2.iloc[0]["metric"])
    else:
        winner = str(face2.iloc[0]["metric"])
    winner_icc = float(face2.loc[face2["metric"] == winner, "icc_2_1"].iloc[0])

    corr_cols = [
        "NV Diameter (CV)",
        "derived_nv_cv_resid_skel",
        "Dilated vessel (%)",
        "Local Diameter Variation (max CV%)",
        "(Skel) Vsl Diameter",
        "Caliber Uniformity Score",
    ]
    corr = pairwise_corr_matrix(df, corr_cols)

    cand_icc.to_csv(OUT_DIR / "caliber_major_params_new_score_icc_stats.csv", index=False)
    # slim candidate list
    face2.to_csv(OUT_DIR / "caliber_major_params_candidates.csv", index=False)

    score_cols = ["case_id", "observer", "Caliber Uniformity Score"] + score_columns(df)
    df[score_cols].to_csv(OUT_DIR / "caliber_major_params_new_score_long.csv", index=False)

    write_main_md(icc_all, cand_icc, meta, corr, winner, OUT_DIR / "caliber_major_params_new_score.md")
    update_changelog(winner, winner_icc)

    print("\n=== Winner ===")
    print(f"  {winner}: ICC={winner_icc:.3f}")
    print(
        "  C baseline:",
        float(cand_icc.loc[cand_icc["metric"] == "caliber_C_winsor_inv_nv_cv", "icc_2_1"].iloc[0]),
    )
    print("  Top 10 candidates:")
    for _, r in face2.head(10).iterrows():
        print(f"    {r['icc_2_1']:.3f}  {r['metric']}")


if __name__ == "__main__":
    main()
