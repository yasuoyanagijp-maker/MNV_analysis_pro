"""
Triad (G1 × G2 × final reader) median resolution for RECHECK cells.

For each RECHECK cell (case image × major-metric column) flagged by the
dual-read RPD adoption (``dual_grader_merge`` / reading-center tool):

- ``final_value``  = median(G1, G2, final reader)
- ``needs_review`` = True when RPD(|median − final reader|) exceeds the SAME
  threshold already used for NA/adoption decisions (``DEFAULT_RPD_PCT`` = 20%).
  The value stays adopted and processing continues (review flag only).
- ``cv_percent``   = SD/mean × 100 over the triad (sample SD, ddof=1) — kept
  for reproducibility reporting (triads are reported as CV%/ICC, not pairwise
  RPD).
- g1/g2/final-reader values are all retained for audit.

Only the cells designated by the RECHECK markdown are resolved; every other
cell of the final reader's re-read is ignored and the existing adopted values
are never overwritten in place. Outputs are NEW files next to the original
integrated outputs:

- ``{prefix}_triad_resolved_cells.csv``  … per-cell audit record
- ``{prefix}_triad_adopted_values.csv``  … adopted CSV with RECHECK cells
  replaced by the triad median (plus a trailing review-flag column)
- ``{prefix}_triad_summary.md``          … counts + rule statement

``dry_run=True`` computes everything and returns the same summary without
writing any file (two-step confirm flow for clinical data safety).
"""

from __future__ import annotations

import math
import statistics
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.utils.dual_grader_merge import match_stem  # noqa: E402
from src.utils.recheck_md_parser import RecheckTarget  # noqa: E402

# Existing RPD(20%) adoption implementation — thresholds reused, not redefined.
from tools.reading_center_rpd.compute_adopted_from_dual_csv import (  # noqa: E402
    DEFAULT_RPD_PCT,
    apply_u2,
    read_csv,
    rpd_pct,
    to_float,
    write_csv,
)

RPD_REVIEW_THRESHOLD_PCT = DEFAULT_RPD_PCT  # same 20% as NA/adoption — no new threshold

TRIAD_CELL_FIELDS = [
    "File",
    "Metric",
    "g1_value",
    "g2_value",
    "final_reader_value",
    "final_value",
    "needs_review",
    "cv_percent",
    "rpd_median_vs_final_reader_pct",
    "n_values",
    "status",
    "note",
]

# Trailing audit column appended to the triad adopted CSV (new file, so the
# batch-CSV schema of the original adopted CSV is untouched).
NEEDS_REVIEW_COL = "Triad Needs Review (metrics)"


def triad_median(values: Sequence[Optional[float]]) -> Optional[float]:
    """Median of the available (non-None) values; None when none available."""
    avail = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    if not avail:
        return None
    return float(statistics.median(avail))


def cv_percent(values: Sequence[Optional[float]]) -> Optional[float]:
    """
    CV% = sample SD (ddof=1) / mean × 100 over available values.

    None when fewer than 2 values or when the mean is ~0 (undefined).
    """
    avail = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    if len(avail) < 2:
        return None
    mean = statistics.fmean(avail)
    if abs(mean) < 1e-12:
        return None
    sd = statistics.stdev(avail)
    return abs(sd / mean) * 100.0


def resolve_cell(
    g1: Optional[float],
    g2: Optional[float],
    final_reader: Optional[float],
    threshold: float = RPD_REVIEW_THRESHOLD_PCT,
) -> Dict[str, Any]:
    """
    Resolve one triad cell. Returns a dict with final_value / needs_review /
    cv_percent / rpd vs final reader / n_values / status / note.

    The cell is UNRESOLVED (final_value None) only when the final reader's
    value is missing — the whole point of the re-read — or when no G1/G2
    value exists at all (median of a single reading is not a triad).
    """
    values = (g1, g2, final_reader)
    note = ""
    if final_reader is None:
        return {
            "final_value": None,
            "needs_review": False,
            "cv_percent": None,
            "rpd_median_vs_final_reader_pct": None,
            "n_values": sum(v is not None for v in values),
            "status": "UNRESOLVED",
            "note": "最終読影者の値がありません（再読影結果にこのセルが無い）",
        }
    if g1 is None and g2 is None:
        return {
            "final_value": None,
            "needs_review": False,
            "cv_percent": None,
            "rpd_median_vs_final_reader_pct": None,
            "n_values": 1,
            "status": "UNRESOLVED",
            "note": "G1/G2の値がどちらもありません（recheck_listを確認）",
        }
    if g1 is None or g2 is None:
        note = "G1/G2の一方が欠損のため2値の中央値（=平均）を使用"

    median = triad_median(values)
    rpd = rpd_pct(median, final_reader)
    needs_review = bool(rpd is not None and rpd > threshold)
    if rpd is None:
        # rpd_pct returns None only when denominator ~0 but |a-b| > eps
        needs_review = True
        note = (note + "; " if note else "") + "RPDが定義できない値の組み合わせ"
    return {
        "final_value": median,
        "needs_review": needs_review,
        "cv_percent": cv_percent(values),
        "rpd_median_vs_final_reader_pct": rpd,
        "n_values": sum(v is not None for v in values),
        "status": "OK",
        "note": note,
    }


# ---------------------------------------------------------------------------
# recheck_list.csv indexing (app format and reading-center CLI format)
# ---------------------------------------------------------------------------


def _recheck_row_stem(row: Dict[str, Any]) -> str:
    f = str(row.get("File") or "").strip()
    if f:
        return match_stem(f)
    case = str(row.get("Case") or "").strip()
    visit = str(row.get("Visit") or "").strip()
    if case and visit:
        return match_stem(f"{case}_{visit}")
    return match_stem(str(row.get("MatchKey") or "").replace("|", "_"))


def _recheck_row_g1_g2(row: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    g1 = to_float(row.get("Value_grader1"))
    if g1 is None:
        g1 = to_float(row.get("Value_site"))
    g2 = to_float(row.get("Value_reader2"))
    return g1, g2


def index_recheck_rows(
    rows: List[Dict[str, Any]],
) -> Dict[Tuple[str, str], Tuple[Optional[float], Optional[float]]]:
    """(stem, metric column) → (g1, g2) from a recheck_list CSV."""
    out: Dict[Tuple[str, str], Tuple[Optional[float], Optional[float]]] = {}
    for r in rows:
        stem = _recheck_row_stem(r)
        metric = str(r.get("Metric") or "").strip()
        if not stem or not metric:
            continue
        out[(stem, metric)] = _recheck_row_g1_g2(r)
    return out


def _apply_u2_safe(
    fieldnames: List[str],
    rows: List[Dict[str, Any]],
    warnings: List[str],
) -> Tuple[List[str], List[Dict[str, Any]]]:
    try:
        return apply_u2(list(fieldnames), [dict(r) for r in rows], None)
    except (Exception, SystemExit) as ex:  # SystemExit: missing reference json
        warnings.append(
            f"U2 recompute failed for final-reader CSV: {ex} — using original values."
        )
        return list(fieldnames), [dict(r) for r in rows]


def _index_rows_by_stem(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    idx: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        key = match_stem(r.get("File", "")) or match_stem(r.get("ID", ""))
        if key:
            idx[key] = r
    return idx


def _fmt(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return f"{v:.10g}"
    return str(v)


def resolve_triad_recheck(
    targets: Sequence[RecheckTarget],
    *,
    recheck_csv: Path,
    adopted_csv: Path,
    final_reader_csv: Path,
    out_dir: Path,
    prefix: str,
    threshold: float = RPD_REVIEW_THRESHOLD_PCT,
    final_reader_label: str = "FinalReader",
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Resolve all RECHECK targets with the triad median rule and (unless
    ``dry_run``) write the three output files next to ``out_dir``.

    Returns a summary dict incl. per-cell records; raises ValueError when the
    inputs cannot be read/matched at all.
    """
    warnings: List[str] = []

    try:
        _, recheck_rows = read_csv(Path(recheck_csv))
        adopted_fields, adopted_rows = read_csv(Path(adopted_csv))
        fr_fields, fr_rows = read_csv(Path(final_reader_csv))
    except (ValueError, SystemExit) as ex:
        raise ValueError(f"CSV read failed: {ex}") from ex

    # Final-reader CSV needs the same mandatory U2 recompute as G1/G2 so that
    # "(U2)" columns exist and are comparable.
    fr_fields, fr_rows = _apply_u2_safe(fr_fields, fr_rows, warnings)
    fr_idx = _index_rows_by_stem(fr_rows)
    g1g2_idx = index_recheck_rows(recheck_rows)

    if not fr_idx:
        raise ValueError(
            f"最終読影者CSVに突合可能な行がありません: {Path(final_reader_csv).name}"
        )

    records: List[Dict[str, Any]] = []
    review_by_stem: Dict[str, List[str]] = {}
    n_resolved = 0
    n_review = 0
    n_unresolved = 0

    for t in targets:
        fr_row = fr_idx.get(t.image_stem)
        fr_val = to_float(fr_row.get(t.column)) if fr_row else None
        if fr_row is None:
            warnings.append(
                f"最終読影者CSVに {t.image_file} の行がありません（未読影？）。"
            )
        pair = g1g2_idx.get((t.image_stem, t.column))
        if pair is None:
            g1 = g2 = None
            warnings.append(
                f"recheck_listに {t.image_file} × {t.column} の行がありません。"
            )
        else:
            g1, g2 = pair

        cell = resolve_cell(g1, g2, fr_val, threshold)
        if cell["status"] == "OK":
            n_resolved += 1
            if cell["needs_review"]:
                n_review += 1
                review_by_stem.setdefault(t.image_stem, []).append(t.column)
        else:
            n_unresolved += 1

        records.append(
            {
                "File": t.image_file,
                "Metric": t.column,
                "g1_value": _fmt(g1),
                "g2_value": _fmt(g2),
                "final_reader_value": _fmt(fr_val),
                "final_value": _fmt(cell["final_value"]),
                "needs_review": _fmt(cell["needs_review"]),
                "cv_percent": _fmt(cell["cv_percent"]),
                "rpd_median_vs_final_reader_pct": _fmt(
                    cell["rpd_median_vs_final_reader_pct"]
                ),
                "n_values": cell["n_values"],
                "status": cell["status"],
                "note": cell["note"],
                # kept out of the CSV (not in TRIAD_CELL_FIELDS) but returned
                # for UI preview use:
                "_stem": t.image_stem,
                "_final_value_raw": cell["final_value"],
            }
        )

    # Apply ONLY the designated cells onto a copy of the adopted CSV rows.
    out_fields = list(adopted_fields)
    if NEEDS_REVIEW_COL not in out_fields:
        out_fields.append(NEEDS_REVIEW_COL)
    triad_rows = [dict(r) for r in adopted_rows]
    triad_rows_idx = _index_rows_by_stem(triad_rows)
    n_cells_applied = 0
    for rec in records:
        if rec["status"] != "OK":
            continue
        row = triad_rows_idx.get(rec["_stem"])
        if row is None:
            warnings.append(
                f"adopted_valuesに {rec['File']} の行がありません（適用スキップ）。"
            )
            continue
        row[rec["Metric"]] = rec["final_value"]
        row["Analyst"] = (
            f"Dual-read mean (RPD<={threshold:g}%; else NA); "
            f"RECHECK cells = triad median (G1, G2, {final_reader_label})"
        )
        n_cells_applied += 1
    for row in triad_rows:
        stem = match_stem(row.get("File", "")) or match_stem(row.get("ID", ""))
        cols = review_by_stem.get(stem)
        row[NEEDS_REVIEW_COL] = "; ".join(cols) if cols else ""

    out_dir = Path(out_dir)
    cells_path = out_dir / f"{prefix}_triad_resolved_cells.csv"
    adopted_path = out_dir / f"{prefix}_triad_adopted_values.csv"
    summary_path = out_dir / f"{prefix}_triad_summary.md"

    summary: Dict[str, Any] = {
        "dry_run": bool(dry_run),
        "threshold_pct": float(threshold),
        "final_reader_label": final_reader_label,
        "recheck_csv": str(recheck_csv),
        "adopted_csv": str(adopted_csv),
        "final_reader_csv": str(final_reader_csv),
        "n_targets": len(targets),
        "n_resolved": n_resolved,
        "n_needs_review": n_review,
        "n_unresolved": n_unresolved,
        "n_cells_applied": n_cells_applied,
        "records": records,
        "warnings": warnings,
        "triad_cells_csv": str(cells_path),
        "triad_adopted_csv": str(adopted_path),
        "triad_summary_md": str(summary_path),
    }

    if not dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)
        write_csv(cells_path, TRIAD_CELL_FIELDS, records)
        write_csv(adopted_path, out_fields, triad_rows)
        summary_path.write_text(_render_triad_summary_md(summary), encoding="utf-8")

    return summary


def _render_triad_summary_md(s: Dict[str, Any]) -> str:
    lines = [
        f"# トライアッド確定（RECHECK再解析） — {datetime.now().date().isoformat()}",
        "",
        f"- recheck_list: `{Path(s['recheck_csv']).name}`",
        f"- adopted_values（元・変更せず）: `{Path(s['adopted_csv']).name}`",
        f"- 最終読影者CSV: `{Path(s['final_reader_csv']).name}`（{s['final_reader_label']}）",
        f"- 要レビューRPD閾値: **{s['threshold_pct']:g}%**（既存のNA/採用判定と同一）",
        "",
        "## ルール",
        "",
        "1. `final_value = median(G1, G2, 最終読影者)`（RECHECK指定セルのみ）。",
        f"2. RPD(median, 最終読影者) > {s['threshold_pct']:g}% → `needs_review = true`"
        "（値は確定・処理は継続）。",
        "3. CV%（SD/平均×100, ddof=1）を3値で算出し再現性報告（CV%/ICC）に使用。",
        "4. RECHECK指定外のセル・既存確定値は一切上書きしない。",
        "",
        "## 集計",
        "",
        f"- 対象セル: {s['n_targets']}",
        f"- 確定: {s['n_resolved']}（うち要レビュー: {s['n_needs_review']}）",
        f"- 未解決: {s['n_unresolved']}",
        f"- adopted への適用セル: {s['n_cells_applied']}",
        "",
        "## セル別",
        "",
        "| File | Metric | G1 | G2 | 最終読影者 | 確定値 | CV% | RPD(med,FR)% | 要レビュー | 状態 |",
        "|------|--------|----|----|-----------|--------|-----|--------------|-----------|------|",
    ]
    for r in s["records"]:
        lines.append(
            "| {File} | {Metric} | {g1} | {g2} | {fr} | {fv} | {cv} | {rpd} | {rev} | {st} |".format(
                File=r["File"],
                Metric=r["Metric"],
                g1=r["g1_value"] or "—",
                g2=r["g2_value"] or "—",
                fr=r["final_reader_value"] or "—",
                fv=r["final_value"] or "—",
                cv=r["cv_percent"] or "—",
                rpd=r["rpd_median_vs_final_reader_pct"] or "—",
                rev="⚠ true" if r["needs_review"] == "true" else "false",
                st=r["status"],
            )
        )
    if s["warnings"]:
        lines += ["", "## 警告", ""]
        lines.extend(f"- {w}" for w in s["warnings"])
    lines.append("")
    return "\n".join(lines)
