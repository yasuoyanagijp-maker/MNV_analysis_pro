#!/usr/bin/env python3
"""Interactive blind grading recorder for YY (chat-driven).

NEVER reads automated_labels.csv / grading_subset_meta.csv.

Usage:
  .venv/bin/python scripts/graefe_revision/interactive_grade.py --status
  .venv/bin/python scripts/graefe_revision/interactive_grade.py --next
  .venv/bin/python scripts/graefe_revision/interactive_grade.py --next --open
  .venv/bin/python scripts/graefe_revision/interactive_grade.py --set B001 "Glomerular"
  .venv/bin/python scripts/graefe_revision/interactive_grade.py --set B001 "Tree in bud" --notes "borderline"
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
GRADING_DIR = REPO_ROOT / "documentation" / "graefe_revision" / "grading"
GRADES = GRADING_DIR / "expert_grades_blind.csv"
MANIFEST = GRADING_DIR / "grading_manifest.csv"

ALLOWED_SUBTYPES = (
    "Dead tree",
    "Tree in bud",
    "Glomerular",
    "Seafan",
    "Medusa",
)
# Case-insensitive lookup → canonical spelling
_SUBTYPE_MAP = {s.casefold(): s for s in ALLOWED_SUBTYPES}

TOTAL_EXPECTED = 54


def _load() -> tuple[pd.DataFrame, pd.DataFrame]:
    grades = pd.read_csv(GRADES, dtype=str).fillna("")
    manifest = pd.read_csv(MANIFEST, dtype=str).fillna("")
    return grades, manifest


def _is_graded(subtype: str) -> bool:
    return bool(str(subtype).strip())


def _progress(grades: pd.DataFrame) -> tuple[int, int]:
    n = len(grades)
    done = int(grades["expert_subtype"].map(_is_graded).sum())
    return done, n


def _next_ungraded(grades: pd.DataFrame) -> pd.Series | None:
    for _, row in grades.iterrows():
        if not _is_graded(row.get("expert_subtype", "")):
            return row
    return None


def _resolve_case(
    blind_id: str, grades: pd.DataFrame, manifest: pd.DataFrame
) -> tuple[pd.Series, pd.Series]:
    g = grades.loc[grades["blind_id"] == blind_id]
    if g.empty:
        raise SystemExit(f"Unknown blind_id: {blind_id}")
    m = manifest.loc[manifest["blind_id"] == blind_id]
    if m.empty:
        raise SystemExit(f"No manifest row for {blind_id}")
    return g.iloc[0], m.iloc[0]


def _normalize_subtype(raw: str) -> str:
    key = raw.strip().casefold()
    if key not in _SUBTYPE_MAP:
        allowed = ", ".join(f'"{s}"' for s in ALLOWED_SUBTYPES)
        raise SystemExit(f"Invalid subtype {raw!r}. Allowed: {allowed}")
    return _SUBTYPE_MAP[key]


def cmd_status(grades: pd.DataFrame) -> None:
    done, n = _progress(grades)
    print(f"Progress: {done}/{n}" + (f" (expected {TOTAL_EXPECTED})" if n != TOTAL_EXPECTED else ""))
    if done >= n and n > 0:
        _print_completion_reminder()
    else:
        nxt = _next_ungraded(grades)
        if nxt is not None:
            print(f"Next: {nxt['blind_id']}")


def cmd_next(grades: pd.DataFrame, manifest: pd.DataFrame, do_open: bool) -> None:
    nxt = _next_ungraded(grades)
    if nxt is None:
        done, n = _progress(grades)
        print(f"All {n} cases graded ({done}/{n}).")
        _print_completion_reminder()
        return

    blind_id = nxt["blind_id"]
    _, mrow = _resolve_case(blind_id, grades, manifest)
    image_path = Path(mrow["image_path"])
    done, n = _progress(grades)
    print(f"blind_id: {blind_id}")
    print(f"stratum: {mrow['stratum']}")
    print(f"file_name: {mrow['file_name']}")
    print(f"image_path: {image_path}")
    print(f"image_exists: {image_path.is_file()}")
    print(f"progress: {done}/{n}")
    print(f"allowed_subtypes: {', '.join(ALLOWED_SUBTYPES)}")
    if do_open:
        _open_image(image_path)


def cmd_set(
    grades: pd.DataFrame,
    blind_id: str,
    subtype_raw: str,
    notes: str | None,
) -> None:
    subtype = _normalize_subtype(subtype_raw)
    idx = grades.index[grades["blind_id"] == blind_id]
    if len(idx) == 0:
        raise SystemExit(f"Unknown blind_id: {blind_id}")
    i = idx[0]
    prev = str(grades.at[i, "expert_subtype"]).strip()
    grades.at[i, "expert_subtype"] = subtype
    grades.at[i, "grader"] = grades.at[i, "grader"] or "YY"
    grades.at[i, "graded_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if notes is not None:
        grades.at[i, "notes"] = notes
    grades.to_csv(GRADES, index=False)
    action = "updated" if prev else "recorded"
    print(f"{action}: {blind_id} -> {subtype}")
    done, n = _progress(grades)
    print(f"progress: {done}/{n}")
    if done >= n:
        _print_completion_reminder()
    else:
        nxt = _next_ungraded(grades)
        if nxt is not None:
            print(f"next: {nxt['blind_id']}")


def cmd_open(grades: pd.DataFrame, manifest: pd.DataFrame, blind_id: str | None) -> None:
    if blind_id is None:
        nxt = _next_ungraded(grades)
        if nxt is None:
            print("Nothing to open — all graded.")
            return
        blind_id = nxt["blind_id"]
    _, mrow = _resolve_case(blind_id, grades, manifest)
    image_path = Path(mrow["image_path"])
    print(f"Opening {blind_id}: {image_path}")
    _open_image(image_path)


def _open_image(path: Path) -> None:
    if not path.is_file():
        raise SystemExit(f"Image missing: {path}")
    subprocess.run(["open", str(path)], check=False)


def _print_completion_reminder() -> None:
    print()
    print("=== ALL 54 GRADED ===")
    print("1. Lock expert_grades_blind.csv (do not edit further).")
    print("2. Run agreement (unblinds vs automated labels):")
    print("   .venv/bin/python scripts/graefe_revision/compute_agreement.py")
    print("Do NOT open automated_labels.csv until locked.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--status", action="store_true", help="Show progress N/54")
    parser.add_argument("--next", action="store_true", help="Print next ungraded case")
    parser.add_argument(
        "--set",
        nargs=2,
        metavar=("BLIND_ID", "SUBTYPE"),
        help='Record subtype, e.g. --set B001 "Glomerular"',
    )
    parser.add_argument("--notes", type=str, default=None, help="Optional notes with --set")
    parser.add_argument(
        "--open",
        action="store_true",
        help="Open image (with --next, or alone for next case)",
    )
    parser.add_argument(
        "--blind-id",
        type=str,
        default=None,
        help="With --open alone: open this blind_id instead of next",
    )
    args = parser.parse_args()

    if not any([args.status, args.next, args.set, args.open]):
        parser.print_help()
        sys.exit(1)

    grades, manifest = _load()

    if args.status:
        cmd_status(grades)
    if args.next:
        cmd_next(grades, manifest, do_open=args.open and not args.set)
    if args.set:
        cmd_set(grades, args.set[0], args.set[1], args.notes)
    if args.open and not args.next:
        cmd_open(grades, manifest, args.blind_id)


if __name__ == "__main__":
    main()
