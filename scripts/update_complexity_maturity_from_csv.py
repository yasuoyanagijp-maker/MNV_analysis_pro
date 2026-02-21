#!/usr/bin/env python3
"""
CSVのデータとcomplexity_ref_*.jsonを用いて
PC1_raw, PC2_raw, PC1_score, PC2_score, complexity_score, maturity_index を算出し、
1) CSVに該当列を追加（P50が50に近いことを確認）
2) mnv_classification_ref_*.json の complexity_score / maturity_index パーセンタイルを更新

計算式:
  Z = (value - mu) / sigma  (各指標)
  PC1_raw = Σ(Z × pc1_weights)
  PC2_raw = Σ(Z × pc2_weights)
  PC1_score = clip(100 × (PC1_raw - score_min) / (score_max - score_min), 0, 100)
  PC2_score = clip(100 × (PC2_raw - PC2_min) / (PC2_max - PC2_min), 0, 100)  # データ内min-max
  complexity_score = PC1_score×evr[0] + PC2_score×evr[1] + Trunk(50)×(1-evr[0]-evr[1])
  maturity_index = clip(50 + (Caliber Uniformity Score - complexity_score) / 2, 0, 100)
"""

import csv
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CSV_DIR = PROJECT_ROOT / "csv"
REF_DIR = PROJECT_ROOT / "resources" / "reference_metrics"

CSV_TO_COMPLEXITY_REF = {
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


def row_to_features(row, headers):
    """row (list or dict) から euler_total_inv, loop_total, junction_density, FD_global を取得"""
    if isinstance(row, list):
        row = dict(zip(headers, row))
    center_euler = num(row.get("Center Euler Number"))
    periphery_euler = num(row.get("Periphery Euler Number"))
    center_loop = num(row.get("Center Loop Number"))
    periphery_loop = num(row.get("Periphery Loop Number"))
    junc = num(row.get("Junction Density (n/mm)"))
    fd = num(row.get("Fractal Dim"))
    euler_total_inv = -(center_euler + periphery_euler) if (center_euler is not None and periphery_euler is not None) else None
    loop_total = (center_loop + periphery_loop) if (center_loop is not None and periphery_loop is not None) else None
    return {
        "euler_total_inv": euler_total_inv,
        "loop_total": loop_total,
        "junction_density": junc,
        "FD_global": fd,
    }


def safe_z(val, mu, sigma):
    if val is None or sigma is None or sigma <= 0:
        return 0.0
    return (float(val) - float(mu)) / float(sigma)


def percentile(sorted_arr, p):
    """sorted_arr は数値のリスト、p は 0-100。NaN は除外済みを想定"""
    if not sorted_arr:
        return float("nan")
    n = len(sorted_arr)
    k = (n - 1) * p / 100.0
    f = int(k)
    c = f + 1 if f + 1 < n else f
    if f == c:
        return sorted_arr[f]
    return sorted_arr[f] + (k - f) * (sorted_arr[c] - sorted_arr[f])


def run_one_csv(csv_path: Path, ref_path: Path, dry_run: bool = False):
    with open(ref_path, encoding="utf-8") as f:
        ref = json.load(f)

    metrics = ref["metrics"]
    mu = ref["mu"]
    sigma = ref["sigma"]
    pc1_w = ref["pc1_weights"]
    pc2_w = ref["pc2_weights"]
    score_min = float(ref["score_min"])
    score_max = float(ref["score_max"])
    evr = ref.get("explained_variance_ratio", [0.7, 0.2])
    w_pc1 = float(evr[0])
    w_pc2 = float(evr[1])
    w_trunk = max(0.0, 1.0 - w_pc1 - w_pc2)  # 残りをTrunkDistに
    trunk_val = 50.0
    score_span = score_max - score_min

    rows = []
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames
        for r in reader:
            rows.append(r)

    pc1_raw_list = []
    pc2_raw_list = []
    caliber_list = []
    for r in rows:
        feats = row_to_features(r, None)
        z_vals = {m: safe_z(feats.get(m), mu.get(m, 0), sigma.get(m, 1)) for m in metrics}
        pc1_raw = sum(z_vals[m] * pc1_w.get(m, 0) for m in metrics)
        pc2_raw = sum(z_vals[m] * pc2_w.get(m, 0) for m in metrics)
        pc1_raw_list.append(pc1_raw)
        pc2_raw_list.append(pc2_raw)
        cal = num(r.get("Caliber Uniformity Score"))
        caliber_list.append(cal)

    pc2_min = min(pc2_raw_list)
    pc2_max = max(pc2_raw_list)
    pc2_span = (pc2_max - pc2_min) if pc2_max > pc2_min else 1.0

    def clip(x, lo, hi):
        return max(lo, min(hi, x))

    complexity_scores = []
    maturity_indices = []
    for i in range(len(rows)):
        pc1_score = clip(100.0 * (pc1_raw_list[i] - score_min) / score_span, 0, 100)
        pc2_score = clip(100.0 * (pc2_raw_list[i] - pc2_min) / pc2_span, 0, 100)
        comp = clip(pc1_score * w_pc1 + pc2_score * w_pc2 + trunk_val * w_trunk, 0, 100)
        complexity_scores.append(comp)
        cal = caliber_list[i]
        if cal is not None:
            mat = clip(50.0 + (cal - comp) / 2.0, 0, 100)
        else:
            mat = None
        maturity_indices.append(mat)
        rows[i]["PC1_raw"] = f"{pc1_raw_list[i]:.6f}"
        rows[i]["PC2_raw"] = f"{pc2_raw_list[i]:.6f}"
        rows[i]["PC1_score"] = f"{pc1_score:.4f}"
        rows[i]["PC2_score"] = f"{pc2_score:.4f}"
        rows[i]["complexity_score_calc"] = f"{comp:.4f}"
        rows[i]["maturity_index_calc"] = f"{mat:.4f}" if mat is not None else ""
        # 空欄の Maturity Index / Network Complexity Score を計算値で補完
        if "Network Complexity Score" in rows[i] and not (rows[i].get("Network Complexity Score") or "").strip():
            rows[i]["Network Complexity Score"] = f"{comp:.4f}"
        if "Maturity Index" in rows[i] and not (rows[i].get("Maturity Index") or "").strip() and mat is not None:
            rows[i]["Maturity Index"] = f"{mat:.4f}"

    comp_valid = [c for c in complexity_scores]
    comp_sorted = sorted(comp_valid)
    p50_comp = percentile(comp_sorted, 50)
    print(f"  [P50 check] complexity_score_calc median = {p50_comp:.2f}  (target ~50)")

    mat_valid = [m for m in maturity_indices if m is not None]
    mat_sorted = sorted(mat_valid) if mat_valid else []
    p50_mat = percentile(mat_sorted, 50) if mat_sorted else float("nan")
    print(f"  [P50 check] maturity_index_calc median   = {p50_mat:.2f}")

    percentiles = [10, 25, 40, 50, 60, 65, 75, 90]
    comp_perc = {f"P{p}": percentile(comp_sorted, p) for p in percentiles}
    mat_perc = {f"P{p}": percentile(mat_sorted, p) if mat_sorted else 0.0 for p in percentiles}

    if not dry_run:
        update_complexity_ref_pc2_bounds(ref_path, pc2_min, pc2_max)
        new_headers = list(headers) + ["PC1_raw", "PC2_raw", "PC1_score", "PC2_score", "complexity_score_calc", "maturity_index_calc"]
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=new_headers, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
        print(f"  Written: {csv_path}")

    return comp_perc, mat_perc


def update_complexity_ref_pc2_bounds(ref_path: Path, pc2_min: float, pc2_max: float):
    """complexity_ref に PC2_min / PC2_max を追加（アプリ計算で使用）"""
    with open(ref_path, encoding="utf-8") as f:
        data = json.load(f)
    data["PC2_min"] = pc2_min
    data["PC2_max"] = pc2_max
    with open(ref_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"  Updated {ref_path.name} with PC2_min={pc2_min:.4f}, PC2_max={pc2_max:.4f}")


def update_mnv_classification_ref(size_class_key: str, comp_perc: dict, mat_perc: dict):
    name = f"mnv_classification_ref_{size_class_key}.json"
    path = REF_DIR / name
    if not path.exists():
        print(f"  Skip (not found): {path}")
        return
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    data["complexity_score"] = comp_perc
    data["maturity_index"] = mat_perc
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"  Updated: {path}")


def main():
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("DRY RUN (no writes)\n")

    for csv_name, ref_name in CSV_TO_COMPLEXITY_REF.items():
        csv_path = CSV_DIR / csv_name
        ref_path = REF_DIR / ref_name
        if not csv_path.exists():
            print(f"Skip CSV (not found): {csv_path}")
            continue
        if not ref_path.exists():
            print(f"Skip ref (not found): {ref_path}")
            continue
        print(f"\n=== {csv_name} + {ref_name} ===")
        comp_perc, mat_perc = run_one_csv(csv_path, ref_path, dry_run=dry_run)
        print(f"  complexity_score percentiles: P50={comp_perc['P50']:.2f}")
        print(f"  maturity_index percentiles:   P50={mat_perc['P50']:.2f}")

        if not dry_run:
            if "large" in csv_name:
                update_mnv_classification_ref("large", comp_perc, mat_perc)
            elif "small_3mm" in csv_name:
                update_mnv_classification_ref("small_3mm", comp_perc, mat_perc)
            else:
                update_mnv_classification_ref("small", comp_perc, mat_perc)

    print("\nDone.")


if __name__ == "__main__":
    main()
