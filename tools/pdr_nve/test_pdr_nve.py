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

from ariake_octa.common.image_loader import ImageLoader  # noqa: E402
from ariake_octa.pdr_nve.io import load_gray_u8  # noqa: E402
from ariake_octa.pdr_nve.metrics import (  # noqa: E402
    FORBIDDEN_SCORE_KEYS,
    assert_raw_only,
    compute_raw_metrics,
    gliding_box_lacunarity,
    percent_change,
)
from ariake_octa.pdr_nve.pipeline import PdrNveConfig, analyze_pair  # noqa: E402
from ariake_octa.pdr_nve.quality import collect_flags  # noqa: E402
from ariake_octa.pdr_nve.roi import auto_lesion_roi, boxes_to_mask, parse_roi_box  # noqa: E402
from ariake_octa.pdr_nve.register import (  # noqa: E402
    combine_slabs,
    identity_result,
    register_after_to_before,
    register_using_reference_slabs,
)
from ariake_octa.pdr_nve.scale import resolve_pixel_scale  # noqa: E402
from ariake_octa.pdr_nve.trim import (  # noqa: E402
    common_blank_border,
    detect_blank_border,
    trim_roi_blank_margin,
)
from ariake_octa.pdr_nve.vessels import (  # noqa: E402
    build_vessel_maps,
    large_vessel_mask,
    remove_speckle,
)


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


class TestBmpIo(unittest.TestCase):
    def test_load_gray_u8_bmp_roundtrip(self):
        img = _network((96, 96))
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "octa.bmp"
            Image.fromarray(img).save(path)
            loaded = load_gray_u8(path)
            self.assertEqual(loaded.shape, img.shape)
            self.assertEqual(loaded.dtype, np.uint8)
            np.testing.assert_allclose(loaded.astype(float), img.astype(float), atol=2)

    def test_load_gray_u8_palette_bmp(self):
        img = _network((96, 96))
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "palette.bmp"
            Image.fromarray(img, mode="L").convert("P").save(path)
            loaded = load_gray_u8(path)
            self.assertEqual(loaded.shape, img.shape)
            self.assertEqual(loaded.dtype, np.uint8)
            # Palette quantization can shift values; structure must remain.
            self.assertGreater(int((loaded > 20).sum()), 100)

    def test_image_loader_accepts_bmp(self):
        img = _network((96, 96))
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "device.BMP"
            Image.fromarray(img).save(path)
            loaded = ImageLoader.load(str(path))
            self.assertEqual(loaded.shape, img.shape)
            self.assertEqual(loaded.dtype, np.uint8)

    def test_pipeline_accepts_bmp_pair(self):
        before = _network((96, 96), prune=False)
        after = _network((96, 96), prune=True)
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            bpath = td / "before.bmp"
            apath = td / "after.bmp"
            Image.fromarray(before).save(bpath)
            Image.fromarray(after).save(apath)
            out = td / "out"
            cfg = PdrNveConfig(
                case_id="bmp",
                scan_size_mm=15.0,
                pixel_width_px=96,
                roi_mode="full",
                register=False,
                trim_blank_border=False,
                trim_roi_margin=False,
                segment_mode="adaptive",
                output_dir=str(out),
                precomputed_before_binary=before > 0,
                precomputed_after_binary=after > 0,
            )
            result = analyze_pair(str(bpath), str(apath), cfg)
            self.assertEqual(result.record["before_path"], str(bpath))
            self.assertTrue(Path(result.paths["metrics_csv"]).is_file())


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

    def test_remove_speckle_keeps_network(self):
        img = _network((96, 96))
        binary = img > 0
        noisy = binary.copy()
        rng = np.random.default_rng(0)
        dots = rng.random(noisy.shape) < 0.02
        # isolated 1-px dots away from the mesh
        dots[30:100, 30:100] = False
        noisy = noisy | dots
        scale = resolve_pixel_scale((96, 96), scan_size_mm=15.0, pixel_width_px=96)
        cleaned = remove_speckle(noisy, scale, min_area_mm2=0.05)
        self.assertGreater(int(cleaned.sum()), 200)
        self.assertLess(int(cleaned.sum()), int(noisy.sum()))
        self.assertLess(int((cleaned & ~binary).sum()), 20)


class TestRoi(unittest.TestCase):
    def test_parse_and_rasterize_box(self):
        self.assertEqual(parse_roi_box("10,20,30,40"), (10.0, 20.0, 30.0, 40.0))
        mask = boxes_to_mask([(10, 20, 30, 40), (50, 50, 10, 10)], (80, 80))
        self.assertEqual(int((mask > 0).sum()), 30 * 40 + 10 * 10)
        self.assertTrue(mask[25, 15] > 0)
        self.assertEqual(int(mask[0, 0]), 0)

    def test_auto_roi_does_not_swallow_whole_field(self):
        """A sparse tuft on a thin tree must not become a full-field ROI."""
        img = np.zeros((128, 128), dtype=np.uint8)
        img[64, 8:120] = 220
        img[8:120, 64] = 220
        img[20:44, 20:44] = 0
        for y in range(20, 44, 3):
            img[y, 20:44] = 200
        for x in range(20, 44, 3):
            img[20:44, x] = 200
        scale = resolve_pixel_scale((128, 128), scan_size_mm=15.0, pixel_width_px=128)
        maps = build_vessel_maps(
            img,
            scale,
            segment_mode="adaptive",
            large_vessel_um=80.0,
            min_cc_mm2=0.002,
        )
        roi = auto_lesion_roi(maps, scale, min_component_mm2=0.02, max_roi_frac=0.40)
        self.assertIsNotNone(roi)
        frac = float((roi > 0).mean())
        self.assertLess(frac, 0.40)
        self.assertGreater(int((roi[20:44, 20:44] > 0).sum()), 20)


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

    def test_combine_slabs_mean_and_sum(self):
        a = np.zeros((16, 16), dtype=np.uint8)
        b = np.zeros((16, 16), dtype=np.uint8)
        a[4:12, 4:12] = 100
        b[4:12, 4:12] = 50
        mean = combine_slabs([a, b], mode="mean")
        summed = combine_slabs([a, b], mode="sum")
        self.assertEqual(int(mean[8, 8]), 75)
        self.assertEqual(int(summed[8, 8]), 255)
        self.assertEqual(int(mean[0, 0]), 0)

    def test_register_on_persistent_slab_warps_analysis(self):
        """Align using a stable 'retina' slab; apply that matrix to a pruned NVE slab."""
        import cv2

        retina = _network((96, 96), prune=False)
        nve_before = retina.copy()
        nve_after = _network((96, 96), prune=True)
        M = np.float32([[1, 0, 7], [0, 1, -4]])
        retina_moved = cv2.warpAffine(retina, M, (96, 96), flags=cv2.INTER_NEAREST)
        nve_after_moved = cv2.warpAffine(nve_after, M, (96, 96), flags=cv2.INTER_NEAREST)
        r = register_using_reference_slabs(
            nve_before,
            nve_after_moved,
            retina,
            retina_moved,
            reference_kind="combined_mean",
            n_register_slabs=2,
            combine_mode="mean",
        )
        self.assertEqual(r.reference_kind, "combined_mean")
        self.assertEqual(r.n_register_slabs, 2)
        overlap = float(np.mean((nve_after > 40) == (r.warped_after > 40)))
        self.assertGreater(overlap, 0.70)


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
                "register_qa",
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

    def test_pipeline_register_slabs_write_refs(self):
        before = _network((96, 96), prune=False)
        after = _network((96, 96), prune=True)
        retina_b = before.copy()
        retina_a = after.copy()
        retina_a[10:20, 10:20] = 180  # extra persistent structure
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            Image.fromarray(before).save(td / "nve_b.png")
            Image.fromarray(after).save(td / "nve_a.png")
            Image.fromarray(retina_b).save(td / "ret_b.png")
            Image.fromarray(retina_a).save(td / "ret_a.png")
            out = td / "out"
            cfg = PdrNveConfig(
                case_id="regref",
                scan_size_mm=15.0,
                pixel_width_px=96,
                roi_mode="full",
                register=True,
                trim_blank_border=False,
                trim_roi_margin=False,
                segment_mode="adaptive",
                output_dir=str(out),
                register_before_paths=[str(td / "ret_b.png")],
                register_after_paths=[str(td / "ret_a.png")],
                register_combine="mean",
                precomputed_before_binary=before > 0,
                precomputed_after_binary=after > 0,
            )
            result = analyze_pair(str(td / "nve_b.png"), str(td / "nve_a.png"), cfg)
            self.assertEqual(result.record["registration_reference"], "single_other_slab")
            self.assertFalse(result.record["registration_used_analysis_slab"])
            for key in (
                "register_ref_before",
                "register_ref_after",
                "register_ref_after_warped",
                "register_qa",
            ):
                self.assertTrue(Path(result.paths[key]).is_file(), msg=key)

    def test_cli_help(self):
        from ariake_octa.pdr_nve.cli import build_parser

        help_text = build_parser().format_help()
        self.assertIn("--scan-size-mm", help_text)
        self.assertIn("--register-before", help_text)
        self.assertIn("--roi-box", help_text)
        self.assertIn("--min-cc-mm2", help_text)
        self.assertIn("RAW", help_text)
        self.assertIn("bmp", help_text.lower())


if __name__ == "__main__":
    unittest.main()
