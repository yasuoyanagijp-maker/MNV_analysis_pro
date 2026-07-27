#!/usr/bin/env python3
"""Generate ICC intra-observer case list (Session 1 = prior analysis; Session 2 = new Flet ROI)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
ICC_DIR = REPO_ROOT / "documentation" / "graefe_revision" / "icc"
SESSION_JSON = REPO_ROOT / "output" / "reference_build_session.json"
INPUT_ROOT = Path("/Users/yy/MNV_quantitatibe analysis_original_inputdata")

SEED = 20260727
TARGET_N = {
    "large": 12,
    "small": 10,
    "small_3mm": 8,
}  # total 30


def pool_from_session(session_path: Path) -> pd.DataFrame:
    with open(session_path, encoding="utf-8") as f:
        session = json.load(f)
    rows = []
    for case_key, payload in session["cases"].items():
        stratum = case_key.split("/", 1)[0]
        if stratum not in TARGET_N:
            continue
        file_name = case_key.split("/", 1)[1]
        # Skip non-CSV small report duplicates not in paper cohort if desired later
        image_path = INPUT_ROOT / stratum / file_name
        rows.append(
            {
                "case_key": case_key,
                "stratum": stratum,
                "file_name": file_name,
                "image_path": str(image_path),
                "image_exists": image_path.is_file(),
                "session1_source": "reference_build_session.json / prior batch analysis",
            }
        )
    return pd.DataFrame(rows)


def sample_icc(pool: pd.DataFrame, seed: int = SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    parts = []
    for stratum, n_target in TARGET_N.items():
        sub = pool.loc[(pool["stratum"] == stratum) & (pool["image_exists"])].copy()
        if len(sub) < n_target:
            raise ValueError(
                f"{stratum}: only {len(sub)} existing images, need {n_target}"
            )
        idx = rng.choice(sub.index.to_numpy(), size=n_target, replace=False)
        parts.append(sub.loc[idx])
    out = pd.concat(parts, ignore_index=True)
    order = rng.permutation(len(out))
    out = out.iloc[order].reset_index(drop=True)
    out.insert(0, "icc_id", [f"ICC{i:02d}" for i in range(1, len(out) + 1)])
    out.insert(1, "icc_seed", seed)
    out["examiner"] = "YY"
    out["session1_status"] = "prior_analysis_counts_as_session1"
    out["session2_status"] = "pending_new_flet_roi"
    out["session_interval_note"] = (
        ">=2 weeks already elapsed since prior analysis; Session 2 may proceed when ready"
    )
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-json", type=Path, default=SESSION_JSON)
    parser.add_argument("--out-dir", type=Path, default=ICC_DIR)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    pool = pool_from_session(args.session_json)
    # Prefer paper-cohort filenames for small: exclude Main Report1/2 if present
    small_exclude = {"Main Report1.png", "Main Report2.png"}
    pool = pool.loc[
        ~((pool["stratum"] == "small") & (pool["file_name"].isin(small_exclude)))
    ].copy()

    icc = sample_icc(pool, seed=args.seed)
    out = args.out_dir / "icc_case_list.csv"
    icc.to_csv(out, index=False)
    print(f"Wrote {out} (n={len(icc)} seed={args.seed})")
    print(icc["stratum"].value_counts().to_string())


if __name__ == "__main__":
    main()
