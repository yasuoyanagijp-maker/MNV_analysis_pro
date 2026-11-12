#!/usr/bin/env python3
"""v1.2.5 unification: one version, Optovue 3 mm on every OS UI, locked RPD."""

from __future__ import annotations

import ast
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.pyinstaller_version import read_app_version  # noqa: E402
from tools.reading_center_rpd.compute_adopted_from_dual_csv import (  # noqa: E402
    DEFAULT_RPD_PCT,
    MAJOR_METRICS,
)
from utils.app_version import format_app_version_label, get_app_version  # noqa: E402
from utils.mnv_size_class import (  # noqa: E402
    OPTOVUE_3MM,
    explicit_mnv_size_class,
    resolve_mnv_complexity_size_class,
)


LOCKED_MAJOR_METRICS = [
    "MNV Area (mm2)",
    "Vsl Area (mm2)",
    "Vsl Density (Vessel Area/MNV (%))",
    "Standardized Caliber Uniformity Score",
    "Standardized Maturity Index",
    "Network Complexity Score",
    "Fractal Dim",
    "Tortuosity",
]


class TestUnifiedVersion(unittest.TestCase):
    def test_version_file_is_1_2_5(self):
        self.assertEqual((ROOT / "VERSION").read_text(encoding="utf-8").strip(), "1.2.5")
        self.assertEqual(read_app_version(ROOT), "1.2.5")
        self.assertEqual(get_app_version(), "1.2.5")
        self.assertEqual(format_app_version_label(), "v1.2.5")

    def test_mac_and_win_specs_read_the_same_version_helper(self):
        for spec in (
            "ARIAKE_OCTA.spec",
            "ARIAKE_OCTA_arm64.spec",
            "ARIAKE_OCTA_x86_64.spec",
            "ARIAKE_OCTA_win.spec",
        ):
            text = (ROOT / spec).read_text(encoding="utf-8")
            self.assertIn("from tools.pyinstaller_version import read_app_version", text)
            self.assertIn("VERSION", text)

    def test_ci_uses_headless_opencv_so_pipeline_golden_cannot_skip(self):
        yml = (ROOT / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
        self.assertIn("opencv-python-headless==4.9.0.80", yml)
        self.assertNotIn("opencv-python==4.9.0.80", yml)
        self.assertIn("Verify cv2 and MNV pipeline import", yml)
        synth = (ROOT / "tools" / "test_synthetic_mnv_optovue.py").read_text(encoding="utf-8")
        self.assertIn("_running_in_ci", synth)
        self.assertIn("pipeline golden must run in CI", synth)

    def test_mac_install_txt_uses_sequoia_methods(self):
        text = (ROOT / "Macインストール手順.txt").read_text(encoding="utf-8")
        self.assertIn("v1.2.5", text)
        self.assertIn("ターミナル方式", text)
        self.assertIn("システム設定方式", text)
        self.assertIn("xattr -cr", text)
        self.assertIn("このまま開く", text)
        cmd = (ROOT / "インストール.command").read_text(encoding="utf-8")
        self.assertIn("[重要]", cmd)
        self.assertIn("ターミナル方式", cmd)
        self.assertIn("このまま開く", cmd)
        self.assertIn("xattr -cr", cmd)

    def test_mac_openssl_align_is_in_build_and_ci(self):
        mac = (ROOT / "build_mac.sh").read_text(encoding="utf-8")
        self.assertIn("--ssl-smoke", mac)
        self.assertIn("mac_openssl_coexistence.py", mac)
        yml = (ROOT / ".github" / "workflows" / "build-mac.yml").read_text(encoding="utf-8")
        self.assertIn("macos-15-intel", yml)
        self.assertIn("|| 'macos-15' }}", yml)
        win = (ROOT / "build_win.ps1").read_text(encoding="utf-8")
        self.assertIn("win_ssl_bundle_align.py", win)
        tests = (ROOT / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
        self.assertIn("tools.test_mac_openssl_coexistence", tests)
        self.assertIn("tools.test_win_ssl_bundle_align", tests)

    def test_build_scripts_default_to_version_file(self):
        mac = (ROOT / "build_mac.sh").read_text(encoding="utf-8")
        self.assertIn('tr -d \'[:space:]\' < "${SCRIPT_DIR}/VERSION"', mac)
        self.assertNotIn("1.2.4d", mac.split("APP_VERSION=", 1)[-1][:200])
        win = (ROOT / "build_win.ps1").read_text(encoding="utf-8")
        self.assertIn("VERSION", win)
        self.assertIn("_win_v$APP_VERSION.zip", win)


class TestWindowsFletHasOptovueButton(unittest.TestCase):
    def test_dashboard_wizard_and_advanced_settings(self):
        dash = (SRC / "flet_ui" / "pages" / "dashboard.py").read_text(encoding="utf-8")
        self.assertIn('_scale_btn("3 mm (Optovue)", "3.0", "optovue"', dash)
        self.assertIn('_scale_btn("3 mm (Zeiss HD)", "3.0", "zeiss_hd"', dash)
        self.assertIn('ft.dropdown.Option("optovue", "3 mm (Optovue)")', dash)
        self.assertIn("device_dd", dash)
        self.assertNotRegex(dash, r'_scale_btn\("3 mm", "3.0"\)')

    def test_windows_spec_bundles_the_same_src_tree(self):
        win = (ROOT / "ARIAKE_OCTA_win.spec").read_text(encoding="utf-8")
        self.assertIn('("src", "src")', win)
        self.assertIn('("resources", "resources")', win)
        pipeline = SRC / "core" / "mnv_pipeline.py"
        self.assertTrue(pipeline.is_file())
        self.assertIn("resolve_mnv_complexity_size_class", pipeline.read_text(encoding="utf-8"))


class TestComplexityCriterionSwitch(unittest.TestCase):
    def test_optovue_button_only_at_3mm(self):
        self.assertEqual(explicit_mnv_size_class(3.0, "optovue"), OPTOVUE_3MM)
        self.assertIsNone(explicit_mnv_size_class(3.0, "zeiss_hd"))
        self.assertIsNone(explicit_mnv_size_class(6.0, "optovue"))

    def test_same_rule_on_every_os(self):
        cases = [
            (3.0, "optovue", 320, "optovue_3mm"),
            (3.0, "optovue_3mm", 1024, "optovue_3mm"),
            (3.0, "zeiss_hd", 320, "small_3mm"),
            (3.0, "", 320, "small_3mm"),
            (3.0, None, 320, "small_3mm"),
            ("3.0", "optovue", 320, "optovue_3mm"),
            (4.5, "optovue", 320, "small"),
            (6.0, "optovue", 320, "large"),
            (6.0, "", 1024, "large"),
            (4.5, "", 900, "large"),
            (4.5, "", 800, "small"),
        ]
        for scale, device, width, expected in cases:
            got = resolve_mnv_complexity_size_class(scale, device, image_width=width)
            self.assertEqual(
                got,
                expected,
                msg=f"scale={scale!r} device={device!r} width={width} → {got} (want {expected})",
            )


class TestRpdColumnsUnchanged(unittest.TestCase):
    def test_major_metrics_and_threshold(self):
        self.assertEqual(list(MAJOR_METRICS), LOCKED_MAJOR_METRICS)
        self.assertEqual(DEFAULT_RPD_PCT, 20.0)

    def test_source_literals_not_rewritten(self):
        src = (ROOT / "tools" / "reading_center_rpd" / "compute_adopted_from_dual_csv.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(src)
        found_metrics = None
        found_rpd = None
        for node in tree.body:
            if isinstance(node, ast.Assign):
                names = [t.id for t in node.targets if isinstance(t, ast.Name)]
                if "MAJOR_METRICS" in names and isinstance(node.value, ast.List):
                    found_metrics = [elt.value for elt in node.value.elts]
                if "DEFAULT_RPD_PCT" in names:
                    found_rpd = ast.literal_eval(node.value)
        self.assertEqual(found_metrics, LOCKED_MAJOR_METRICS)
        self.assertEqual(found_rpd, 20.0)


class TestLoginShowsUnifiedVersion(unittest.TestCase):
    def test_subtitle_uses_formatter(self):
        shared = (SRC / "flet_ui" / "components" / "shared.py").read_text(encoding="utf-8")
        self.assertTrue(
            re.search(r"APP_LOGIN_SUBTITLE = f\"Researcher Access.*format_app_version_label", shared)
        )


if __name__ == "__main__":
    unittest.main()
