#!/usr/bin/env python3
"""
PC1_score の分布を確認:
- 基本統計量（mean, median, std, min, max）
- パーセンタイル（P10, P25, P40, P50, P60, P65, P75, P90）
- 偏り（skewness）、外れ値（IQR法）
- 正規性の簡易確認
"""

import csv
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CSV_DIR = PROJECT_ROOT / "csv"
REF_DIR = PROJECT_ROOT / "resources" / "reference_metrics"

CSV_TO_REF = {
    "MNV_batch_20260220_230245_large.csv": ("large", "complexity_ref_large.json"),
    "MNV_batch_20260220_083448small.csv": ("small", "complexity_ref_small.json"),
    "MNV_batch_20260220_223647_small_3mm.csv": ("small_3mm", "complexity_ref_small_3mm.json"),
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


def clip(x, lo, hi):
    return max(lo, min(hi, x))


def skewness(arr):
    """標本歪度 (Fisher-Pearson)"""
    n = len(arr)
    if n < 3:
        return float("nan")
    mean = sum(arr) / n
    m2 = sum((x - mean) ** 2 for x in arr) / n
    m3 = sum((x - mean) ** 3 for x in arr) / n
    if m2 <= 0:
        return 0.0
    return m3 / (m2 ** 1.5)


def main():
    for csv_name, (size_key, ref_name) in CSV_TO_REF.items():
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
        score_min = float(ref["score_min"])
        score_max = float(ref["score_max"])
        score_span = score_max - score_min

        pc1_raw_list = []
        pc1_score_list = []
        with open(csv_path, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                feats = row_to_features(r)
                z = {m: safe_z(feats.get(m), mu.get(m, 0), sigma.get(m, 1)) for m in metrics}
                pc1_raw = sum(z[m] * pc1_w.get(m, 0) for m in metrics)
                pc1_score = clip(100.0 * (pc1_raw - score_min) / score_span, 0, 100)
                pc1_raw_list.append(pc1_raw)
                pc1_score_list.append(pc1_score)

        pc1_sorted = sorted(pc1_score_list)
        n = len(pc1_sorted)
        mean = sum(pc1_sorted) / n
        median = percentile(pc1_sorted, 50)
        var = sum((x - mean) ** 2 for x in pc1_sorted) / n
        std = var ** 0.5

        # IQR 法で外れ値
        q1 = percentile(pc1_sorted, 25)
        q3 = percentile(pc1_sorted, 75)
        iqr = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        outliers_low = [x for x in pc1_sorted if x < lower]
        outliers_high = [x for x in pc1_sorted if x > upper]

        sk = skewness(pc1_sorted)

        print(f"\n{'='*60}")
        print(f"  {ref_name} / {size_key}  (n={n})")
        print("=" * 60)
        print("\n【PC1_raw と score_min/score_max】")
        raw_min, raw_max = min(pc1_raw_list), max(pc1_raw_list)
        raw_median = percentile(sorted(pc1_raw_list), 50)
        print(f"  PC1_raw:  min={raw_min:.4f}, median={raw_median:.4f}, max={raw_max:.4f}")
        print(f"  ref:      score_min={score_min:.4f}, score_max={score_max:.4f}")
        print(f"  中央値の位置: (median - min)/(max - min) = {(raw_median - raw_min)/(raw_max - raw_min):.2%}")
        print(f"  ref範囲での位置: (median - score_min)/(score_max - score_min) = {(raw_median - score_min)/score_span:.2%}")

        print("\n【PC1_score 基本統計量】")
        print(f"  min={pc1_sorted[0]:.2f}, max={pc1_sorted[-1]:.2f}")
        print(f"  mean={mean:.2f}, median={median:.2f}, std={std:.2f}")

        print("\n【パーセンタイル】")
        for p in [10, 25, 40, 50, 60, 65, 75, 90]:
            print(f"  P{p:2d} = {percentile(pc1_sorted, p):.2f}")

        print("\n【偏り・正規性】")
        print(f"  歪度(skewness) = {sk:.3f}  (0=対称, >0=右裾, <0=左裾)")

        print("\n【外れ値 (IQR法: Q1-1.5*IQR 未満 / Q3+1.5*IQR 超過)】")
        print(f"  Q1={q1:.2f}, Q3={q3:.2f}, IQR={iqr:.2f}")
        print(f"  下側閾値={lower:.2f}, 上側閾値={upper:.2f}")
        print(f"  下側外れ値: {len(outliers_low)}件  {outliers_low[:5]}{'...' if len(outliers_low)>5 else ''}")
        print(f"  上側外れ値: {len(outliers_high)}件  {outliers_high[:5]}{'...' if len(outliers_high)>5 else ''}")

        # 極端に大きな値の個数
        high_80 = sum(1 for x in pc1_sorted if x >= 80)
        high_90 = sum(1 for x in pc1_sorted if x >= 90)
        high_95 = sum(1 for x in pc1_sorted if x >= 95)
        print("\n【高値側の件数】")
        print(f"  PC1_score >= 80: {high_80}件, >= 90: {high_90}件, >= 95: {high_95}件")

        # ヒストグラム風テキスト
        print("\n【ヒストグラム (0-100を10刻み)】")
        bins = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
        for i in range(len(bins) - 1):
            lo, hi = bins[i], bins[i + 1]
            count = sum(1 for x in pc1_sorted if lo <= x < hi or (i == len(bins) - 2 and x == 100))
            bar = "█" * count + "░" * (max(0, n // 5 - count))
            print(f"  [{lo:3d}-{hi:3d}): {count:2d} {bar}")

    print("\n")


if __name__ == "__main__":
    main()
