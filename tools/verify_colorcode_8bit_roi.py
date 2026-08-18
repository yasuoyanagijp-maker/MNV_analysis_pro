#!/usr/bin/env python3
"""Re-run MNV on color-coded visualization_rgb.png converted to 8-bit gray,
using each folder's debug_roi_mask.png as ROI. Compare loop vs LUT particle wipe.

Usage (from repo root):
  python tools/verify_colorcode_8bit_roi.py
  python tools/verify_colorcode_8bit_roi.py --size 1024
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MNV_ROOT = Path(r"C:\Users\Y\ARIAKE_OCTA_Data\output\mnv")


def _to_gray8(bgr: np.ndarray) -> np.ndarray:
    if bgr.ndim == 2:
        return bgr.astype(np.uint8)
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)


def _wipe_pair(src: np.ndarray, ref_fn, lut_fn) -> dict:
    t0 = time.perf_counter()
    a = ref_fn(src)
    t_ref = time.perf_counter() - t0
    t0 = time.perf_counter()
    b = lut_fn(src)
    t_lut = time.perf_counter() - t0
    equal = bool(a.shape == b.shape and np.array_equal(a, b))
    return {
        "equal": equal,
        "diff_px": 0 if equal else int(np.count_nonzero(a != b)),
        "ref_s": round(t_ref, 4),
        "lut_s": round(t_lut, 4),
        "fg_ref": int(np.count_nonzero(a)),
        "fg_lut": int(np.count_nonzero(b)),
        "src_fg": int(np.count_nonzero(src)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--size",
        type=int,
        default=0,
        help="If >0, upsample gray (linear) and ROI (nearest) to size×size.",
    )
    args = parser.parse_args()
    size = int(args.size)

    from utils.cv2_path import imread_bgr, imread_grayscale
    from core.preprocessing import BinaryPostProcessor, FilterBank
    from core.mnv_pipeline import (
        FILTER_PARAMS_LARGE,
        FILTER_PARAMS_SMALL,
        MNVPipeline,
        SMALL_IMAGE_THRESHOLD,
    )
    from core.vessel_detection import MNVPreprocessor

    suffix = f"_{size}" if size > 0 else ""
    out_path = ROOT / "scratch" / "bench_plan1" / f"colorcode_8bit_roi{suffix}.json"
    gray_dir = ROOT / "scratch" / "bench_plan1" / f"colorcode_8bit{suffix}"

    ref = BinaryPostProcessor.remove_small_particles_improved_ref
    lut = BinaryPostProcessor.remove_small_particles_improved
    gray_dir.mkdir(parents=True, exist_ok=True)

    cases = []
    folders = sorted(p for p in MNV_ROOT.iterdir() if p.is_dir())
    print(f"Found {len(folders)} MNV run folders under {MNV_ROOT}", flush=True)

    for folder in folders:
        vis = folder / "visualization_rgb.png"
        mask_p = folder / "debug_roi_mask.png"
        if not vis.is_file() or not mask_p.is_file():
            print(f"SKIP {folder.name}: missing vis or mask", flush=True)
            continue
        bgr = imread_bgr(str(vis))
        mask = imread_grayscale(str(mask_p))
        if bgr is None or mask is None:
            print(f"SKIP {folder.name}: read failed", flush=True)
            continue
        gray = _to_gray8(bgr)
        if mask.shape != gray.shape:
            mask = cv2.resize(
                mask, (gray.shape[1], gray.shape[0]), interpolation=cv2.INTER_NEAREST
            )
        if size > 0:
            gray = cv2.resize(gray, (size, size), interpolation=cv2.INTER_LINEAR)
            mask = cv2.resize(mask, (size, size), interpolation=cv2.INTER_NEAREST)
        gray_path = gray_dir / f"{folder.name}_gray8.png"
        ok, buf = cv2.imencode(".png", gray)
        if not ok:
            raise RuntimeError("imencode gray failed")
        gray_path.write_bytes(buf.tobytes())

        w = gray.shape[1]
        filter_params = dict(
            FILTER_PARAMS_SMALL if w < SMALL_IMAGE_THRESHOLD else FILTER_PARAMS_LARGE
        )
        pre = MNVPreprocessor(
            mexican_hat_sigma=1.0,
            tubeness_sigma=float(filter_params.get("sigma", 2.5)),
            filter_params=filter_params,
            use_parallel=False,
        )
        image_for_mex = cv2.medianBlur(gray, 3)
        mex = pre.filter_bank.mexican_hat_multiscale(
            image_for_mex,
            sigmas=(1.0, 1.5, 2.0),
            **{
                k: v
                for k, v in filter_params.items()
                if k in ("percentile_low", "percentile_high", "otsu_scale", "normalization")
            },
        )
        mex_morph = BinaryPostProcessor._despeckle_morphological(mex, erosion_size=3)
        tub_kwargs = {
            k: v
            for k, v in filter_params.items()
            if k
            in (
                "percentile_low",
                "percentile_high",
                "sauvola_k",
                "sigma",
                "beta",
                "c",
                "normalization",
            )
        }
        tub = FilterBank.tubeness_filter_accurate(gray, **tub_kwargs)
        tub_morph = BinaryPostProcessor._despeckle_morphological(tub, erosion_size=3)

        mex_cmp = _wipe_pair(mex_morph, ref, lut)
        tub_cmp = _wipe_pair(tub_morph, ref, lut)

        pipeline = MNVPipeline(
            scale_mm=6.0,
            save_stages=False,
            verbose=False,
            debug=False,
            enable_roi_refinement=False,
            filter_params=filter_params,
        )
        t0 = time.perf_counter()
        results = pipeline.analyze(
            str(gray_path),
            output_dir=str(gray_dir / folder.name),
            roi_mask=mask,
        )
        analyze_s = time.perf_counter() - t0
        binary = results.get("binary")
        roi_fg = int(np.count_nonzero(mask))
        vessel_in_roi = (
            int(np.count_nonzero((binary > 0) & (mask > 0))) if binary is not None else None
        )
        row = {
            "run_id": folder.name,
            "gray_shape": list(gray.shape),
            "roi_fg": roi_fg,
            "roi_coverage_pct": round(100.0 * roi_fg / gray.size, 2),
            "filter_set": "SMALL" if w < SMALL_IMAGE_THRESHOLD else "LARGE",
            "mex_wipe": mex_cmp,
            "tub_wipe": tub_cmp,
            "wipe_equal": bool(mex_cmp["equal"] and tub_cmp["equal"]),
            "analyze_s": round(analyze_s, 4),
            "timing": (
                pipeline._timer.as_dict() if getattr(pipeline, "_timer", None) else {}
            ),
            "mnv_area_mm2": float(results.get("mnv_area_mm2") or 0),
            "vessel_area_mm2": float(results.get("vessel_area_mm2") or 0),
            "vessel_density": float(results.get("vessel_density") or 0),
            "vessel_in_roi_px": vessel_in_roi,
        }
        cases.append(row)
        print(
            f"{folder.name[:8]}  {gray.shape[1]}x{gray.shape[0]}  "
            f"wipe_equal={row['wipe_equal']}  "
            f"mex_diff={mex_cmp['diff_px']} tub_diff={tub_cmp['diff_px']}  "
            f"tub_ref={tub_cmp['ref_s']:.3f}s lut={tub_cmp['lut_s']:.3f}s  "
            f"VD={row['vessel_density']*100:.2f}%  analyze={analyze_s:.2f}s",
            flush=True,
        )

    all_equal = all(c["wipe_equal"] for c in cases) if cases else False
    report = {
        "source": str(MNV_ROOT),
        "upsample_px": size,
        "n_cases": len(cases),
        "all_wipe_equal": all_equal,
        "cases": cases,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nALL_WIPE_EQUAL={all_equal}  n={len(cases)}  upsample={size}", flush=True)
    print(f"Wrote {out_path}", flush=True)
    return 0 if all_equal else 1


if __name__ == "__main__":
    raise SystemExit(main())
