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
    resolve_caliber_u2_size_class,
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
        # Sanitized export stems (spaces → _) must match the same stratum.
        self.assertEqual(
            infer_size_class_from_filename("Patient_Plex_Elite_6x6.png"),
            "large",
        )
        self.assertEqual(
            infer_size_class_from_filename("Optovue_Solix_AngioVue_6x6.png"),
            "small",
        )

    def test_resolve_u2_size_class_device_locked(self):
        # CIRRUS 3×3
        self.assertEqual(resolve_caliber_u2_size_class(3.0, 320), "small_3mm")
        # Solix / AngioVue 6×6 (typical <800 px) must NOT inherit pipeline's
        # scale>=6 → large mapping used for PCA Complexity refs.
        self.assertEqual(resolve_caliber_u2_size_class(6.0, 640), "small")
        self.assertEqual(resolve_caliber_u2_size_class(6.0, 400), "small")
        self.assertEqual(resolve_caliber_u2_size_class(6.0, 799), "small")
        # Boundary must match FILTER_PARAMS_LARGE (w >= 800), including ROI 800×800.
        self.assertEqual(resolve_caliber_u2_size_class(6.0, 800), "large")
        # PlexElite 6×6 (high-res)
        self.assertEqual(resolve_caliber_u2_size_class(6.0, 1024), "large")
        # Same median inputs score differently under Solix vs PlexElite strata
        ref = load_caliber_u2_device_ref()
        st_small = ref["strata"]["small"]
        score_solix, _ = calculate_caliber_u2_score(
            st_small["nv_cv"]["median"],
            st_small["dilated_pct"]["median"],
            size_class="small",
            ref=ref,
        )
        score_plex, _ = calculate_caliber_u2_score(
            st_small["nv_cv"]["median"],
            st_small["dilated_pct"]["median"],
            size_class="large",
            ref=ref,
        )
        self.assertAlmostEqual(score_solix, 50.0, places=3)
        self.assertLess(score_plex, 40.0)

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


class TestCaliberU2AppWiring(unittest.TestCase):
    """Main-app CSV column mapping: default Caliber = Standardized, PCA as fallback."""

    def test_imagej_csv_pca_columns_after_default(self):
        from src.utils.mnv_imagej_csv import IMAGEJ_CSV_COLUMNS, _PIPELINE_TO_IMAGEJ

        i_mat = IMAGEJ_CSV_COLUMNS.index("Maturity Index")
        self.assertEqual(IMAGEJ_CSV_COLUMNS[i_mat + 1], "Maturity Index (PCA)")
        i_cal = IMAGEJ_CSV_COLUMNS.index("Caliber Uniformity Score")
        self.assertEqual(
            IMAGEJ_CSV_COLUMNS[i_cal + 1], "Caliber Uniformity Score (PCA)"
        )
        self.assertEqual(
            _PIPELINE_TO_IMAGEJ["stability_score"], "Caliber Uniformity Score"
        )
        self.assertEqual(
            _PIPELINE_TO_IMAGEJ["stability_score_pca"],
            "Caliber Uniformity Score (PCA)",
        )

    def test_metrics_row_maps_default_and_pca(self):
        from src.utils.mnv_imagej_csv import _metrics_to_imagej_row

        row = _metrics_to_imagej_row(
            "demo.tif",
            0,
            "OK",
            True,
            {
                "maturity_index": 55.0,
                "maturity_index_pca": 48.0,
                "stability_score": 60.0,
                "stability_score_pca": 40.0,
                "complexity_score": 50.0,
            },
        )
        self.assertEqual(float(row["Caliber Uniformity Score"]), 60.0)
        self.assertEqual(float(row["Caliber Uniformity Score (PCA)"]), 40.0)
        self.assertEqual(float(row["Maturity Index"]), 55.0)
        self.assertEqual(float(row["Maturity Index (PCA)"]), 48.0)

    def test_pipeline_uses_caliber_u2(self):
        pipeline_src = (REPO / "src" / "core" / "mnv_pipeline.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("calculate_caliber_u2_score", pipeline_src)
        self.assertIn("resolve_caliber_u2_size_class", pipeline_src)
        self.assertIn("stability_score_pca", pipeline_src)
        self.assertIn("maturity_index_pca", pipeline_src)
        self.assertIn("from core.caliber_u2 import", pipeline_src)
        # Pathophysiology gates must stay on PCA-calibrated scores.
        self.assertIn("maturity_index=maturity_index_pca", pipeline_src)
        self.assertIn("stability_score=stability_score_pca", pipeline_src)


if __name__ == "__main__":
    unittest.main()
