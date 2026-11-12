#!/usr/bin/env python3
"""Synthetic (non-patient) 3 mm scan: Optovue vs Zeiss HD on the same pixels."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")


def _synthetic_octa(size: int = 320):
    import cv2
    import numpy as np

    img = np.zeros((size, size), dtype=np.uint8)
    cy = cx = size // 2
    cv2.circle(img, (cx, cy), 90, 210, 3)
    cv2.circle(img, (cx, cy), 55, 190, 2)
    for angle in range(0, 180, 15):
        rad = np.deg2rad(angle)
        x1 = int(cx + 20 * np.cos(rad))
        y1 = int(cy + 20 * np.sin(rad))
        x2 = int(cx + 95 * np.cos(rad))
        y2 = int(cy + 95 * np.sin(rad))
        cv2.line(img, (x1, y1), (x2, y2), 200, 2)
    cv2.GaussianBlur(img, (3, 3), 0, dst=img)
    mask = np.zeros((size, size), dtype=np.uint8)
    cv2.circle(mask, (cx, cy), 110, 255, -1)
    return img, mask


class TestSyntheticOptovueVsZeiss(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import cv2  # noqa: F401
            import numpy  # noqa: F401
            from core.mnv_pipeline import MNVPipeline  # noqa: F401
        except Exception as exc:
            raise unittest.SkipTest(f"pipeline imports unavailable: {exc}") from exc

    def test_same_pixels_optovue_changes_complexity_only(self):
        import cv2
        from core.mnv_pipeline import MNVPipeline

        img, mask = _synthetic_octa()
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            path = tdir / "synthetic_3mm.png"
            cv2.imwrite(str(path), img)
            out_o = tdir / "out_optovue"
            out_z = tdir / "out_zeiss"
            out_o.mkdir()
            out_z.mkdir()
            opt = MNVPipeline(
                scale_mm=3.0,
                size_class="optovue",
                save_stages=False,
                verbose=False,
                enable_roi_refinement=False,
            )
            zeiss = MNVPipeline(
                scale_mm=3.0,
                size_class="zeiss_hd",
                save_stages=False,
                verbose=False,
                enable_roi_refinement=False,
            )
            self.assertEqual(opt.size_class_override, "optovue_3mm")
            self.assertIsNone(zeiss.size_class_override)
            r_opt = opt.analyze(str(path), output_dir=str(out_o), roi_mask=mask)
            r_z = zeiss.analyze(str(path), output_dir=str(out_z), roi_mask=mask)

        self.assertEqual(r_opt.get("complexity_size_class"), "optovue_3mm")
        self.assertEqual(r_z.get("complexity_size_class"), "small_3mm")
        self.assertAlmostEqual(float(r_opt["mnv_area_mm2"]), float(r_z["mnv_area_mm2"]), places=10)
        self.assertAlmostEqual(float(r_opt["vessel_area_mm2"]), float(r_z["vessel_area_mm2"]), places=10)
        self.assertAlmostEqual(float(r_opt["vessel_length_mm"]), float(r_z["vessel_length_mm"]), places=10)
        c_opt = float(r_opt["complexity_score"])
        c_z = float(r_z["complexity_score"])
        self.assertNotAlmostEqual(c_opt, c_z, places=4)
        # Linux / numpy 1.26.4 / opencv 4.9.0.80 reference for this synthetic PNG.
        # Geometry is identical; Complexity differs only by the Optovue vs Zeiss PCA refs.
        self.assertAlmostEqual(float(r_opt["mnv_area_mm2"]), 3.338173828125, places=10)
        self.assertAlmostEqual(float(r_opt["vessel_area_mm2"]), 0.584208984375, places=10)
        self.assertAlmostEqual(float(r_opt["vessel_length_mm"]), 31.64142855093034, places=8)
        self.assertAlmostEqual(c_opt, 68.59606941290195, places=6)
        self.assertAlmostEqual(c_z, 98.51536607077992, places=6)


if __name__ == "__main__":
    unittest.main()
