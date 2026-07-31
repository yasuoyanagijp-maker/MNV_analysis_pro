#!/usr/bin/env python3
"""Unit tests for Caliber Uniformity U2 + CSV inserter."""

from __future__ import annotations

import csv
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from src.core.caliber_u2 import (  # noqa: E402
    calculate_caliber_u2_score,
    calculate_maturity_index,
    infer_size_class_from_filename,
    load_caliber_u2_device_ref,
    piecewise_scale,
)


def _load_csv_script():
    path = REPO / "tools" / "caliber_u2" / "compute_caliber_u2_from_csv.py"
    spec = importlib.util.spec_from_file_location("compute_caliber_u2_from_csv", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class TestCaliberU2(unittest.TestCase):
    def test_ref_loads(self):
        ref = load_caliber_u2_device_ref()
        self.assertIsNotNone(ref)
        self.assertIn("small_3mm", ref["strata"])

    def test_piecewise_median_is_50(self):
        scored = piecewise_scale(
            np.asarray([-47.295175835]),
            -79.119217,
            -47.295175835,
            -43.07717553,
        )
        self.assertAlmostEqual(float(scored[0]), 50.0, places=5)

    def test_u2_at_stratum_median_near_50(self):
        ref = load_caliber_u2_device_ref()
        st = ref["strata"]["small_3mm"]
        score, details = calculate_caliber_u2_score(
            st["nv_cv"]["median"],
            st["dilated_pct"]["median"],
            size_class="small_3mm",
            ref=ref,
        )
        self.assertFalse(details.get("fallback"))
        self.assertAlmostEqual(score, 50.0, places=4)

    def test_maturity_uses_caliber_minus_complexity(self):
        self.assertAlmostEqual(calculate_maturity_index(60.0, 40.0), 60.0)
        self.assertAlmostEqual(calculate_maturity_index(40.0, 60.0), 40.0)

    def test_infer_stratum(self):
        self.assertEqual(
            infer_size_class_from_filename("foo_Angiography 3x3 mm_bar.jpg"),
            "small_3mm",
        )
        self.assertEqual(
            infer_size_class_from_filename("patient_Optovue_Solix_6x6.png"),
            "small",
        )
        self.assertEqual(
            infer_size_class_from_filename("PlexElite_6x6_OD.png"),
            "large",
        )

    def test_csv_insert_columns(self):
        mod = _load_csv_script()
        sample = (
            REPO
            / "documentation/graefe_revision/data/MNV_batch_20260220_223647_small_3mm.csv"
        )
        self.assertTrue(sample.is_file())
        with open(sample, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            fieldnames = list(reader.fieldnames)
            rows = [dict(r) for r in reader]
        out_fields, out_rows = mod.process_rows(
            fieldnames, rows[:3], size_class_override="small_3mm"
        )
        self.assertIn("Caliber Uniformity Score (U2)", out_fields)
        self.assertIn("Maturity Index (U2)", out_fields)
        i_cal = out_fields.index("Caliber Uniformity Score")
        self.assertEqual(out_fields[i_cal + 1], "Caliber Uniformity Score (U2)")
        i_mat = out_fields.index("Maturity Index")
        self.assertEqual(out_fields[i_mat + 1], "Maturity Index (U2)")
        for r in out_rows:
            self.assertTrue(r["Caliber Uniformity Score (U2)"])
            u2 = float(r["Caliber Uniformity Score (U2)"])
            cx = float(r["Network Complexity Score"])
            mat = float(r["Maturity Index (U2)"])
            self.assertAlmostEqual(mat, calculate_maturity_index(u2, cx), places=4)

        with tempfile.TemporaryDirectory() as td:
            outp = Path(td) / "out.csv"
            mod._write_csv(outp, out_fields, out_rows)
            self.assertTrue(outp.is_file())


if __name__ == "__main__":
    unittest.main()
