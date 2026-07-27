#!/usr/bin/env python3
"""Interactive ICC Session 2 recorder for YY (chat-driven).

IMPORTANT: --next does NOT show Session 1 scores (avoid anchoring before ROI).

Usage:
  .venv/bin/python scripts/graefe_revision/interactive_icc_s2.py --status
  .venv/bin/python scripts/graefe_revision/interactive_icc_s2.py --next
  .venv/bin/python scripts/graefe_revision/interactive_icc_s2.py --set ICC01 \\
      --uuid <run-uuid> --complexity 45.2 --caliber 60.1 --maturity 55.0 --area 1.2
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
ICC_DIR = REPO_ROOT / "documentation" / "graefe_revision" / "icc"
CASE_LIST = ICC_DIR / "icc_case_list.csv"
SESSION1 = ICC_DIR / "icc_session1.csv"
SESSION2 = ICC_DIR / "icc_session2.csv"
MANIFEST = ICC_DIR / "icc_session2_manifest.csv"

TOTAL_EXPECTED = 30

FOV_HINT = {
    "large": "6mm",
    "small": "6mm",
    "small_3mm": "3mm",
}


def _load_s2() -> pd.DataFrame:
    return pd.read_csv(SESSION2, dtype=str).fillna("")


def _load_s1() -> pd.DataFrame:
    """Load Session1 for integrity / post-ROI compare only — never print in --next."""
    if not SESSION1.is_file():
        raise SystemExit(f"Missing Session1 file: {SESSION1}")
    return pd.read_csv(SESSION1, dtype=str).fillna("")


def _load_cases() -> pd.DataFrame:
    return pd.read_csv(CASE_LIST, dtype=str).fillna("")


def _is_done(row: pd.Series) -> bool:
    """Session2 row is complete when all four metrics are filled."""
    for col in ("Network Complexity", "Caliber Uniformity", "Maturity", "MNV Area"):
        if not str(row.get(col, "")).strip():
            return False
    return True


def _progress(s2: pd.DataFrame) -> tuple[int, int]:
    n = len(s2)
    done = int(s2.apply(_is_done, axis=1).sum())
    return done, n


def _next_pending(s2: pd.DataFrame) -> pd.Series | None:
    for _, row in s2.iterrows():
        if not _is_done(row):
            return row
    return None


def _fov_hint(stratum: str) -> str:
    return FOV_HINT.get(stratum, "check stratum")


def cmd_status(s2: pd.DataFrame) -> None:
    done, n = _progress(s2)
    print(f"Progress: {done}/{n}" + (f" (expected {TOTAL_EXPECTED})" if n != TOTAL_EXPECTED else ""))
    if done >= n and n > 0:
        _print_completion_reminder()
    else:
        nxt = _next_pending(s2)
        if nxt is not None:
            print(f"Next: {nxt['icc_id']}")


def cmd_next(s2: pd.DataFrame, cases: pd.DataFrame) -> None:
    nxt = _next_pending(s2)
    if nxt is None:
        done, n = _progress(s2)
        print(f"All {n} Session2 cases recorded ({done}/{n}).")
        _print_completion_reminder()
        return

    icc_id = nxt["icc_id"]
    case = cases.loc[cases["icc_id"] == icc_id]
    if case.empty:
        image_path = ""
        stratum = nxt.get("stratum", "")
    else:
        crow = case.iloc[0]
        image_path = crow["image_path"]
        stratum = crow["stratum"]

    done, n = _progress(s2)
    fov = _fov_hint(stratum)
    print(f"icc_id: {icc_id}")
    print(f"stratum: {stratum}")
    print(f"FOV hint: {fov}  (large/small → 6mm; small_3mm → 3mm)")
    print(f"file_name: {nxt.get('file_name', '')}")
    print(f"image_path: {image_path}")
    print(f"image_exists: {Path(image_path).is_file() if image_path else False}")
    print(f"progress: {done}/{n}")
    print()
    print("Session1 scores are intentionally HIDDEN until after ROI (no anchoring).")
    print()
    print("--- Flet Session2 steps ---")
    print("1. Launch: ./run_flet.sh")
    print(f"2. Open image: {image_path}")
    print(f"3. Set scale to {fov}; draw a NEW freehand ROI (do not reload prior ROI).")
    print("4. Run fully automated processing (unchanged parameters).")
    print("5. Record metrics with --set (uuid = output/mnv/<uuid>/).")
    print(
        f"   .venv/bin/python scripts/graefe_revision/interactive_icc_s2.py --set {icc_id} "
        "--uuid <UUID> --complexity <NC> --caliber <CU> --maturity <MI> --area <AREA>"
    )


def cmd_set(
    s2: pd.DataFrame,
    icc_id: str,
    uuid: str,
    complexity: str,
    caliber: str,
    maturity: str,
    area: str,
    notes: str | None,
    output_path: str | None,
) -> None:
    idx = s2.index[s2["icc_id"] == icc_id]
    if len(idx) == 0:
        raise SystemExit(f"Unknown icc_id: {icc_id}")
    i = idx[0]
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = output_path or str(REPO_ROOT / "output" / "mnv" / uuid)

    s2.at[i, "Network Complexity"] = str(complexity)
    s2.at[i, "Caliber Uniformity"] = str(caliber)
    s2.at[i, "Maturity"] = str(maturity)
    s2.at[i, "MNV Area"] = str(area)
    s2.at[i, "uuid"] = uuid
    s2.at[i, "output_path"] = out
    s2.at[i, "session2_timestamp"] = ts
    if notes is not None:
        s2.at[i, "notes"] = notes
    s2.to_csv(SESSION2, index=False)

    # Mirror done flag in manifest if present
    if MANIFEST.is_file():
        man = pd.read_csv(MANIFEST, dtype=str).fillna("")
        midx = man.index[man["icc_id"] == icc_id]
        if len(midx):
            mi = midx[0]
            man.at[mi, "uuid"] = uuid
            man.at[mi, "output_path"] = out
            man.at[mi, "session2_done"] = "True"
            man.at[mi, "session2_timestamp"] = ts
            if notes is not None:
                man.at[mi, "notes"] = notes
            man.to_csv(MANIFEST, index=False)

    print(f"recorded: {icc_id}")
    print(f"  NC={complexity}  CU={caliber}  Maturity={maturity}  Area={area}")
    print(f"  uuid={uuid}")
    print(f"  output_path={out}")
    done, n = _progress(s2)
    print(f"progress: {done}/{n}")
    if done >= n:
        _print_completion_reminder()
    else:
        nxt = _next_pending(s2)
        if nxt is not None:
            print(f"next: {nxt['icc_id']}")


def _print_completion_reminder() -> None:
    print()
    print("=== ALL 30 SESSION2 RECORDED ===")
    print("1. Lock icc_session2.csv.")
    print("2. Compute ICC:")
    print("   .venv/bin/python scripts/graefe_revision/compute_icc.py")


def cmd_show_s1(s1: pd.DataFrame, s2: pd.DataFrame, icc_id: str) -> None:
    """Show Session1 only after that case's Session2 is recorded (anti-anchoring)."""
    s2row = s2.loc[s2["icc_id"] == icc_id]
    if s2row.empty:
        raise SystemExit(f"Unknown icc_id: {icc_id}")
    if not _is_done(s2row.iloc[0]):
        raise SystemExit(
            f"{icc_id}: Session2 not yet recorded — refusing to show Session1 "
            "(complete ROI + --set first)."
        )
    s1row = s1.loc[s1["icc_id"] == icc_id]
    if s1row.empty:
        raise SystemExit(f"No Session1 row for {icc_id}")
    r = s1row.iloc[0]
    print(f"Session1 ({icc_id}) — for post-ROI reference only:")
    print(f"  Network Complexity: {r['Network Complexity']}")
    print(f"  Caliber Uniformity: {r['Caliber Uniformity']}")
    print(f"  Maturity: {r['Maturity']}")
    print(f"  MNV Area: {r['MNV Area']}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--next", action="store_true", help="Next pending case (no S1 scores)")
    parser.add_argument("--set", metavar="ICC_ID", help="Record Session2 metrics for this icc_id")
    parser.add_argument(
        "--show-s1",
        metavar="ICC_ID",
        help="Show Session1 scores ONLY if that case's Session2 is already filled",
    )
    parser.add_argument("--uuid", type=str, default=None)
    parser.add_argument("--complexity", type=str, default=None, help="Network Complexity")
    parser.add_argument("--caliber", type=str, default=None, help="Caliber Uniformity")
    parser.add_argument("--maturity", type=str, default=None, help="Maturity Index")
    parser.add_argument("--area", type=str, default=None, help="MNV Area")
    parser.add_argument("--output-path", type=str, default=None)
    parser.add_argument("--notes", type=str, default=None)
    args = parser.parse_args()

    if not any([args.status, args.next, args.set, args.show_s1]):
        parser.print_help()
        sys.exit(1)

    s2 = _load_s2()
    s1 = _load_s1()  # integrity; scores never shown via --next
    cases = _load_cases()

    if args.status:
        cmd_status(s2)
    if args.next:
        cmd_next(s2, cases)
    if args.set:
        missing = [
            name
            for name, val in (
                ("--uuid", args.uuid),
                ("--complexity", args.complexity),
                ("--caliber", args.caliber),
                ("--maturity", args.maturity),
                ("--area", args.area),
            )
            if val is None
        ]
        if missing:
            raise SystemExit(f"--set requires: {', '.join(missing)}")
        cmd_set(
            s2,
            args.set,
            args.uuid,
            args.complexity,
            args.caliber,
            args.maturity,
            args.area,
            args.notes,
            args.output_path,
        )
        s2 = _load_s2()  # refresh after write
    if args.show_s1:
        cmd_show_s1(s1, s2, args.show_s1)


if __name__ == "__main__":
    main()
