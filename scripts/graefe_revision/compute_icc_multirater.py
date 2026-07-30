#!/usr/bin/env python3
"""Multi-rater ICC for WS1 (3 observers × shared cases).

Primary: Shrout & Fleiss ICC(2,1) — two-way random effects, absolute
agreement, single measures — per metric, with 95% CI.

Also: pairwise ICC(2,1); multilevel variance-component ICC
= σ²_case / (σ²_case + σ²_observer + σ²_error) via ANOVA / MixedLM.

Expected layout
---------------
documentation/graefe_revision/icc/incoming/
  observer_YY/*.csv
  observer_A/*.csv   # Inoue
  observer_B/*.csv   # Osada

Until complete incoming CSVs are present, prints "awaiting incoming data"
and exits 0 without claiming ICC complete.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
ICC_DIR = REPO_ROOT / "documentation" / "graefe_revision" / "icc"
INCOMING_DIR = ICC_DIR / "incoming"

# Canonical compute folders (clear-name aliases also accepted)
OBSERVER_DIRS = ("observer_YY", "observer_A", "observer_B")
OBSERVER_ALIASES_DIRS = {
    "observer_YY": "YY",
    "observer_A": "Inoue",
    "observer_B": "Osada",
    "observer_inoue": "Inoue",
    "observer_osada": "Osada",
}

METRICS = {
    "area": (
        "area",
        "MNV Area (mm2)",
        "MNV Area (mm²)",
        "MNV Area",
        "mnv_area",
        "lesion_area",
    ),
    "complexity": (
        "complexity",
        "Network Complexity Score",
        "Network Complexity",
        "network_complexity",
        "Standardized Complexity Score",
    ),
    "caliber_uniformity": (
        "caliber_uniformity",
        "Caliber Uniformity Score",
        "Caliber Uniformity",
        "caliber_uniformity_score",
        "Standardized Caliber Uniformity Score",
    ),
    "maturity": (
        "maturity",
        "Maturity Index",
        "Maturity",
        "maturity_index",
    ),
}

METRIC_LABELS = {
    "area": "MNV Area (mm²)",
    "complexity": "Network Complexity Score",
    "caliber_uniformity": "Caliber Uniformity Score",
    "maturity": "Maturity Index",
}

CASE_ALIASES = ("case_id", "icc_id", "Case", "File", "file_name", "image_key")
OBSERVER_COL_ALIASES = ("observer", "rater", "examiner", "operator")
DATE_ALIASES = ("date", "session_date", "analysis_date", "timestamp", "Started At")


def _first_present(columns: pd.Index, aliases: tuple[str, ...]) -> str | None:
    lower = {str(c).lower().strip(): c for c in columns}
    for a in aliases:
        if a in columns:
            return a
        key = a.lower().strip()
        if key in lower:
            return lower[key]
    # substring fallback for area etc.
    for a in aliases:
        key = a.lower().strip()
        for col_l, col in lower.items():
            if key and key in col_l:
                return col
    return None


def _normalize_case_id(val: object) -> str:
    s = str(val).strip()
    if not s or s.lower() == "nan":
        return ""
    # Drop Windows/Unix path prefixes; keep basename
    s = s.replace("\\", "/")
    s = s.rsplit("/", 1)[-1]
    # Normalize common OCTA export suffixes / extensions
    for ext in (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"):
        if s.lower().endswith(ext):
            s = s[: -len(ext)]
            break
    return s.strip().lower()


def _load_observer_csvs(folder: Path) -> pd.DataFrame | None:
    csvs = sorted(p for p in folder.glob("*.csv") if p.stat().st_size > 0)
    if not csvs:
        return None
    frames = []
    for p in csvs:
        df = pd.read_csv(p, encoding="utf-8-sig")
        df["_source_file"] = p.name
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    df["_source_folder"] = folder.name
    return df


def _normalize(df: pd.DataFrame, default_observer: str) -> pd.DataFrame | None:
    case_col = _first_present(df.columns, CASE_ALIASES)
    if case_col is None:
        return None

    out = pd.DataFrame()
    out["case_id"] = df[case_col].map(_normalize_case_id)
    out["case_id_raw"] = df[case_col].astype(str).str.strip()

    tag = OBSERVER_ALIASES_DIRS.get(
        default_observer, default_observer.replace("observer_", "")
    )
    obs_col = _first_present(df.columns, OBSERVER_COL_ALIASES)
    # Prefer folder-derived observer label (Analyst column is often shared login)
    out["observer"] = tag

    date_col = _first_present(df.columns, DATE_ALIASES)
    out["date"] = df[date_col] if date_col is not None else pd.NA

    for canon, aliases in METRICS.items():
        col = _first_present(df.columns, aliases)
        if col is None:
            return None
        out[canon] = pd.to_numeric(df[col], errors="coerce")

    out["_source_folder"] = df["_source_folder"]
    out["_source_file"] = df.get("_source_file", "")
    return out


def discover_incoming(
    incoming_dir: Path,
) -> tuple[pd.DataFrame | None, list[str], dict]:
    """Return concatenated long-format ratings, or (None, reasons, meta)."""
    reasons: list[str] = []
    meta: dict = {"per_observer_n": {}, "dropped": []}
    parts: list[pd.DataFrame] = []

    for name in OBSERVER_DIRS:
        folder = incoming_dir / name
        if not folder.is_dir():
            reasons.append(f"missing folder: {folder}")
            continue
        raw = _load_observer_csvs(folder)
        if raw is None:
            reasons.append(f"no CSV in {folder}")
            continue
        norm = _normalize(raw, default_observer=name)
        if norm is None:
            reasons.append(
                f"{folder}: CSV present but required metric/case columns not found"
            )
            continue
        # Deduplicate by case_id (keep first)
        before = len(norm)
        norm = norm[norm["case_id"] != ""].copy()
        dup = int(norm["case_id"].duplicated().sum())
        if dup:
            meta["dropped"].append(
                f"{name}: dropped {dup} duplicate case_id rows (kept first)"
            )
            norm = norm.drop_duplicates(subset=["case_id"], keep="first")
        if norm[list(METRICS)].isna().all().all():
            reasons.append(f"{folder}: empty or all-NaN scores")
            continue
        meta["per_observer_n"][OBSERVER_ALIASES_DIRS.get(name, name)] = len(norm)
        if before != len(norm):
            pass
        parts.append(norm)

    if len(parts) < 3:
        if not reasons:
            reasons.append("need CSVs from all three observers")
        return None, reasons, meta

    combined = pd.concat(parts, ignore_index=True)
    sets = {
        obs: set(g["case_id"])
        for obs, g in combined.groupby("observer")
    }
    observers = sorted(sets)
    if len(observers) < 3:
        return None, ["fewer than 3 distinct observer labels after normalize"], meta

    intersection = set.intersection(*(sets[o] for o in observers))
    union = set.union(*(sets[o] for o in observers))
    only = {o: sorted(sets[o] - intersection) for o in observers}
    meta["union_n"] = len(union)
    meta["intersection_n"] = len(intersection)
    meta["only_per_observer"] = {o: len(v) for o, v in only.items()}
    meta["missing_cases"] = only

    if len(intersection) < 5:
        return None, [
            f"only {len(intersection)} cases with all 3 observers "
            "(need a usable multi-rater set, target n≈20)"
        ], meta

    complete = combined[combined["case_id"].isin(intersection)].copy()
    return complete, [], meta


def icc_2_1_multirater(ratings: np.ndarray) -> dict[str, float]:
    """ICC(2,1) absolute agreement for n subjects × k raters (numpy fallback)."""
    ratings = np.asarray(ratings, dtype=float)
    mask = np.isfinite(ratings).all(axis=1)
    ratings = ratings[mask]
    n, k = ratings.shape
    if n < 3 or k < 2:
        return {
            "n": float(n),
            "k": float(k),
            "icc": float("nan"),
            "ci_low": float("nan"),
            "ci_high": float("nan"),
        }

    grand = ratings.mean()
    subject_means = ratings.mean(axis=1)
    rater_means = ratings.mean(axis=0)

    ss_subjects = k * np.sum((subject_means - grand) ** 2)
    ss_raters = n * np.sum((rater_means - grand) ** 2)
    ss_total = np.sum((ratings - grand) ** 2)
    ss_error = ss_total - ss_subjects - ss_raters

    ms_subjects = ss_subjects / (n - 1)
    ms_raters = ss_raters / (k - 1)
    ms_error = ss_error / ((n - 1) * (k - 1))

    denom = ms_subjects + (k - 1) * ms_error + (k / n) * (ms_raters - ms_error)
    icc = (ms_subjects - ms_error) / denom if denom != 0 else float("nan")

    from scipy import stats

    alpha = 0.05
    f_obs = ms_subjects / ms_error if ms_error > 0 else float("nan")
    df1, df2 = n - 1, (n - 1) * (k - 1)
    a = (k * (ms_raters - ms_error)) / n if n else 0.0
    try:
        f_l = f_obs / stats.f.ppf(1 - alpha / 2, df1, df2)
        f_u = f_obs * stats.f.ppf(1 - alpha / 2, df2, df1)
        if ms_error > 0:
            icc_l = (f_l - 1.0) / (f_l + k - 1.0 + (k * a) / ms_error)
            icc_u = (f_u - 1.0) / (f_u + k - 1.0 + (k * a) / ms_error)
        else:
            icc_l = icc_u = float("nan")
        if not np.isfinite(icc_l) or not np.isfinite(icc_u):
            icc_l = (f_l - 1.0) / (f_l + k - 1.0)
            icc_u = (f_u - 1.0) / (f_u + k - 1.0)
    except Exception:
        icc_l = icc_u = float("nan")

    return {
        "n": float(n),
        "k": float(k),
        "icc": float(icc),
        "ci_low": float(min(icc_l, icc_u)) if np.isfinite(icc_l) else float("nan"),
        "ci_high": float(max(icc_l, icc_u)) if np.isfinite(icc_u) else float("nan"),
        "ms_subjects": float(ms_subjects),
        "ms_raters": float(ms_raters),
        "ms_error": float(ms_error),
    }


def try_pingouin_icc(long_df: pd.DataFrame, metric: str) -> dict | None:
    try:
        import pingouin as pg
    except ImportError:
        return None
    sub = long_df[["case_id", "observer", metric]].dropna().copy()
    if sub.empty or sub["observer"].nunique() < 2:
        return None
    icc = pg.intraclass_corr(
        data=sub,
        targets="case_id",
        raters="observer",
        ratings=metric,
    )
    row = icc[icc["Type"] == "ICC2"].iloc[0]
    ci = row["CI95%"]
    if isinstance(ci, (list, tuple, np.ndarray)):
        lo, hi = float(ci[0]), float(ci[1])
    else:
        # pingouin may return string like "[0.8 0.95]"
        s = str(ci).strip("[]")
        parts = s.replace(",", " ").split()
        lo, hi = float(parts[0]), float(parts[1])
    return {
        "n": float(sub["case_id"].nunique()),
        "k": float(sub["observer"].nunique()),
        "icc": float(row["ICC"]),
        "ci_low": lo,
        "ci_high": hi,
        "source": "pingouin",
    }


def variance_components_anova(ratings: np.ndarray) -> dict[str, float]:
    """Two-way random ANOVA variance components + ICC_case."""
    ratings = np.asarray(ratings, dtype=float)
    mask = np.isfinite(ratings).all(axis=1)
    ratings = ratings[mask]
    n, k = ratings.shape
    if n < 3 or k < 2:
        return {
            "n": float(n),
            "k": float(k),
            "var_case": float("nan"),
            "var_observer": float("nan"),
            "var_error": float("nan"),
            "icc_vc": float("nan"),
        }

    grand = ratings.mean()
    subject_means = ratings.mean(axis=1)
    rater_means = ratings.mean(axis=0)

    ss_subjects = k * np.sum((subject_means - grand) ** 2)
    ss_raters = n * np.sum((rater_means - grand) ** 2)
    ss_total = np.sum((ratings - grand) ** 2)
    ss_error = ss_total - ss_subjects - ss_raters

    ms_subjects = ss_subjects / (n - 1)
    ms_raters = ss_raters / (k - 1)
    ms_error = ss_error / ((n - 1) * (k - 1))

    var_error = ms_error
    var_case = max((ms_subjects - ms_error) / k, 0.0)
    var_observer = max((ms_raters - ms_error) / n, 0.0)
    denom = var_case + var_observer + var_error
    icc_vc = var_case / denom if denom > 0 else float("nan")

    return {
        "n": float(n),
        "k": float(k),
        "var_case": float(var_case),
        "var_observer": float(var_observer),
        "var_error": float(var_error),
        "icc_vc": float(icc_vc),
        "source": "anova_vc",
    }


def try_mixedlm_vc(long_df: pd.DataFrame, metric: str) -> dict | None:
    """Optional MixedLM with random case + random observer (statsmodels)."""
    try:
        import statsmodels.formula.api as smf
    except ImportError:
        return None
    sub = long_df[["case_id", "observer", metric]].dropna().copy()
    sub = sub.rename(columns={metric: "y"})
    if sub["case_id"].nunique() < 5 or sub["observer"].nunique() < 2:
        return None
    # Nested / crossed random effects: case + observer
    # statsmodels MixedLM supports one random effect easily; for crossed,
    # use variance-components ANOVA as primary VC. Try variance components
    # via MixedLM with case random + observer as fixed (conservative).
    try:
        # Crossed random effects via VC formula is limited; use ANOVA VC.
        return None
    except Exception:
        return None


def _fmt_ci(lo: float, hi: float) -> str:
    if not (np.isfinite(lo) and np.isfinite(hi)):
        return "—"
    return f"{lo:.3f}–{hi:.3f}"


def _fmt_icc(x: float) -> str:
    if not np.isfinite(x):
        return "—"
    return f"{x:.3f}"


def write_outputs(
    data: pd.DataFrame,
    meta: dict,
    primary: pd.DataFrame,
    pairwise: pd.DataFrame,
    vc: pd.DataFrame,
) -> None:
    # Supporting CSVs
    long_path = ICC_DIR / "icc_multirater_long.csv"
    wide_path = ICC_DIR / "icc_multirater_wide.csv"
    primary_csv = ICC_DIR / "icc_multirater_stats.csv"
    pairwise_csv = ICC_DIR / "icc_multirater_pairwise.csv"
    vc_csv = ICC_DIR / "icc_multirater_variance_components.csv"
    md_path = ICC_DIR / "icc_multirater_results.md"

    data_out = data[
        ["case_id", "case_id_raw", "observer", "date", *METRICS]
    ].sort_values(["case_id", "observer"])
    data_out.to_csv(long_path, index=False)

    wide_frames = []
    for metric in METRICS:
        w = data.pivot_table(
            index="case_id", columns="observer", values=metric, aggfunc="mean"
        )
        w.columns = [f"{metric}_{c}" for c in w.columns]
        wide_frames.append(w)
    wide = pd.concat(wide_frames, axis=1).reset_index()
    # attach one raw filename
    raw_map = (
        data.drop_duplicates("case_id")
        .set_index("case_id")["case_id_raw"]
        .to_dict()
    )
    wide.insert(1, "file_example", wide["case_id"].map(raw_map))
    wide.to_csv(wide_path, index=False)

    primary.to_csv(primary_csv, index=False)
    pairwise.to_csv(pairwise_csv, index=False)
    vc.to_csv(vc_csv, index=False)

    n = int(data["case_id"].nunique())
    observers = sorted(data["observer"].unique())
    obs_n = meta.get("per_observer_n", {})

    lines = [
        "# Multi-rater ICC results (Graefe revision WS1)",
        "",
        f"**Date computed:** 2026-07-30  ",
        f"**n (intersection of 3 observers):** {n}  ",
        f"**Observers:** {', '.join(observers)} "
        f"(YY = original analyst; Inoue = observer_A; Osada = observer_B)  ",
        f"**Primary model:** ICC(2,1) — two-way random effects, absolute agreement, "
        "single measures (Shrout & Fleiss / McGraw & Wong)",
        "",
        "## Data sources",
        "",
        "| Observer | Folder | CSV | Rows (unique cases) |",
        "|----------|--------|-----|---------------------|",
        f"| YY | `incoming/observer_YY/` | `MNV_batch_20260730_165332.csv` | {obs_n.get('YY', '—')} |",
        f"| Inoue | `incoming/observer_A/` (alias `observer_inoue/`) | `MNV_batch_20260729_180525_inoue.csv` | {obs_n.get('Inoue', '—')} |",
        f"| Osada | `incoming/observer_B/` (alias `observer_osada/`) | `MNV_batch_20260730_131130_osada.csv` | {obs_n.get('Osada', '—')} |",
        "",
        "Join key: `File` basename, lowercased, extension stripped.",
        "",
        "## Case matching",
        "",
        f"- Union of case IDs: **{meta.get('union_n', '—')}**",
        f"- Intersection (all 3 observers): **{n}**",
    ]
    only = meta.get("only_per_observer", {})
    for o, cnt in only.items():
        if cnt:
            lines.append(f"- Cases only in {o} (dropped from ICC): **{cnt}**")
    for note in meta.get("dropped", []):
        lines.append(f"- {note}")
    missing = meta.get("missing_cases", {})
    any_missing = any(missing.get(o) for o in missing)
    if any_missing:
        lines += ["", "### Dropped / non-overlapping cases", ""]
        for o, cases in missing.items():
            if not cases:
                continue
            lines.append(f"**{o} only ({len(cases)}):**")
            for c in cases[:30]:
                lines.append(f"- `{c}`")
            if len(cases) > 30:
                lines.append(f"- … and {len(cases) - 30} more")
            lines.append("")
    else:
        lines.append("- No observer-specific dropouts beyond intersection filter.")

    lines += [
        "",
        "## Primary: 3-rater ICC(2,1)",
        "",
        "| Metric | n | k | ICC(2,1) | 95% CI | Source |",
        "|--------|---|---|----------|--------|--------|",
    ]
    for _, r in primary.iterrows():
        lines.append(
            f"| {METRIC_LABELS.get(r['metric'], r['metric'])} | "
            f"{int(r['n'])} | {int(r['k'])} | {_fmt_icc(r['icc'])} | "
            f"{_fmt_ci(r['ci_low'], r['ci_high'])} | {r.get('source', '')} |"
        )

    lines += [
        "",
        "## Supplementary: pairwise ICC(2,1)",
        "",
        "| Metric | Pair | n | ICC(2,1) | 95% CI | Source |",
        "|--------|------|---|----------|--------|--------|",
    ]
    for _, r in pairwise.iterrows():
        lines.append(
            f"| {METRIC_LABELS.get(r['metric'], r['metric'])} | {r['pair']} | "
            f"{int(r['n'])} | {_fmt_icc(r['icc'])} | "
            f"{_fmt_ci(r['ci_low'], r['ci_high'])} | {r.get('source', '')} |"
        )

    lines += [
        "",
        "## Multilevel / variance-component ICC",
        "",
        "Two-way random ANOVA variance components:",
        "",
        r"$$\mathrm{ICC}_{\mathrm{case}} = "
        r"\sigma^2_{\mathrm{case}} / "
        r"(\sigma^2_{\mathrm{case}} + \sigma^2_{\mathrm{observer}} + "
        r"\sigma^2_{\varepsilon})$$",
        "",
        "| Metric | σ²_case | σ²_observer | σ²_error | ICC_case |",
        "|--------|---------|-------------|---------|----------|",
    ]
    for _, r in vc.iterrows():
        lines.append(
            f"| {METRIC_LABELS.get(r['metric'], r['metric'])} | "
            f"{r['var_case']:.4g} | {r['var_observer']:.4g} | "
            f"{r['var_error']:.4g} | {_fmt_icc(r['icc_vc'])} |"
        )

    lines += [
        "",
        "## Interpretation notes",
        "",
        "- Primary claim for the Response / Methods: **3-rater ICC(2,1)** with 95% CI.",
        "- Pairwise ICCs are supplementary (YY–Inoue, YY–Osada, Inoue–Osada).",
        "- Variance-component ICC_case is complementary (case vs observer vs residual).",
        "- Intra-observer (same-operator test–retest) was not the primary analysis for this revision.",
        "",
        "## Output files",
        "",
        f"- `{md_path.name}` — this report",
        f"- `{primary_csv.name}` — primary 3-rater ICC table",
        f"- `{pairwise_csv.name}` — pairwise ICC table",
        f"- `{vc_csv.name}` — variance components",
        f"- `{long_path.name}` — long-format matched ratings",
        f"- `{wide_path.name}` — wide-format matched ratings",
        "",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {md_path}")
    print(f"Wrote {primary_csv}")
    print(f"Wrote {pairwise_csv}")
    print(f"Wrote {vc_csv}")
    print(f"Wrote {long_path}")
    print(f"Wrote {wide_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--incoming",
        type=Path,
        default=INCOMING_DIR,
        help="Incoming root (default: documentation/graefe_revision/icc/incoming)",
    )
    args = parser.parse_args()
    incoming = args.incoming

    print("WS1 multi-rater ICC")
    print(f"  Incoming: {incoming}")
    print("  Expected folders:", ", ".join(OBSERVER_DIRS))
    print(
        "  Primary model: ICC(2,1) two-way random, absolute agreement, "
        "single measures (3 raters)"
    )

    data, reasons, meta = discover_incoming(incoming)
    if data is None:
        print("awaiting incoming data")
        for r in reasons:
            print(f"  - {r}")
        return 0

    n_cases = int(data["case_id"].nunique())
    observers = sorted(data["observer"].unique())
    print(f"Found {n_cases} complete cases × {len(observers)} observers: {observers}")

    primary_rows = []
    pairwise_rows = []
    vc_rows = []

    for metric in METRICS:
        # Primary 3-rater
        pg_res = try_pingouin_icc(data, metric)
        wide = data.pivot_table(
            index="case_id", columns="observer", values=metric, aggfunc="mean"
        )
        # Stable column order
        wide = wide.reindex(columns=[c for c in ("YY", "Inoue", "Osada") if c in wide.columns])
        if pg_res is not None:
            primary_rows.append({"metric": metric, **pg_res})
        else:
            res = icc_2_1_multirater(wide.to_numpy())
            res["source"] = "numpy"
            primary_rows.append({"metric": metric, **res})

        # Pairwise
        pairs = [("YY", "Inoue"), ("YY", "Osada"), ("Inoue", "Osada")]
        for a, b in pairs:
            if a not in wide.columns or b not in wide.columns:
                continue
            sub = wide[[a, b]].dropna()
            pair_long = (
                sub.reset_index()
                .melt(id_vars="case_id", var_name="observer", value_name=metric)
            )
            pg_p = try_pingouin_icc(pair_long, metric)
            if pg_p is not None:
                pairwise_rows.append(
                    {"metric": metric, "pair": f"{a}–{b}", **pg_p}
                )
            else:
                res_p = icc_2_1_multirater(sub.to_numpy())
                res_p["source"] = "numpy"
                pairwise_rows.append(
                    {"metric": metric, "pair": f"{a}–{b}", **res_p}
                )

        vc = variance_components_anova(wide.to_numpy())
        vc_rows.append({"metric": metric, **vc})
        _ = try_mixedlm_vc(data, metric)  # reserved; ANOVA VC is primary VC

    primary = pd.DataFrame(primary_rows)
    pairwise = pd.DataFrame(pairwise_rows)
    vc = pd.DataFrame(vc_rows)
    write_outputs(data, meta, primary, pairwise, vc)

    print("\nPrimary ICC(2,1):")
    for _, r in primary.iterrows():
        print(
            f"  {METRIC_LABELS[r['metric']]}: "
            f"{r['icc']:.3f} ({r['ci_low']:.3f}–{r['ci_high']:.3f}) "
            f"[{r.get('source')}]"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
