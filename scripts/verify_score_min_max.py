#!/usr/bin/env python3
"""
complexity_ref_*.json の score_min / score_max が、
CSV データから算出した PC1_raw の範囲と整合しているか確認する。
PC1_raw = Σ(Z × pc1_weights)、Z = (value - mu) / sigma
"""

import csv
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CSV_DIR = PROJECT_ROOT / "csv"
REF_DIR = PROJECT_ROOT / "resources" / "reference_metrics"

CSV_TO_REF = {
    "MNV_batch_20260220_230245_large.csv": "complexity_ref_large.json",
    "MNV_batch_20260220_083448small.csv": "complexity_ref_small.json",
    "MNV_batch_20260220_223647_small_3mm.csv": "complexity_ref_small_3mm.json",
}


def num(s):
    if s is None or s == "":
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def row_to_features(row):
    ce = num(row.get("Center Euler Number"))
    pe = num(row.get("Periphery Euler Number"))
    cl = num(row.get("Center Loop Number"))
    pl = num(row.get("Periphery Loop Number"))
    jd = num(row.get("Junction Density (n/mm)"))
    fd = num(row.get("Fractal Dim"))
    euler = -(ce + pe) if (ce is not None and pe is not None) else None
    loop = (cl + pl) if (cl is not None and pl is not None) else None
    return {"euler_total_inv": euler, "loop_total": loop, "junction_density": jd, "FD_global": fd}


def safe_z(val, mu, sigma):
    if val is None or sigma is None or sigma <= 0:
        return 0.0
    return (float(val) - float(mu)) / float(sigma)


def main():
    for csv_name, ref_name in CSV_TO_REF.items():
        csv_path = CSV_DIR / csv_name
        ref_path = REF_DIR / ref_name
        if not csv_path.exists() or not ref_path.exists():
            continue
        with open(ref_path, encoding="utf-8") as f:
            ref = json.load(f)
        mu = ref["mu"]
        sigma = ref["sigma"]
        pc1_w = ref["pc1_weights"]
        metrics = ref["metrics"]
        score_min = ref["score_min"]
        score_max = ref["score_max"]
        pc1_raw_list = []
        with open(csv_path, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                feats = row_to_features(r)
                z = {m: safe_z(feats.get(m), mu.get(m, 0), sigma.get(m, 1)) for m in metrics}
                pc1_raw = sum(z[m] * pc1_w.get(m, 0) for m in metrics)
                pc1_raw_list.append(pc1_raw)
        if not pc1_raw_list:
            continue
        csv_min = min(pc1_raw_list)
        csv_max = max(pc1_raw_list)
        n = len(pc1_raw_list)
        below = sum(1 for x in pc1_raw_list if x < score_min)
        above = sum(1 for x in pc1_raw_list if x > score_max)
        in_range = sum(1 for x in pc1_raw_list if score_min <= x <= score_max)
        print(f"\n=== {ref_name} ===")
        print(f"  ref: score_min={score_min:.4f}, score_max={score_max:.4f}")
        print(f"  CSV PC1_raw: min={csv_min:.4f}, max={csv_max:.4f}, n={n}")
        print(f"  PC1_raw < score_min: {below}件, > score_max: {above}件, in [min,max]: {in_range}件")
        if csv_min >= score_min and csv_max <= score_max:
            print("  => OK: CSVのPC1_rawはすべて[score_min, score_max]内")
        else:
            print("  => 要確認: CSVのPC1_rawがrefの範囲外")
        if csv_min < score_min:
            print(f"      score_minを{min(csv_min, score_min) - 0.1:.2f}程度に下げると全件含まれる可能性")
        if csv_max > score_max:
            print(f"      score_maxを{max(csv_max, score_max) + 0.1:.2f}程度に上げると全件含まれる可能性")


if __name__ == "__main__":
    main()
