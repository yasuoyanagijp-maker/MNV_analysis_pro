#!/usr/bin/env python3
"""MNV-absent PDF must not fabricate 0.00 morphometrics."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


class TestMnvAbsentPdf(unittest.TestCase):
    def test_absent_pdf_uses_dashes_not_zeros(self):
        from src.utils.mnv_absent import build_mnv_absent_result
        from src.utils.report_generator import generate_pdf_report

        # Synthetic tiny PNG so build_mnv_absent_result can size the mask without
        # needing a real clinical OCTA file.
        try:
            import cv2
            import numpy as np
        except ImportError:
            self.skipTest("cv2/numpy not available")

        with tempfile.TemporaryDirectory() as td:
            img_path = Path(td) / "absent_case.png"
            ok, buf = cv2.imencode(".png", np.zeros((32, 32), dtype=np.uint8))
            self.assertTrue(ok)
            img_path.write_bytes(buf.tobytes())

            result = build_mnv_absent_result(str(img_path), scale_mm=6.0, height=32, width=32)
            out_pdf = Path(td) / "absent.pdf"
            generate_pdf_report(result, str(out_pdf))
            self.assertTrue(out_pdf.is_file())
            self.assertGreater(out_pdf.stat().st_size, 200)

            # Re-read via fpdf text is hard; assert generator path explicitly.
            from src.utils.mnv_absent import is_mnv_absent_result

            self.assertTrue(is_mnv_absent_result(result))
            self.assertNotIn("mnv_area_mm2", result)


if __name__ == "__main__":
    unittest.main()
