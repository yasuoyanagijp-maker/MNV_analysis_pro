"""macOS frozen apps must not spawn the API child (codesign kill)."""

from __future__ import annotations

import threading

import wrapper


def test_macos_backend_uses_thread(monkeypatch):
    monkeypatch.setattr(wrapper.sys, "platform", "darwin")
    seen = {}

    def fake_run(port):
        seen["port"] = port

    monkeypatch.setattr(wrapper, "run_api_server", fake_run)
    worker = wrapper._start_backend(18001)
    assert isinstance(worker, threading.Thread)
    worker.join(timeout=2)
    assert seen["port"] == 18001
    assert not worker.is_alive()


def test_non_darwin_backend_uses_process(monkeypatch):
    monkeypatch.setattr(wrapper.sys, "platform", "win32")

    class _FakeProc:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.started = False

        def start(self):
            self.started = True

        def is_alive(self):
            return self.started

    monkeypatch.setattr(wrapper.multiprocessing, "Process", _FakeProc)
    worker = wrapper._start_backend(18002)
    assert isinstance(worker, _FakeProc)
    assert worker.started is True
    assert worker.kwargs.get("daemon") is True
