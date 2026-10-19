#!/usr/bin/env python3
"""Build an Optovue 3mm complexity reference the same way as the other strata.

PCA on euler_total_inv, loop_total, junction_density, FD_global.
PC1 and PC2 are linearly scaled so each axis median maps to 50, then PC1 is
shifted so the cohort median of Complexity is 50. Trunk is not in the source
CSV, so the trunk term is the neutral value 50.

Rows with FD quality flag 1 (fd_out_of_range) are kept in the scored table
but are not part of the reference fit.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

METRICS = (
    "euler_total_inv",
    "loop_total",
    "junction_density",
    "FD_global",
)
PERCENTILES = (10, 25, 40, 50, 60, 65, 75, 90)
TRUNK_NEUTRAL = 50.0


def _features(row: dict) -> np.ndarray:
    euler = float(row["Center Euler Number"]) + float(row["Periphery Euler Number"])
    loops = float(row["Center Loop Number"]) + float(row["Periphery Loop Number"])
    return np.array(
        [
            -euler,
            loops,
            float(row["Junction Density (n/mm)"]),
            float(row["Fractal Dim"]),
        ],
        dtype=float,
    )


def _fd_failed(row: dict) -> bool:
    flag = str(row.get("FD quality flag (0=OK 1=abnormal)", "")).strip()
    return flag == "1" or float(row["Fractal Dim"]) == 0.0


def _orient(loadings: np.ndarray) -> np.ndarray:
    """Match the other strata: more mesh raises PC1; PC2 falls as junction density rises."""
    out = loadings.copy()
    if out[0, [0, 1, 3]].sum() < 0:
        out[0] *= -1
    if out[1, 2] > 0:
        out[1] *= -1
    return out


def _linear_median_50(raw: np.ndarray) -> tuple[np.ndarray, float, float]:
    """Linear map whose midpoint is the median, so the median scores 50. No in-cohort clipping."""
    med = float(np.median(raw))
    half = max(med - float(raw.min()), float(raw.max()) - med)
    if half <= 0:
        half = 1.0
    score_min = med - half
    score_max = med + half
    score = 100.0 * (raw - score_min) / (score_max - score_min)
    return score, score_min, score_max


def _shift_scale(score_min: float, score_max: float, delta: float) -> tuple[float, float]:
    """Add `delta` points to every linear score without changing the slope."""
    span = score_max - score_min
    shift = delta * span / 100.0
    return score_min - shift, score_max - shift


def _percentile_block(values: np.ndarray) -> dict[str, float]:
    pct = np.percentile(values, PERCENTILES)
    return {f"P{p}": float(v) for p, v in zip(PERCENTILES, pct)}


def build(rows: list[dict]) -> tuple[dict, dict, list[dict]]:
    fit_idx = [i for i, row in enumerate(rows) if not _fd_failed(row)]
    x_all = np.vstack([_features(row) for row in rows])
    x_fit = x_all[fit_idx]
    mu = x_fit.mean(axis=0)
    sigma = x_fit.std(axis=0, ddof=1)
    sigma = np.where(sigma <= 0, 1.0, sigma)
    z_fit = (x_fit - mu) / sigma
    z_all = (x_all - mu) / sigma

    _u, singular, vt = np.linalg.svd(z_fit, full_matrices=False)
    loadings = _orient(vt[:2])
    variance = singular**2
    evr = variance / variance.sum()
    w1 = float(evr[0])
    w2 = float(evr[1])
    w_trunk = max(0.0, 1.0 - w1 - w2)

    pc_fit = z_fit @ loadings.T
    pc_all = z_all @ loadings.T
    s1_fit, score_min, score_max = _linear_median_50(pc_fit[:, 0])
    s2_fit, pc2_min, pc2_max = _linear_median_50(pc_fit[:, 1])
    comp_fit = w1 * s1_fit + w2 * s2_fit + w_trunk * TRUNK_NEUTRAL
    delta = (50.0 - float(np.median(comp_fit))) / w1
    score_min, score_max = _shift_scale(score_min, score_max, delta)

    def complexity(pc: np.ndarray) -> np.ndarray:
        s1 = 100.0 * (pc[:, 0] - score_min) / (score_max - score_min)
        s2 = 100.0 * (pc[:, 1] - pc2_min) / (pc2_max - pc2_min)
        s1 = np.clip(s1, 0.0, 100.0)
        s2 = np.clip(s2, 0.0, 100.0)
        return w1 * s1 + w2 * s2 + w_trunk * TRUNK_NEUTRAL

    comp_fit = complexity(pc_fit)
    comp_all = complexity(pc_all)
    if abs(float(np.median(comp_fit)) - 50.0) > 1e-6:
        raise RuntimeError(f"median Complexity is {np.median(comp_fit)}, expected 50")

    n_fit = len(fit_idx)
    n_before = sum(1 for i in fit_idx if str(rows[i].get("Timepoint", "")).strip() == "1")
    n_after = sum(1 for i in fit_idx if str(rows[i].get("Timepoint", "")).strip() == "2")
    ref = {
        "size_class": "optovue_3mm",
        "n_cases": n_fit,
        "n_before": n_before,
        "n_after": n_after,
        "n_excluded_fd_fail": len(rows) - n_fit,
        "metrics": list(METRICS),
        "note": (
            "Optovue 3mm cohort (Tsuzu 2026-08-12 combined CSV). "
            "PCA on euler_total_inv, loop_total, junction_density, FD_global, "
            "same inputs as complexity_ref_{small,large,small_3mm}.json. "
            "PC1/PC2 linear scales put each axis median at 50; PC1 is then shifted "
            "so the cohort median of Complexity is 50. Trunk raw score is absent "
            f"from the CSV, so the trunk term is the neutral value {TRUNK_NEUTRAL:.0f}. "
            "FD quality flag 1 (fd_out_of_range) excluded from the fit. "
            "Runtime weights are explained_variance_ratio; final_weights 0.7/0.2/0.1 "
            "are recorded for schema parity and are not used."
        ),
        "mu": {name: float(mu[i]) for i, name in enumerate(METRICS)},
        "sigma": {name: float(sigma[i]) for i, name in enumerate(METRICS)},
        "pc1_weights": {name: float(loadings[0, i]) for i, name in enumerate(METRICS)},
        "pc2_weights": {name: float(loadings[1, i]) for i, name in enumerate(METRICS)},
        "explained_variance_ratio": [w1, w2],
        "score_min": float(score_min),
        "score_max": float(score_max),
        "final_weights": {"PC1": 0.7, "PC2": 0.2, "TrunkDist": 0.1},
        "PC2_min": float(pc2_min),
        "PC2_max": float(pc2_max),
        "trunk_term": {
            "value": TRUNK_NEUTRAL,
            "reason": "Trunk distribution inputs are not in the batch CSV.",
        },
    }
    complexity_score = _percentile_block(comp_fit)
    # Direct P30. The app interpolates P30 only when the key is absent.
    complexity_score = {
        "P10": complexity_score["P10"],
        "P25": complexity_score["P25"],
        "P30": float(np.percentile(comp_fit, 30)),
        "P40": complexity_score["P40"],
        "P50": complexity_score["P50"],
        "P60": complexity_score["P60"],
        "P65": complexity_score["P65"],
        "P75": complexity_score["P75"],
        "P90": complexity_score["P90"],
    }
    cls = {
        "size_class": "optovue_3mm",
        "n_cases": n_fit,
        "n_before": n_before,
        "n_after": n_after,
        "note": (
            f"n={n_fit} FD-valid Optovue 3mm scans. "
            "complexity_score percentiles are from complexity_ref_optovue_3mm.json "
            "(cohort median Complexity = 50, trunk neutral at 50). "
            "Morphology gates match the other strata: Dead tree < P10, "
            "Glomerular >= P30, Tree in bud in between. "
            "Medusa and Seafan need trunk pattern, which this CSV does not contain. "
            "provisional_no_trunk assigns Medusa at >= P65 and Seafan at >= P40 "
            "without trunk."
        ),
        "provisional_no_trunk": {
            "uses_trunk": False,
            "order": [
                "Dead tree if complexity < P10",
                "Medusa if complexity >= P65",
                "Seafan if complexity >= P40",
                "Glomerular if complexity >= P30",
                "Tree in bud otherwise",
            ],
        },
        "percentiles": list(PERCENTILES),
        "complexity_ref": "complexity_ref_optovue_3mm.json",
        "complexity_score": complexity_score,
    }

    scored = []
    for row, score in zip(rows, comp_all):
        scored.append({**row, "_complexity": float(score), "_fd_failed": _fd_failed(row)})
    return ref, cls, scored


def classify(score: float, ref: dict) -> str:
    block = ref["complexity_score"]
    if score < block["P10"]:
        return "Dead tree"
    if score >= block["P30"]:
        return "Glomerular"
    return "Tree in bud"


def classify_provisional(score: float, ref: dict) -> str:
    """Five classes from complexity alone. P65 then P40 stand in for trunk."""
    block = ref["complexity_score"]
    if score < block["P10"]:
        return "Dead tree"
    if score >= block["P65"]:
        return "Medusa"
    if score >= block["P40"]:
        return "Seafan"
    if score >= block["P30"]:
        return "Glomerular"
    return "Tree in bud"


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "csv",
        nargs="?",
        default="/tmp/mnv_batch_20260812_combined.csv",
    )
    parser.add_argument(
        "--out-dir",
        default="resources/reference_metrics",
    )
    args = parser.parse_args()
    src = Path(args.csv)
    rows = list(csv.DictReader(src.read_text(encoding="utf-8-sig").splitlines()))
    ref, cls, scored = build(rows)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "complexity_ref_optovue_3mm.json").write_text(
        json.dumps(ref, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "mnv_classification_ref_optovue_3mm.json").write_text(
        json.dumps(cls, indent=2) + "\n", encoding="utf-8"
    )

    p10 = cls["complexity_score"]["P10"]
    p30 = cls["complexity_score"]["P30"]
    labels = [classify(item["_complexity"], cls) for item in scored]
    provisional = [classify_provisional(item["_complexity"], cls) for item in scored]
    from collections import Counter

    print("n_fit", ref["n_cases"], "excluded", ref["n_excluded_fd_fail"])
    print("median check stored via build()")
    fit_scores = [
        item["_complexity"] for item in scored if not item["_fd_failed"]
    ]
    print("fit median", float(np.median(fit_scores)))
    print("P10", p10, "P30", p30, "P40", cls["complexity_score"]["P40"],
          "P65", cls["complexity_score"]["P65"], "P50", cls["complexity_score"]["P50"])
    print("labels", Counter(labels))
    print("provisional fit", Counter(
        lab for lab, item in zip(provisional, scored) if not item["_fd_failed"]
    ))
    print("provisional fd_fail", Counter(
        lab for lab, item in zip(provisional, scored) if item["_fd_failed"]
    ))

    extra = [
        "Network Complexity Score (Optovue 3mm PCA)",
        "Subtype (Optovue 3mm PCA)",
        "Subtype (Optovue 3mm PCA, provisional)",
        "FD excluded from reference (0=used 1=excluded)",
    ]
    fieldnames = list(rows[0].keys()) + extra
    dest = Path("data/optovue_3mm_20260812/mnv_batch_20260812_combined_subtype.csv")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for item, label, provisional_label in zip(scored, labels, provisional):
            row = {key: item[key] for key in rows[0].keys()}
            row["Network Complexity Score (Optovue 3mm PCA)"] = f"{item['_complexity']:.6f}"
            row["Subtype (Optovue 3mm PCA)"] = label
            row["Subtype (Optovue 3mm PCA, provisional)"] = provisional_label
            row["FD excluded from reference (0=used 1=excluded)"] = (
                "1" if item["_fd_failed"] else "0"
            )
            writer.writerow(row)
    print("wrote", dest)


if __name__ == "__main__":
    main()
