#!/usr/bin/env python3
"""Build automated subtype labels for Graefe revision expert-agreement study.

- large / small_3mm: Subtype from git commit 1e5d202 batch CSVs
- small: re-run classify_morphology_final using CSV scores + trunk pattern from
  output/reference_build_session.json raw metrics (see grading/README.md)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from core.mnv_analysis import TrunkVesselClassifier  # noqa: E402
from core.pattern_classifier import classify_morphology_final  # noqa: E402
from core.pattern_metrics import (  # noqa: E402
    apply_trunk_scale_correction,
    calculate_complexity_pca,
    calculate_stability_score,
    load_complexity_ref,
    load_stability_ref,
)

DATA_DIR = REPO_ROOT / "documentation" / "graefe_revision" / "data"
GRADING_DIR = REPO_ROOT / "documentation" / "graefe_revision" / "grading"
SESSION_JSON = REPO_ROOT / "output" / "reference_build_session.json"
INPUT_ROOT = Path("/Users/yy/MNV_quantitatibe analysis_original_inputdata")

# Mid-tier defaults: session raw lacks thick_vessel_center_ratio / diameter_ratio
DEFAULT_THICK_VESSEL_CENTER_RATIO = 7.5
DEFAULT_DIAMETER_RATIO = 1.1

CSV_MAP = {
    "large": "MNV_batch_20260220_230245_large.csv",
    "small": "MNV_batch_20260220_083448small.csv",
    "small_3mm": "MNV_batch_20260220_223647_small_3mm.csv",
}


def _read_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [str(c).lstrip("\ufeff") for c in df.columns]
    return df


def _normalize_subtype(value: object) -> str:
    s = str(value).strip()
    aliases = {
        "Tree-in-bud": "Tree in bud",
        "Tree-in-Bud": "Tree in bud",
        "tree in bud": "Tree in bud",
        "treein bud": "Tree in bud",
        "Dead-tree": "Dead tree",
        "Dead-Tree": "Dead tree",
    }
    return aliases.get(s, s)


def _session_small_index(session_cases: dict) -> dict[str, dict]:
    out = {}
    for key, payload in session_cases.items():
        if not key.startswith("small/"):
            continue
        fname = key.split("/", 1)[1]
        out[fname] = payload.get("raw", {})
    return out


def _trunk_from_raw(raw: dict) -> tuple[str, str]:
    """Return (trunk_pattern, method_note)."""
    needed = ("eccentricity", "angular_cv", "radial_uniformity")
    if not all(k in raw for k in needed):
        return "INTERMEDIATE", "fallback_intermediate_missing_raw"
    tp = TrunkVesselClassifier.classify_trunk_pattern(
        float(raw["eccentricity"]),
        float(raw["angular_cv"]),
        float(raw["radial_uniformity"]),
        DEFAULT_THICK_VESSEL_CENTER_RATIO,
        DEFAULT_DIAMETER_RATIO,
    )
    return (
        str(tp["pattern"]),
        "trunk_from_session_raw_ecc_angcv_raduni_plus_mid_defaults_for_thick_diam",
    )


def _recomputed_scores(raw: dict) -> tuple[float | None, float | None]:
    try:
        cref = load_complexity_ref("small")
        sref = load_stability_ref("small")
        trunk = float(apply_trunk_scale_correction(float(raw["trunk_score_raw"]), cref))
        comp = float(
            calculate_complexity_pca(
                euler_center=float(raw["euler_center"]),
                euler_periphery=float(raw["euler_periphery"]),
                loop_total=float(raw["loop_total"]),
                junction_density=float(raw["junction_density"]),
                tortuosity_center=float(raw["tortuosity_center"]),
                tortuosity_periphery=float(raw["tortuosity_periphery"]),
                fd_global=float(raw["FD_global"]),
                trunk_score=trunk,
                size_class="small",
            )
        )
        stab = float(
            calculate_stability_score(
                raw["stab_cv"],
                raw["stab_mean_adjacent_change"],
                raw["stab_residual_cv"],
                raw["stab_range_percent"],
                sref,
                trunk_score=trunk,
            )
        )
        return comp, stab
    except Exception:
        return None, None


def build_labels(data_dir: Path, session_path: Path) -> pd.DataFrame:
    with open(session_path, encoding="utf-8") as f:
        session = json.load(f)
    small_raw = _session_small_index(session["cases"])

    rows = []
    for stratum, fname in CSV_MAP.items():
        df = _read_csv(data_dir / fname)
        for _, r in df.iterrows():
            file_name = str(r["File"])
            image_path = INPUT_ROOT / stratum / file_name
            case_key = f"{stratum}/{file_name}"
            base = {
                "case_key": case_key,
                "stratum": stratum,
                "file_name": file_name,
                "image_path": str(image_path),
                "image_exists": image_path.is_file(),
                "source_csv": fname,
                "complexity_score_csv": float(r["Network Complexity Score"]),
                "caliber_uniformity_score_csv": float(r["Caliber Uniformity Score"]),
                "maturity_index_csv": float(r["Maturity Index"]),
            }

            if stratum in ("large", "small_3mm"):
                subtype = _normalize_subtype(r["Subtype"])
                rows.append(
                    {
                        **base,
                        "automated_subtype": subtype,
                        "label_method": f"csv_subtype_column_{stratum}",
                        "trunk_pattern": "",
                        "trunk_method": "",
                        "complexity_score_used": base["complexity_score_csv"],
                        "caliber_score_used": base["caliber_uniformity_score_csv"],
                        "complexity_score_recomputed": "",
                        "caliber_score_recomputed": "",
                        "classifier_confidence": "",
                    }
                )
                continue

            # small: classifier re-run
            raw = small_raw.get(file_name)
            if raw:
                trunk_pattern, trunk_method = _trunk_from_raw(raw)
                recomputed_c, recomputed_s = _recomputed_scores(raw)
            else:
                trunk_pattern, trunk_method = "INTERMEDIATE", "fallback_no_session_match"
                recomputed_c, recomputed_s = None, None

            # Paper-batch scores drive classification; recomputed scores stored for audit
            clf = classify_morphology_final(
                complexity_score=base["complexity_score_csv"],
                stability_score=base["caliber_uniformity_score_csv"],
                trunk_pattern=trunk_pattern,
                size_class="small",
                eccentricity=float(raw["eccentricity"]) if raw and "eccentricity" in raw else -1.0,
                radial_uniformity=float(raw["radial_uniformity"])
                if raw and "radial_uniformity" in raw
                else -1.0,
                angular_cv=float(raw["angular_cv"]) if raw and "angular_cv" in raw else -1.0,
            )
            if clf is None:
                subtype = "Unknown"
                conf = ""
                method = "classifier_failed_ref_missing"
            else:
                subtype = _normalize_subtype(clf["subtype"])
                conf = clf.get("confidence", "")
                if raw:
                    method = "classifier_rerun_csv_scores_plus_session_trunk"
                else:
                    method = "classifier_rerun_csv_scores_fallback_intermediate_trunk"

            rows.append(
                {
                    **base,
                    "automated_subtype": subtype,
                    "label_method": method,
                    "trunk_pattern": trunk_pattern,
                    "trunk_method": trunk_method,
                    "complexity_score_used": base["complexity_score_csv"],
                    "caliber_score_used": base["caliber_uniformity_score_csv"],
                    "complexity_score_recomputed": recomputed_c if recomputed_c is not None else "",
                    "caliber_score_recomputed": recomputed_s if recomputed_s is not None else "",
                    "classifier_confidence": conf,
                }
            )

    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--session-json", type=Path, default=SESSION_JSON)
    parser.add_argument("--out-dir", type=Path, default=GRADING_DIR)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    labels = build_labels(args.data_dir, args.session_json)
    out = args.out_dir / "automated_labels.csv"
    labels.to_csv(out, index=False)
    print(f"Wrote {out} (n={len(labels)})")
    print(labels.groupby(["stratum", "automated_subtype"]).size().to_string())
    missing = labels.loc[~labels["image_exists"], ["case_key", "image_path"]]
    if len(missing):
        print(f"WARNING: {len(missing)} images not found under {INPUT_ROOT}")
        print(missing.to_string(index=False))


if __name__ == "__main__":
    main()
