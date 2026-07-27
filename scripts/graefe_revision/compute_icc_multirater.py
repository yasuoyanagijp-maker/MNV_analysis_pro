#!/usr/bin/env python3
"""Multi-rater ICC for WS1 (3 observers × ≈20 cases).

Primary: Shrout & Fleiss ICC(2,1) — two-way random effects, absolute
agreement, single measures — per metric, with 95% CI.

Optional (if pingouin / statsmodels available): multilevel variance-component
ICC = σ²_case / (σ²_case + σ²_observer + σ²_error).

Expected layout
---------------
documentation/graefe_revision/icc/incoming/
  observer_YY/*.csv
  observer_A/*.csv
  observer_B/*.csv

Required columns (aliases accepted)
-----------------------------------
  case_id, area, complexity, caliber_uniformity, maturity, observer, date

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

OBSERVER_DIRS = ("observer_YY", "observer_A", "observer_B")

METRICS = {
    "area": ("area", "MNV Area", "mnv_area", "lesion_area"),
    "complexity": ("complexity", "Network Complexity", "network_complexity"),
    "caliber_uniformity": (
        "caliber_uniformity",
        "Caliber Uniformity",
        "caliber_uniformity_score",
    ),
    "maturity": ("maturity", "Maturity", "Maturity Index", "maturity_index"),
}

CASE_ALIASES = ("case_id", "icc_id", "Case", "File", "file_name", "image_key")
OBSERVER_ALIASES = ("observer", "rater", "examiner", "operator")
DATE_ALIASES = ("date", "session_date", "analysis_date", "timestamp")


def _first_present(columns: pd.Index, aliases: tuple[str, ...]) -> str | None:
    lower = {c.lower(): c for c in columns}
    for a in aliases:
        if a in columns:
            return a
        if a.lower() in lower:
            return lower[a.lower()]
    return None


def _load_observer_csvs(folder: Path) -> pd.DataFrame | None:
    csvs = sorted(folder.glob("*.csv"))
    if not csvs:
        return None
    frames = [pd.read_csv(p) for p in csvs]
    df = pd.concat(frames, ignore_index=True)
    df["_source_folder"] = folder.name
    return df


def _normalize(df: pd.DataFrame, default_observer: str) -> pd.DataFrame | None:
    case_col = _first_present(df.columns, CASE_ALIASES)
    if case_col is None:
        return None

    out = pd.DataFrame()
    out["case_id"] = df[case_col].astype(str).str.strip()

    obs_col = _first_present(df.columns, OBSERVER_ALIASES)
    if obs_col is not None:
        out["observer"] = df[obs_col].astype(str).str.strip()
    else:
        # Derive from folder name: observer_YY -> YY
        tag = default_observer.replace("observer_", "")
        out["observer"] = tag

    date_col = _first_present(df.columns, DATE_ALIASES)
    out["date"] = df[date_col] if date_col is not None else pd.NA

    for canon, aliases in METRICS.items():
        col = _first_present(df.columns, aliases)
        if col is None:
            return None
        out[canon] = pd.to_numeric(df[col], errors="coerce")

    return out


def discover_incoming(
    incoming_dir: Path,
) -> tuple[pd.DataFrame | None, list[str]]:
    """Return concatenated long-format ratings, or (None, reasons)."""
    reasons: list[str] = []
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
        if norm["case_id"].eq("").all() or norm[list(METRICS)].isna().all().all():
            reasons.append(f"{folder}: empty or all-NaN scores")
            continue
        parts.append(norm)

    if len(parts) < 3:
        if not reasons:
            reasons.append("need CSVs from all three observers")
        return None, reasons

    combined = pd.concat(parts, ignore_index=True)
    # Require overlapping cases with all 3 observers
    counts = combined.groupby("case_id")["observer"].nunique()
    complete_cases = counts[counts >= 3].index
    if len(complete_cases) < 5:
        return None, [
            f"only {len(complete_cases)} cases with all 3 observers "
            "(need a usable multi-rater set, target n≈20)"
        ]

    return combined[combined["case_id"].isin(complete_cases)].copy(), []


def icc_2_1_multirater(ratings: np.ndarray) -> dict[str, float]:
    """ICC(2,1) absolute agreement for n subjects × k raters (numpy fallback).

    ratings: shape (n, k). Sketches McGraw & Wong two-way random ICC(A,1).
    """
    ratings = np.asarray(ratings, dtype=float)
    # Drop rows with any NaN
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

    # Approximate 95% CI via F (McGraw & Wong); keep simple for stub
    from scipy import stats

    alpha = 0.05
    f_obs = ms_subjects / ms_error if ms_error > 0 else float("nan")
    df1, df2 = n - 1, (n - 1) * (k - 1)
    try:
        f_l = f_obs / stats.f.ppf(1 - alpha / 2, df1, df2)
        f_u = f_obs * stats.f.ppf(1 - alpha / 2, df2, df1)
        # Convert F bounds back to ICC(2,1) scale (simplified)
        icc_l = (f_l - 1) / (f_l + k - 1)
        icc_u = (f_u - 1) / (f_u + k - 1)
    except Exception:
        icc_l = icc_u = float("nan")

    return {
        "n": float(n),
        "k": float(k),
        "icc": float(icc),
        "ci_low": float(icc_l),
        "ci_high": float(icc_u),
    }


def try_pingouin_icc(long_df: pd.DataFrame, metric: str) -> dict | None:
    try:
        import pingouin as pg
    except ImportError:
        return None
    sub = long_df[["case_id", "observer", metric]].dropna()
    if sub.empty:
        return None
    icc = pg.intraclass_corr(
        data=sub,
        targets="case_id",
        raters="observer",
        ratings=metric,
    )
    row = icc[icc["Type"] == "ICC2"].iloc[0]
    return {
        "n": float(sub["case_id"].nunique()),
        "k": float(sub["observer"].nunique()),
        "icc": float(row["ICC"]),
        "ci_low": float(row["CI95%"][0]),
        "ci_high": float(row["CI95%"][1]),
        "source": "pingouin",
    }


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
        "  Required columns: case_id, area, complexity, "
        "caliber_uniformity, maturity, observer, date"
    )
    print(
        "  Primary model: ICC(2,1) two-way random, absolute agreement, "
        "single measures (3 raters)"
    )
    print(
        "  Optional: multilevel ICC = σ²_case / "
        "(σ²_case + σ²_observer + σ²_error) via LMM if available"
    )

    data, reasons = discover_incoming(incoming)
    if data is None:
        print("awaiting incoming data")
        for r in reasons:
            print(f"  - {r}")
        print(
            "\nDrop collaborator CSVs under incoming/observer_{YY,A,B}/ "
            "then re-run. Real computation will run when columns are locked."
        )
        return 0

    # Data present — sketch computation (full write-up when schema finalized)
    print(
        f"Found {data['case_id'].nunique()} complete cases × "
        f"{data['observer'].nunique()} observers"
    )
    rows = []
    for metric in METRICS:
        pg_res = try_pingouin_icc(data, metric)
        if pg_res is not None:
            rows.append({"metric": metric, **pg_res})
            continue
        # Wide matrix for numpy fallback
        wide = data.pivot_table(
            index="case_id", columns="observer", values=metric, aggfunc="mean"
        )
        res = icc_2_1_multirater(wide.to_numpy())
        res["source"] = "numpy"
        rows.append({"metric": metric, **res})

    out = pd.DataFrame(rows)
    out_csv = ICC_DIR / "multirater_icc_stats.csv"
    out_md = ICC_DIR / "multirater_icc_stats.md"
    out.to_csv(out_csv, index=False)
    lines = [
        "# Multi-rater ICC (draft)",
        "",
        f"Cases: {int(data['case_id'].nunique())}; "
        f"observers: {', '.join(sorted(data['observer'].unique()))}",
        "",
        "| Metric | n | k | ICC(2,1) | 95% CI | source |",
        "|--------|---|---|--------|--------|--------|",
    ]
    for _, r in out.iterrows():
        lines.append(
            f"| {r['metric']} | {int(r['n'])} | {int(r['k'])} | "
            f"{r['icc']:.3f} | {r['ci_low']:.3f}–{r['ci_high']:.3f} | "
            f"{r.get('source', '')} |"
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {out_csv}")
    print(f"Wrote {out_md}")
    print(
        "Note: multilevel LMM variance-component ICC not yet auto-run; "
        "add when statsmodels/rpy2 path is confirmed."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
