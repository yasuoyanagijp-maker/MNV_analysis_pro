"""Command-line entry for PDR NVE before/after analysis."""

from __future__ import annotations

import argparse
import sys

from ._paths import ensure_import_paths

ensure_import_paths()

from .pipeline import PdrNveConfig, analyze_pair  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m ariake_octa.pdr_nve",
        description=(
            "PDR NVE/NVD analysis on 15×15 mm OCTA en-face pairs. "
            "Writes RAW metrics only (no MNV standardized scores / maturity index)."
        ),
    )
    p.add_argument("--before", required=True, help="Before-treatment OCTA (png/tif/bmp)")
    p.add_argument("--after", required=True, help="After-treatment OCTA (png/tif/bmp)")
    p.add_argument("--output", required=True, help="Output directory")
    p.add_argument("--case-id", default="case", help="Prefix for output files")
    p.add_argument("--scan-size-mm", type=float, default=15.0, help="Scan width in mm")
    p.add_argument(
        "--pixel-width",
        type=int,
        default=None,
        help="Pixel width used for um/px (default: image width)",
    )
    p.add_argument(
        "--um-per-px",
        type=float,
        default=None,
        help="Override µm/pixel (otherwise scan-size-mm / pixel-width)",
    )
    p.add_argument(
        "--roi-mask",
        default=None,
        help="Optional freeform ROI mask PNG (nonzero = keep)",
    )
    p.add_argument(
        "--roi-polygon",
        default=None,
        help="Optional polygon JSON/CSV of (x,y) vertices in before-image pixels",
    )
    p.add_argument(
        "--roi-mode",
        choices=["auto", "full", "mask", "polygon"],
        default="auto",
        help="ROI source when --roi-mask/--roi-polygon are omitted (default: auto)",
    )
    p.add_argument(
        "--no-register",
        action="store_true",
        help="Skip after→before registration (pair already aligned)",
    )
    p.add_argument(
        "--register-before",
        action="append",
        default=None,
        metavar="PATH",
        help=(
            "Slab used only to estimate the after→before transform "
            "(repeat for several slabs). Prefer Retina, VRI+Retina Global, "
            "or every exported slab — same idea as stack_reg Image 5 average. "
            "Must pair with --register-after."
        ),
    )
    p.add_argument(
        "--register-after",
        action="append",
        default=None,
        metavar="PATH",
        help="Matching after-treatment slab(s) for --register-before.",
    )
    p.add_argument(
        "--register-combine",
        choices=["mean", "sum", "max"],
        default="mean",
        help="How to merge --register-before/--register-after slabs (default: mean)",
    )
    p.add_argument(
        "--no-trim-border",
        action="store_true",
        help="Do not crop common near-black export borders",
    )
    p.add_argument(
        "--no-trim-roi",
        action="store_true",
        help="Do not apply the existing 余白trim (border-touching blank padding)",
    )
    p.add_argument(
        "--exclude-disc",
        action="store_true",
        help="Try to punch out a compact optic-disc circle from the ROI",
    )
    p.add_argument(
        "--no-large-vessel-filter",
        action="store_true",
        help="Do not build a large-caliber mask (metrics still report both series)",
    )
    p.add_argument(
        "--large-vessel-um",
        type=float,
        default=100.0,
        help="Diameter threshold (µm) for the large-vessel mask (default: 100)",
    )
    p.add_argument(
        "--segment-mode",
        choices=["mnv", "adaptive"],
        default="mnv",
        help="Vessel segmentation: reuse MNV preprocessor, or CLAHE+Li fallback",
    )
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    cfg = PdrNveConfig(
        case_id=args.case_id,
        scan_size_mm=args.scan_size_mm,
        pixel_width_px=args.pixel_width,
        um_per_px=args.um_per_px,
        roi_mode=args.roi_mode,
        roi_mask_path=args.roi_mask,
        roi_polygon_path=args.roi_polygon,
        register=not args.no_register,
        register_before_paths=args.register_before,
        register_after_paths=args.register_after,
        register_combine=args.register_combine,
        trim_blank_border=not args.no_trim_border,
        trim_roi_margin=not args.no_trim_roi,
        exclude_disc=args.exclude_disc,
        exclude_large_vessels=not args.no_large_vessel_filter,
        large_vessel_um=args.large_vessel_um,
        segment_mode=args.segment_mode,
        output_dir=args.output,
    )
    result = analyze_pair(args.before, args.after, cfg)
    rec = result.record
    print(f"Wrote {result.paths.get('metrics_csv')}")
    print(
        f"  um/px={rec['um_per_px']:.4f}  roi={rec['roi_mode']}  "
        f"reg_cc={rec['registration_cc']:.3f}  "
        f"persistent={rec.get('registration_cc_persistent', float('nan')):.3f}  "
        f"({rec['registration_method']}, ref={rec.get('registration_reference')})"
    )
    print(
        f"  vessel_area_density  before={rec['before_vessel_area_density']:.4f}  "
        f"after={rec['after_vessel_area_density']:.4f}  "
        f"pct={rec['pct_vessel_area_density']}"
    )
    print(
        f"  fractal_dimension    before={rec['before_fractal_dimension']:.4f}  "
        f"after={rec['after_fractal_dimension']:.4f}  "
        f"pct={rec['pct_fractal_dimension']}"
    )
    print(f"  flags: {rec['quality_flags'] or '(none)'}")
    print(f"  exclude_suggested: {rec['exclude_suggested']}")
    print("  images:")
    for key in (
        "overlay_qa",
        "before_rgb",
        "after_rgb",
        "before_vessel_mask",
        "after_vessel_mask",
        "before_roi_mask",
        "after_roi_mask",
        "before_vessel_mask_no_large",
        "after_vessel_mask_no_large",
    ):
        if key in result.paths:
            print(f"    {key}: {result.paths[key]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
