#!/usr/bin/env python3
"""Unit tests for the RECHECK markdown parser (final-reader triad workflow)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.utils.recheck_md_parser import (  # noqa: E402
    RecheckMdError,
    UnknownParameterError,
    map_parameter_name,
    parse_recheck_md,
    parse_recheck_md_text,
    sibling_pipeline_files,
)

CANONICAL_MD = """\
# 統合解析データ (dual-read adoption) — 2026-08-15

## RECHECK

- 主要指標セル: 3 件（対象症例 2 件）
- 症例別（NA となった主要指標）:
  - 102-001_Week04.png: Vsl Area (mm2)
  - 102-002_Week04.png: MNV Area (mm2), Caliber Uniformity Score
"""


class TestParameterMapping(unittest.TestCase):
    def test_exact_major_metrics(self):
        self.assertEqual(map_parameter_name("Vsl Area (mm2)"), "Vsl Area (mm2)")
        self.assertEqual(map_parameter_name("MNV Area (mm2)"), "MNV Area (mm2)")
        self.assertEqual(
            map_parameter_name("Caliber Uniformity Score (U2)"),
            "Caliber Uniformity Score (U2)",
        )

    def test_loose_aliases_map_to_u2_columns(self):
        self.assertEqual(
            map_parameter_name("Caliber Uniformity Score"),
            "Caliber Uniformity Score (U2)",
        )
        self.assertEqual(map_parameter_name("Maturity Index"), "Maturity Index (U2)")
        self.assertEqual(
            map_parameter_name("Vsl Density"), "Vsl Density (Vessel Area/MNV (%))"
        )

    def test_fullwidth_brackets_and_case(self):
        self.assertEqual(map_parameter_name("Vsl Area （mm2）"), "Vsl Area (mm2)")
        self.assertEqual(map_parameter_name("vsl area (MM2)"), "Vsl Area (mm2)")
        # NFKC: superscript 2 → "2"
        self.assertEqual(map_parameter_name("MNV Area (mm²)"), "MNV Area (mm2)")

    def test_unknown_returns_none(self):
        self.assertIsNone(map_parameter_name("Totally Unknown Metric"))


class TestParseCanonical(unittest.TestCase):
    def test_targets_and_counts(self):
        res = parse_recheck_md_text(CANONICAL_MD)
        self.assertEqual(res.declared_cells, 3)
        self.assertEqual(res.declared_cases, 2)
        self.assertEqual(len(res.targets), 3)
        self.assertEqual(res.warnings, [])
        pairs = [(t.image_file, t.column) for t in res.targets]
        self.assertEqual(
            pairs,
            [
                ("102-001_Week04.png", "Vsl Area (mm2)"),
                ("102-002_Week04.png", "MNV Area (mm2)"),
                ("102-002_Week04.png", "Caliber Uniformity Score (U2)"),
            ],
        )
        self.assertEqual(res.targets[0].image_stem, "102-001_week04")

    def test_image_files_deduped_in_order(self):
        res = parse_recheck_md_text(CANONICAL_MD)
        self.assertEqual(
            res.image_files, ["102-001_Week04.png", "102-002_Week04.png"]
        )

    def test_columns_for_stem(self):
        res = parse_recheck_md_text(CANONICAL_MD)
        self.assertEqual(
            res.columns_for_stem("102-002_week04"),
            ["MNV Area (mm2)", "Caliber Uniformity Score (U2)"],
        )


class TestFormattingVariants(unittest.TestCase):
    def test_fullwidth_colon_and_bullets(self):
        md = """\
## RECHECK

・ 主要指標セル： 2 件（対象ファイル 1 件）
・ 症例別（NA となった主要指標）：
  ・ 102-001_Week04.png： Vsl Area （mm2）、 Tortuosity
"""
        res = parse_recheck_md_text(md)
        self.assertEqual(res.declared_cells, 2)
        self.assertEqual(res.declared_cases, 1)
        self.assertEqual(
            [(t.image_file, t.column) for t in res.targets],
            [
                ("102-001_Week04.png", "Vsl Area (mm2)"),
                ("102-001_Week04.png", "Tortuosity"),
            ],
        )

    def test_app_writer_per_metric_counts_are_not_targets(self):
        # The app writer also emits per-metric count bullets inside ## RECHECK.
        md = """\
## RECHECK

- 主要指標セル: 1 件（対象症例 1 件）
  - Vsl Area (mm2): 1
- 症例別（NA となった主要指標）:
  - 102-001_Week04.png: Vsl Area (mm2)
"""
        res = parse_recheck_md_text(md)
        self.assertEqual(len(res.targets), 1)
        self.assertEqual(res.targets[0].image_file, "102-001_Week04.png")

    def test_section_ends_at_next_heading(self):
        md = CANONICAL_MD + """
## 警告

- 999-999_Week04.png: Vsl Area (mm2)
"""
        res = parse_recheck_md_text(md)
        self.assertEqual(len(res.targets), 3)

    def test_tif_extension_and_numbered_list(self):
        md = """\
### RECHECK
1. 102-001_Week04.tif: Fractal Dim
"""
        res = parse_recheck_md_text(md)
        self.assertEqual(res.targets[0].column, "Fractal Dim")


class TestErrors(unittest.TestCase):
    def test_unknown_parameter_stops_processing(self):
        md = """\
## RECHECK

- 症例別（NA となった主要指標）:
  - 102-001_Week04.png: Vsl Area (mm2), Imaginary Metric Xyz
"""
        with self.assertRaises(UnknownParameterError) as cm:
            parse_recheck_md_text(md)
        self.assertIn("Imaginary Metric Xyz", cm.exception.unknown)

    def test_no_recheck_section(self):
        with self.assertRaises(RecheckMdError):
            parse_recheck_md_text("# something else\n- 102-001_Week04.png: Vsl Area (mm2)\n")

    def test_no_per_case_lines(self):
        md = "## RECHECK\n\n- 主要指標セル: 0 件（対象症例 0 件）\n  - (なし)\n"
        with self.assertRaises(RecheckMdError):
            parse_recheck_md_text(md)

    def test_count_mismatch_is_warning_not_error(self):
        md = """\
## RECHECK

- 主要指標セル: 5 件（対象症例 4 件）
- 症例別（NA となった主要指標）:
  - 102-001_Week04.png: Vsl Area (mm2)
"""
        res = parse_recheck_md_text(md)
        self.assertEqual(len(res.targets), 1)
        self.assertEqual(len(res.warnings), 2)


class TestSiblingFiles(unittest.TestCase):
    def test_prefix_and_lookup(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            md = d / "MNV_integrated_20260815_120000_summary.md"
            md.write_text(CANONICAL_MD, encoding="utf-8")
            (d / "MNV_integrated_20260815_120000_recheck_list.csv").write_text(
                "File,Metric\n", encoding="utf-8"
            )
            (d / "MNV_integrated_20260815_120000_adopted_values.csv").write_text(
                "ID,File\n", encoding="utf-8"
            )
            recheck, adopted, prefix = sibling_pipeline_files(md)
            self.assertEqual(prefix, "MNV_integrated_20260815_120000")
            self.assertIsNotNone(recheck)
            self.assertIsNotNone(adopted)
            # Round-trip: parse the file we just wrote
            res = parse_recheck_md(md)
            self.assertEqual(len(res.targets), 3)


if __name__ == "__main__":
    unittest.main()
