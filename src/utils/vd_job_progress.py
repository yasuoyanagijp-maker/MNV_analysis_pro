"""In-memory VD analysis job progress (polled by Flet UI)."""

from __future__ import annotations

import threading
import uuid
from typing import Any, Dict, Optional


_lock = threading.Lock()
_jobs: Dict[str, Dict[str, Any]] = {}


def vd_progress_create(total: int = 0) -> str:
    job_id = str(uuid.uuid4())
    with _lock:
        _jobs[job_id] = {
            "status": "running",
            "current": 0,
            "total": max(int(total), 0),
            "message": "Starting VD analysis…",
            "result": None,
            "error": None,
        }
    return job_id


def vd_progress_set_total(job_id: str, total: int, message: str = "") -> None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        job["total"] = max(int(total), 1)
        if message:
            job["message"] = message


def vd_progress_update(job_id: str, current: int, message: str) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        job["current"] = int(current)
        if message:
            job["message"] = message


def vd_progress_complete(job_id: str, result: Any) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        job["status"] = "completed"
        job["current"] = job["total"]
        job["message"] = "VD analysis complete."
        job["result"] = result


def vd_progress_fail(job_id: str, error: str) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        job["status"] = "failed"
        job["error"] = error
        job["message"] = f"Failed: {error}"


def vd_progress_get(job_id: str) -> Optional[Dict[str, Any]]:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return None
        total = max(int(job.get("total") or 1), 1)
        current = min(max(int(job.get("current") or 0), 0), total)
        out = dict(job)
        out["current"] = current
        out["total"] = total
        out["percent"] = round(100.0 * current / total, 1)
        return out


def vd_progress_discard(job_id: str) -> None:
    with _lock:
        _jobs.pop(job_id, None)
