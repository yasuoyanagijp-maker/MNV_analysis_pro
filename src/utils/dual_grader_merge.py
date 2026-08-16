"""
Merge first-grader and second-reader MNV CSVs into one adopted-values CSV.

Reuses the reading-center RPD adoption code
(``tools/reading_center_rpd/compute_adopted_from_dual_csv.py``):

1. Recompute Standardized Caliber Uniformity + Standardized Maturity on both CSVs.
2. Match rows by image file stem (the second reader grades the exported
   ``export/images/{institution}/{lesion_id}.png`` files, whose stems equal the
   first grader's original filenames after sanitization).
3. Per numeric column, adopt the arithmetic mean when RPD <= threshold
   (default 20%); otherwise NA (recheck) — via the existing ``adopt_pair``.

Outputs (into the second reader's output folder):
  - ``{prefix}_adopted_values.csv``  … batch-CSV schema, adopted values
  - ``{prefix}_recheck_list.csv``    … discordant major metrics (RPD > threshold)
  - ``{prefix}_summary.md``          … counts + rule statement
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Existing RPD(20%) adoption implementation — reused, not reimplemented.
from tools.reading_center_rpd.compute_adopted_from_dual_csv import (  # noqa: E402
    DEFAULT_RPD_PCT,
    MAJOR_METRICS,
    adopt_pair,
    apply_u2,
    is_numeric_column,
    read_csv,
    rpd_pct,
    to_float,
    write_csv,
)

RPD_THRESHOLD_PCT = DEFAULT_RPD_PCT  # 20%

# RECHECK flagging must survive a failed Standardized (U2) recompute
# (_apply_u2_safe keeps the original values): older CSVs then still carry the
# pre-rename "(U2)" columns, which would otherwise silently drop out of the
# RECHECK list. A successful recompute removes the legacy columns, so this
# never double-flags the same metric.
MAJOR_METRICS_COMPAT = list(MAJOR_METRICS) + [
    "Caliber Uniformity Score (U2)",
    "Maturity Index (U2)",
]

RECHECK_FIELDS = [
    "File",
    "Metric",
    "FirstGrader",
    "SecondReader",
    "Value_grader1",
    "Value_reader2",
    "RPD_pct",
    "Adopted",
    "Rule",
]

_QUALITATIVE_META = ("Subtype", "Pathophysiology", "Quality of analysis")


def match_stem(filename: str) -> str:
    """Normalized match key from a File cell (extension/sanitization agnostic)."""
    stem = Path(str(filename or "").strip()).stem
    safe = re.sub(r"[^\w\-]+", "_", stem, flags=re.UNICODE)
    safe = re.sub(r"_+", "_", safe).strip("_")
    return safe.lower()


def _index_rows(rows: List[Dict[str, Any]]) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    idx: Dict[str, Dict[str, Any]] = {}
    dup: List[str] = []
    for r in rows:
        key = match_stem(r.get("File", "")) or match_stem(r.get("ID", ""))
        if not key:
            continue
        if key in idx:
            dup.append(key)
        idx[key] = r
    return idx, dup


def _apply_u2_safe(
    fieldnames: List[str],
    rows: List[Dict[str, Any]],
    warnings: List[str],
    label: str,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    try:
        return apply_u2(list(fieldnames), [dict(r) for r in rows], None)
    except (Exception, SystemExit) as ex:  # SystemExit: missing reference json
        warnings.append(
            f"Standardized score recompute failed for {label}: {ex} — using original values."
        )
        return list(fieldnames), [dict(r) for r in rows]


def merge_dual_grader_csvs(
    first_csv: Path,
    second_csv: Path,
    out_dir: Path,
    *,
    rpd_threshold: float = RPD_THRESHOLD_PCT,
    first_label: str = "Grader1",
    second_label: str = "Reader2",
    prefix: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build the integrated (adopted-values) CSV from the two readers' CSVs.

    Returns a summary dict with output paths and counts. Raises ValueError when
    the CSVs cannot be matched at all.
    """
    first_csv = Path(first_csv)
    second_csv = Path(second_csv)
    warnings: List[str] = []

    try:
        fields_a, rows_a = read_csv(first_csv)
        fields_b, rows_b = read_csv(second_csv)
    except ValueError as ex:
        raise ValueError(f"CSV read failed: {ex}") from ex
    except SystemExit as ex:
        # Legacy callers / older tool builds may still raise SystemExit.
        raise ValueError(f"CSV read failed: {ex}") from ex

    # Step 1 — Standardized (U2) recompute (same fixed pipeline as the reading-center tool)
    fields_a, rows_a = _apply_u2_safe(fields_a, rows_a, warnings, first_label)
    fields_b, rows_b = _apply_u2_safe(fields_b, rows_b, warnings, second_label)

    # Union fieldnames: first-grader order, then extras from the second reader
    fieldnames = list(fields_a)
    for c in fields_b:
        if c not in fieldnames:
            fieldnames.append(c)

    # Step 2 — match by file stem
    idx_a, dup_a = _index_rows(rows_a)
    idx_b, dup_b = _index_rows(rows_b)
    for dup, label in ((dup_a, first_label), (dup_b, second_label)):
        if dup:
            warnings.append(f"Duplicate match keys in {label} CSV (last wins): {', '.join(dup[:5])}")

    order_a = [k for k in (match_stem(r.get("File", "")) or match_stem(r.get("ID", "")) for r in rows_a) if k]
    seen: set = set()
    common = [k for k in order_a if k in idx_b and not (k in seen or seen.add(k))]
    only_a = sorted(set(idx_a) - set(idx_b))
    only_b = sorted(set(idx_b) - set(idx_a))

    if not common:
        raise ValueError(
            "第1グレーダーCSVと第2リーダーCSVでファイル名が一致する行がありません。"
            f"（{first_csv.name} / {second_csv.name}）"
        )

    numeric_cols = [c for c in fieldnames if is_numeric_column(c, rows_a, rows_b)]

    # Step 3 — RPD adoption per numeric column (existing RPD<=20% rule)
    adopted_rows: List[Dict[str, Any]] = []
    recheck_rows: List[Dict[str, str]] = []
    for key in common:
        ra, rb = idx_a[key], idx_b[key]
        out = {k: "" for k in fieldnames}
        out["ID"] = ra.get("ID") or rb.get("ID") or ""
        out["File"] = ra.get("File") or rb.get("File") or key
        out["Analyst"] = f"Dual-read mean (RPD<={rpd_threshold:g}%; else NA)"
        for meta in _QUALITATIVE_META:
            va = str(ra.get(meta) or "").strip()
            vb = str(rb.get(meta) or "").strip()
            out[meta] = va if va == vb else ("NA" if (va or vb) else "")

        for col in numeric_cols:
            a, b = to_float(ra.get(col)), to_float(rb.get(col))
            val, status, rpd_s = adopt_pair(a, b, rpd_threshold)
            out[col] = val
            if col in MAJOR_METRICS_COMPAT and status in ("RECHECK", "MISSING"):
                rule = (
                    "MISSING"
                    if status == "MISSING"
                    else f"RPD>{rpd_threshold:g}%"
                )
                recheck_rows.append(
                    {
                        "File": out["File"],
                        "Metric": col,
                        "FirstGrader": first_label,
                        "SecondReader": second_label,
                        "Value_grader1": "" if a is None else f"{a:.10g}",
                        "Value_reader2": "" if b is None else f"{b:.10g}",
                        "RPD_pct": rpd_s,
                        "Adopted": "NA",
                        "Rule": rule,
                    }
                )
        adopted_rows.append(out)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if not prefix:
        prefix = f"MNV_integrated_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    adopted_path = out_dir / f"{prefix}_adopted_values.csv"
    recheck_path = out_dir / f"{prefix}_recheck_list.csv"
    summary_path = out_dir / f"{prefix}_summary.md"

    write_csv(adopted_path, fieldnames, adopted_rows)
    write_csv(recheck_path, RECHECK_FIELDS, recheck_rows)

    recheck_by_metric = dict(Counter(r["Metric"] for r in recheck_rows))
    files_recheck = len({r["File"] for r in recheck_rows})
    summary = {
        "first_csv": str(first_csv),
        "second_csv": str(second_csv),
        "first_label": first_label,
        "second_label": second_label,
        "threshold_pct": float(rpd_threshold),
        "n_matched": len(common),
        "n_first_only": len(only_a),
        "n_second_only": len(only_b),
        "first_only": only_a,
        "second_only": only_b,
        "recheck_cells": len(recheck_rows),
        "recheck_files": files_recheck,
        "recheck_by_metric": recheck_by_metric,
        "warnings": warnings,
        "adopted_csv": str(adopted_path),
        "recheck_csv": str(recheck_path),
        "summary_md": str(summary_path),
    }
    summary_path.write_text(_render_summary_md(summary), encoding="utf-8")
    return summary


def _render_summary_md(s: Dict[str, Any]) -> str:
    lines = [
        f"# 統合解析データ (dual-read adoption) — {datetime.now().date().isoformat()}",
        "",
        f"- 第1グレーダー CSV: `{Path(s['first_csv']).name}`",
        f"- 第2リーダー CSV: `{Path(s['second_csv']).name}`",
        f"- RPD 閾値: **{s['threshold_pct']:g}%**",
        f"- 突合成功: **{s['n_matched']}** 行"
        f"（第1のみ: {s['n_first_only']} / 第2のみ: {s['n_second_only']}）",
        "",
        "## ルール",
        "",
        "1. 両CSVで Caliber/Maturity の **Standardized スコア**を再計算。",
        "2. ファイル名（stem）で行を突合。",
        f"3. RPD ≤ {s['threshold_pct']:g}% → 採用値 = 算術平均、超過 → **NA**（再計測）。",
        "",
        "**根拠:** 20%は測定誤差を許容しつつ、過度な除外を避けるために設定した。",
        "",
        "## RECHECK",
        "",
        f"- 主要指標セル: {s['recheck_cells']} 件（対象ファイル {s['recheck_files']} 件）",
    ]
    if s["recheck_by_metric"]:
        for m, n in sorted(s["recheck_by_metric"].items(), key=lambda x: -x[1]):
            lines.append(f"  - {m}: {n}")
    else:
        lines.append("  - (なし)")
    if s["first_only"] or s["second_only"]:
        lines += ["", "## 突合できなかった行", ""]
        if s["first_only"]:
            lines.append("第1のみ: " + ", ".join(s["first_only"][:30]))
        if s["second_only"]:
            lines.append("第2のみ: " + ", ".join(s["second_only"][:30]))
    if s["warnings"]:
        lines += ["", "## 警告", ""]
        lines.extend(f"- {w}" for w in s["warnings"])
    lines.append("")
    return "\n".join(lines)
