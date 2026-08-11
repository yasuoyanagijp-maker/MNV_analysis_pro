#!/usr/bin/env python3
"""
Reading-center dual-CSV adoption (RPD threshold).

Pipeline (fixed order)
----------------------
1. Recompute Caliber Uniformity (U2) + Maturity (U2) on each input CSV
2. Match rows between site CSV and 2nd-reader CSV (flexible keys)
3. Adopt arithmetic mean when RPD <= threshold (default 20%); else NA

Micron output set (3 files)
---------------------------
- *_adopted_values.csv   … same schema as batch CSV (NA = recheck)
- *_recheck_list.csv     … discordant major metrics
- *_summary.md           … RPD/ICC/BA-lite justification summary
"""

from __future__ import annotations

import argparse
import csv
import math
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tools.caliber_u2.compute_caliber_u2_from_csv import (  # noqa: E402
    process_rows as u2_process_rows,
)

DEFAULT_RPD_PCT = 20.0
EPS = 1e-12

MAJOR_METRICS = [
    "MNV Area (mm2)",
    "Vsl Area (mm2)",
    "Vsl Density (Vessel Area/MNV (%))",
    "Caliber Uniformity Score (U2)",
    "Maturity Index (U2)",
    "Network Complexity Score",
    "Fractal Dim",
    "Tortuosity",
]

META_COLS = {
    "ID",
    "File",
    "Subtype",
    "Pathophysiology",
    "Quality of analysis",
    "FD quality flag (0=OK 1=abnormal)",
    "Exclude from FD analysis",
    "FD quality reason",
    "ROI coverage low quality (0=OK 1=low)",
    "FD box sizes",
    "N FD box sizes",
    "FD scale insufficient (0=OK 1=insufficient)",
    "Analyst",
    "Started At",
    "Ended At",
    "Duration Sec",
    "Session ID",
}


@dataclass(frozen=True)
class MatchKey:
    case: str
    visit: str

    @property
    def label(self) -> str:
        return f"{self.case}|{self.visit}"


def read_csv(path: Path) -> Tuple[List[str], List[Dict[str, str]]]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            # ValueError (not SystemExit): safe for UI / library callers.
            raise ValueError(f"No header: {path}")
        return list(reader.fieldnames), [dict(r) for r in reader]


def write_csv(path: Path, fieldnames: Sequence[str], rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(fieldnames), extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})


def to_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    s = str(x).strip()
    if s == "" or s.upper() in {"NA", "NAN", "NULL"}:
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    return v if math.isfinite(v) else None


def rpd_pct(a: float, b: float) -> Optional[float]:
    denom = (abs(a) + abs(b)) / 2.0
    if denom < EPS:
        return 0.0 if abs(a - b) < EPS else None
    return abs(a - b) / denom * 100.0


def apply_u2(
    fieldnames: List[str],
    rows: List[Dict[str, str]],
    size_class: Optional[str],
) -> Tuple[List[str], List[Dict[str, Any]]]:
    return u2_process_rows(fieldnames, rows, size_class_override=size_class)


# ---------------------------------------------------------------------------
# Flexible matching (multi-center)
# ---------------------------------------------------------------------------

_VISIT_PATTERNS = [
    re.compile(r"(?P<visit>Baseline)", re.I),
    re.compile(r"(?P<visit>Week\s*\d+)", re.I),
    re.compile(r"(?P<visit>W\d+)", re.I),
    re.compile(r"(?P<visit>BL)\b", re.I),
    re.compile(r"(?P<visit>M\d+)", re.I),  # Month01 etc. if used
]


def normalize_visit(raw: str) -> str:
    s = re.sub(r"\s+", "", raw.strip())
    if re.fullmatch(r"(?i)bl|baseline", s):
        return "Baseline"
    m = re.fullmatch(r"(?i)w(?:eek)?(\d+)", s)
    if m:
        # Zero-pad so Week01/Week04/Week08 sort and match batch File stems.
        return f"Week{int(m.group(1)):02d}"
    m = re.fullmatch(r"(?i)m(?:onth)?(\d+)", s)
    if m:
        return f"M{int(m.group(1)):02d}"
    return s


def extract_visit_from_text(text: str) -> Optional[str]:
    for pat in _VISIT_PATTERNS:
        m = pat.search(text)
        if m:
            return normalize_visit(m.group("visit"))
    return None


def extract_case_from_text(text: str, case_regex: Optional[str]) -> Optional[str]:
    if case_regex:
        m = re.search(case_regex, text)
        if m:
            return m.groupdict().get("case") or (m.group(1) if m.lastindex else m.group(0))
    # Common patterns: 102-001, SITE01-00012, ABC_001
    for pat in (
        r"(?P<case>\d{2,4}-\d{2,5})",
        r"(?P<case>[A-Za-z]{2,10}\d{0,4}[-_]\d{2,6})",
        r"(?P<case>\d{6,})",
    ):
        m = re.search(pat, text)
        if m:
            return m.group("case")
    return None


def row_match_key(
    row: Dict[str, str],
    *,
    case_col: Optional[str],
    visit_col: Optional[str],
    case_regex: Optional[str],
    file_col: str = "File",
    id_col: str = "ID",
) -> MatchKey:
    case = ""
    visit = ""

    if case_col and row.get(case_col, "").strip():
        case = row[case_col].strip()
    if visit_col and row.get(visit_col, "").strip():
        visit = normalize_visit(row[visit_col])

    blob = " ".join(
        [
            str(row.get(file_col, "")),
            str(row.get(id_col, "")),
            str(row.get("Case", "")),
            str(row.get("Visit", "")),
        ]
    )
    if not case:
        case = extract_case_from_text(blob, case_regex) or str(row.get(id_col, "")).strip() or "UNKNOWN"
    if not visit:
        visit = extract_visit_from_text(blob) or "UNKNOWN"

    return MatchKey(case=case, visit=visit)


def index_by_key(
    rows: List[Dict[str, Any]],
    **kwargs: Any,
) -> Dict[MatchKey, Dict[str, Any]]:
    out: Dict[MatchKey, Dict[str, Any]] = {}
    dup = 0
    for r in rows:
        k = row_match_key(r, **kwargs)
        if k in out:
            dup += 1
        out[k] = r
    if dup:
        print(f"Warning: {dup} duplicate match keys (last wins)", file=sys.stderr)
    return out


def is_numeric_column(col: str, rows_a: List[Dict[str, Any]], rows_b: List[Dict[str, Any]]) -> bool:
    if col in META_COLS:
        return False
    for rows in (rows_a, rows_b):
        for r in rows:
            if col not in r:
                return False
            if to_float(r.get(col)) is not None:
                return True
    return False


def adopt_pair(a: Optional[float], b: Optional[float], threshold: float) -> Tuple[str, str, str]:
    if a is None or b is None:
        return "NA", "MISSING", "NA"
    r = rpd_pct(a, b)
    if r is None:
        return "NA", "RECHECK", "NA"
    if r > threshold:
        return "NA", "RECHECK", f"{r:.4f}"
    return f"{(a + b) / 2.0:.10g}", "OK", f"{r:.4f}"


def icc_2_1(xs: List[float], ys: List[float]) -> Tuple[int, float]:
    import numpy as np

    x = np.asarray(xs, float)
    y = np.asarray(ys, float)
    mask = np.isfinite(x) & np.isfinite(y)
    ratings = np.column_stack([x[mask], y[mask]])
    n, k = ratings.shape
    if n < 3:
        return n, float("nan")
    grand = ratings.mean()
    subject_means = ratings.mean(axis=1)
    rater_means = ratings.mean(axis=0)
    ss_subjects = k * np.sum((subject_means - grand) ** 2)
    ss_raters = n * np.sum((rater_means - grand) ** 2)
    ss_total = np.sum((ratings - grand) ** 2)
    ss_error = ss_total - ss_subjects - ss_raters
    ms_subjects = ss_subjects / (n - 1)
    ms_raters = ss_raters / (k - 1)
    ms_error = ss_error / ((n - 1) * (k - 1))
    denom = ms_subjects + (k - 1) * ms_error + (k / n) * (ms_raters - ms_error)
    icc = (ms_subjects - ms_error) / denom if denom != 0 else float("nan")
    return int(n), float(icc)


def bland_altman(xs: List[float], ys: List[float]) -> Dict[str, float]:
    import numpy as np

    x = np.asarray(xs, float)
    y = np.asarray(ys, float)
    mask = np.isfinite(x) & np.isfinite(y)
    d = y[mask] - x[mask]
    if d.size == 0:
        return {k: float("nan") for k in ("n", "bias", "sd", "loa_lo", "loa_hi")}
    bias = float(d.mean())
    sd = float(d.std(ddof=1)) if d.size > 1 else float("nan")
    return {
        "n": float(d.size),
        "bias": bias,
        "sd": sd,
        "loa_lo": bias - 1.96 * sd,
        "loa_hi": bias + 1.96 * sd,
    }


def build_outputs(
    *,
    site_rows: List[Dict[str, Any]],
    reader2_rows: List[Dict[str, Any]],
    fieldnames: List[str],
    threshold: float,
    site_label: str,
    reader2_label: str,
    match_kwargs: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]], Dict[str, Any]]:
    idx_a = index_by_key(site_rows, **match_kwargs)
    idx_b = index_by_key(reader2_rows, **match_kwargs)
    common = sorted(set(idx_a) & set(idx_b), key=lambda k: (k.case, k.visit))
    only_a = sorted(set(idx_a) - set(idx_b), key=lambda k: k.label)
    only_b = sorted(set(idx_b) - set(idx_a), key=lambda k: k.label)

    numeric_cols = [c for c in fieldnames if is_numeric_column(c, site_rows, reader2_rows)]
    adopted_rows: List[Dict[str, Any]] = []
    recheck_rows: List[Dict[str, str]] = []

    rpd_store: Dict[str, List[float]] = {m: [] for m in MAJOR_METRICS}
    pair_xy: Dict[str, Tuple[List[float], List[float]]] = {
        m: ([], []) for m in MAJOR_METRICS
    }

    for key in common:
        ra, rb = idx_a[key], idx_b[key]
        out = {k: "" for k in fieldnames}
        out["ID"] = ra.get("ID") or rb.get("ID") or key.case
        out["File"] = ra.get("File") or rb.get("File") or ""
        out["Analyst"] = f"Dual-read mean (RPD<={threshold:g}%; else NA)"
        for meta in ("Subtype", "Pathophysiology", "Quality of analysis"):
            va, vb = (ra.get(meta) or "").strip(), (rb.get(meta) or "").strip()
            out[meta] = va if va == vb else ("NA" if (va or vb) else "")

        visit_major_recheck = False
        for col in numeric_cols:
            a, b = to_float(ra.get(col)), to_float(rb.get(col))
            val, status, rpd_s = adopt_pair(a, b, threshold)
            out[col] = val
            if col not in MAJOR_METRICS:
                continue
            if a is not None and b is not None:
                r = rpd_pct(a, b)
                if r is not None:
                    rpd_store[col].append(r)
                pair_xy[col][0].append(a)
                pair_xy[col][1].append(b)
            # Discordance OR missingness on a major metric → remeasure.
            if status in ("RECHECK", "MISSING"):
                visit_major_recheck = True
                rule = (
                    "MISSING"
                    if status == "MISSING"
                    else f"RPD>{threshold:g}%"
                )
                recheck_rows.append(
                    {
                        "Case": key.case,
                        "Visit": key.visit,
                        "MatchKey": key.label,
                        "Metric": col,
                        "SiteReader": site_label,
                        "SecondReader": reader2_label,
                        "Value_site": "" if a is None else f"{a:.10g}",
                        "Value_reader2": "" if b is None else f"{b:.10g}",
                        "RPD_pct": rpd_s,
                        "Adopted": "NA",
                        "Rule": rule,
                    }
                )
        out["_Case"] = key.case
        out["_Visit"] = key.visit
        out["_Visit_needs_recheck"] = "YES" if visit_major_recheck else "NO"
        adopted_rows.append(out)

    # summary stats
    major_cells = len(common) * len(MAJOR_METRICS)
    major_recheck = len(recheck_rows)
    visits_recheck = sum(1 for r in adopted_rows if r.get("_Visit_needs_recheck") == "YES")
    summary: Dict[str, Any] = {
        "date": date.today().isoformat(),
        "threshold_pct": threshold,
        "n_matched": len(common),
        "n_site_only": len(only_a),
        "n_reader2_only": len(only_b),
        "site_only": [k.label for k in only_a],
        "reader2_only": [k.label for k in only_b],
        "major_cells": major_cells,
        "major_recheck_cells": major_recheck,
        "major_cell_exclusion_rate_pct": (100.0 * major_recheck / major_cells) if major_cells else 0.0,
        "visits_recheck": visits_recheck,
        "visit_exclusion_rate_pct": (100.0 * visits_recheck / len(common)) if common else 0.0,
        "recheck_by_metric": dict(Counter(r["Metric"] for r in recheck_rows)),
        "metrics": {},
        "site_label": site_label,
        "reader2_label": reader2_label,
        "justification": (
            f"{threshold:g}%は測定誤差を許容しつつ、過度な除外を避けるために設定した。"
        ),
    }
    for m in MAJOR_METRICS:
        arr = rpd_store[m]
        xs, ys = pair_xy[m]
        n_icc, icc = icc_2_1(xs, ys)
        ba = bland_altman(xs, ys)
        if arr:
            import numpy as np

            a = np.asarray(arr, float)
            summary["metrics"][m] = {
                "n": int(a.size),
                "rpd_median": float(np.median(a)),
                "rpd_p90": float(np.percentile(a, 90)),
                "pct_le_threshold": float(100.0 * np.mean(a <= threshold)),
                "icc_2_1": icc,
                "icc_n": n_icc,
                "ba_bias": ba["bias"],
                "ba_loa_lo": ba["loa_lo"],
                "ba_loa_hi": ba["loa_hi"],
            }
        else:
            summary["metrics"][m] = {"n": 0}

    return adopted_rows, recheck_rows, summary


def render_summary_md(summary: Dict[str, Any]) -> str:
    lines = [
        f"# Dual-read adoption summary ({summary['date']})",
        "",
        f"- Site reader: **{summary['site_label']}**",
        f"- 2nd reader: **{summary['reader2_label']}**",
        f"- RPD threshold: **{summary['threshold_pct']:g}%**",
        f"- Matched visits: **{summary['n_matched']}**",
        f"- Unmatched (site only): {summary['n_site_only']}",
        f"- Unmatched (2nd only): {summary['n_reader2_only']}",
        "",
        "## Rule",
        "",
        "1. Recompute Caliber/Maturity **U2** on both CSVs (mandatory).",
        "2. Match by Case + Visit (flexible filename / column rules).",
        f"3. If RPD ≤ {summary['threshold_pct']:g}% → adopted = mean; else **NA** (recheck).",
        "",
        f"**Justification:** {summary['justification']}",
        "",
        "## Exclusion at this threshold",
        "",
        f"- Major-metric cell exclusion: "
        f"{summary['major_recheck_cells']}/{summary['major_cells']} "
        f"({summary['major_cell_exclusion_rate_pct']:.2f}%)",
        f"- Visits with any major RECHECK: "
        f"{summary['visits_recheck']}/{summary['n_matched']} "
        f"({summary['visit_exclusion_rate_pct']:.2f}%)",
        "",
        "### RECHECK by major metric",
        "",
    ]
    if summary["recheck_by_metric"]:
        for m, n in sorted(summary["recheck_by_metric"].items(), key=lambda x: -x[1]):
            lines.append(f"- {m}: {n}")
    else:
        lines.append("- (none)")

    lines += ["", "## Per-metric RPD / ICC / Bland–Altman", ""]
    lines.append("| Metric | n | RPD median | RPD P90 | ≤thr % | ICC(2,1) | BA bias | 95% LoA |")
    lines.append("|--------|---|------------|---------|--------|----------|---------|---------|")
    for m, st in summary["metrics"].items():
        if not st.get("n"):
            continue
        lines.append(
            "| {m} | {n} | {med:.2f}% | {p90:.2f}% | {pct:.1f}% | {icc:.3f} | {bias:.4g} | [{lo:.4g}, {hi:.4g}] |".format(
                m=m,
                n=st["n"],
                med=st["rpd_median"],
                p90=st["rpd_p90"],
                pct=st["pct_le_threshold"],
                icc=st["icc_2_1"],
                bias=st["ba_bias"],
                lo=st["ba_loa_lo"],
                hi=st["ba_loa_hi"],
            )
        )

    if summary["site_only"] or summary["reader2_only"]:
        lines += ["", "## Unmatched keys", ""]
        if summary["site_only"]:
            lines.append("Site only: " + ", ".join(summary["site_only"][:50]))
        if summary["reader2_only"]:
            lines.append("2nd only: " + ", ".join(summary["reader2_only"][:50]))

    lines.append("")
    return "\n".join(lines)


def strip_internal(rows: List[Dict[str, Any]], fieldnames: List[str]) -> List[Dict[str, Any]]:
    clean = []
    for r in rows:
        clean.append({k: r.get(k, "") for k in fieldnames})
    return clean


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description="Reading-center dual CSV → U2 + RPD adoption (Micron 3-file set)"
    )
    p.add_argument("--site-csv", type=Path, required=True, help="Facility / primary reader CSV")
    p.add_argument("--reader2-csv", type=Path, required=True, help="Second reader CSV")
    p.add_argument("--out-dir", type=Path, required=True, help="Output directory")
    p.add_argument("--prefix", type=str, default="dual_adopted", help="Output filename prefix")
    p.add_argument("--rpd-threshold", type=float, default=DEFAULT_RPD_PCT)
    p.add_argument(
        "--size-class",
        choices=["small", "large", "small_3mm"],
        default=None,
        help="Force U2 size_class (default: infer from File)",
    )
    p.add_argument("--site-label", default="site")
    p.add_argument("--reader2-label", default="reader2")
    p.add_argument("--case-col", default=None, help="Optional Case column name")
    p.add_argument("--visit-col", default=None, help="Optional Visit column name")
    p.add_argument(
        "--case-regex",
        default=None,
        help=r"Regex with (?P<case>...) for filename/ID (multi-center)",
    )
    p.add_argument(
        "--keep-u2-csv",
        action="store_true",
        help="Also write intermediate *_U2.csv for each input",
    )
    args = p.parse_args(argv)

    if not args.site_csv.is_file():
        raise SystemExit(f"Not found: {args.site_csv}")
    if not args.reader2_csv.is_file():
        raise SystemExit(f"Not found: {args.reader2_csv}")

    try:
        fields_a, rows_a = read_csv(args.site_csv)
        fields_b, rows_b = read_csv(args.reader2_csv)
    except ValueError as ex:
        raise SystemExit(str(ex)) from ex

    print("Step1: U2 recompute (mandatory)", file=sys.stderr)
    fields_a, rows_a = apply_u2(fields_a, rows_a, args.size_class)
    fields_b, rows_b = apply_u2(fields_b, rows_b, args.size_class)

    # Union fieldnames preserving site order then extras from reader2
    fieldnames = list(fields_a)
    for c in fields_b:
        if c not in fieldnames:
            fieldnames.append(c)

    match_kwargs = dict(
        case_col=args.case_col,
        visit_col=args.visit_col,
        case_regex=args.case_regex,
    )

    print("Step2–3: match + RPD adoption", file=sys.stderr)
    adopted, recheck, summary = build_outputs(
        site_rows=rows_a,
        reader2_rows=rows_b,
        fieldnames=fieldnames,
        threshold=args.rpd_threshold,
        site_label=args.site_label,
        reader2_label=args.reader2_label,
        match_kwargs=match_kwargs,
    )

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = args.prefix

    adopted_path = out_dir / f"{prefix}_adopted_values.csv"
    recheck_path = out_dir / f"{prefix}_recheck_list.csv"
    summary_path = out_dir / f"{prefix}_summary.md"

    write_csv(adopted_path, fieldnames, strip_internal(adopted, fieldnames))
    recheck_fields = [
        "Case",
        "Visit",
        "MatchKey",
        "Metric",
        "SiteReader",
        "SecondReader",
        "Value_site",
        "Value_reader2",
        "RPD_pct",
        "Adopted",
        "Rule",
    ]
    write_csv(recheck_path, recheck_fields, recheck)
    summary_path.write_text(render_summary_md(summary), encoding="utf-8")

    if args.keep_u2_csv:
        write_csv(out_dir / f"{prefix}_site_U2.csv", fields_a, rows_a)
        write_csv(out_dir / f"{prefix}_reader2_U2.csv", fields_b, rows_b)

    print(f"Wrote {adopted_path}", file=sys.stderr)
    print(f"Wrote {recheck_path}", file=sys.stderr)
    print(f"Wrote {summary_path}", file=sys.stderr)
    print(
        f"Matched={summary['n_matched']} major_RECHECK_cells={summary['major_recheck_cells']} "
        f"visit_RECHECK={summary['visits_recheck']}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
