#!/usr/bin/env python3
"""Extract ICC Session 1 scores from prior batch CSVs (primary) for icc_case_list.csv.

Maps each ICC case (stratum + file_name) to Network Complexity, Caliber Uniformity,
Maturity Index, and MNV Area from the recovered 1e5d202 batch CSVs under
documentation/graefe_revision/data/. Session JSON is used only as a presence check
fallback note (scores themselves live in the CSVs).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "documentation" / "graefe_revision" / "data"
ICC_DIR = REPO_ROOT / "documentation" / "graefe_revision" / "icc"
SESSION_JSON = REPO_ROOT / "output" / "reference_build_session.json"

CSV_MAP = {
    "large": "MNV_batch_20260220_230245_large.csv",
    "small": "MNV_batch_20260220_083448small.csv",
    "small_3mm": "MNV_batch_20260220_223647_small_3mm.csv",
}

SCORE_COLS = [
    "Network Complexity Score",
    "Caliber Uniformity Score",
    "Maturity Index",
    "MNV Area (mm2)",
]


def _read_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [str(c).lstrip("\ufeff") for c in df.columns]
    return df


def build_lookup(data_dir: Path) -> dict[tuple[str, str], dict]:
    lookup: dict[tuple[str, str], dict] = {}
    for stratum, fname in CSV_MAP.items():
        path = data_dir / fname
        df = _read_csv(path)
        missing = [c for c in ["File", *SCORE_COLS] if c not in df.columns]
        if missing:
            raise KeyError(f"{fname}: missing columns {missing}")
        for _, row in df.iterrows():
            key = (stratum, str(row["File"]))
            lookup[key] = {
                "Network Complexity": float(row["Network Complexity Score"]),
                "Caliber Uniformity": float(row["Caliber Uniformity Score"]),
                "Maturity": float(row["Maturity Index"]),
                "MNV Area": float(row["MNV Area (mm2)"]),
                "source_file": fname,
            }
    return lookup


def extract_session1(
    case_list: pd.DataFrame,
    lookup: dict[tuple[str, str], dict],
    session_keys: set[str] | None = None,
) -> pd.DataFrame:
    rows = []
    for _, case in case_list.iterrows():
        stratum = str(case["stratum"])
        file_name = str(case["file_name"])
        case_key = str(case.get("case_key", f"{stratum}/{file_name}"))
        hit = lookup.get((stratum, file_name))
        in_session = (
            None if session_keys is None else (case_key in session_keys)
        )
        if hit is None:
            rows.append(
                {
                    "icc_id": case["icc_id"],
                    "stratum": stratum,
                    "image_key": case_key,
                    "file_name": file_name,
                    "Network Complexity": None,
                    "Caliber Uniformity": None,
                    "Maturity": None,
                    "MNV Area": None,
                    "source_file": "",
                    "match_status": "not_found",
                    "in_session_json": in_session,
                }
            )
            continue
        rows.append(
            {
                "icc_id": case["icc_id"],
                "stratum": stratum,
                "image_key": case_key,
                "file_name": file_name,
                "Network Complexity": hit["Network Complexity"],
                "Caliber Uniformity": hit["Caliber Uniformity"],
                "Maturity": hit["Maturity"],
                "MNV Area": hit["MNV Area"],
                "source_file": hit["source_file"],
                "match_status": "matched_csv",
                "in_session_json": in_session,
            }
        )
    return pd.DataFrame(rows)


def write_session2_templates(out_dir: Path, session1: pd.DataFrame) -> None:
    """Empty Session 2 score template + run manifest for Flet recording."""
    s2 = session1[
        ["icc_id", "stratum", "image_key", "file_name"]
    ].copy()
    for col in [
        "Network Complexity",
        "Caliber Uniformity",
        "Maturity",
        "MNV Area",
    ]:
        s2[col] = ""
    s2["uuid"] = ""
    s2["output_path"] = ""
    s2["session2_timestamp"] = ""
    s2["notes"] = ""
    s2_path = out_dir / "icc_session2.csv"
    s2.to_csv(s2_path, index=False)

    manifest = session1[["icc_id", "stratum", "image_key", "file_name"]].copy()
    # Prefer paths from case list if present upstream; leave blank for fill-in
    case_list_path = out_dir / "icc_case_list.csv"
    if case_list_path.is_file():
        cl = pd.read_csv(case_list_path)
        if "image_path" in cl.columns:
            manifest = manifest.merge(
                cl[["icc_id", "image_path"]], on="icc_id", how="left"
            )
        else:
            manifest["image_path"] = ""
    else:
        manifest["image_path"] = ""
    manifest["uuid"] = ""
    manifest["output_path"] = ""
    manifest["session2_done"] = False
    manifest["session2_timestamp"] = ""
    manifest["notes"] = ""
    manifest_path = out_dir / "icc_session2_manifest.csv"
    manifest.to_csv(manifest_path, index=False)
    print(f"Wrote {s2_path}")
    print(f"Wrote {manifest_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--icc-dir", type=Path, default=ICC_DIR)
    parser.add_argument("--session-json", type=Path, default=SESSION_JSON)
    parser.add_argument(
        "--write-session2-templates",
        action="store_true",
        default=True,
        help="Also write empty icc_session2.csv and icc_session2_manifest.csv",
    )
    parser.add_argument(
        "--no-session2-templates",
        action="store_true",
        help="Skip writing Session 2 templates",
    )
    args = parser.parse_args()

    case_list = pd.read_csv(args.icc_dir / "icc_case_list.csv")
    lookup = build_lookup(args.data_dir)

    session_keys: set[str] | None = None
    if args.session_json.is_file():
        with open(args.session_json, encoding="utf-8") as f:
            session = json.load(f)
        session_keys = set(session.get("cases", {}).keys())

    session1 = extract_session1(case_list, lookup, session_keys)
    out = args.icc_dir / "icc_session1.csv"
    args.icc_dir.mkdir(parents=True, exist_ok=True)
    session1.to_csv(out, index=False)

    n = len(session1)
    n_ok = int((session1["match_status"] == "matched_csv").sum())
    print(f"Wrote {out}")
    print(f"Session1 match rate: {n_ok}/{n}")
    if n_ok < n:
        bad = session1.loc[session1["match_status"] != "matched_csv"]
        print("Unmatched:")
        print(bad[["icc_id", "stratum", "file_name"]].to_string(index=False))

    if args.write_session2_templates and not args.no_session2_templates:
        write_session2_templates(args.icc_dir, session1)


if __name__ == "__main__":
    main()
