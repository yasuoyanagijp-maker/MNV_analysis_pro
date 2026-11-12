"""Optovue 3mm button selects its complexity reference; Zeiss HD 3mm does not."""

import sys
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from core.pattern_classifier import classify_morphology_final
from core.pattern_metrics import (
    load_complexity_ref,
    load_mnv_classification_ref,
    trunk_term_for_complexity,
)
from utils.mnv_size_class import (
    explicit_mnv_size_class,
    resolve_mnv_complexity_size_class,
)


class TestOptovue3mmDevice(unittest.TestCase):
    def test_explicit_size_class_only_for_optovue_at_3mm(self):
        self.assertEqual(explicit_mnv_size_class(3.0, "optovue"), "optovue_3mm")
        self.assertEqual(explicit_mnv_size_class("3.0", "optovue_3mm"), "optovue_3mm")
        self.assertIsNone(explicit_mnv_size_class(3.0, "zeiss_hd"))
        self.assertIsNone(explicit_mnv_size_class(3.0, ""))
        self.assertIsNone(explicit_mnv_size_class(3.0, None))
        self.assertIsNone(explicit_mnv_size_class(6.0, "optovue"))
        self.assertIsNone(explicit_mnv_size_class(4.5, "optovue"))

    def test_optovue_complexity_ref_fixes_trunk_at_50(self):
        ref = load_complexity_ref("optovue_3mm")
        self.assertIsNotNone(ref)
        self.assertEqual(ref["size_class"], "optovue_3mm")
        self.assertNotIn("trunk_scale_correction", ref)
        self.assertEqual(trunk_term_for_complexity(12.0, ref), 50.0)
        self.assertEqual(trunk_term_for_complexity(90.0, ref), 50.0)

        zeiss = load_complexity_ref("small_3mm")
        median = float(zeiss["trunk_scale_correction"]["median"])
        self.assertAlmostEqual(trunk_term_for_complexity(median, zeiss), 50.0, places=4)
        self.assertNotAlmostEqual(trunk_term_for_complexity(12.0, zeiss), 50.0, places=1)

    def test_morphology_thresholds_differ_from_zeiss(self):
        optovue = load_mnv_classification_ref("optovue_3mm")
        self.assertAlmostEqual(optovue["complexity_score"]["P10"], 39.01825381367814)
        self.assertAlmostEqual(optovue["complexity_score"]["P65"], 55.106741443043006)

        self.assertEqual(
            classify_morphology_final(30, 50, "SEAFAN", "optovue_3mm")["subtype"],
            "Dead tree",
        )
        self.assertEqual(
            classify_morphology_final(60, 50, "MEDUSA", "optovue_3mm")["subtype"],
            "Medusa",
        )
        self.assertEqual(
            classify_morphology_final(50, 50, "SEAFAN", "optovue_3mm")["subtype"],
            "Seafan",
        )
        self.assertEqual(
            classify_morphology_final(47, 50, "INTERMEDIATE", "optovue_3mm")["subtype"],
            "Glomerular",
        )
        self.assertNotEqual(
            classify_morphology_final(60, 50, "MEDUSA", "small_3mm")["subtype"],
            "Medusa",
        )

    def test_complexity_pca_same_features_differ_by_stratum(self):
        from core.pattern_metrics import calculate_complexity_pca

        kwargs = dict(
            euler_center=4.0,
            euler_periphery=6.0,
            loop_total=22.0,
            junction_density=15.5,
            tortuosity_center=1.20,
            tortuosity_periphery=1.10,
            fd_global=1.11,
            trunk_score=50.0,
        )
        optovue = calculate_complexity_pca(size_class="optovue_3mm", **kwargs)
        zeiss = calculate_complexity_pca(size_class="small_3mm", **kwargs)
        self.assertNotAlmostEqual(optovue, zeiss, places=4)
        # Linux reference (numpy 1.26.4). Same input must match on Mac/Windows.
        self.assertAlmostEqual(optovue, 47.96209019582987, places=10)
        self.assertAlmostEqual(zeiss, 94.70098580409832, places=10)

    def test_pipeline_helper_matches_ui_tokens(self):
        self.assertEqual(
            resolve_mnv_complexity_size_class(3.0, "optovue", image_width=320),
            "optovue_3mm",
        )
        self.assertEqual(
            resolve_mnv_complexity_size_class(3.0, "zeiss_hd", image_width=320),
            "small_3mm",
        )


if __name__ == "__main__":
    unittest.main()
