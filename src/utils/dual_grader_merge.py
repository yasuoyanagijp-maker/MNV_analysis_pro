"""
Merge first-grader and second-reader MNV CSVs into one adopted-values CSV.

Reuses the reading-center RPD adoption code
(``tools/reading_center_rpd/compute_adopted_from_dual_csv.py``):

1. Match rows by image file stem (the second reader grades the exported
   ``export/images/{institution}/{lesion_id}.png`` files, whose stems equal the
   first grader's original filenames after sanitization).
2. Per numeric column, adopt the arithmetic mean when RPD <= threshold
   (default 20%); otherwise NA (recheck) — via the existing ``adopt_pair``.

CSV values are used as-is (no merge-time U2 recompute): the analysis pipeline
already writes U2-based Caliber Uniformity / Maturity into the default columns.

Outputs (into the second reader's output folder):
  - ``{prefix}_adopted_values.csv``  … batch-CSV schema, adopted values
  - ``{prefix}_recheck_list.csv``    … discordant major metrics (RPD > threshold)
  - ``{prefix}_summary.md``          … counts + rule statement
"""

from __future__ import annotations

import re
import sys
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
    is_numeric_column,
    read_csv,
    rpd_pct,
    to_float,
    write_csv,
)

RPD_THRESHOLD_PCT = DEFAULT_RPD_PCT  # 20%

# App batch CSVs carry the U2-based values in the default Caliber/Maturity
# columns (no separate suffix), the reading-center CLI historically wrote
# "... (U2)" columns, and newer CLI builds write "Standardized ..." columns
# (MAJOR_METRICS). Any of these notations designates the same metric, so
# RECHECK flagging must cover every variant — each CSV only ever carries one
# of them, so a metric is never double-flagged.
MAJOR_METRICS_MERGE = list(
    dict.fromkeys(
        list(MAJOR_METRICS)
        + [
            "Caliber Uniformity Score",
            "Maturity Index",
            "Caliber Uniformity Score (U2)",
            "Maturity Index (U2)",
        ]
    )
)

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

    # Union fieldnames: first-grader order, then extras from the second reader
    fieldnames = list(fields_a)
    for c in fields_b:
        if c not in fieldnames:
            fieldnames.append(c)

    # Step 1 — match by file stem
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

    # Step 2 — RPD adoption per numeric column (existing RPD<=20% rule)
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
            if col in MAJOR_METRICS_MERGE and status in ("RECHECK", "MISSING"):
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

    # NA list per case (File) — the final reader's RECHECK re-reading input
    # (recheck_md_parser reads this format back from the summary MD).
    recheck_by_file: Dict[str, List[str]] = {}
    for r in recheck_rows:
        recheck_by_file.setdefault(r["File"], []).append(r["Metric"])
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
        "recheck_files": len(recheck_by_file),
        "recheck_by_file": recheck_by_file,
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
        "1. ファイル名（stem）で行を突合。",
        f"2. RPD ≤ {s['threshold_pct']:g}% → 採用値 = 算術平均、超過 → **NA**（再計測）。",
        "",
        "**根拠:** 20%は測定誤差を許容しつつ、過度な除外を避けるために設定した。",
        "",
        "## RECHECK",
        "",
        f"- 主要指標セル: {s['recheck_cells']} 件（対象症例 {s['recheck_files']} 件）",
    ]
    # 症例別（最終読影者が再読影する対象 — recheck_md_parser がこの形式を読む）
    recheck_by_file = s.get("recheck_by_file") or {}
    if recheck_by_file:
        lines.append("- 症例別（NA となった主要指標）:")
        for fname in sorted(recheck_by_file):
            lines.append(f"  - {fname}: {', '.join(recheck_by_file[fname])}")
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
