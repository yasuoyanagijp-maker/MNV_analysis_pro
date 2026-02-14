import argparse
from pathlib import Path

from .io import save_results_table, scan_images
from .pipeline import process_file


def run_vd_analysis(input_dir, output_dir, params):
    files = scan_images(input_dir, pattern="*1.tif")
    print(f"[DEBUG] run_vd_analysis: found {len(files)} files")
    if len(files) > 0:
        print(f"[DEBUG] first file: {files[0]}")
    rows = []
    for f in files:
        r = process_file(f, output_dir, params)
        r["file"] = f
        rows.append(r)
    print(f"[DEBUG] run_vd_analysis: collected rows={len(rows)}")
    if len(rows) > 0:
        print(f"[DEBUG] run_vd_analysis: first row keys={list(rows[0].keys())}")
    save_results_table(rows, str(Path(output_dir) / "vd_results.csv"))


def run_mnv_analysis(input_dir, output_dir, params):
    files = scan_images(input_dir, pattern="*.tif")
    print(f"[DEBUG] run_mnv_analysis: found {len(files)} files")
    if len(files) > 0:
        print(f"[DEBUG] first file: {files[0]}")
    rows = []
    for f in files:
        r = process_file(f, output_dir, params)
        r["file"] = f
        rows.append(r)
    print(f"[DEBUG] run_mnv_analysis: collected rows={len(rows)}")
    if len(rows) > 0:
        print(f"[DEBUG] run_mnv_analysis: first row keys={list(rows[0].keys())}")
    save_results_table(rows, str(Path(output_dir) / "mnv_results.csv"))


def main():
    p = argparse.ArgumentParser(description="ARIAKE OCTA analysis (prototype)")
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--mode", choices=["vd", "mnv", "both"], default="both")
    p.add_argument("--scale-mm", type=float, default=6.0)
    args = p.parse_args()
    params = {"scale_mm": args.scale_mm}
    if args.mode in ("vd", "both"):
        run_vd_analysis(args.input, args.output, params)
    if args.mode in ("mnv", "both"):
        run_mnv_analysis(args.input, args.output, params)


if __name__ == "__main__":
    main()
