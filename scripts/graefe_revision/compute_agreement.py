#!/usr/bin/env python3
"""Expert vs automated morphological agreement (WS2).

Loads locked expert grades + automated labels (via grading_subset_meta, or
manifest → automated_labels.csv), normalizes 'Tree in bud', computes overall
agreement, quadratic weighted κ (order: Dead tree → Tree in bud → Glomerular →
Seafan → Medusa) with bootstrap 95% CI, and a confusion matrix.

Writes grading/agreement_stats.md (+ CSV / confusion_matrix.csv) when expert
file is locked (all rows filled). If grades are not filled, exits gracefully
with a clear message (no unblinding).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
GRADING_DIR = REPO_ROOT / "documentation" / "graefe_revision" / "grading"

ORDER = [
    "Dead tree",
    "Tree in bud",
    "Glomerular",
    "Seafan",
    "Medusa",
]

BOOTSTRAP_SEED = 20260727
BOOTSTRAP_N = 10000


def _normalize_subtype(value: object) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    s = str(value).strip()
    if not s or s.lower() in {"nan", "none"}:
        return ""
    aliases = {
        "Tree-in-bud": "Tree in bud",
        "Tree-in-Bud": "Tree in bud",
        "tree in bud": "Tree in bud",
        "TreeInBud": "Tree in bud",
        "tree-in-bud": "Tree in bud",
        "Dead-tree": "Dead tree",
        "Dead-Tree": "Dead tree",
        "dead tree": "Dead tree",
        "Sea fan": "Seafan",
        "Sea-fan": "Seafan",
        "sea fan": "Seafan",
    }
    return aliases.get(s, s)


def resolve_expert_path(grading_dir: Path) -> Path:
    locked = grading_dir / "expert_grades_locked.csv"
    blind = grading_dir / "expert_grades_blind.csv"
    if locked.is_file():
        return locked
    return blind


def expert_grades_locked(path: Path) -> tuple[bool, str]:
    if not path.is_file():
        return False, f"Expert grades file not found: {path}"
    df = pd.read_csv(path)
    if "expert_subtype" not in df.columns:
        return False, f"{path.name} missing expert_subtype column"
    filled = df["expert_subtype"].map(_normalize_subtype)
    n = len(df)
    n_filled = int((filled != "").sum())
    if n_filled == 0:
        return False, (
            f"Expert grades not filled ({n_filled}/{n}). "
            "Fill expert_grades_blind.csv then re-run. "
            "Do not open automated_labels.csv while grading."
        )
    if n_filled < n:
        blank_ids = df.loc[filled == "", "blind_id"].astype(str).tolist()
        return False, (
            f"Expert grades incomplete ({n_filled}/{n} filled). "
            f"Blank blind_ids: {', '.join(blank_ids)}. "
            "Lock all rows before computing agreement."
        )
    bad = sorted({v for v in filled if v not in ORDER})
    if bad:
        return False, f"Unrecognized expert subtypes (normalize spelling): {bad}"
    return True, f"Expert grades locked ({n_filled}/{n}) from {path.name}"


def quadratic_weighted_kappa(
    y_true: list[str], y_pred: list[str], labels: list[str]
) -> float:
    """Quadratic weighted Cohen's κ for ordinal labels."""
    label_to_i = {lab: i for i, lab in enumerate(labels)}
    n = len(labels)
    conf = np.zeros((n, n), dtype=float)
    for a, b in zip(y_true, y_pred):
        conf[label_to_i[a], label_to_i[b]] += 1.0
    total = conf.sum()
    if total == 0:
        return float("nan")
    conf = conf / total

    w = np.zeros((n, n), dtype=float)
    for i in range(n):
        for j in range(n):
            w[i, j] = ((i - j) ** 2) / ((n - 1) ** 2)

    row_marg = conf.sum(axis=1)
    col_marg = conf.sum(axis=0)
    expected = np.outer(row_marg, col_marg)

    num = np.sum(w * conf)
    den = np.sum(w * expected)
    if den == 0:
        return float("nan")
    return float(1.0 - num / den)


def bootstrap_kappa_ci(
    y_true: list[str],
    y_pred: list[str],
    labels: list[str],
    n_boot: int = BOOTSTRAP_N,
    seed: int = BOOTSTRAP_SEED,
) -> tuple[float, float]:
    """Percentile bootstrap 95% CI for quadratic weighted κ."""
    rng = np.random.default_rng(seed)
    y_true_arr = np.asarray(y_true, dtype=object)
    y_pred_arr = np.asarray(y_pred, dtype=object)
    n = len(y_true_arr)
    samples = np.empty(n_boot, dtype=float)
    for b in range(n_boot):
        idx = rng.integers(0, n, size=n)
        samples[b] = quadratic_weighted_kappa(
            y_true_arr[idx].tolist(),
            y_pred_arr[idx].tolist(),
            labels,
        )
    lo, hi = np.nanpercentile(samples, [2.5, 97.5])
    return float(lo), float(hi)


def confusion_matrix_df(
    y_true: list[str], y_pred: list[str], labels: list[str]
) -> pd.DataFrame:
    idx = {lab: i for i, lab in enumerate(labels)}
    mat = np.zeros((len(labels), len(labels)), dtype=int)
    for a, b in zip(y_true, y_pred):
        mat[idx[a], idx[b]] += 1
    return pd.DataFrame(mat, index=labels, columns=labels)


def _auto_col(df: pd.DataFrame) -> str:
    for cand in ("automated_subtype", "Subtype", "subtype", "auto_subtype"):
        if cand in df.columns:
            return cand
    raise KeyError(
        f"No automated subtype column found (columns={list(df.columns)})"
    )


def load_paired(grading_dir: Path, expert_path: Path) -> pd.DataFrame:
    """Merge expert grades with automated subtypes for the graded subset.

    Prefer grading_subset_meta.csv; fall back to
    grading_manifest.csv → automated_labels.csv.
    """
    expert = pd.read_csv(expert_path)
    meta_path = grading_dir / "grading_subset_meta.csv"
    if meta_path.is_file():
        meta = pd.read_csv(meta_path)
        auto_col = _auto_col(meta)
        merged = expert.merge(
            meta[["blind_id", auto_col]], on="blind_id", how="left"
        )
        merged["expert_subtype"] = merged["expert_subtype"].map(_normalize_subtype)
        merged["automated_subtype"] = merged[auto_col].map(_normalize_subtype)
        # Cross-check against automated_labels.csv when present
        labels_path = grading_dir / "automated_labels.csv"
        manifest_path = grading_dir / "grading_manifest.csv"
        if labels_path.is_file() and manifest_path.is_file():
            manifest = pd.read_csv(manifest_path)
            labels = pd.read_csv(labels_path)
            key_col = "case_key" if "case_key" in labels.columns else None
            man_key = "case_key" if "case_key" in manifest.columns else None
            if key_col and man_key and "blind_id" in manifest.columns:
                auto_col2 = _auto_col(labels)
                via = manifest[["blind_id", man_key]].merge(
                    labels[[key_col, auto_col2]],
                    left_on=man_key,
                    right_on=key_col,
                    how="left",
                )
                via["auto_via_labels"] = via[auto_col2].map(_normalize_subtype)
                check = merged.merge(
                    via[["blind_id", "auto_via_labels"]], on="blind_id", how="left"
                )
                mismatch = check[
                    check["automated_subtype"] != check["auto_via_labels"]
                ]
                if len(mismatch):
                    raise ValueError(
                        "automated subtype mismatch between "
                        f"grading_subset_meta and automated_labels.csv "
                        f"({len(mismatch)} rows)"
                    )
        return merged

    # Fallback: manifest → automated_labels
    manifest = pd.read_csv(grading_dir / "grading_manifest.csv")
    labels = pd.read_csv(grading_dir / "automated_labels.csv")
    auto_col = _auto_col(labels)
    via = manifest[["blind_id", "case_key"]].merge(
        labels[["case_key", auto_col]], on="case_key", how="left"
    )
    merged = expert.merge(via[["blind_id", auto_col]], on="blind_id", how="left")
    merged["expert_subtype"] = merged["expert_subtype"].map(_normalize_subtype)
    merged["automated_subtype"] = merged[auto_col].map(_normalize_subtype)
    return merged


def write_report(
    paired: pd.DataFrame,
    kappa: float,
    kappa_lo: float,
    kappa_hi: float,
    overall: float,
    conf: pd.DataFrame,
    out_md: Path,
    out_csv: Path,
) -> None:
    n = len(paired)
    n_agree = int(
        (paired["expert_subtype"] == paired["automated_subtype"]).sum()
    )
    pct = 100.0 * overall
    lines = [
        "# Expert–automated agreement (WS2)",
        "",
        "Ordinal order for quadratic weighted κ: "
        "Dead tree → Tree in bud → Glomerular → Seafan → Medusa.",
        "Spelling normalized to `Tree in bud`.",
        f"Bootstrap 95% CI: {BOOTSTRAP_N} resamples, seed `{BOOTSTRAP_SEED}`.",
        "",
        f"- n (subset): **{n}**",
        f"- Overall agreement: **{pct:.1f}%** ({n_agree}/{n})",
        f"- Quadratic weighted κ: **{kappa:.3f}** "
        f"(95% CI {kappa_lo:.3f}–{kappa_hi:.3f})",
        "",
        "## Confusion matrix (rows = expert, columns = automated)",
        "",
        "| expert \\ automated | " + " | ".join(conf.columns.astype(str)) + " |",
        "|---|" + "|".join(["---"] * len(conf.columns)) + "|",
    ]
    for idx, row in conf.iterrows():
        lines.append(
            "| " + str(idx) + " | " + " | ".join(str(int(v)) for v in row.tolist()) + " |"
        )
    lines.extend(["", ""])
    out_md.write_text("\n".join(lines), encoding="utf-8")

    summary = pd.DataFrame(
        [
            {
                "n": n,
                "n_agree": n_agree,
                "overall_agreement": overall,
                "overall_agreement_pct": pct,
                "quadratic_weighted_kappa": kappa,
                "kappa_ci_low": kappa_lo,
                "kappa_ci_high": kappa_hi,
                "bootstrap_n": BOOTSTRAP_N,
                "bootstrap_seed": BOOTSTRAP_SEED,
            }
        ]
    )
    summary.to_csv(out_csv, index=False)
    conf.to_csv(out_md.with_name("confusion_matrix.csv"))
    # Keep legacy alias used in earlier drafts
    conf.to_csv(out_md.with_name("agreement_confusion_matrix.csv"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grading-dir", type=Path, default=GRADING_DIR)
    args = parser.parse_args()

    expert_path = resolve_expert_path(args.grading_dir)
    locked, msg = expert_grades_locked(expert_path)
    print(msg)
    if not locked:
        sys.exit(0)

    paired = load_paired(args.grading_dir, expert_path)
    missing_auto = paired["automated_subtype"] == ""
    if missing_auto.any():
        print(
            f"ERROR: {int(missing_auto.sum())} rows lack automated subtype "
            "after merge; check grading_subset_meta.csv / automated_labels.csv"
        )
        sys.exit(1)
    bad_auto = sorted(
        {v for v in paired["automated_subtype"] if v not in ORDER}
    )
    if bad_auto:
        print(f"ERROR: unrecognized automated subtypes: {bad_auto}")
        sys.exit(1)

    y_true = paired["expert_subtype"].tolist()
    y_pred = paired["automated_subtype"].tolist()
    overall = float(np.mean([a == b for a, b in zip(y_true, y_pred)]))
    kappa = quadratic_weighted_kappa(y_true, y_pred, ORDER)
    kappa_lo, kappa_hi = bootstrap_kappa_ci(y_true, y_pred, ORDER)
    conf = confusion_matrix_df(y_true, y_pred, ORDER)

    out_md = args.grading_dir / "agreement_stats.md"
    out_csv = args.grading_dir / "agreement_stats.csv"
    write_report(
        paired, kappa, kappa_lo, kappa_hi, overall, conf, out_md, out_csv
    )
    print(f"Wrote {out_md}")
    print(f"Wrote {out_csv}")
    print(f"Wrote {args.grading_dir / 'confusion_matrix.csv'}")
    print(
        f"overall={overall:.3f} ({100*overall:.1f}%) "
        f"quadratic_weighted_kappa={kappa:.3f} "
        f"(95% CI {kappa_lo:.3f}–{kappa_hi:.3f})"
    )


if __name__ == "__main__":
    main()
