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
        self.assertIn("applicationShouldTerminate:", text)
        self.assertIn("_NS_TERMINATE_CANCEL", text)
        self.assertIn("_mac_request_clean_quit", text)
        self.assertIn("applicationShouldHandleReopen:hasVisibleWindows:", text)
        self.assertIn("com.appveyor.flet", text)
        self.assertIn("def _mac_allow_signal_off_main", text)
        self.assertIn("signal only works in main thread", text)
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

    def test_clean_quit_sets_event_without_appkit(self):
        import wrapper

        wrapper._MAC_QUIT.clear()
        wrapper._mac_request_clean_quit()
        self.assertTrue(wrapper._MAC_QUIT.is_set())
        wrapper._MAC_QUIT.clear()
        wrapper._mac_terminate_flet_view()
        wrapper._mac_activate_flet_view()

    def test_build_script_smoke_mentions_helper(self):
        mac = (ROOT / "build_mac.sh").read_text(encoding="utf-8")
        self.assertIn("_mac_signal_nsapp_launched", mac)
        self.assertIn("signal only works in main thread", mac)
        self.assertIn("Starting Flet", mac)

    def test_signal_patch_allows_worker_thread(self):
        import asyncio
        import signal
        import threading

        import wrapper

        wrapper._mac_allow_signal_off_main()
        err = []

        def _worker():
            async def _app_async():
                # Flet 0.28 flet/app.py app_async
                signal.signal(signal.SIGINT, lambda *_a: None)
                return True

            try:
                asyncio.run(_app_async())
            except ValueError as exc:
                err.append(str(exc))

        t = threading.Thread(target=_worker, name="flet-signal-test")
        t.start()
        t.join(timeout=5)
        self.assertEqual(err, [])


if __name__ == "__main__":
    unittest.main()
