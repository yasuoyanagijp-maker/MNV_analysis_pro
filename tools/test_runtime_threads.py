"""Tests for Plan-1 thread pinning (opt-in, setdefault)."""

from __future__ import annotations

import os

from src.utils.runtime_threads import apply_plan1_env, plan1_requested, use_filter_parallel
from src.utils.step_timer import StepTimer


def test_plan1_unset_is_off(monkeypatch):
    monkeypatch.delenv("ARIAKE_WIN_PERF_PLAN1", raising=False)
    assert plan1_requested() is False
    assert use_filter_parallel() is True


def test_plan1_explicit_on(monkeypatch):
    monkeypatch.setenv("ARIAKE_WIN_PERF_PLAN1", "1")
    assert plan1_requested() is True
    assert use_filter_parallel() is False


def test_plan1_explicit_off(monkeypatch):
    monkeypatch.setenv("ARIAKE_WIN_PERF_PLAN1", "0")
    assert plan1_requested() is False
    assert use_filter_parallel() is True


def test_apply_plan1_noop_when_disabled(monkeypatch):
    monkeypatch.delenv("ARIAKE_WIN_PERF_PLAN1", raising=False)
    monkeypatch.delenv("OMP_NUM_THREADS", raising=False)
    info = apply_plan1_env()
    assert info["enabled"] is False
    assert "OMP_NUM_THREADS" not in os.environ


def test_apply_plan1_does_not_overwrite_user_omp(monkeypatch):
    monkeypatch.setenv("ARIAKE_WIN_PERF_PLAN1", "1")
    monkeypatch.setenv("OMP_NUM_THREADS", "8")
    monkeypatch.delenv("OPENBLAS_NUM_THREADS", raising=False)
    info = apply_plan1_env()
    assert info["enabled"] is True
    assert os.environ["OMP_NUM_THREADS"] == "8"
    assert os.environ["OPENBLAS_NUM_THREADS"] == "1"


def test_step_timer_as_dict_sums_duplicate_names():
    timer = StepTimer()
    timer.record("a", 0.1)
    timer.record("a", 0.2)
    timer.record("b", 0.3)
    rows = timer.as_dict()
    assert rows["a"] == 0.3
    assert rows["b"] == 0.3
