#!/usr/bin/env python3
"""Table 3 Kruskal–Wallis effect sizes (ε²) with bootstrap 95% CIs.

Primary score source: git commit 1e5d202 batch CSVs recovered under
documentation/graefe_revision/data/.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "documentation" / "graefe_revision" / "data"
OUT_DIR = REPO_ROOT / "documentation" / "graefe_revision" / "stats"

CSV_FILES = {
    "large": "MNV_batch_20260220_230245_large.csv",
    "small": "MNV_batch_20260220_083448small.csv",
    "small_3mm": "MNV_batch_20260220_223647_small_3mm.csv",
}

SCORE_COLS = [
    "Network Complexity Score",
    "Caliber Uniformity Score",
    "Maturity Index",
]

BOOTSTRAP_SEED = 20260727
BOOTSTRAP_N = 10000


def _read_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [str(c).lstrip("\ufeff") for c in df.columns]
    return df


def load_per_case_scores(data_dir: Path) -> pd.DataFrame:
    frames = []
    for stratum, fname in CSV_FILES.items():
        df = _read_csv(data_dir / fname)
        missing = [c for c in SCORE_COLS + ["File"] if c not in df.columns]
        if missing:
            raise KeyError(f"{fname}: missing columns {missing}")
        part = df[["File", *SCORE_COLS]].copy()
        part.insert(0, "stratum", stratum)
        part.insert(1, "source_csv", fname)
        frames.append(part)
    out = pd.concat(frames, ignore_index=True)
    for col in SCORE_COLS:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    if out[SCORE_COLS].isna().any().any():
        bad = out[out[SCORE_COLS].isna().any(axis=1)]
        raise ValueError(f"Non-numeric/missing scores in rows:\n{bad}")
    return out


def epsilon_squared(groups: list[np.ndarray]) -> tuple[float, float, float, int]:
    """Return (H, p, ε², n). ε² = (H - k + 1) / (n - k)."""
    clean = [np.asarray(g, dtype=float) for g in groups]
    clean = [g[~np.isnan(g)] for g in clean]
    clean = [g for g in clean if g.size > 0]
    k = len(clean)
    n = int(sum(g.size for g in clean))
    if k < 2 or n <= k:
        return float("nan"), float("nan"), float("nan"), n
    H, p = stats.kruskal(*clean)
    eps2 = (float(H) - k + 1.0) / (n - k)
    return float(H), float(p), float(eps2), n


def bootstrap_epsilon_ci(
    groups: list[np.ndarray],
    n_boot: int = BOOTSTRAP_N,
    seed: int = BOOTSTRAP_SEED,
    alpha: float = 0.05,
) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    arrays = [np.asarray(g, dtype=float) for g in groups]
    sizes = [a.size for a in arrays]
    vals = []
    for _ in range(n_boot):
        resampled = [rng.choice(a, size=sz, replace=True) for a, sz in zip(arrays, sizes)]
        _, _, eps2, _ = epsilon_squared(resampled)
        if np.isfinite(eps2):
            vals.append(eps2)
    if not vals:
        return float("nan"), float("nan")
    lo, hi = np.quantile(vals, [alpha / 2, 1 - alpha / 2])
    return float(lo), float(hi)


def analyze(per_case: pd.DataFrame) -> pd.DataFrame:
    rows = []
    strata = ["large", "small", "small_3mm"]
    for metric in SCORE_COLS:
        groups = [per_case.loc[per_case["stratum"] == s, metric].to_numpy() for s in strata]
        H, p, eps2, n = epsilon_squared(groups)
        lo, hi = bootstrap_epsilon_ci(groups)
        ns = {s: int(g.size) for s, g in zip(strata, groups)}
        medians = {s: float(np.median(g)) for s, g in zip(strata, groups)}
        rows.append(
            {
                "metric": metric,
                "n_total": n,
                "n_large": ns["large"],
                "n_small": ns["small"],
                "n_small_3mm": ns["small_3mm"],
                "median_large": medians["large"],
                "median_small": medians["small"],
                "median_small_3mm": medians["small_3mm"],
                "H": H,
                "p_kruskal": p,
                "epsilon_squared": eps2,
                "epsilon_squared_ci_low": lo,
                "epsilon_squared_ci_high": hi,
                "bootstrap_n": BOOTSTRAP_N,
                "bootstrap_seed": BOOTSTRAP_SEED,
            }
        )
    return pd.DataFrame(rows)


def format_md(summary: pd.DataFrame, per_case: pd.DataFrame) -> str:
    lines = [
        "# Table 3 — Kruskal–Wallis effect sizes (ε²)",
        "",
        "## Source",
        "",
        "- Git commit `1e5d202` batch CSVs recovered to `documentation/graefe_revision/data/`",
        "- Metrics: `Network Complexity Score`, `Caliber Uniformity Score`, `Maturity Index`",
        "- Strata: large / small / small_3mm (device / FOV analysis strata)",
        "",
        "## Method",
        "",
        "- Omnibus test: Kruskal–Wallis across 3 strata",
        "- Effect size: ε² = (H − k + 1) / (n − k), with k = 3 "
        "(display truncates negative ε² / CI lower bound to 0 when H < k−1)",
        f"- Bootstrap 95% CI: {BOOTSTRAP_N} resamples within strata (with replacement), seed `{BOOTSTRAP_SEED}`",
        "- Interpretation (common rule of thumb): ε² < 0.01 negligible; ~0.01–0.08 small; "
        "~0.08–0.26 medium; ≥0.26 large",
        "",
        f"**N cases used:** {len(per_case)} "
        f"(large={sum(per_case.stratum=='large')}, "
        f"small={sum(per_case.stratum=='small')}, "
        f"small_3mm={sum(per_case.stratum=='small_3mm')})",
        "",
        "## Results",
        "",
        "| Metric | H | p | ε² | 95% CI | medians (L / S / S3) |",
        "|---|---:|---:|---:|---|---|",
    ]
    for _, r in summary.iterrows():
        e_disp = max(0.0, float(r["epsilon_squared"]))
        lo_disp = max(0.0, float(r["epsilon_squared_ci_low"]))
        lines.append(
            "| {metric} | {H:.3f} | {p:.3g} | {e:.4f} | {lo:.4f}–{hi:.4f} | "
            "{ml:.1f} / {ms:.1f} / {m3:.1f} |".format(
                metric=r["metric"],
                H=r["H"],
                p=r["p_kruskal"],
                e=e_disp,
                lo=lo_disp,
                hi=r["epsilon_squared_ci_high"],
                ml=r["median_large"],
                ms=r["median_small"],
                m3=r["median_small_3mm"],
            )
        )
    lines.extend(
        [
            "",
            "## Notes for manuscript / response letter",
            "",
            "- Medians near 50 after piecewise-linear normalization are **not** evidence of biological equivalence.",
            "- On these 1e5d202 CSVs, **Network Complexity** does not differ across strata "
            "(p≈0.43; ε²≈0), but **Caliber Uniformity** and **Maturity Index** do "
            "(both p<0.001; ε²≈0.24). Do **not** reuse the original manuscript claim that all "
            "three Kruskal–Wallis tests were non-significant.",
            "- Report ε² + bootstrap CI alongside Kruskal–Wallis p-values; soften any "
            "“comparable across devices” wording for Caliber/Maturity.",
            "- Per-case scores: `table3_per_case_scores.csv`",
            "- Machine-readable summary (raw ε², may be slightly negative): `table3_effect_sizes.csv`",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    per_case = load_per_case_scores(args.data_dir)
    summary = analyze(per_case)

    per_case_path = args.out_dir / "table3_per_case_scores.csv"
    summary_csv = args.out_dir / "table3_effect_sizes.csv"
    summary_md = args.out_dir / "table3_effect_sizes.md"

    per_case.to_csv(per_case_path, index=False)
    summary.to_csv(summary_csv, index=False)
    summary_md.write_text(format_md(summary, per_case), encoding="utf-8")

    print(f"Wrote {per_case_path}")
    print(f"Wrote {summary_csv}")
    print(f"Wrote {summary_md}")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
