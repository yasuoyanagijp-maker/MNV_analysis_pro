#!/usr/bin/env python3
"""Unit tests for the isolated PDR NVE module (does not exercise the MNV app)."""

from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
for p in (str(ROOT), str(SRC)):
    if p not in sys.path:
        sys.path.insert(0, p)

from ariake_octa.pdr_nve.metrics import (  # noqa: E402
    FORBIDDEN_SCORE_KEYS,
    assert_raw_only,
    compute_raw_metrics,
    gliding_box_lacunarity,
    percent_change,
)
from ariake_octa.pdr_nve.pipeline import PdrNveConfig, analyze_pair  # noqa: E402
from ariake_octa.pdr_nve.quality import collect_flags  # noqa: E402
from ariake_octa.pdr_nve.register import (  # noqa: E402
    identity_result,
    register_after_to_before,
)
from ariake_octa.pdr_nve.scale import resolve_pixel_scale  # noqa: E402
from ariake_octa.pdr_nve.trim import (  # noqa: E402
    common_blank_border,
    detect_blank_border,
    trim_roi_blank_margin,
)
from ariake_octa.pdr_nve.vessels import build_vessel_maps, large_vessel_mask  # noqa: E402


def _network(shape=(128, 128), prune=False):
    img = np.zeros(shape, dtype=np.uint8)
    # thin looping NVE-like mesh
    for y in range(30, 100, 8):
        img[y, 30:100] = 200
    for x in range(30, 100, 8):
        img[30:100, x] = 200
    # thick trunk
    img[60:68, 10:118] = 220
    if prune:
        img[30:100, 70:100] = 0
        img[70:100, 30:100] = 0
        img[60:68, 10:118] = 220
    return img


class TestScale(unittest.TestCase):
    def test_15mm_1024(self):
        s = resolve_pixel_scale((1024, 1024), scan_size_mm=15.0, pixel_width_px=1024)
        self.assertAlmostEqual(s.um_per_px, 15000.0 / 1024.0, places=6)
        rec = s.to_record()
        self.assertEqual(rec["scan_size_mm"], 15.0)
        self.assertIn("um_per_px", rec)

    def test_explicit_um(self):
        s = resolve_pixel_scale((64, 64), scan_size_mm=15.0, um_per_px=14.65)
        self.assertAlmostEqual(s.um_per_px, 14.65)


class TestTrim(unittest.TestCase):
    def test_blank_border(self):
        img = np.zeros((80, 80), dtype=np.uint8)
        img[10:70, 15:65] = 80
        crop = detect_blank_border(img)
        self.assertEqual(crop.top, 10)
        self.assertEqual(crop.left, 15)
        cropped = crop.apply(img)
        self.assertEqual(cropped.shape, (60, 50))

    def test_common_border_keeps_alignment(self):
        a = np.zeros((40, 40), dtype=np.uint8)
        b = np.zeros((40, 40), dtype=np.uint8)
        a[5:35, 5:35] = 50
        b[8:32, 2:38] = 50
        c = common_blank_border(a, b)
        self.assertEqual(c.top, 5)
        self.assertEqual(c.left, 2)

    def test_roi_trim_drops_border_padding_only(self):
        roi = np.zeros((40, 40), dtype=np.uint8)
        roi[5:35, 5:35] = 255
        color = np.zeros((40, 40), dtype=bool)
        color[10:30, 10:30] = True
        # enclosed hole inside color ring
        color[18:22, 18:22] = False
        refined, info = trim_roi_blank_margin(roi, color)
        self.assertGreater(info["n_border_padding_px"], 0)
        self.assertTrue(refined[12, 12] > 0)
        self.assertEqual(refined[6, 6], 0)
        # enclosed hole stays in ROI
        self.assertGreater(refined[20, 20], 0)


class TestVesselsAndMetrics(unittest.TestCase):
    def test_large_vessel_filter(self):
        binary = np.zeros((80, 80), dtype=bool)
        binary[20:60, 38:42] = True  # ~4 px half-width → diameter 8 px
        scale = resolve_pixel_scale((80, 80), scan_size_mm=15.0)
        # 4 px wide bar → EDT radius 2 px → diameter = 4 px. Threshold just below that.
        mask = large_vessel_mask(binary, scale, threshold_um=scale.um_per_px * 3.5)
        self.assertTrue(mask[40, 40])

    def test_loop_and_caliber(self):
        binary = np.zeros((64, 64), dtype=bool)
        binary[16:48, 16] = True
        binary[16:48, 47] = True
        binary[16, 16:48] = True
        binary[47, 16:48] = True
        scale = resolve_pixel_scale((64, 64), scan_size_mm=6.0)
        maps = build_vessel_maps(
            np.zeros((64, 64), dtype=np.uint8),
            scale,
            segment_mode="adaptive",
            large_vessel_um=200.0,
            precomputed_binary=binary,
        )
        roi = np.ones((64, 64), dtype=np.uint8) * 255
        m = compute_raw_metrics(maps, roi, scale)
        self.assertGreaterEqual(m["n_loops"], 1)
        self.assertGreater(m["vessel_area_density"], 0)
        self.assertGreater(m["skeleton_length_mm"], 0)
        self.assertGreater(m["caliber_mean_um"], 0)
        self.assertNotIn("maturity_index", m)

    def test_lacunarity_sparse_gt_dense(self):
        dense = np.ones((64, 64), dtype=bool)
        clustered = np.zeros((64, 64), dtype=bool)
        clustered[6:22, 6:22] = True
        clustered[40:50, 42:54] = True
        ld = gliding_box_lacunarity(dense, box_sizes=(4, 8))
        ls = gliding_box_lacunarity(clustered, box_sizes=(4, 8))
        self.assertGreater(ls[8], ld[8])

    def test_percent_change(self):
        self.assertAlmostEqual(percent_change(10, 7), -30.0)
        self.assertTrue(np.isnan(percent_change(0, 1)))


class TestRegistration(unittest.TestCase):
    def test_identity_when_disabled(self):
        img = _network()
        r = register_after_to_before(img, img, enabled=False)
        self.assertEqual(r.method, "identity")
        np.testing.assert_array_equal(r.warped_after, img)

    def test_recovers_translation(self):
        src = _network((96, 96))
        M = np.float32([[1, 0, 8], [0, 1, -5]])
        import cv2

        moved = cv2.warpAffine(src, M, (96, 96), flags=cv2.INTER_NEAREST)
        r = register_after_to_before(src, moved, enabled=True)
        self.assertGreater(r.score, 0.5)
        # warped after should overlap the reference network
        overlap = float(np.mean((src > 0) == (r.warped_after > 40)))
        self.assertGreater(overlap, 0.75)


class TestQualityAndRawOnly(unittest.TestCase):
    def test_flags_and_forbidden_keys(self):
        img = np.zeros((32, 32), dtype=np.uint8)
        scale = resolve_pixel_scale((32, 32), scan_size_mm=15.0)
        q = collect_flags(
            img,
            img,
            scale,
            identity_result(img),
            np.ones((32, 32), dtype=np.uint8),
            0,
            0,
            "full",
        )
        self.assertTrue(q["exclude_suggested"])
        self.assertIn("full_field_roi", q["quality_flags"])
        with self.assertRaises(AssertionError):
            assert_raw_only({"maturity_index": 50})
        for key in FORBIDDEN_SCORE_KEYS:
            self.assertNotIn(key, q)


class TestPipelineArtifacts(unittest.TestCase):
    def test_analyze_pair_writes_rgb_and_masks(self):
        before = _network((96, 96), prune=False)
        after = _network((96, 96), prune=True)
        before_bin = before > 0
        after_bin = after > 0
        with tempfile.TemporaryDirectory() as td:
            bpath = Path(td) / "before.png"
            apath = Path(td) / "after.png"
            Image.fromarray(before).save(bpath)
            Image.fromarray(after).save(apath)
            out = Path(td) / "out"
            cfg = PdrNveConfig(
                case_id="toy",
                scan_size_mm=15.0,
                pixel_width_px=96,
                roi_mode="full",
                register=False,
                trim_blank_border=False,
                trim_roi_margin=False,
                large_vessel_um=80.0,
                segment_mode="adaptive",
                output_dir=str(out),
                precomputed_before_binary=before_bin,
                precomputed_after_binary=after_bin,
            )
            result = analyze_pair(str(bpath), str(apath), cfg)
            rec = result.record
            self.assertNotIn("maturity_index", rec)
            self.assertNotIn("complexity_score", rec)
            self.assertIn("um_per_px", rec)
            self.assertLess(
                rec["after_vessel_area_density"], rec["before_vessel_area_density"]
            )
            self.assertLess(rec["pct_vessel_area_density"], 0)
            required = [
                "metrics_csv",
                "overlay_qa",
                "before_rgb",
                "after_rgb",
                "before_vessel_mask",
                "after_vessel_mask",
                "before_roi_mask",
                "after_roi_mask",
                "before_vessel_mask_no_large",
                "after_vessel_mask_no_large",
                "before_large_vessel_mask",
                "after_large_vessel_mask",
            ]
            for key in required:
                p = Path(result.paths[key])
                self.assertTrue(p.is_file(), msg=key)
                self.assertGreater(p.stat().st_size, 0, msg=key)
            rgb = np.array(Image.open(result.paths["before_rgb"]))
            self.assertEqual(rgb.ndim, 3)
            self.assertEqual(rgb.shape[2], 3)
            with open(result.paths["metrics_csv"], encoding="utf-8-sig") as fh:
                rows = list(csv.DictReader(fh))
            self.assertEqual(len(rows), 1)
            self.assertIn("um_per_px", rows[0])
            self.assertNotIn("Maturity Index", rows[0])

    def test_cli_help(self):
        from ariake_octa.pdr_nve.cli import build_parser

        help_text = build_parser().format_help()
        self.assertIn("--scan-size-mm", help_text)
        self.assertIn("RAW", help_text)


if __name__ == "__main__":
    unittest.main()
