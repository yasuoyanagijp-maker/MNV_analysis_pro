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

On images the final reader actually re-read, remaining **numeric NA** cells
(non-major metrics that failed dual-read RPD) are filled with the same triad
median. Already-adopted values (RPD ≤ 20%) are never overwritten.

**Subtype / Pathophysiology** NA on those images is filled from the grader
whose **Vsl Area (mm2)** equals the triad median (the person whose vessel
area was selected). Ties prefer the final reader.

Outputs are NEW files next to the original integrated outputs:

- ``{prefix}_triad_resolved_cells.csv``  … per-cell audit record
- ``{prefix}_triad_adopted_values.csv``  … official triad-adopted values
- ``{prefix}_triad_avg_fallback.csv``    … PROVISIONAL: leftover NA copied
  from the dual-read ``avg_fallback`` (G1/G2 mean). Not for submission.
- ``{prefix}_triad_summary.md``          … counts + rule statement

``dry_run=True`` computes everything and returns the same summary without
writing any file (two-step confirm flow for clinical data safety).
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.utils.dual_grader_merge import (  # noqa: E402
    AVG_FILLED_COLS_COL,
    AVG_FILLED_FLAG_COL,
    MAJOR_METRICS_MERGE,
    match_stem,
)
from src.utils.recheck_md_parser import (  # noqa: E402
    RecheckTarget,
    column_candidates,
    map_parameter_name,
)

# Existing RPD(20%) adoption implementation — thresholds reused, not redefined.
from src.utils.second_reader import discover_dual_source_csvs  # noqa: E402
from tools.reading_center_rpd.compute_adopted_from_dual_csv import (  # noqa: E402
    DEFAULT_RPD_PCT,
    META_COLS,
    apply_u2,
    is_numeric_column,
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
VSL_AREA_COL = "Vsl Area (mm2)"
CATEGORY_COLS = ("Subtype", "Pathophysiology")
_OWNER_PREF = ("FR", "G2", "G1")
_SOURCE_CSV_JSON_SUFFIX = "_source_csvs.json"
_AVG_FALLBACK_SKIP_COLS = {
    "ID",
    "File",
    "Analyst",
    AVG_FILLED_FLAG_COL,
    AVG_FILLED_COLS_COL,
    NEEDS_REVIEW_COL,
}
_MAJOR_REMAINDER_SKIP = frozenset(
    cand for metric in MAJOR_METRICS_MERGE for cand in column_candidates(metric)
)


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


def _is_na_token(val: Any) -> bool:
    s = str(val if val is not None else "").strip()
    return s == "" or s.upper() == "NA"


def _finite_close(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12)


def vsl_area_median_owner(
    g1: Optional[float],
    g2: Optional[float],
    final_reader: Optional[float],
) -> Optional[str]:
    """
    Return ``"G1"`` / ``"G2"`` / ``"FR"`` for the grader whose Vsl Area is
    the triad median.

    Three distinct values → the middle measurement (unique). Exact ties
    prefer FR then G2 then G1. When the median is the mean of two values
    (one grader missing) and equals neither, pick the closest; equal
    distance uses the same preference order.
    """
    labeled = [("G1", g1), ("G2", g2), ("FR", final_reader)]
    avail: List[Tuple[str, float]] = []
    for key, raw in labeled:
        if raw is None:
            continue
        try:
            v = float(raw)
        except (TypeError, ValueError):
            continue
        if math.isfinite(v):
            avail.append((key, v))
    if not avail:
        return None
    med = float(statistics.median([v for _, v in avail]))
    exact = [k for k, v in avail if _finite_close(v, med)]
    if exact:
        for pref in _OWNER_PREF:
            if pref in exact:
                return pref
        return exact[0]
    rank = {k: i for i, k in enumerate(_OWNER_PREF)}
    return min(avail, key=lambda kv: (abs(kv[1] - med), rank.get(kv[0], 9)))[0]


def _category_text(row: Optional[Dict[str, Any]], column: str) -> str:
    if row is None:
        return ""
    return str(row.get(column) or "").strip()


def _load_source_csv_paths(
    *,
    adopted_csv: Path,
    prefix: str,
    first_csv: Optional[Path],
    second_csv: Optional[Path],
    warnings: List[str],
) -> Tuple[Optional[Path], Optional[Path]]:
    """Resolve G1/G2 batch CSVs: explicit args → sidecar JSON → sibling folders."""

    def _ok(p: Optional[Path]) -> Optional[Path]:
        if p is None:
            return None
        path = Path(p).expanduser()
        return path if path.is_file() else None

    g1 = _ok(first_csv)
    g2 = _ok(second_csv)
    if first_csv is not None and g1 is None:
        warnings.append(f"第1グレーダーCSVが見つかりません: {first_csv}")
    if second_csv is not None and g2 is None:
        warnings.append(f"第2リーダーCSVが見つかりません: {second_csv}")
    if g1 is not None and g2 is not None:
        return g1, g2

    sidecar = Path(adopted_csv).parent / f"{prefix}{_SOURCE_CSV_JSON_SUFFIX}"
    if sidecar.is_file():
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as ex:
            warnings.append(f"source_csvs.json を読めません: {ex}")
        else:
            if g1 is None:
                g1 = _ok(Path(str(data.get("first_csv") or "")))
            if g2 is None:
                g2 = _ok(Path(str(data.get("second_csv") or "")))

    if g1 is None or g2 is None:
        found_g1, found_g2 = discover_dual_source_csvs(adopted_csv)
        if g1 is None:
            g1 = _ok(found_g1)
        if g2 is None:
            g2 = _ok(found_g2)

    return g1, g2


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
    """(stem, canonical metric column) → (g1, g2) from a recheck_list CSV.

    Metric names are canonicalized (bare / "(U2)" / "Standardized" Caliber
    and Maturity notations all designate the same metric) so lookups match
    regardless of which pipeline build wrote the recheck list.
    """
    out: Dict[Tuple[str, str], Tuple[Optional[float], Optional[float]]] = {}
    for r in rows:
        stem = _recheck_row_stem(r)
        metric = str(r.get("Metric") or "").strip()
        if not stem or not metric:
            continue
        canonical = map_parameter_name(metric) or metric
        out[(stem, canonical)] = _recheck_row_g1_g2(r)
    return out


def _first_available_value(
    row: Optional[Dict[str, Any]], column: str
) -> Optional[float]:
    """First finite value among the column's equivalent names in ``row``."""
    if row is None:
        return None
    for cand in column_candidates(column):
        v = to_float(row.get(cand))
        if v is not None:
            return v
    return None


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


def _index_rows_by_stem(
    rows: List[Dict[str, Any]],
    warnings: Optional[List[str]] = None,
    label: str = "",
) -> Dict[str, Dict[str, Any]]:
    idx: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        key = match_stem(r.get("File", "")) or match_stem(r.get("ID", ""))
        if not key:
            continue
        if key in idx and warnings is not None:
            warnings.append(
                f"重複する行キーを検出（後の行を使用）: {key}"
                + (f"（{label}）" if label else "")
            )
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


def _make_record(
    *,
    image_file: str,
    metric: str,
    g1: Any,
    g2: Any,
    fr: Any,
    cell: Dict[str, Any],
    stem: str,
    extra_note: str = "",
    final_override: Any = None,
) -> Dict[str, Any]:
    note = cell.get("note") or ""
    if extra_note:
        note = f"{note}; {extra_note}" if note else extra_note
    final_raw = cell["final_value"] if final_override is None else final_override
    return {
        "File": image_file,
        "Metric": metric,
        "g1_value": _fmt(g1),
        "g2_value": _fmt(g2),
        "final_reader_value": _fmt(fr),
        "final_value": _fmt(final_raw),
        "needs_review": _fmt(cell.get("needs_review", False)),
        "cv_percent": _fmt(cell.get("cv_percent")),
        "rpd_median_vs_final_reader_pct": _fmt(
            cell.get("rpd_median_vs_final_reader_pct")
        ),
        "n_values": cell.get("n_values", 0),
        "status": cell.get("status") or "",
        "note": note,
        "_stem": stem,
        "_final_value_raw": final_raw,
    }


def _write_adopted_cell(
    row: Dict[str, Any],
    metric: str,
    value: Any,
    adopted_field_set: set,
    warnings: List[str],
    image_file: str,
) -> bool:
    target_col = next(
        (c for c in column_candidates(metric) if c in adopted_field_set),
        metric if metric in adopted_field_set else None,
    )
    if target_col is None:
        warnings.append(
            f"adopted_valuesに列 {metric} がありません（適用スキップ）: {image_file}"
        )
        return False
    row[target_col] = value if isinstance(value, str) else _fmt(value)
    return True


def _triad_avg_fallback_readme_text(csv_name: str, n_filled: int) -> str:
    return "\n".join(
        [
            f"{csv_name} について",
            "",
            "PROVISIONAL / REFERENCE ONLY — NOT the official triad-adopted values.",
            "Leftover NA cells in the triad adopted CSV are copied from the dual-read",
            f"`*_avg_fallback.csv` (G1/G2 simple mean when RPD > {RPD_REVIEW_THRESHOLD_PCT:g}%).",
            "Already-resolved triad values are never overwritten.",
            f"Filled cells this file: {n_filled}. Flags: {AVG_FILLED_FLAG_COL} / {AVG_FILLED_COLS_COL}.",
            "",
            "この CSV はトライアッド確定後も残った NA を、既存の avg_fallback",
            "（G1/G2単純平均）で埋めた参考・暫定ファイルです。新しい解析は行っていません。",
            "正式な確定値ではありません。提出・二次解析には *_triad_adopted_values.csv を使用してください。",
            "RPD閾値超過の単純平均は真値の折衷にはなりません。",
            "",
        ]
    )


def overlay_avg_fallback(
    triad_rows: List[Dict[str, Any]],
    triad_fields: List[str],
    avg_rows: List[Dict[str, Any]],
) -> Tuple[List[str], List[Dict[str, Any]], int]:
    """Copy non-NA avg_fallback values into triad cells that are still NA."""
    avg_idx = _index_rows_by_stem(avg_rows)
    out_fields = list(triad_fields)
    for col in (AVG_FILLED_FLAG_COL, AVG_FILLED_COLS_COL):
        if col not in out_fields:
            out_fields.append(col)
    n_filled = 0
    out_rows: List[Dict[str, Any]] = []
    for row in triad_rows:
        out = dict(row)
        stem = match_stem(row.get("File", "")) or match_stem(row.get("ID", ""))
        src = avg_idx.get(stem)
        filled: List[str] = []
        if src is not None:
            for col in triad_fields:
                if col in _AVG_FALLBACK_SKIP_COLS:
                    continue
                if not _is_na_token(out.get(col)):
                    continue
                cand = src.get(col)
                if _is_na_token(cand):
                    continue
                out[col] = cand
                filled.append(col)
        n_filled += len(filled)
        out[AVG_FILLED_FLAG_COL] = "TRUE" if filled else "FALSE"
        out[AVG_FILLED_COLS_COL] = ";".join(filled)
        if filled:
            base = str(out.get("Analyst") or "").rstrip()
            suffix = (
                "PROVISIONAL remaining-NA = G1/G2 mean (avg_fallback, reference only)"
            )
            out["Analyst"] = f"{base}; {suffix}" if base else suffix
        out_rows.append(out)
    return out_fields, out_rows, n_filled


def _looks_numeric_col(
    col: str,
    g1_row: Optional[Dict[str, Any]],
    g2_row: Optional[Dict[str, Any]],
    fr_row: Optional[Dict[str, Any]],
    g1_rows: List[Dict[str, Any]],
    g2_rows: List[Dict[str, Any]],
) -> bool:
    if col in META_COLS or col in CATEGORY_COLS or col == NEEDS_REVIEW_COL:
        return False
    if g1_rows and g2_rows and is_numeric_column(col, g1_rows, g2_rows):
        return True
    return any(
        to_float((r or {}).get(col)) is not None for r in (g1_row, g2_row, fr_row)
    )


def _fill_reread_remainder(
    *,
    triad_rows_idx: Dict[str, Dict[str, Any]],
    adopted_fields: List[str],
    g1_idx: Dict[str, Dict[str, Any]],
    g2_idx: Dict[str, Dict[str, Any]],
    fr_idx: Dict[str, Dict[str, Any]],
    g1_rows: List[Dict[str, Any]],
    g2_rows: List[Dict[str, Any]],
    threshold: float,
    review_by_stem: Dict[str, List[str]],
    warnings: List[str],
) -> Tuple[List[Dict[str, Any]], int, int]:
    """Fill leftover NA on images present in the final-reader CSV."""
    extra: List[Dict[str, Any]] = []
    n_numeric = 0
    n_category = 0
    adopted_field_set = set(adopted_fields)
    skip_cols = (set(META_COLS) | {NEEDS_REVIEW_COL}) - set(CATEGORY_COLS)

    for stem, fr_row in fr_idx.items():
        row = triad_rows_idx.get(stem)
        if row is None:
            continue
        g1_row = g1_idx.get(stem)
        g2_row = g2_idx.get(stem)
        image_file = str(row.get("File") or fr_row.get("File") or stem)
        g1_vsl = _first_available_value(g1_row, VSL_AREA_COL)
        g2_vsl = _first_available_value(g2_row, VSL_AREA_COL)
        fr_vsl = _first_available_value(fr_row, VSL_AREA_COL)
        owner = vsl_area_median_owner(g1_vsl, g2_vsl, fr_vsl)
        owner_row = {"G1": g1_row, "G2": g2_row, "FR": fr_row}.get(owner or "")

        for col in adopted_fields:
            if col in skip_cols or not _is_na_token(row.get(col)):
                continue
            if col in CATEGORY_COLS:
                if owner is None or owner_row is None:
                    extra.append(
                        _make_record(
                            image_file=image_file,
                            metric=col,
                            g1=_category_text(g1_row, col),
                            g2=_category_text(g2_row, col),
                            fr=_category_text(fr_row, col),
                            cell={
                                "final_value": None,
                                "needs_review": False,
                                "cv_percent": None,
                                "rpd_median_vs_final_reader_pct": None,
                                "n_values": 0,
                                "status": "UNRESOLVED",
                                "note": "Vsl Area中央値のグレーダーを特定できない",
                            },
                            stem=stem,
                        )
                    )
                    continue
                chosen = _category_text(owner_row, col)
                if _is_na_token(chosen):
                    extra.append(
                        _make_record(
                            image_file=image_file,
                            metric=col,
                            g1=_category_text(g1_row, col),
                            g2=_category_text(g2_row, col),
                            fr=_category_text(fr_row, col),
                            cell={
                                "final_value": None,
                                "needs_review": False,
                                "cv_percent": None,
                                "rpd_median_vs_final_reader_pct": None,
                                "n_values": 3,
                                "status": "UNRESOLVED",
                                "note": f"Vsl Area中央値グレーダー({owner})の{col}が空",
                            },
                            stem=stem,
                        )
                    )
                    continue
                cat_cell = {
                    "final_value": chosen,
                    "needs_review": False,
                    "cv_percent": None,
                    "rpd_median_vs_final_reader_pct": None,
                    "n_values": 3,
                    "status": "OK",
                    "note": "",
                }
                rec = _make_record(
                    image_file=image_file,
                    metric=col,
                    g1=_category_text(g1_row, col),
                    g2=_category_text(g2_row, col),
                    fr=_category_text(fr_row, col),
                    cell=cat_cell,
                    stem=stem,
                    extra_note=(
                        f"Vsl Area中央値のグレーダー({owner})の{col}を採用"
                    ),
                    final_override=chosen,
                )
                if _write_adopted_cell(
                    row, col, chosen, adopted_field_set, warnings, image_file
                ):
                    n_category += 1
                    extra.append(rec)
                continue

            if not _looks_numeric_col(col, g1_row, g2_row, fr_row, g1_rows, g2_rows):
                continue
            if col in _MAJOR_REMAINDER_SKIP:
                # Major metrics are filled only via the RECHECK target list.
                continue
            a = _first_available_value(g1_row, col)
            b = _first_available_value(g2_row, col)
            f = _first_available_value(fr_row, col)
            cell = resolve_cell(a, b, f, threshold)
            rec = _make_record(
                image_file=image_file,
                metric=col,
                g1=a,
                g2=b,
                fr=f,
                cell=cell,
                stem=stem,
                extra_note="再読影像の数値NAをトライアッド中央値で補完",
            )
            extra.append(rec)
            if cell["status"] != "OK":
                continue
            if cell["needs_review"]:
                review_by_stem.setdefault(stem, []).append(col)
            if _write_adopted_cell(
                row,
                col,
                rec["final_value"],
                adopted_field_set,
                warnings,
                image_file,
            ):
                n_numeric += 1
    return extra, n_numeric, n_category


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
    first_csv: Optional[Path] = None,
    second_csv: Optional[Path] = None,
    avg_fallback_csv: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Resolve RECHECK targets with the triad median rule, then fill leftover
    numeric NA (and Subtype/Pathophysiology NA) on re-read images.

    Unless ``dry_run``, write output files next to ``out_dir``.
    ``first_csv`` / ``second_csv`` are optional; when omitted the resolver
    reads ``{prefix}_source_csvs.json`` or sibling ``output_folder_*`` /
    ``second_reader_output_*`` folders.
    ``avg_fallback_csv`` defaults to ``{prefix}_avg_fallback.csv`` beside
    ``adopted_csv``; leftover triad NA is copied from it into a provisional
    ``{prefix}_triad_avg_fallback.csv``.
    """
    warnings: List[str] = []

    try:
        _, recheck_rows = read_csv(Path(recheck_csv))
        adopted_fields, adopted_rows = read_csv(Path(adopted_csv))
        fr_fields, fr_rows = read_csv(Path(final_reader_csv))
    except (ValueError, SystemExit) as ex:
        raise ValueError(f"CSV read failed: {ex}") from ex

    # Final-reader CSV gets the same U2 recompute as G1/G2 so standardized
    # columns exist when possible; value lookups additionally fall back to
    # the equivalent column names (bare / "(U2)" / "Standardized").
    fr_fields, fr_rows = _apply_u2_safe(fr_fields, fr_rows, warnings)
    fr_idx = _index_rows_by_stem(fr_rows, warnings, "最終読影者CSV")
    g1g2_idx = index_recheck_rows(recheck_rows)

    src_g1, src_g2 = _load_source_csv_paths(
        adopted_csv=Path(adopted_csv),
        prefix=prefix,
        first_csv=first_csv,
        second_csv=second_csv,
        warnings=warnings,
    )
    g1_rows: List[Dict[str, Any]] = []
    g2_rows: List[Dict[str, Any]] = []
    g1_idx: Dict[str, Dict[str, Any]] = {}
    g2_idx: Dict[str, Dict[str, Any]] = {}
    if src_g1 is not None and src_g2 is not None:
        try:
            g1_fields, g1_rows = read_csv(src_g1)
            g2_fields, g2_rows = read_csv(src_g2)
        except (ValueError, SystemExit) as ex:
            warnings.append(f"G1/G2 CSV read failed: {ex}")
            g1_rows, g2_rows = [], []
        else:
            _, g1_rows = _apply_u2_safe(g1_fields, g1_rows, warnings)
            _, g2_rows = _apply_u2_safe(g2_fields, g2_rows, warnings)
            g1_idx = _index_rows_by_stem(g1_rows, warnings, "第1グレーダーCSV")
            g2_idx = _index_rows_by_stem(g2_rows, warnings, "第2リーダーCSV")
    elif src_g1 is None or src_g2 is None:
        warnings.append(
            "G1/G2のバッチCSVを特定できないため、再読影像の残NA補完"
            "（非主要指標・Subtype/Pathophysiology）をスキップします。"
        )

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
        fr_val = _first_available_value(fr_row, t.column)
        if fr_row is None:
            warnings.append(
                f"最終読影者CSVに {t.image_file} の行がありません（未読影？）。"
            )
        canonical = map_parameter_name(t.column) or t.column
        pair = g1g2_idx.get((t.image_stem, canonical))
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
    triad_rows_idx = _index_rows_by_stem(triad_rows, warnings, "adopted_values")
    adopted_field_set = set(adopted_fields)
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
        # Write into the equivalent column that actually exists in the
        # adopted CSV — a name absent from its header would be dropped by
        # the CSV writer and the resolution silently lost.
        target_col = next(
            (c for c in column_candidates(rec["Metric"]) if c in adopted_field_set),
            None,
        )
        if target_col is None:
            warnings.append(
                f"adopted_valuesに列 {rec['Metric']} がありません（適用スキップ）: "
                f"{rec['File']}"
            )
            continue
        row[target_col] = rec["final_value"]
        n_cells_applied += 1

    n_extra_numeric = 0
    n_extra_category = 0
    if g1_idx and g2_idx:
        extra_recs, n_extra_numeric, n_extra_category = _fill_reread_remainder(
            triad_rows_idx=triad_rows_idx,
            adopted_fields=adopted_fields,
            g1_idx=g1_idx,
            g2_idx=g2_idx,
            fr_idx=fr_idx,
            g1_rows=g1_rows,
            g2_rows=g2_rows,
            threshold=threshold,
            review_by_stem=review_by_stem,
            warnings=warnings,
        )
        records.extend(extra_recs)
        n_cells_applied += n_extra_numeric + n_extra_category
        for rec in extra_recs:
            if rec["status"] == "OK":
                n_resolved += 1
                if rec["needs_review"] == "true":
                    n_review += 1
            elif rec["status"] == "UNRESOLVED":
                n_unresolved += 1

    analyst = (
        f"Dual-read mean (RPD<={threshold:g}%; else NA); "
        f"RECHECK cells = triad median (G1, G2, {final_reader_label})"
    )
    if n_extra_numeric or n_extra_category:
        analyst += (
            "; re-read leftover NA = triad median; "
            "Subtype/Pathophysiology NA = Vsl Area median grader"
        )
    for rec in records:
        if rec["status"] != "OK":
            continue
        row = triad_rows_idx.get(rec["_stem"])
        if row is not None:
            row["Analyst"] = analyst

    for row in triad_rows:
        stem = match_stem(row.get("File", "")) or match_stem(row.get("ID", ""))
        cols = review_by_stem.get(stem)
        row[NEEDS_REVIEW_COL] = "; ".join(cols) if cols else ""

    out_dir = Path(out_dir)
    cells_path = out_dir / f"{prefix}_triad_resolved_cells.csv"
    adopted_path = out_dir / f"{prefix}_triad_adopted_values.csv"
    summary_path = out_dir / f"{prefix}_triad_summary.md"
    fallback_path = out_dir / f"{prefix}_triad_avg_fallback.csv"
    fallback_readme_path = out_dir / f"{prefix}_triad_avg_fallback_README.txt"

    avg_src = Path(avg_fallback_csv) if avg_fallback_csv else (
        Path(adopted_csv).parent / f"{prefix}_avg_fallback.csv"
    )
    n_avg_filled = 0
    fallback_fields: List[str] = []
    fallback_rows: List[Dict[str, Any]] = []
    if avg_src.is_file():
        try:
            _, avg_rows = read_csv(avg_src)
        except (ValueError, SystemExit) as ex:
            warnings.append(f"avg_fallback CSV read failed: {ex}")
        else:
            fallback_fields, fallback_rows, n_avg_filled = overlay_avg_fallback(
                triad_rows, out_fields, avg_rows
            )
    else:
        warnings.append(
            f"avg_fallback が無いため暫定NA埋めファイルをスキップします: {avg_src.name}"
        )

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
        "n_extra_numeric": n_extra_numeric,
        "n_extra_category": n_extra_category,
        "n_avg_filled": n_avg_filled,
        "first_csv": str(src_g1) if src_g1 else "",
        "second_csv": str(src_g2) if src_g2 else "",
        "records": records,
        "warnings": warnings,
        "triad_cells_csv": str(cells_path),
        "triad_adopted_csv": str(adopted_path),
        "triad_summary_md": str(summary_path),
        "triad_avg_fallback_csv": str(fallback_path),
        "triad_avg_fallback_readme": str(fallback_readme_path),
    }

    if not dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)
        write_csv(cells_path, TRIAD_CELL_FIELDS, records)
        write_csv(adopted_path, out_fields, triad_rows)
        summary_path.write_text(_render_triad_summary_md(summary), encoding="utf-8")
        if fallback_rows:
            write_csv(fallback_path, fallback_fields, fallback_rows)
            fallback_readme_path.write_text(
                _triad_avg_fallback_readme_text(fallback_path.name, n_avg_filled),
                encoding="utf-8",
            )

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
        "1. `final_value = median(G1, G2, 最終読影者)`（RECHECK指定セル、および最終読影者が再読影した画像に残った数値NA）。",
        f"2. RPD(median, 最終読影者) > {s['threshold_pct']:g}% → `needs_review = true`"
        "（値は確定・処理は継続）。",
        "3. CV%（SD/平均×100, ddof=1）を3値で算出し再現性報告（CV%/ICC）に使用。",
        "4. 既に採用済みの値（RPD≤20%の平均）は上書きしない。最終読影CSVに無い画像は触らない。",
        "5. 再読影像の Subtype / Pathophysiology が NA のとき、"
        "Vsl Area (mm2) のトライアッド中央値を出したグレーダーの分類を採用する。",
        "6. 参考出力 `*_triad_avg_fallback.csv`: トライアッド後も残った NA を"
        "既存の G1/G2 単純平均（avg_fallback）で埋めた**暫定ファイル**（正本ではない）。",
        "",
        "## 集計",
        "",
        f"- RECHECK対象セル: {s['n_targets']}",
        f"- 確定: {s['n_resolved']}（うち要レビュー: {s['n_needs_review']}）",
        f"- 未解決: {s['n_unresolved']}",
        f"- 再読影像の数値NA補完: {s.get('n_extra_numeric', 0)}",
        f"- Subtype/Pathophysiology NA補完: {s.get('n_extra_category', 0)}",
        f"- adopted への適用セル: {s['n_cells_applied']}",
        f"- 暫定 avg_fallback 埋め（残NA）: {s.get('n_avg_filled', 0)}"
        + (
            f"（`{Path(s['triad_avg_fallback_csv']).name}`）"
            if s.get("triad_avg_fallback_csv")
            else ""
        ),
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
