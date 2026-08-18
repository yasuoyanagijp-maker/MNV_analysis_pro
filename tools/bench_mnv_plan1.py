#!/usr/bin/env python3
"""A/B bench: current MNV pipeline vs plan-1 thread/BLAS pin.

Runs each mode in a fresh process so OpenBLAS/OpenMP env vars bind before
numpy import.

Usage (from repo root):
  python tools/bench_mnv_plan1.py
  python tools/bench_mnv_plan1.py --reps 2 --size 1024
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRATCH = ROOT / "scratch" / "bench_plan1"


def _make_synth(path: Path, size: int, seed: int = 0) -> Path:
    import cv2
    import numpy as np

    rng = np.random.default_rng(seed)
    img = np.full((size, size), 18, dtype=np.uint8)
    center = (size // 2, size // 2)
    cv2.circle(img, center, size // 3, 40, -1)
    for _ in range(55):
        x1, y1 = rng.integers(80, size - 80, size=2)
        x2, y2 = rng.integers(80, size - 80, size=2)
        color = int(rng.integers(90, 200))
        thick = int(rng.integers(1, 4))
        cv2.line(img, (int(x1), int(y1)), (int(x2), int(y2)), color, thick)
    img = cv2.GaussianBlur(img, (0, 0), 0.9)
    noise = rng.integers(0, 22, (size, size), dtype=np.int16)
    img = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise RuntimeError("failed to encode synthetic image")
    path.write_bytes(buf.tobytes())

    roi = np.zeros((size, size), dtype=np.uint8)
    cv2.circle(roi, center, size // 3, 255, -1)
    roi_path = path.with_name(path.stem + "_roi.png")
    ok, buf = cv2.imencode(".png", roi)
    if not ok:
        raise RuntimeError("failed to encode ROI")
    roi_path.write_bytes(buf.tobytes())
    return path


def _run_worker(plan1: bool, image: Path, roi: Path, out_dir: Path) -> dict:
    env = os.environ.copy()
    env["ARIAKE_WIN_PERF_PLAN1"] = "1" if plan1 else "0"
    env["PYTHONUNBUFFERED"] = "1"
    cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        "--image",
        str(image),
        "--roi",
        str(roi),
        "--out",
        str(out_dir),
    ]
    t0 = time.perf_counter()
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    wall = time.perf_counter() - t0
    timing_path = out_dir / "aria_timing.json"
    timing = {}
    if timing_path.is_file():
        timing = json.loads(timing_path.read_text(encoding="utf-8"))
    else:
        for line in (proc.stdout or "").splitlines():
            if line.startswith("[ARIAKE timing json] "):
                timing = json.loads(line.split(" ", 3)[-1])
                break
    if proc.returncode != 0:
        err_tail = (proc.stderr or proc.stdout or "")[-4000:]
        raise RuntimeError(
            f"worker plan1={plan1} exit {proc.returncode}\n{err_tail}"
        )
    return {
        "plan1": plan1,
        "returncode": proc.returncode,
        "wall_s": round(wall, 4),
        "timing": timing,
        "stdout_tail": (proc.stdout or "")[-1500:],
    }


def _worker_main(image: Path, roi: Path, out_dir: Path) -> None:
    src = ROOT / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    from utils.runtime_threads import apply_plan1_env, apply_plan1_imported_libs

    env_info = apply_plan1_env()
    from core.mnv_pipeline import MNVPipeline
    import cv2
    from utils.cv2_path import imread_grayscale

    lib_info = apply_plan1_imported_libs()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "plan1_env.json").write_text(
        json.dumps({"env": env_info, "libs": lib_info}, indent=2),
        encoding="utf-8",
    )

    roi_mask = imread_grayscale(str(roi))
    if roi_mask is None:
        roi_mask = cv2.imread(str(roi), cv2.IMREAD_GRAYSCALE)
    pipeline = MNVPipeline(
        scale_mm=6.0,
        save_stages=False,
        verbose=True,
        debug=False,
        enable_roi_refinement=False,
    )
    pipeline.analyze(
        str(image),
        output_dir=str(out_dir),
        roi_mask=roi_mask,
    )


def _mean_timings(runs: list[dict]) -> dict:
    keys = set()
    for r in runs:
        keys.update((r.get("timing") or {}).keys())
    out = {}
    for k in sorted(keys):
        vals = [float((r.get("timing") or {}).get(k, 0.0)) for r in runs]
        out[k] = round(sum(vals) / len(vals), 4)
    walls = [float(r["wall_s"]) for r in runs]
    out["wall_s"] = round(sum(walls) / len(walls), 4)
    return out


def _orchestrate(args: argparse.Namespace) -> None:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    image = SCRATCH / f"synth_{args.size}.png"
    _make_synth(image, args.size)
    roi = image.with_name(image.stem + "_roi.png")

    print("=== warmup (discarded) ===", flush=True)
    _run_worker(False, image, roi, SCRATCH / "warmup")

    baseline_runs = []
    plan1_runs = []
    for i in range(args.reps):
        print(f"=== baseline rep {i + 1}/{args.reps} ===", flush=True)
        out = SCRATCH / f"baseline_r{i + 1}"
        baseline_runs.append(_run_worker(False, image, roi, out))
        print(
            f"  total={baseline_runs[-1]['timing'].get('total')}s "
            f"wall={baseline_runs[-1]['wall_s']}s",
            flush=True,
        )
    for i in range(args.reps):
        print(f"=== plan1 rep {i + 1}/{args.reps} ===", flush=True)
        out = SCRATCH / f"plan1_r{i + 1}"
        plan1_runs.append(_run_worker(True, image, roi, out))
        print(
            f"  total={plan1_runs[-1]['timing'].get('total')}s "
            f"wall={plan1_runs[-1]['wall_s']}s",
            flush=True,
        )

    base_mean = _mean_timings(baseline_runs)
    plan_mean = _mean_timings(plan1_runs)
    delta = {}
    speedup = {}
    for k in sorted(set(base_mean) | set(plan_mean)):
        b = base_mean.get(k, 0.0)
        p = plan_mean.get(k, 0.0)
        delta[k] = round(p - b, 4)
        speedup[k] = round(b / p, 3) if p > 1e-6 else None

    report = {
        "host": {
            "python": sys.version,
            "platform": sys.platform,
            "size_px": args.size,
            "reps": args.reps,
            "image": str(image),
        },
        "baseline_runs": baseline_runs,
        "plan1_runs": plan1_runs,
        "baseline_mean_s": base_mean,
        "plan1_mean_s": plan_mean,
        "delta_plan1_minus_baseline_s": delta,
        "speedup_baseline_over_plan1": speedup,
    }
    out_json = SCRATCH / "comparison.json"
    out_json.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\n=== mean seconds ===", flush=True)
    keys = ["total", "wall_s", "step2_preprocess", "step2_tubeness", "step3_skeleton"]
    for k in keys:
        if k in base_mean or k in plan_mean:
            print(
                f"{k:24s}  baseline={base_mean.get(k, 0):7.3f}  "
                f"plan1={plan_mean.get(k, 0):7.3f}  "
                f"delta={delta.get(k, 0):+7.3f}  "
                f"x{speedup.get(k)}",
                flush=True,
            )
    print(f"\nWrote {out_json}", flush=True)


def main() -> None:
    p = argparse.ArgumentParser(description="MNV plan-1 A/B bench")
    p.add_argument("--worker", action="store_true")
    p.add_argument("--image", type=Path)
    p.add_argument("--roi", type=Path)
    p.add_argument("--out", type=Path)
    p.add_argument("--reps", type=int, default=2)
    p.add_argument("--size", type=int, default=1024)
    args = p.parse_args()
    if args.worker:
        if not args.image or not args.roi or not args.out:
            raise SystemExit("--worker requires --image --roi --out")
        _worker_main(args.image, args.roi, args.out)
        return
    _orchestrate(args)


if __name__ == "__main__":
    main()
