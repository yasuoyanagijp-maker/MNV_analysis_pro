#!/usr/bin/env python3
"""
CSV の PC1_raw から、中央値が 50 になるよう score_min / score_max を計算し、
complexity_ref_*.json を更新する。

L = max(median - min, max - median)
score_min = median - L
score_max = median + L
→ 全症例が範囲内、中央値が 50 に対応
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


def percentile(sorted_arr, p):
    if not sorted_arr:
        return float("nan")
    n = len(sorted_arr)
    k = (n - 1) * p / 100.0
    f = int(k)
    c = f + 1 if f + 1 < n else f
    if f == c:
        return sorted_arr[f]
    return sorted_arr[f] + (k - f) * (sorted_arr[c] - sorted_arr[f])


def main():
    for csv_name, ref_name in CSV_TO_REF.items():
        csv_path = CSV_DIR / csv_name
        ref_path = REF_DIR / ref_name
        if not csv_path.exists() or not ref_path.exists():
            print(f"Skip (not found): {csv_path} or {ref_path}")
            continue

        with open(ref_path, encoding="utf-8") as f:
            ref = json.load(f)

        mu = ref["mu"]
        sigma = ref["sigma"]
        pc1_w = ref["pc1_weights"]
        metrics = ref["metrics"]

        pc1_raw_list = []
        with open(csv_path, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                feats = row_to_features(r)
                z = {m: safe_z(feats.get(m), mu.get(m, 0), sigma.get(m, 1)) for m in metrics}
                pc1_raw = sum(z[m] * pc1_w.get(m, 0) for m in metrics)
                pc1_raw_list.append(pc1_raw)

        if not pc1_raw_list:
            print(f"Skip (no data): {csv_name}")
            continue

        pc1_sorted = sorted(pc1_raw_list)
        pmin = pc1_sorted[0]
        pmax = pc1_sorted[-1]
        pmedian = percentile(pc1_sorted, 50)

        L = max(pmedian - pmin, pmax - pmedian)
        new_score_min = pmedian - L
        new_score_max = pmedian + L

        ref["score_min"] = new_score_min
        ref["score_max"] = new_score_max

        with open(ref_path, "w", encoding="utf-8") as f:
            json.dump(ref, f, indent=2, ensure_ascii=False)

        print(f"Updated {ref_name}")
        print(f"  PC1_raw: min={pmin:.4f}, median={pmedian:.4f}, max={pmax:.4f}")
        print(f"  L={L:.4f}, score_min={new_score_min:.4f}, score_max={new_score_max:.4f}")
        print()


if __name__ == "__main__":
    main()
