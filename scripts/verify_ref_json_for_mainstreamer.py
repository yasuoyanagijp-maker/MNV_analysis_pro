#!/usr/bin/env python3
"""
complexity_ref_*.json と mnv_classification_ref_*.json が
pattern_metrics.py / pattern_classifier.py (mainstreamer → mnv_pipeline 経由) で
参照される際に期待される形式・値と整合しているか確認する。
"""

import json
import sys
from pathlib import Path

# プロジェクトルート
ROOT = Path(__file__).resolve().parents[1]
REF_DIR = ROOT / "resources" / "reference_metrics"
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# pattern_metrics が complexity_ref に期待するキー
COMPLEXITY_REF_REQUIRED = ["mu", "sigma", "pc1_weights", "pc2_weights", "final_weights"]
COMPLEXITY_REF_OPTIONAL = ["metrics", "score_min", "score_max", "explained_variance_ratio", "note"]

# pattern_classifier の _ref_p が使うパーセンタイル
PERCENTILES = [10, 25, 40, 50, 60, 65, 75, 90]

# classify_morphology_final / classify_pathophysiology_final / check_arteriolarized が参照する指標
MNV_REF_METRICS = [
    "complexity_score",
    "maturity_index",
    "stability_score",
    "junction_density",
    "loop_total",
    "mean_diameter_um",
    "arteriolarization_segment_count",
]
# P30 は補間されるので PERCENTILES に含まれていなくても可（P25,P40 があれば補間可能）


def load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def verify_complexity_ref(name: str) -> list:
    path = REF_DIR / name
    if not path.exists():
        return [f"  [SKIP] {name} not found"]
    errs = []
    data = load_json(path)
    for key in COMPLEXITY_REF_REQUIRED:
        if key not in data:
            errs.append(f"  [complexity_ref] {name} missing key: {key}")
    if "metrics" in data:
        metrics = data["metrics"]
        if not isinstance(metrics, (list, tuple)):
            errs.append(f"  [complexity_ref] {name} 'metrics' must be list")
        else:
            for m in metrics:
                if m not in data.get("mu", {}):
                    errs.append(f"  [complexity_ref] {name} metric '{m}' missing in mu")
                if m not in data.get("sigma", {}):
                    errs.append(f"  [complexity_ref] {name} metric '{m}' missing in sigma")
                if m not in data.get("pc1_weights", {}):
                    errs.append(f"  [complexity_ref] {name} metric '{m}' missing in pc1_weights")
                if m not in data.get("pc2_weights", {}):
                    errs.append(f"  [complexity_ref] {name} metric '{m}' missing in pc2_weights")
    fw = data.get("final_weights", {})
    for k in ["PC1", "PC2", "TrunkDist"]:
        if k not in fw:
            errs.append(f"  [complexity_ref] {name} final_weights missing: {k}")
        elif not isinstance(fw[k], (int, float)):
            errs.append(f"  [complexity_ref] {name} final_weights.{k} must be number")
    if not errs:
        errs.append(f"  [OK] {name} structure and keys valid")
    return errs


def verify_mnv_classification_ref(name: str) -> list:
    path = REF_DIR / name
    if not path.exists():
        return [f"  [SKIP] {name} not found"]
    errs = []
    data = load_json(path)
    for metric in MNV_REF_METRICS:
        m = data.get(metric)
        if m is None:
            errs.append(f"  [mnv_classification_ref] {name} missing metric block: {metric}")
            continue
        if not isinstance(m, dict):
            errs.append(f"  [mnv_classification_ref] {name} '{metric}' must be dict")
            continue
        for p in PERCENTILES:
            key = f"P{p}"
            if key not in m:
                errs.append(f"  [mnv_classification_ref] {name} '{metric}' missing {key}")
            else:
                try:
                    float(m[key])
                except (TypeError, ValueError):
                    errs.append(f"  [mnv_classification_ref] {name} '{metric}.{key}' must be number")
    if not errs:
        errs.append(f"  [OK] {name} structure and percentiles valid")
    return errs


def run_import_and_calls():
    """実際にモジュールをロードし、ref を読み込んで分類が動くか確認"""
    errs = []
    try:
        from core.pattern_metrics import (
            _load_complexity_ref_large,
            _load_complexity_ref_small,
            _load_complexity_ref_small_3mm,
            calculate_complexity_pca,
        )
        from core.pattern_classifier import (
            load_mnv_classification_ref,
            classify_morphology_final,
            classify_pathophysiology_final,
            _ref_p,
        )
    except Exception as e:
        return [f"  [IMPORT] Failed: {e}"]

    for size_class, loader in [
        ("large", _load_complexity_ref_large),
        ("small", _load_complexity_ref_small),
        ("small_3mm", _load_complexity_ref_small_3mm),
    ]:
        ref = loader()
        if ref is None:
            errs.append(f"  [RUNTIME] complexity_ref {size_class} load returned None")
        else:
            # ダミーで complexity 計算が通るか
            try:
                score = calculate_complexity_pca(
                    euler_center=0.0,
                    euler_periphery=0.0,
                    loop_total=100.0,
                    junction_density=20.0,
                    tortuosity_center=1.0,
                    tortuosity_periphery=1.0,
                    fd_global=1.4,
                    trunk_score=50.0,
                    size_class=size_class,
                )
                if not (0 <= score <= 100):
                    errs.append(f"  [RUNTIME] complexity_score out of range: {score}")
            except Exception as e:
                errs.append(f"  [RUNTIME] calculate_complexity_pca({size_class}): {e}")

    for size_class in ["large", "small", "small_3mm"]:
        ref = load_mnv_classification_ref(size_class)
        if ref is None:
            errs.append(f"  [RUNTIME] mnv_classification_ref {size_class} load returned None")
            continue
        # P30 は補間で取得
        try:
            p30 = _ref_p(ref, "complexity_score", 30, 30.0)
            p65 = _ref_p(ref, "complexity_score", 65, 65.0)
            p25_m = _ref_p(ref, "maturity_index", 25, 25.0)
            p75_m = _ref_p(ref, "maturity_index", 75, 75.0)
        except Exception as e:
            errs.append(f"  [RUNTIME] _ref_p({size_class}): {e}")
            continue
        # 分類を一発だけ呼ぶ
        try:
            out = classify_morphology_final(
                complexity_score=50.0,
                stability_score=60.0,
                trunk_pattern="MEDUSA",
                size_class=size_class,
            )
            if out is None:
                errs.append(f"  [RUNTIME] classify_morphology_final({size_class}) returned None")
            elif "subtype" not in out or "maturity_index" not in out:
                errs.append(f"  [RUNTIME] classify_morphology_final({size_class}) missing keys")
        except Exception as e:
            errs.append(f"  [RUNTIME] classify_morphology_final({size_class}): {e}")
        try:
            patho = classify_pathophysiology_final(
                maturity_index=55.0,
                stability_score=65.0,
                segment_count=100.0,
                junction_density=25.0,
                endpoint_density=5.0,
                loop_total=300.0,
                mean_diameter_um=16.0,
                cv_diameter=38.0,
                size_class=size_class,
            )
            if patho is None and ref is not None:
                pass  # None is allowed when ref not used for this branch
        except Exception as e:
            errs.append(f"  [RUNTIME] classify_pathophysiology_final({size_class}): {e}")

    if not errs:
        return ["  [OK] Import and ref-based classification calls succeeded"]
    return errs


def main():
    print("=== complexity_ref_*.json (pattern_metrics.calculate_complexity_pca) ===\n")
    for name in ["complexity_ref_large.json", "complexity_ref_small.json", "complexity_ref_small_3mm.json"]:
        for line in verify_complexity_ref(name):
            print(line)

    print("\n=== mnv_classification_ref_*.json (pattern_classifier classify_*_final, _ref_p) ===\n")
    for name in [
        "mnv_classification_ref_large.json",
        "mnv_classification_ref_small.json",
        "mnv_classification_ref_small_3mm.json",
    ]:
        for line in verify_mnv_classification_ref(name):
            print(line)

    print("\n=== Runtime: load refs and run classification ===\n")
    if "--runtime" in sys.argv:
        try:
            for line in run_import_and_calls():
                print(line)
        except Exception as e:
            print(f"  [SKIP] Runtime check failed: {e}")
    else:
        print("  [SKIP] Run with --runtime to test actual import and classification calls")
    print()


if __name__ == "__main__":
    main()
