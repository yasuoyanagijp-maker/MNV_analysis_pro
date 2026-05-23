"""
VD folder SCP/DCP pair discovery and preflight (aligned with VDAnalyzer pair mode).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence, Tuple


_SUPPORTED_EXTS = (
    ".tif",
    ".tiff",
    ".jpg",
    ".jpeg",
    ".png",
    ".TIF",
    ".TIFF",
    ".JPG",
    ".JPEG",
    ".PNG",
)


def parse_vd_suffixes(suffix: str) -> List[str]:
    return [s.strip() for s in str(suffix or "").split(",") if s.strip()]


def vd_pair_suffixes_configured(sup_suffix: str, deep_suffix: str) -> bool:
    """True when both superficial and deep suffixes are set (pair mode available)."""
    return bool(parse_vd_suffixes(sup_suffix)) and bool(parse_vd_suffixes(deep_suffix))


def _collect_images(input_dir: Path) -> List[Path]:
    all_files: List[Path] = []
    for ext in _SUPPORTED_EXTS:
        all_files.extend(input_dir.glob(f"*{ext}"))
        all_files.extend(input_dir.rglob(f"**/*{ext}"))
    return sorted(set(all_files), key=lambda p: p.name.lower())


def find_vd_file_pairs(
    input_dir: Path,
    sup_suffix: str = "1.tif",
    deep_suffix: str = "2.tif",
) -> Tuple[List[Tuple[Path, Path]], List[Path]]:
    """
    Find SCP/DCP pairs by suffix (same rules as VDAnalyzer._find_file_pairs).

    Returns:
        pairs: (superficial, deep) paths
        unpaired_superficial: superficial files with no matching deep file
    """
    folder = Path(input_dir)
    sup_suffixes = parse_vd_suffixes(sup_suffix) or ["1.tif"]
    deep_suffixes = parse_vd_suffixes(deep_suffix) or ["2.tif"]
    sup_suffixes_sorted = sorted(sup_suffixes, key=len, reverse=True)
    deep_suffixes_sorted = sorted(deep_suffixes, key=len, reverse=True)

    all_files = _collect_images(folder)

    sup_files: List[Path] = []
    for f in all_files:
        for suf in sup_suffixes_sorted:
            if f.name.endswith(suf):
                sup_files.append(f)
                break

    sup_files.sort(key=lambda p: p.name.lower())
    pairs: List[Tuple[Path, Path]] = []
    unpaired: List[Path] = []

    for sup_file in sup_files:
        matched_sup = None
        for suf in sup_suffixes_sorted:
            if sup_file.name.endswith(suf):
                matched_sup = suf
                break
        if matched_sup is None:
            continue
        patient_id = sup_file.name[: -len(matched_sup)]
        deep_file = None
        for ds in deep_suffixes_sorted:
            candidate = sup_file.parent / (patient_id + ds)
            if candidate.exists():
                deep_file = candidate
                break
        if deep_file is not None:
            pairs.append((sup_file, deep_file))
        else:
            unpaired.append(sup_file)

    return pairs, unpaired


@dataclass
class VDFolderPairScan:
    folder: Path
    sup_suffix: str
    deep_suffix: str
    total_images: int
    superficial_candidates: int
    pair_count: int
    pairs: List[Tuple[Path, Path]]
    unpaired_superficial: List[Path]

    @property
    def pair_mode_viable(self) -> bool:
        return self.pair_count > 0

    def console_lines(self) -> List[str]:
        lines = [
            f"VD pair scan [{self.folder.name}]: sup={self.sup_suffix!r} deep={self.deep_suffix!r}",
            f"  Images in folder: {self.total_images}",
            f"  Superficial (SCP) candidates: {self.superficial_candidates}",
            f"  Valid SCP+DCP pairs: {self.pair_count}",
        ]
        if self.unpaired_superficial:
            lines.append(
                f"  Unpaired superficial (skipped in pair mode): {len(self.unpaired_superficial)}"
            )
            for p in self.unpaired_superficial[:5]:
                lines.append(f"    - {p.name}")
            if len(self.unpaired_superficial) > 5:
                lines.append(f"    … and {len(self.unpaired_superficial) - 5} more")
        if self.pair_count:
            for sup, deep in self.pairs[:5]:
                lines.append(f"    ✓ {sup.name} <-> {deep.name}")
            if self.pair_count > 5:
                lines.append(f"    … and {self.pair_count - 5} more pair(s)")
        return lines


def scan_vd_folder_pairs(folder: Path, sup_suffix: str, deep_suffix: str) -> VDFolderPairScan:
    folder = Path(folder)
    pairs, unpaired = find_vd_file_pairs(folder, sup_suffix, deep_suffix)
    all_images = _collect_images(folder)
    return VDFolderPairScan(
        folder=folder,
        sup_suffix=sup_suffix,
        deep_suffix=deep_suffix,
        total_images=len(all_images),
        superficial_candidates=len(unpaired) + len(pairs),
        pair_count=len(pairs),
        pairs=pairs,
        unpaired_superficial=unpaired,
    )
