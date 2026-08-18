"""Lightweight step timer for analysis pipelines."""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from typing import Dict, Iterator, List, Tuple


class StepTimer:
    def __init__(self) -> None:
        self.records: List[Tuple[str, float]] = []

    @contextmanager
    def measure(self, name: str) -> Iterator[None]:
        t0 = time.perf_counter()
        try:
            yield
        finally:
            self.records.append((name, time.perf_counter() - t0))

    def record(self, name: str, seconds: float) -> None:
        self.records.append((name, float(seconds)))

    def as_dict(self) -> Dict[str, float]:
        """Seconds per step name. Duplicate names are summed, then rounded."""
        out: Dict[str, float] = {}
        for name, sec in self.records:
            out[name] = out.get(name, 0.0) + float(sec)
        return {name: round(sec, 4) for name, sec in out.items()}

    def summary_lines(self) -> List[str]:
        rows = self.as_dict()
        if not rows:
            return ["(no timings)"]
        width = max(len(k) for k in rows)
        lines = [f"{'step':<{width}}  seconds"]
        lines.append("-" * (width + 10))
        for name, sec in rows.items():
            lines.append(f"{name:<{width}}  {sec:7.3f}")
        return lines

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False)
