"""
RECHECK markdown parser for the final-reader (最終読影者) triad workflow.

Parses the ``## RECHECK`` section of a dual-read summary markdown
(``{prefix}_summary.md`` written by ``dual_grader_merge``) into a list of
(case image file × parameter column) pairs the final reader must re-grade.

Expected shape (formatting variants — full/half-width brackets & colons,
different bullet characters, extra whitespace — are tolerated)::

    ## RECHECK

    - 主要指標セル: 3 件（対象症例 2 件）
    - 症例別（NA となった主要指標）:
      - 102-001_Week04.png: Vsl Area (mm2)
      - 102-002_Week04.png: MNV Area (mm2), Caliber Uniformity Score

Parameter display names are mapped to the internal CSV column identifiers
used by the RPD adoption pipeline (``MAJOR_METRICS``). Unknown parameter
notations raise :class:`UnknownParameterError` — they are never silently
ignored, because a typo could otherwise drop a cell from the triad
resolution without anyone noticing.
"""

from __future__ import annotations

import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.utils.dual_grader_merge import match_stem  # noqa: E402
from tools.reading_center_rpd.compute_adopted_from_dual_csv import (  # noqa: E402
    MAJOR_METRICS,
)


class RecheckMdError(ValueError):
    """Base error for RECHECK markdown parsing problems."""


class UnknownParameterError(RecheckMdError):
    """A parameter notation could not be mapped to an internal column."""

    def __init__(self, unknown: List[str]):
        self.unknown = list(unknown)
        known = ", ".join(sorted(_CANONICAL_BY_NORMALIZED.values()))
        super().__init__(
            "RECHECK MDに未知のパラメータ表記があります（処理を中止しました）: "
            + ", ".join(f"「{u}」" for u in self.unknown)
            + f" — マッピング可能な表記: {known}"
        )


@dataclass(frozen=True)
class RecheckTarget:
    """One cell (case image × parameter) the final reader must resolve."""

    image_file: str        # as written in the MD, e.g. "102-001_Week04.png"
    image_stem: str        # match_stem() key used across the adoption pipeline
    display_name: str      # parameter as written in the MD
    column: str            # internal CSV column, e.g. "Vsl Area (mm2)"


@dataclass
class RecheckParseResult:
    targets: List[RecheckTarget] = field(default_factory=list)
    declared_cells: Optional[int] = None    # 主要指標セル: N 件
    declared_cases: Optional[int] = None    # （対象症例/ファイル M 件）
    warnings: List[str] = field(default_factory=list)

    @property
    def image_files(self) -> List[str]:
        seen: set = set()
        out: List[str] = []
        for t in self.targets:
            if t.image_stem not in seen:
                seen.add(t.image_stem)
                out.append(t.image_file)
        return out

    def columns_for_stem(self, stem: str) -> List[str]:
        return [t.column for t in self.targets if t.image_stem == stem]


def _normalize_param(raw: str) -> str:
    """
    Normalization key for parameter-name matching: NFKC (full-width brackets,
    superscripts → ASCII), collapse whitespace, casefold.
    """
    s = unicodedata.normalize("NFKC", str(raw or ""))
    s = re.sub(r"\s+", " ", s).strip()
    return s.casefold()


def _build_alias_table() -> Dict[str, str]:
    table: Dict[str, str] = {}
    for col in MAJOR_METRICS:
        table[_normalize_param(col)] = col
    # Loose display names used in summaries / by humans. The recheck pipeline
    # only ever flags the (U2) variants, so bare names map to them.
    aliases = {
        "Caliber Uniformity Score": "Caliber Uniformity Score (U2)",
        "Maturity Index": "Maturity Index (U2)",
        "Vsl Density": "Vsl Density (Vessel Area/MNV (%))",
        "Fractal Dimension": "Fractal Dim",
        "MNV Area": "MNV Area (mm2)",
        "Vsl Area": "Vsl Area (mm2)",
    }
    for alias, col in aliases.items():
        table.setdefault(_normalize_param(alias), col)
    return table


_CANONICAL_BY_NORMALIZED = _build_alias_table()

_IMAGE_EXT_RE = re.compile(r"\.(png|tiff?|jpe?g)$", re.IGNORECASE)
_HEADING_RE = re.compile(r"^(#{1,6})\s*(.*?)\s*#*\s*$")
_BULLET_RE = re.compile(r"^\s*(?:[-*+•‣・●○◦]|\d+[.)])\s+(.*)$")
# 主要指標セル: 3 件（対象症例 2 件） / 対象ファイル 2 件
_COUNTS_RE = re.compile(
    r"主要指標セル\s*[:：]\s*(\d+)\s*件(?:\s*[（(]\s*対象(?:症例|ファイル)\s*(\d+)\s*件\s*[）)])?"
)


def map_parameter_name(raw: str) -> Optional[str]:
    """Display parameter name → internal CSV column (None when unknown)."""
    return _CANONICAL_BY_NORMALIZED.get(_normalize_param(raw))


def _split_params(rhs: str) -> List[str]:
    """
    Split the parameter list on top-level commas only — "Vsl Density
    (Vessel Area/MNV (%))" contains no comma, but guard nested brackets anyway.
    """
    parts: List[str] = []
    depth = 0
    buf: List[str] = []
    for ch in rhs:
        if ch in "（(":
            depth += 1
        elif ch in "）)":
            depth = max(0, depth - 1)
        if ch in ",、，" and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip()]


def _split_first_colon(line: str) -> Optional[Tuple[str, str]]:
    m = re.search(r"[:：]", line)
    if not m:
        return None
    return line[: m.start()].strip(), line[m.end():].strip()


def _looks_like_image_lhs(lhs: str) -> bool:
    token = unicodedata.normalize("NFKC", lhs).strip().strip("`*_ ")
    if _IMAGE_EXT_RE.search(token):
        return True
    # Extension-less variants still need a case-id-like token (e.g. 102-001)
    return bool(re.search(r"\d{2,4}-\d{2,5}", token))


def _iter_recheck_section(lines: List[str]):
    """Yield lines inside the RECHECK section (any heading level)."""
    in_section = False
    section_level = 0
    for line in lines:
        m = _HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            title = _normalize_param(m.group(2))
            if "recheck" in title:
                in_section = True
                section_level = level
                continue
            if in_section and level <= section_level:
                in_section = False
            continue
        if in_section:
            yield line


def parse_recheck_md_text(text: str) -> RecheckParseResult:
    """
    Parse RECHECK markdown text into (image × column) targets.

    Raises
    ------
    RecheckMdError
        No RECHECK section / no per-case lines found.
    UnknownParameterError
        Any parameter notation that cannot be mapped (never ignored).
    """
    result = RecheckParseResult()
    unknown: List[str] = []
    lines = str(text or "").splitlines()

    section_lines = list(_iter_recheck_section(lines))
    if not section_lines:
        raise RecheckMdError(
            "RECHECKセクション（## RECHECK）が見つかりません。"
            "統合解析データの *_summary.md を選択してください。"
        )

    for raw_line in section_lines:
        mb = _BULLET_RE.match(raw_line)
        if not mb:
            continue
        body = mb.group(1).strip()

        mc = _COUNTS_RE.search(body)
        if mc:
            result.declared_cells = int(mc.group(1))
            if mc.group(2) is not None:
                result.declared_cases = int(mc.group(2))
            continue

        split = _split_first_colon(body)
        if split is None:
            continue
        lhs, rhs = split
        if not rhs:
            # sub-section header like 「症例別（NA となった主要指標）:」
            continue
        if not _looks_like_image_lhs(lhs):
            # summary lines (per-metric counts etc.) — not per-case targets
            continue

        image_file = unicodedata.normalize("NFKC", lhs).strip().strip("`*_ ")
        stem = match_stem(image_file)
        if not stem:
            result.warnings.append(f"画像ファイル名を解釈できない行をスキップ: {raw_line.strip()}")
            continue
        for param in _split_params(rhs):
            col = map_parameter_name(param)
            if col is None:
                unknown.append(param)
                continue
            result.targets.append(
                RecheckTarget(
                    image_file=image_file,
                    image_stem=stem,
                    display_name=param,
                    column=col,
                )
            )

    if unknown:
        # De-duplicate while keeping order
        seen: set = set()
        uniq = [u for u in unknown if not (u in seen or seen.add(u))]
        raise UnknownParameterError(uniq)

    if not result.targets:
        raise RecheckMdError(
            "RECHECKセクションに症例別の対象行（例: 102-001_Week04.png: Vsl Area (mm2)）が"
            "見つかりません。RECHECK対象が0件の場合、再読影は不要です。"
        )

    if result.declared_cells is not None and result.declared_cells != len(result.targets):
        result.warnings.append(
            f"MD記載のセル数（{result.declared_cells}）と解析結果（{len(result.targets)}）が"
            "一致しません。MDの編集有無を確認してください。"
        )
    n_cases = len({t.image_stem for t in result.targets})
    if result.declared_cases is not None and result.declared_cases != n_cases:
        result.warnings.append(
            f"MD記載の対象症例数（{result.declared_cases}）と解析結果（{n_cases}）が"
            "一致しません。"
        )
    return result


def parse_recheck_md(path: Path) -> RecheckParseResult:
    """Read + parse a RECHECK markdown file (UTF-8 with BOM tolerance)."""
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8-sig")
    except OSError as ex:
        raise RecheckMdError(f"RECHECK MDを読み込めません: {p} ({ex})") from ex
    return parse_recheck_md_text(text)


def sibling_pipeline_files(md_path: Path) -> Tuple[Optional[Path], Optional[Path], str]:
    """
    Locate the recheck-list / adopted-values CSVs written alongside
    ``{prefix}_summary.md`` by the dual-read merge.

    Returns ``(recheck_csv, adopted_csv, prefix)`` (paths may be None).
    """
    p = Path(md_path)
    name = p.name
    prefix = name[: -len("_summary.md")] if name.endswith("_summary.md") else p.stem
    recheck = p.parent / f"{prefix}_recheck_list.csv"
    adopted = p.parent / f"{prefix}_adopted_values.csv"
    return (
        recheck if recheck.is_file() else None,
        adopted if adopted.is_file() else None,
        prefix,
    )
