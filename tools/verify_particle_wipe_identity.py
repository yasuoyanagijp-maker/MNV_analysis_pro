#!/usr/bin/env python3
"""Prove LUT particle wipe matches the previous Python loop (bitwise).

Usage (from repo root):
  python tools/verify_particle_wipe_identity.py --image path/to.tif
  ARIAKE_VERIFY_IMAGE=path/to.tif python tools/verify_particle_wipe_identity.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_IMAGE = (
    r"C:\Users\Y\OneDrive - Yokohama City University\デスクトップ"
    r"\normal_sample_folder\999-99-9999_20240729_101347_Angio (3)_R_001.tif"
)


def _default_image() -> Path:
    env = (os.environ.get("ARIAKE_VERIFY_IMAGE") or "").strip()
    if env:
        return Path(env)
    return Path(DEFAULT_IMAGE)


def _load_gray(path: Path):
    from utils.cv2_path import imread_grayscale
    from utils.image_utils import ImageProcessor

    img = imread_grayscale(str(path))
    if img is None:
        proc = ImageProcessor()
        img = proc.load_image(str(path), as_gray=True)
        img = proc.ensure_8bit(img)
    else:
        proc = ImageProcessor()
        img = proc.ensure_8bit(img)
    return img


def _compare(name: str, src, ref_fn, lut_fn) -> dict:
    t0 = time.perf_counter()
    a = ref_fn(src)
    t_ref = time.perf_counter() - t0
    t0 = time.perf_counter()
    b = lut_fn(src)
    t_lut = time.perf_counter() - t0
    equal = bool(a.shape == b.shape and (a == b).all())
    n_diff = 0 if equal else int((a != b).sum())
    print(
        f"  {name}: equal={equal}  diff_px={n_diff}  "
        f"ref={t_ref:.3f}s  lut={t_lut:.3f}s  "
        f"fg_ref={int((a > 0).sum())}  fg_lut={int((b > 0).sum())}",
        flush=True,
    )
    return {
        "name": name,
        "equal": equal,
        "diff_px": n_diff,
        "ref_s": round(t_ref, 4),
        "lut_s": round(t_lut, 4),
        "fg_ref": int((a > 0).sum()),
        "fg_lut": int((b > 0).sum()),
        "src_fg": int((src > 0).sum()),
        "src_shape": list(src.shape),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--image", type=Path, default=_default_image())
    p.add_argument(
        "--out",
        type=Path,
        default=ROOT / "scratch" / "bench_plan1" / "particle_wipe_identity.json",
    )
    args = p.parse_args()

    from core.preprocessing import BinaryPostProcessor, FilterBank
    from core.mnv_pipeline import MNVPipeline, SMALL_IMAGE_THRESHOLD, FILTER_PARAMS_SMALL, FILTER_PARAMS_LARGE
    from core.vessel_detection import MNVPreprocessor

    ref = BinaryPostProcessor.remove_small_particles_improved_ref
    lut = BinaryPostProcessor.remove_small_particles_improved

    if not args.image.is_file():
        print(f"IMAGE MISSING: {args.image}", flush=True)
        return 2

    print(f"Loading {args.image}", flush=True)
    t0 = time.perf_counter()
    image = _load_gray(args.image)
    print(
        f"  loaded {image.shape} dtype={image.dtype} in {time.perf_counter()-t0:.2f}s",
        flush=True,
    )

    w = image.shape[1]
    filter_params = dict(
        FILTER_PARAMS_SMALL if w < SMALL_IMAGE_THRESHOLD else FILTER_PARAMS_LARGE
    )
    pre = MNVPreprocessor(
        mexican_hat_sigma=1.0,
        tubeness_sigma=float(filter_params.get("sigma", 2.5)),
        filter_params=filter_params,
        use_parallel=False,
    )

    print("Building Mexican Hat / Tubeness binaries (before particle wipe)...", flush=True)
    t0 = time.perf_counter()
    image_for_mex = __import__("cv2").medianBlur(image, 3)
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
    print(f"  mex+morph {time.perf_counter()-t0:.2f}s fg={int((mex_morph>0).sum())}", flush=True)

    t0 = time.perf_counter()
    tub = FilterBank.tubeness_filter_accurate(
        image,
        **{
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
        },
    )
    tub_morph = BinaryPostProcessor._despeckle_morphological(tub, erosion_size=3)
    print(f"  tub+morph {time.perf_counter()-t0:.2f}s fg={int((tub_morph>0).sum())}", flush=True)

    checks = []
    print("Identity checks (loop ref vs LUT):", flush=True)
    checks.append(_compare("mex_hat_after_morph", mex_morph, ref, lut))
    checks.append(_compare("tubeness_after_morph", tub_morph, ref, lut))

    rng = __import__("numpy").random.default_rng(0)
    noise = (rng.random(image.shape) > 0.92).astype("uint8") * 255
    checks.append(_compare("random_speckle", noise, ref, lut))

    all_equal = all(c["equal"] for c in checks)
    print(f"\nALL_EQUAL={all_equal}", flush=True)

    print("\nFull MNV pipeline (LUT in production path)...", flush=True)
    out_dir = args.out.parent / "mnv_clinical_lut"
    pipeline = MNVPipeline(
        scale_mm=6.0,
        save_stages=False,
        verbose=True,
        debug=False,
        enable_roi_refinement=False,
        filter_params=filter_params,
    )
    t0 = time.perf_counter()
    results = pipeline.analyze(str(args.image), output_dir=str(out_dir))
    analyze_s = time.perf_counter() - t0
    binary = results.get("binary")
    report = {
        "image": str(args.image),
        "shape": list(image.shape),
        "filter_params": filter_params,
        "all_equal": all_equal,
        "checks": checks,
        "analyze_s": round(analyze_s, 4),
        "timing": getattr(pipeline, "_timer", None).as_dict()
        if getattr(pipeline, "_timer", None)
        else {},
        "vessel_density": float(results.get("vessel_density") or 0),
        "mnv_area_mm2": float(results.get("mnv_area_mm2") or 0),
        "vessel_area_mm2": float(results.get("vessel_area_mm2") or 0),
        "binary_fg": int((binary > 0).sum()) if binary is not None else None,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {args.out}", flush=True)
    return 0 if all_equal else 1


if __name__ == "__main__":
    raise SystemExit(main())
