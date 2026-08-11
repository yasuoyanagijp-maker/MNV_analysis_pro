#!/usr/bin/env python3
"""Unit tests for MNV folder auto-select filename filtering."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.utils.batch_input_filter import (  # noqa: E402
    filter_mnv_files_for_roi_selection,
    select_mnv_images_for_batch,
)


def _names(paths):
    return [p.name for p in paths]


class TestMnvBatchInputFilter(unittest.TestCase):
    def test_keeps_octa_enface_slot_3(self):
        files = [
            Path("OD_AngioVue_6x6_1.tif"),
            Path("OD_AngioVue_6x6_2.tif"),
            Path("OD_AngioVue_6x6_3.tif"),
            Path("OD_AngioVue_6x6_4.tif"),
        ]
        self.assertEqual(
            _names(filter_mnv_files_for_roi_selection(files, "MNV")),
            ["OD_AngioVue_6x6_3.tif"],
        )

    def test_keeps_multi_digit_case_ids_ending_in_124(self):
        files = [
            Path("Patient001.tif"),
            Path("Patient002.tif"),
            Path("Patient003.tif"),
            Path("Patient004.tif"),
        ]
        self.assertEqual(
            _names(filter_mnv_files_for_roi_selection(files, "MNV")),
            [
                "Patient001.tif",
                "Patient002.tif",
                "Patient003.tif",
                "Patient004.tif",
            ],
        )

    def test_image10_not_treated_as_image1(self):
        files = [Path("Patient_image10.tif"), Path("Patient_image3.tif")]
        self.assertEqual(
            _names(filter_mnv_files_for_roi_selection(files, "MNV")),
            ["Patient_image10.tif", "Patient_image3.tif"],
        )

    def test_still_excludes_legacy_image_slot_tokens(self):
        files = [
            Path("scan_image1.png"),
            Path("scan_image2.png"),
            Path("scan_image3.png"),
            Path("scan_image4.png"),
        ]
        self.assertEqual(
            _names(filter_mnv_files_for_roi_selection(files, "MNV")),
            ["scan_image3.png"],
        )

    def test_fallback_when_all_excluded(self):
        files = [Path("only1.tif"), Path("only2.tif"), Path("only4.tif")]
        self.assertEqual(
            _names(filter_mnv_files_for_roi_selection(files, "MNV")),
            ["only1.tif", "only2.tif", "only4.tif"],
        )

    def test_select_all_mode_bypasses_filter(self):
        files = [Path("a1.tif"), Path("b3.tif")]
        self.assertEqual(
            _names(select_mnv_images_for_batch(files, mode="all")),
            ["a1.tif", "b3.tif"],
        )


if __name__ == "__main__":
    unittest.main()
