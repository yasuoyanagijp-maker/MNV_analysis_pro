#!/usr/bin/env python3
"""Create stratified blind expert-grading subset from automated_labels.csv."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
GRADING_DIR = REPO_ROOT / "documentation" / "graefe_revision" / "grading"

# Stratified subset ~48% of cohort, proportional by device stratum
SEED = 20260727
TARGET_N = {
    "large": 24,  # of 49
    "small": 16,  # of 33
    "small_3mm": 14,  # of 30
}  # total 54


def sample_subset(labels: pd.DataFrame, seed: int = SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    parts = []
    for stratum, n_target in TARGET_N.items():
        pool = labels.loc[labels["stratum"] == stratum].copy()
        # Prefer cases with readable images for blinded grading
        if "image_exists" in pool.columns:
            with_img = pool.loc[pool["image_exists"].astype(bool)].copy()
            if len(with_img) >= n_target:
                pool = with_img
        if len(pool) < n_target:
            raise ValueError(f"{stratum}: only {len(pool)} cases, need {n_target}")
        idx = rng.choice(pool.index.to_numpy(), size=n_target, replace=False)
        parts.append(pool.loc[idx])
    out = pd.concat(parts, ignore_index=True)
    # Blind IDs shuffled across strata so order does not leak device
    order = rng.permutation(len(out))
    out = out.iloc[order].reset_index(drop=True)
    out.insert(0, "blind_id", [f"B{i:03d}" for i in range(1, len(out) + 1)])
    out.insert(1, "grading_seed", seed)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, default=GRADING_DIR / "automated_labels.csv")
    parser.add_argument("--out-dir", type=Path, default=GRADING_DIR)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()

    labels = pd.read_csv(args.labels)
    subset = sample_subset(labels, seed=args.seed)

    manifest = subset[
        [
            "blind_id",
            "case_key",
            "stratum",
            "file_name",
            "image_path",
            "grading_seed",
        ]
    ].copy()
    expert = pd.DataFrame(
        {
            "blind_id": subset["blind_id"],
            "expert_subtype": "",
            "notes": "",
            "grader": "YY",
            "graded_at": "",
        }
    )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.out_dir / "grading_manifest.csv"
    expert_path = args.out_dir / "expert_grades_blind.csv"
    subset_meta = args.out_dir / "grading_subset_meta.csv"

    manifest.to_csv(manifest_path, index=False)
    expert.to_csv(expert_path, index=False)
    subset[
        [
            "blind_id",
            "case_key",
            "stratum",
            "automated_subtype",
            "label_method",
            "grading_seed",
        ]
    ].to_csv(subset_meta, index=False)

    print(f"Wrote {manifest_path}")
    print(f"Wrote {expert_path} (NO automated labels)")
    print(f"Wrote {subset_meta} (unblinding aid; keep separate from grader)")
    print(f"n={len(subset)} seed={args.seed}")
    print(subset["stratum"].value_counts().to_string())


if __name__ == "__main__":
    main()
