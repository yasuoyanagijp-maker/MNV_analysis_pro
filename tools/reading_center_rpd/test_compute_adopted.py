#!/usr/bin/env python3
"""Unit tests for dual-CSV adoption helpers (Bugbot follow-ups)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.reading_center_rpd.compute_adopted_from_dual_csv import (
    MAJOR_METRICS,
    adopt_pair,
    build_outputs,
    normalize_visit,
    read_csv,
)


class TestNormalizeVisit(unittest.TestCase):
    def test_zero_pads_week_and_month(self):
        self.assertEqual(normalize_visit("Week01"), "Week01")
        self.assertEqual(normalize_visit("Week1"), "Week01")
        self.assertEqual(normalize_visit("W4"), "Week04")
        self.assertEqual(normalize_visit("Week12"), "Week12")
        self.assertEqual(normalize_visit("Baseline"), "Baseline")
        self.assertEqual(normalize_visit("M1"), "M01")

    def test_week_sort_order(self):
        visits = [normalize_visit(v) for v in ("Week12", "Week4", "Week8", "Week1")]
        self.assertEqual(sorted(visits), ["Week01", "Week04", "Week08", "Week12"])


class TestMissingMajorRecheck(unittest.TestCase):
    def test_adopt_pair_missing(self):
        val, status, rpd = adopt_pair(None, 1.0, 20.0)
        self.assertEqual(val, "NA")
        self.assertEqual(status, "MISSING")
        self.assertEqual(rpd, "NA")

    def test_missing_major_appears_on_recheck_list(self):
        fieldnames = ["ID", "File", "Analyst"] + list(MAJOR_METRICS)
        site = {
            "ID": "102-001",
            "File": "102-001_Week01.png",
            "Analyst": "site",
            **{m: "1.0" for m in MAJOR_METRICS},
        }
        reader2 = {
            "ID": "102-001",
            "File": "102-001_Week01.png",
            "Analyst": "reader2",
            **{m: "1.0" for m in MAJOR_METRICS},
        }
        # Blank one major endpoint on reader2 → MISSING
        reader2["MNV Area (mm2)"] = ""

        adopted, recheck, summary = build_outputs(
            site_rows=[site],
            reader2_rows=[reader2],
            fieldnames=fieldnames,
            threshold=20.0,
            site_label="site",
            reader2_label="reader2",
            match_kwargs=dict(case_col=None, visit_col=None, case_regex=None),
        )
        self.assertEqual(len(adopted), 1)
        self.assertEqual(adopted[0]["_Visit_needs_recheck"], "YES")
        missing = [r for r in recheck if r["Rule"] == "MISSING"]
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0]["Metric"], "MNV Area (mm2)")
        self.assertEqual(missing[0]["Visit"], "Week01")
        self.assertGreaterEqual(summary["major_recheck_cells"], 1)
        self.assertEqual(summary["visits_recheck"], 1)


class TestReadCsvNoSystemExit(unittest.TestCase):
    def test_empty_header_raises_value_error(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "empty.csv"
            path.write_text("", encoding="utf-8")
            with self.assertRaises(ValueError):
                read_csv(path)


if __name__ == "__main__":
    unittest.main()
