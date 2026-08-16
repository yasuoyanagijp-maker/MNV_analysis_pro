#!/usr/bin/env python3
"""Unit tests for the triad (G1 × G2 × final reader) median resolver."""

from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.utils.recheck_md_parser import RecheckTarget  # noqa: E402
from src.utils.triad_median_resolver import (  # noqa: E402
    NEEDS_REVIEW_COL,
    RPD_REVIEW_THRESHOLD_PCT,
    cv_percent,
    resolve_cell,
    resolve_triad_recheck,
    triad_median,
)
from tools.reading_center_rpd.compute_adopted_from_dual_csv import (  # noqa: E402
    DEFAULT_RPD_PCT,
)


class TestThresholdReuse(unittest.TestCase):
    def test_review_threshold_is_existing_adoption_threshold(self):
        self.assertEqual(RPD_REVIEW_THRESHOLD_PCT, DEFAULT_RPD_PCT)
        self.assertEqual(RPD_REVIEW_THRESHOLD_PCT, 20.0)


class TestTriadMath(unittest.TestCase):
    def test_median_of_three(self):
        self.assertEqual(triad_median([1.0, 3.0, 2.0]), 2.0)

    def test_median_robust_to_final_reader_outlier(self):
        # Final reader wildly off — median stays between G1/G2
        self.assertEqual(triad_median([1.0, 1.2, 99.0]), 1.2)

    def test_median_of_two_when_one_missing(self):
        self.assertEqual(triad_median([1.0, None, 2.0]), 1.5)

    def test_cv_percent(self):
        # values 1,2,3: mean=2, sd(ddof=1)=1 → CV=50%
        self.assertAlmostEqual(cv_percent([1.0, 2.0, 3.0]), 50.0)
        self.assertIsNone(cv_percent([1.0, None, None]))
        self.assertIsNone(cv_percent([1.0, -1.0]))  # mean ~0 → undefined


class TestResolveCell(unittest.TestCase):
    def test_concordant_triad_no_review(self):
        cell = resolve_cell(1.0, 1.1, 1.05)
        self.assertEqual(cell["status"], "OK")
        self.assertEqual(cell["final_value"], 1.05)
        self.assertFalse(cell["needs_review"])
        self.assertEqual(cell["n_values"], 3)
        self.assertIsNotNone(cell["cv_percent"])

    def test_final_reader_far_from_median_sets_review_but_keeps_value(self):
        # median(1.0, 1.1, 3.0) = 1.1; RPD(1.1, 3.0) ≈ 92.7% > 20%
        cell = resolve_cell(1.0, 1.1, 3.0)
        self.assertEqual(cell["status"], "OK")
        self.assertEqual(cell["final_value"], 1.1)
        self.assertTrue(cell["needs_review"])

    def test_missing_final_reader_is_unresolved(self):
        cell = resolve_cell(1.0, 1.1, None)
        self.assertEqual(cell["status"], "UNRESOLVED")
        self.assertIsNone(cell["final_value"])
        self.assertFalse(cell["needs_review"])

    def test_missing_one_grader_uses_median_of_two(self):
        cell = resolve_cell(None, 2.0, 2.2)
        self.assertEqual(cell["status"], "OK")
        self.assertAlmostEqual(cell["final_value"], 2.1)
        self.assertEqual(cell["n_values"], 2)

    def test_missing_both_graders_unresolved(self):
        cell = resolve_cell(None, None, 2.0)
        self.assertEqual(cell["status"], "UNRESOLVED")


def _write_csv(path: Path, fieldnames, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _read_csv(path: Path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), [dict(r) for r in reader]


class TestResolveTriadRecheckEndToEnd(unittest.TestCase):
    def _build_inputs(self, d: Path):
        prefix = "itest"
        recheck_csv = d / f"{prefix}_recheck_list.csv"
        adopted_csv = d / f"{prefix}_adopted_values.csv"
        fr_csv = d / "MNV_final_reader.csv"

        _write_csv(
            recheck_csv,
            [
                "File", "Metric", "FirstGrader", "SecondReader",
                "Value_grader1", "Value_reader2", "RPD_pct", "Adopted", "Rule",
            ],
            [
                {
                    "File": "102-001_Week04.png",
                    "Metric": "Vsl Area (mm2)",
                    "Value_grader1": "1.0",
                    "Value_reader2": "1.6",
                    "Adopted": "NA",
                    "Rule": "RPD>20%",
                },
                {
                    "File": "102-002_Week04.png",
                    "Metric": "MNV Area (mm2)",
                    "Value_grader1": "2.0",
                    "Value_reader2": "",
                    "Adopted": "NA",
                    "Rule": "MISSING",
                },
            ],
        )
        _write_csv(
            adopted_csv,
            ["ID", "File", "Analyst", "Vsl Area (mm2)", "MNV Area (mm2)", "Tortuosity"],
            [
                {
                    "ID": "1",
                    "File": "102-001_Week04.png",
                    "Analyst": "Dual-read mean (RPD<=20%; else NA)",
                    "Vsl Area (mm2)": "NA",
                    "MNV Area (mm2)": "1.5",
                    "Tortuosity": "1.11",
                },
                {
                    "ID": "2",
                    "File": "102-002_Week04.png",
                    "Analyst": "Dual-read mean (RPD<=20%; else NA)",
                    "Vsl Area (mm2)": "0.9",
                    "MNV Area (mm2)": "NA",
                    "Tortuosity": "1.22",
                },
            ],
        )
        # Final reader re-read BOTH images; Tortuosity is present but NOT a
        # recheck target — it must never touch the adopted values.
        _write_csv(
            fr_csv,
            ["ID", "File", "Vsl Area (mm2)", "MNV Area (mm2)", "Tortuosity"],
            [
                {
                    "ID": "1",
                    "File": "102-001_Week04.png",
                    "Vsl Area (mm2)": "1.1",
                    "MNV Area (mm2)": "9.9",
                    "Tortuosity": "9.9",
                },
                {
                    "ID": "2",
                    "File": "102-002_Week04.png",
                    "Vsl Area (mm2)": "9.9",
                    "MNV Area (mm2)": "2.4",
                    "Tortuosity": "9.9",
                },
            ],
        )
        targets = [
            RecheckTarget(
                image_file="102-001_Week04.png",
                image_stem="102-001_week04",
                display_name="Vsl Area (mm2)",
                column="Vsl Area (mm2)",
            ),
            RecheckTarget(
                image_file="102-002_Week04.png",
                image_stem="102-002_week04",
                display_name="MNV Area (mm2)",
                column="MNV Area (mm2)",
            ),
        ]
        return prefix, recheck_csv, adopted_csv, fr_csv, targets

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            prefix, recheck_csv, adopted_csv, fr_csv, targets = self._build_inputs(d)
            summary = resolve_triad_recheck(
                targets,
                recheck_csv=recheck_csv,
                adopted_csv=adopted_csv,
                final_reader_csv=fr_csv,
                out_dir=d,
                prefix=prefix,
                dry_run=True,
            )
            self.assertTrue(summary["dry_run"])
            self.assertEqual(summary["n_resolved"], 2)
            self.assertFalse(Path(summary["triad_cells_csv"]).exists())
            self.assertFalse(Path(summary["triad_adopted_csv"]).exists())
            self.assertFalse(Path(summary["triad_summary_md"]).exists())

    def test_commit_writes_only_designated_cells(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            prefix, recheck_csv, adopted_csv, fr_csv, targets = self._build_inputs(d)
            summary = resolve_triad_recheck(
                targets,
                recheck_csv=recheck_csv,
                adopted_csv=adopted_csv,
                final_reader_csv=fr_csv,
                out_dir=d,
                prefix=prefix,
                dry_run=False,
            )
            self.assertEqual(summary["n_resolved"], 2)
            self.assertEqual(summary["n_cells_applied"], 2)

            # cell 1: median(1.0, 1.6, 1.1) = 1.1; RPD(1.1, 1.1)=0 → no review
            rec1 = summary["records"][0]
            self.assertEqual(rec1["final_value"], "1.1")
            self.assertEqual(rec1["needs_review"], "false")
            self.assertNotEqual(rec1["cv_percent"], "")

            # cell 2: G2 missing → median(2.0, 2.4) = 2.2;
            # RPD(2.2, 2.4) ≈ 8.7% ≤ 20 → no review
            rec2 = summary["records"][1]
            self.assertEqual(rec2["final_value"], "2.2")
            self.assertEqual(rec2["needs_review"], "false")
            self.assertEqual(rec2["n_values"], 2)

            # adopted output: only the two designated cells changed
            fields, rows = _read_csv(Path(summary["triad_adopted_csv"]))
            self.assertIn(NEEDS_REVIEW_COL, fields)
            by_file = {r["File"]: r for r in rows}
            r1 = by_file["102-001_Week04.png"]
            r2 = by_file["102-002_Week04.png"]
            self.assertEqual(r1["Vsl Area (mm2)"], "1.1")
            self.assertEqual(r2["MNV Area (mm2)"], "2.2")
            # Non-target cells untouched (final reader's 9.9 never leaks)
            self.assertEqual(r1["MNV Area (mm2)"], "1.5")
            self.assertEqual(r2["Vsl Area (mm2)"], "0.9")
            self.assertEqual(r1["Tortuosity"], "1.11")
            self.assertEqual(r2["Tortuosity"], "1.22")
            self.assertIn("triad median", r1["Analyst"])

            # original adopted CSV untouched
            _, orig_rows = _read_csv(adopted_csv)
            self.assertEqual(orig_rows[0]["Vsl Area (mm2)"], "NA")

            self.assertTrue(Path(summary["triad_cells_csv"]).exists())
            self.assertTrue(Path(summary["triad_summary_md"]).exists())

    def test_review_flag_set_when_final_reader_deviates(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            prefix, recheck_csv, adopted_csv, fr_csv, targets = self._build_inputs(d)
            # Overwrite FR value for cell 1 far from G1/G2:
            # median(1.0, 1.6, 30.0) = 1.6; RPD(1.6, 30.0) ≈ 179.7% > 20%
            _write_csv(
                fr_csv,
                ["ID", "File", "Vsl Area (mm2)", "MNV Area (mm2)"],
                [
                    {"ID": "1", "File": "102-001_Week04.png",
                     "Vsl Area (mm2)": "30.0", "MNV Area (mm2)": ""},
                    {"ID": "2", "File": "102-002_Week04.png",
                     "Vsl Area (mm2)": "", "MNV Area (mm2)": "2.4"},
                ],
            )
            summary = resolve_triad_recheck(
                targets,
                recheck_csv=recheck_csv,
                adopted_csv=adopted_csv,
                final_reader_csv=fr_csv,
                out_dir=d,
                prefix=prefix,
                dry_run=False,
            )
            rec1 = summary["records"][0]
            self.assertEqual(rec1["needs_review"], "true")
            # Value still adopted (median), processing not blocked
            self.assertEqual(rec1["final_value"], "1.6")
            self.assertEqual(summary["n_needs_review"], 1)

            _, rows = _read_csv(Path(summary["triad_adopted_csv"]))
            by_file = {r["File"]: r for r in rows}
            self.assertEqual(
                by_file["102-001_Week04.png"][NEEDS_REVIEW_COL], "Vsl Area (mm2)"
            )
            self.assertEqual(by_file["102-002_Week04.png"][NEEDS_REVIEW_COL], "")

    def test_unresolved_when_final_reader_row_missing(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            prefix, recheck_csv, adopted_csv, fr_csv, targets = self._build_inputs(d)
            _write_csv(
                fr_csv,
                ["ID", "File", "Vsl Area (mm2)"],
                [{"ID": "1", "File": "102-001_Week04.png", "Vsl Area (mm2)": "1.1"}],
            )
            summary = resolve_triad_recheck(
                targets,
                recheck_csv=recheck_csv,
                adopted_csv=adopted_csv,
                final_reader_csv=fr_csv,
                out_dir=d,
                prefix=prefix,
                dry_run=False,
            )
            self.assertEqual(summary["n_resolved"], 1)
            self.assertEqual(summary["n_unresolved"], 1)
            # Unresolved cell keeps NA in the triad adopted CSV
            _, rows = _read_csv(Path(summary["triad_adopted_csv"]))
            by_file = {r["File"]: r for r in rows}
            self.assertEqual(by_file["102-002_Week04.png"]["MNV Area (mm2)"], "NA")


class TestSummaryMdRoundTrip(unittest.TestCase):
    def test_merge_summary_md_parses_back_into_targets(self):
        """dual_grader_merge summary → recheck_md_parser round trip."""
        from src.utils.dual_grader_merge import _render_summary_md
        from src.utils.recheck_md_parser import parse_recheck_md_text

        s = {
            "first_csv": "a.csv",
            "second_csv": "b.csv",
            "threshold_pct": 20.0,
            "n_matched": 3,
            "n_first_only": 0,
            "n_second_only": 0,
            "first_only": [],
            "second_only": [],
            "recheck_cells": 3,
            "recheck_files": 2,
            "recheck_by_metric": {
                "Vsl Area (mm2)": 1,
                "MNV Area (mm2)": 1,
                "Caliber Uniformity Score (U2)": 1,
            },
            "recheck_by_file": {
                "102-001_Week04.png": ["Vsl Area (mm2)"],
                "102-002_Week04.png": [
                    "MNV Area (mm2)",
                    "Caliber Uniformity Score (U2)",
                ],
            },
            "warnings": [],
        }
        md = _render_summary_md(s)
        res = parse_recheck_md_text(md)
        self.assertEqual(res.declared_cells, 3)
        self.assertEqual(res.declared_cases, 2)
        self.assertEqual(len(res.targets), 3)
        self.assertEqual(res.warnings, [])
        self.assertEqual(
            {(t.image_stem, t.column) for t in res.targets},
            {
                ("102-001_week04", "Vsl Area (mm2)"),
                ("102-002_week04", "MNV Area (mm2)"),
                # "(U2)" notation canonicalizes to the bare default column
                ("102-002_week04", "Caliber Uniformity Score"),
            },
        )


class TestColumnNameEquivalence(unittest.TestCase):
    """Bare / "(U2)" / "Standardized" Caliber notations must interoperate.

    App batch CSVs (PR #10+) hold the U2 values in the bare default columns,
    while the reading-center CLI writes "... (U2)" columns. A recheck list
    written by one build must resolve against CSVs written by another.
    """

    def test_u2_recheck_metric_resolves_against_bare_columns(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            prefix = "xcompat"
            recheck_csv = d / f"{prefix}_recheck_list.csv"
            adopted_csv = d / f"{prefix}_adopted_values.csv"
            fr_csv = d / "MNV_final_reader.csv"

            # CLI-style recheck list: Metric uses the "(U2)" notation
            _write_csv(
                recheck_csv,
                ["File", "Metric", "Value_grader1", "Value_reader2"],
                [
                    {
                        "File": "102-001_Week04.png",
                        "Metric": "Caliber Uniformity Score (U2)",
                        "Value_grader1": "50.0",
                        "Value_reader2": "80.0",
                    }
                ],
            )
            # App-style adopted CSV / final-reader CSV: bare default column
            _write_csv(
                adopted_csv,
                ["ID", "File", "Analyst", "Caliber Uniformity Score"],
                [
                    {
                        "ID": "1",
                        "File": "102-001_Week04.png",
                        "Analyst": "Dual-read mean (RPD<=20%; else NA)",
                        "Caliber Uniformity Score": "NA",
                    }
                ],
            )
            _write_csv(
                fr_csv,
                ["ID", "File", "Caliber Uniformity Score"],
                [
                    {
                        "ID": "1",
                        "File": "102-001_Week04.png",
                        "Caliber Uniformity Score": "60.0",
                    }
                ],
            )
            # MD written with the "(U2)" notation → canonical bare column
            targets = [
                RecheckTarget(
                    image_file="102-001_Week04.png",
                    image_stem="102-001_week04",
                    display_name="Caliber Uniformity Score (U2)",
                    column="Caliber Uniformity Score",
                )
            ]
            summary = resolve_triad_recheck(
                targets,
                recheck_csv=recheck_csv,
                adopted_csv=adopted_csv,
                final_reader_csv=fr_csv,
                out_dir=d,
                prefix=prefix,
                dry_run=False,
            )
            self.assertEqual(summary["n_resolved"], 1)
            self.assertEqual(summary["n_cells_applied"], 1)
            rec = summary["records"][0]
            # median(50, 80, 60) = 60
            self.assertEqual(rec["final_value"], "60")
            _, rows = _read_csv(Path(summary["triad_adopted_csv"]))
            self.assertEqual(rows[0]["Caliber Uniformity Score"], "60")


if __name__ == "__main__":
    unittest.main()
