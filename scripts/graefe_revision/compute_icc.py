#!/usr/bin/env python3
"""Compute intra-observer ICCs for WS1 after Session 1 + Session 2 are paired.

Model: two-way mixed-effects, absolute agreement, single measures — ICC(2,1)
(Shrout & Fleiss / McGraw & Wong convention).

If Session 2 scores are missing, prints "awaiting session2" and exits 0
without claiming ICC complete.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
ICC_DIR = REPO_ROOT / "documentation" / "graefe_revision" / "icc"

METRICS = [
    "Network Complexity",
    "Caliber Uniformity",
    "Maturity",
    "MNV Area",
]


def _filled_scores(df: pd.DataFrame, metrics: list[str]) -> bool:
    if df.empty:
        return False
    for col in metrics:
        if col not in df.columns:
            return False
        series = pd.to_numeric(df[col], errors="coerce")
        if series.isna().all():
            return False
        if series.isna().any():
            # Partial fill still counts as "not ready"
            return False
    return True


def icc_2_1(x: np.ndarray, y: np.ndarray) -> dict[str, float]:
    """ICC(2,1) absolute agreement for two raters/sessions.

    Returns ICC, and approximate 95% CI via F distribution (McGraw & Wong).
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    n = int(x.size)
    if n < 3:
        return {
            "n": float(n),
            "icc": float("nan"),
            "ci_low": float("nan"),
            "ci_high": float("nan"),
        }

    ratings = np.column_stack([x, y])
    k = 2
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

    icc = (ms_subjects - ms_error) / (
        ms_subjects + (k - 1) * ms_error + (k / n) * (ms_raters - ms_error)
    )

    # 95% CI (McGraw & Wong absolute-agreement single measures)
    alpha = 0.05
    from scipy import stats

    F = ms_subjects / ms_error if ms_error > 0 else float("inf")
    df1 = n - 1
    df2 = (n - 1) * (k - 1)
    F_L = F / stats.f.ppf(1 - alpha / 2, df1, df2)
    F_U = F * stats.f.ppf(1 - alpha / 2, df2, df1)
    # Convert F bounds to ICC bounds for ICC(A,1)
    # Using formula from McGraw & Wong Table 7 / common psychometrics form:
    v = (k * ms_raters - ms_error) / n  # rater effect term in denominator scale
    # Simpler widely used CI on the ICC(2,1) form:
    # ICC_L = (F_L - 1) / (F_L + k - 1)
    # ICC_U = (F_U - 1) / (F_U + k - 1)
    # Adjust for absolute agreement rater term when present:
    a = (k * (ms_raters - ms_error)) / n if n else 0.0
    # Prefer F-based absolute-agreement CI (Landis/Koch / common R psych implementations):
    icc_L = (F_L - 1.0) / (F_L + k - 1.0 + (k * a) / ms_error) if ms_error > 0 else float("nan")
    icc_U = (F_U - 1.0) / (F_U + k - 1.0 + (k * a) / ms_error) if ms_error > 0 else float("nan")
    # Fall back to relative-agreement-style F CI if numerical issues
    if not np.isfinite(icc_L) or not np.isfinite(icc_U):
        icc_L = (F_L - 1.0) / (F_L + k - 1.0)
        icc_U = (F_U - 1.0) / (F_U + k - 1.0)

    return {
        "n": float(n),
        "icc": float(icc),
        "ci_low": float(min(icc_L, icc_U)),
        "ci_high": float(max(icc_L, icc_U)),
        "ms_subjects": float(ms_subjects),
        "ms_error": float(ms_error),
        "ms_raters": float(ms_raters),
    }


def load_pair(
    s1_path: Path, s2_path: Path
) -> tuple[pd.DataFrame, pd.DataFrame, str | None]:
    if not s1_path.is_file():
        return pd.DataFrame(), pd.DataFrame(), f"missing Session 1: {s1_path}"
    s1 = pd.read_csv(s1_path)
    if not s2_path.is_file():
        return s1, pd.DataFrame(), "awaiting session2 (icc_session2.csv not found)"
    s2 = pd.read_csv(s2_path)
    if not _filled_scores(s2, METRICS):
        return s1, s2, "awaiting session2"
    return s1, s2, None


def compute_all(s1: pd.DataFrame, s2: pd.DataFrame) -> pd.DataFrame:
    merged = s1.merge(
        s2,
        on="icc_id",
        suffixes=("_s1", "_s2"),
        how="inner",
    )
    rows = []
    for metric in METRICS:
        c1 = f"{metric}_s1" if f"{metric}_s1" in merged.columns else metric
        c2 = f"{metric}_s2"
        if c1 not in merged.columns or c2 not in merged.columns:
            # Session1 may use same names without suffix if merge failed oddly
            raise KeyError(f"Missing columns for {metric}: need {c1} and {c2}")
        x = pd.to_numeric(merged[c1], errors="coerce").to_numpy()
        y = pd.to_numeric(merged[c2], errors="coerce").to_numpy()
        res = icc_2_1(x, y)
        rows.append(
            {
                "metric": metric,
                "n": int(res["n"]),
                "icc_2_1": res["icc"],
                "ci_low_95": res["ci_low"],
                "ci_high_95": res["ci_high"],
            }
        )
    return pd.DataFrame(rows)


def write_markdown(stats: pd.DataFrame, out_path: Path) -> None:
    lines = [
        "# Intra-observer ICC (WS1)",
        "",
        "Model: two-way mixed-effects, absolute agreement, single measures "
        "(ICC(2,1)). Examiner: YY. Session 1 = prior batch CSV scores; "
        "Session 2 = new Flet ROI.",
        "",
        "| Metric | n | ICC(2,1) | 95% CI |",
        "|--------|---|----------|--------|",
    ]
    for _, r in stats.iterrows():
        lines.append(
            f"| {r['metric']} | {int(r['n'])} | {r['icc_2_1']:.3f} | "
            f"{r['ci_low_95']:.3f}–{r['ci_high_95']:.3f} |"
        )
    lines.extend(
        [
            "",
            "Do not claim ICC complete in the Response letter until these "
            "numbers are reviewed and Session 2 provenance is locked.",
            "",
        ]
    )
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--icc-dir", type=Path, default=ICC_DIR)
    parser.add_argument(
        "--demo",
        action="store_true",
        help="With only Session 1: print dry-run status (default behavior too)",
    )
    args = parser.parse_args()

    s1_path = args.icc_dir / "icc_session1.csv"
    s2_path = args.icc_dir / "icc_session2.csv"
    s1, s2, status = load_pair(s1_path, s2_path)

    if status is not None:
        n1 = len(s1) if not s1.empty else 0
        print(f"Session 1 rows: {n1}")
        if not s1.empty and "match_status" in s1.columns:
            n_ok = int((s1["match_status"] == "matched_csv").sum())
            print(f"Session 1 matched scores: {n_ok}/{n1}")
        print(status)
        if args.demo or status.startswith("awaiting"):
            print("Dry/demo: ICC not computed. Re-run after filling icc_session2.csv.")
        sys.exit(0)

    stats = compute_all(s1, s2)
    out_csv = args.icc_dir / "icc_stats.csv"
    out_md = args.icc_dir / "icc_stats.md"
    stats.to_csv(out_csv, index=False)
    write_markdown(stats, out_md)
    print(f"Wrote {out_csv}")
    print(f"Wrote {out_md}")
    print(stats.to_string(index=False))


if __name__ == "__main__":
    main()
