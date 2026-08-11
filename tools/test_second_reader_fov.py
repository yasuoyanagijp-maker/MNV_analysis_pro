#!/usr/bin/env python3
"""Tests for second-reader FOV resolution from export/meta."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.utils.second_reader import (
    bind_fov_to_batch_paths,
    format_scale_dropdown_value,
    resolve_image_fov_map,
)


class TestSecondReaderFov(unittest.TestCase):
    def test_resolve_fov_from_meta(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            img = root / "Plex_Elite_case.png"
            img.write_bytes(b"x")
            meta = root / "Plex_Elite_case.json"
            meta.write_text(
                json.dumps(
                    {
                        "lesion_id": "Plex_Elite_case",
                        "fov_mm": 6.0,
                        "stratum": "large",
                    }
                ),
                encoding="utf-8",
            )
            path_map, default_fov, warnings = resolve_image_fov_map([img], [meta])
            self.assertEqual(default_fov, 6.0)
            self.assertEqual(path_map[str(img.resolve())], 6.0)
            self.assertEqual(warnings, [])
            self.assertEqual(format_scale_dropdown_value(6.0), "6.0")
            self.assertEqual(format_scale_dropdown_value(3.0), "3.0")
            # Staging uses a different absolute path but the same basename.
            staged = str((root / "staging" / img.name).resolve())
            (root / "staging").mkdir()
            (root / "staging" / img.name).write_bytes(b"y")
            rebound = bind_fov_to_batch_paths(
                [staged],
                {"Plex_Elite_case": 6.0},
                {img.name: 6.0},
            )
            self.assertEqual(rebound[staged], 6.0)

    def test_stratum_fallback_3mm(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            img = root / "case.png"
            img.write_bytes(b"x")
            meta = root / "case.json"
            meta.write_text(
                json.dumps({"lesion_id": "case", "stratum": "small_3mm"}),
                encoding="utf-8",
            )
            _, default_fov, _ = resolve_image_fov_map([img], [meta])
            self.assertEqual(default_fov, 3.0)


if __name__ == "__main__":
    unittest.main()
