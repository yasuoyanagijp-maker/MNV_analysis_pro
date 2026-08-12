"""
Institution ID resolution for metadata / training-dataset exports.

Priority (first non-empty wins):
  1. ARIAKE_INSTITUTION_ID environment variable (site-locked install)
  2. Flet page.session["institution_id"]
  3. page.client_storage["institution_id"] (persists across reloads)
  4. Fallback UNKNOWN

Use coded identifiers (UPPER_SNAKE), not free-form hospital names, so Hold-out
splits and LoRA dataset paths stay parseable.
"""

from __future__ import annotations

import os
import re
from typing import Any, List, Optional, Sequence, Tuple

# (code, display label) — codes are path-safe and stable for ML pipelines
INSTITUTION_PRESETS: List[Tuple[str, str]] = [
    ("ARIAKE_OHANACHAYA", "お花茶屋眼科 (ARIAKE)"),
    ("TEAM_YY", "Team YY（中央読影センター / OCTA-MIC）"),
    ("NIPPON_MEDICAL_SCHOOL", "日本医科大学付属病院"),
    ("YOKOHAMA_CITY_UNIV", "横浜市立大学"),
    ("OZAWAGANKA", "小沢眼科内科病院"),
    ("TOHOKU_UNIV", "東北大学病院"),
    ("JUNTENDO_URAYASU", "順天堂大学浦安病院"),
    ("KAWASAKI_MED", "川崎医科大学"),
    ("HIROSHIMA_UNIV", "広島大学病院"),
    ("OSAKA_METRO_UNIV", "大阪公立大学"),
    ("EHIME_UNIV", "愛媛大学"),
    ("KYUSHU_UNIV", "九州大学"),
    ("FUKUI_UNIV", "福井大学"),
    ("TOKYO_UNIV", "東京大学"),
    ("YAMAGATA_UNIV", "山形大学"),
    ("ST_MARIANNA", "聖マリアンナ医科大学"),
    ("TSUKUBA_UNIV", "筑波大学"),
    ("TOHO_OHASHI", "東邦大学大橋病院"),
    ("TOKYO_MED_IBARAKI", "東京医科大学茨城"),
    ("SHIGA_MED", "滋賀医科大学"),
    ("YAMANASHI_UNIV", "山梨大学"),
    ("SAITAMA_MED", "埼玉医科大学病院"),
    ("JIKEI_UNIV", "慈恵医大"),
    ("NISHIKASAI_INOUE", "西葛西井上眼科"),
    ("NAGOYA_UNIV", "名古屋大学"),
    ("NIHON_UNIV", "日本大学病院"),
    ("CUSTOM", "Other (type code below)"),
]

_CUSTOM_SENTINEL = "CUSTOM"
_FALLBACK = "UNKNOWN"
_ENV_KEY = "ARIAKE_INSTITUTION_ID"
_STORAGE_KEY = "institution_id"


def normalize_institution_id(raw: Optional[str]) -> str:
    """Normalize to a path-safe UPPER_SNAKE code."""
    if raw is None:
        return _FALLBACK
    s = str(raw).strip()
    if not s or s.upper() == _CUSTOM_SENTINEL:
        return _FALLBACK
    s = s.replace("\u3000", "_").replace(" ", "_")
    s = re.sub(r"[^\w\-]+", "_", s, flags=re.UNICODE)
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        return _FALLBACK
    return s.upper()


def institution_preset_codes() -> Sequence[str]:
    return [code for code, _ in INSTITUTION_PRESETS]


def resolve_institution_id(
    session: Any = None,
    client_storage: Any = None,
    *,
    explicit: Optional[str] = None,
) -> str:
    """
    Resolve institution_id for meta.json / export paths.

    ``explicit`` overrides everything (e.g. value just typed in the UI).
    """
    if explicit is not None and str(explicit).strip():
        return normalize_institution_id(explicit)

    env = (os.environ.get(_ENV_KEY) or "").strip()
    if env:
        return normalize_institution_id(env)

    if session is not None:
        try:
            sess_val = session.get(_STORAGE_KEY)
        except Exception:
            sess_val = None
        if sess_val:
            return normalize_institution_id(str(sess_val))

    if client_storage is not None:
        try:
            stored = client_storage.get(_STORAGE_KEY)
        except Exception:
            stored = None
        if stored:
            return normalize_institution_id(str(stored))

    return _FALLBACK


def persist_institution_id(
    institution_id: str,
    session: Any = None,
    client_storage: Any = None,
) -> str:
    """Normalize, store on session + client_storage, return the code used."""
    code = normalize_institution_id(institution_id)
    if session is not None:
        try:
            session.set(_STORAGE_KEY, code)
        except Exception:
            pass
    if client_storage is not None:
        try:
            client_storage.set(_STORAGE_KEY, code)
        except Exception:
            pass
    return code


def load_persisted_institution_id(
    session: Any = None,
    client_storage: Any = None,
) -> str:
    """Convenience for filling UI controls (does not apply env override to display)."""
    if session is not None:
        try:
            sess_val = session.get(_STORAGE_KEY)
        except Exception:
            sess_val = None
        if sess_val:
            return normalize_institution_id(str(sess_val))
    if client_storage is not None:
        try:
            stored = client_storage.get(_STORAGE_KEY)
        except Exception:
            stored = None
        if stored:
            return normalize_institution_id(str(stored))
    env = (os.environ.get(_ENV_KEY) or "").strip()
    if env:
        return normalize_institution_id(env)
    return ""
