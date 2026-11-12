"""Dock bounce: PyInstaller .app never finishes NSApplication; Flet opens Flet.app."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestMacDockBounceFix(unittest.TestCase):
    def test_wrapper_signals_nsapplication_on_darwin(self):
        text = (ROOT / "wrapper.py").read_text(encoding="utf-8")
        self.assertIn("def _mac_signal_nsapp_launched", text)
        self.assertIn("def _mac_pump_main_until", text)
        self.assertIn("_run_on_worker_pump_main", text)
        self.assertIn("flet-frontend", text)
        self.assertIn("finishLaunching", text)
        self.assertIn("setActivationPolicy:", text)
        self.assertIn("open Flet.app", text)
        self.assertIn("Every click", text)
        self.assertIn("_mac_signal_nsapp_launched()", text)
        self.assertNotRegex(text, r'"LSUIElement"\s*:')
        self.assertNotRegex(text, r'"LSBackgroundOnly"\s*:')

    def test_mac_specs_are_cocoa_apps_not_agents(self):
        for name in (
            "ARIAKE_OCTA.spec",
            "ARIAKE_OCTA_arm64.spec",
            "ARIAKE_OCTA_x86_64.spec",
        ):
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn('"NSPrincipalClass": "NSApplication"', text)
            self.assertIn("argv_emulation=False", text)
            self.assertNotRegex(text, r'"LSUIElement"\s*:')
            self.assertNotRegex(text, r'"LSBackgroundOnly"\s*:')

    def test_non_darwin_helper_is_noop(self):
        import wrapper

        self.assertFalse(wrapper._mac_signal_nsapp_launched(pump=False))
        self.assertEqual(wrapper._run_on_worker_pump_main(lambda: 7, "t"), 7)

    def test_build_script_smoke_mentions_helper(self):
        mac = (ROOT / "build_mac.sh").read_text(encoding="utf-8")
        self.assertIn("_mac_signal_nsapp_launched", mac)


if __name__ == "__main__":
    unittest.main()
