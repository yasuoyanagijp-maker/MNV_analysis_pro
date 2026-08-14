"""
GakuNin RDM 上の施設別データへのアクセス制御（OCTA-MIC）。

規則
----
- 一般施設: 自施設 (institution_id) の第1読影データのみ選択・取得可能
- 中央読影 Team YY: 全参加施設の第1読影データを横断選択可能
- 第1グレーダー同期先: ``{base}/{institution_id}/``
- 第2リーダー同期先: ``{base}/second_reading/{institution_id}/``
  （第1データと物理的に分離し、次の取得と混ざらないようにする）
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.utils.institution_config import normalize_institution_id

# Login / Advanced Settings で選べる中央読影コード
TEAM_YY_INSTITUTION_ID = "TEAM_YY"
# Session keys for the facility currently being second-read (GakuNin / local scan)
GRDM_GRADED_INSTITUTION_KEY = "grdm_graded_institution_id"
GRDM_PENDING_INSTITUTION_KEY = "grdm_pending_institution_id"
_CENTRAL_ENV = "ARIAKE_CENTRAL_READING"
_INST_STORAGE_KEY = "institution_id"

# データルート直下で「施設フォルダ」とみなさない予約名
_RESERVED_TOP_LEVEL = frozenset(
    {
        "second_reading",
        "raw_images",
        "measurements",  # legacy container; peeked into separately
        "logs",
        "tmp",
        "temp",
    }
)

# MedSAM / export レイアウト名 — 施設コードではない
_LAYOUT_FOLDER_NAMES = frozenset(
    {
        "images",
        "masks",
        "meta",
        "export",
        "pdfs",
        "mnv_rgb",
        "vd_visualization",
        "logs",
        "uploads",
        "output",
        "grdm_downloads",
    }
)

_INST_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,64}$")
# Isolated download / output stamps: INST_YYYYMMDD_HHMMSS or …_YYYY_MM_DD
_TIMESTAMP_SUFFIX_RE = re.compile(
    r"_(?:20\d{2}(?:_?\d{2}){2,}(?:_?\d{2}){0,3})$"
)


def login_institution_id(session: Any = None, client_storage: Any = None) -> str:
    """Institution chosen at login / UI — for ACL and GRDM scoping.

    Unlike ``resolve_institution_id``, this does **not** let
    ``ARIAKE_INSTITUTION_ID`` override a Team YY (or other) login selection.
    Env is only a fallback when session/client_storage are empty (site-locked
    installs that never show the institution picker).
    """
    if session is not None:
        try:
            sess_val = session.get(_INST_STORAGE_KEY)
        except Exception:
            sess_val = None
        if sess_val:
            return normalize_institution_id(str(sess_val))

    if client_storage is not None:
        try:
            stored = client_storage.get(_INST_STORAGE_KEY)
        except Exception:
            stored = None
        if stored:
            return normalize_institution_id(str(stored))

    env = (os.environ.get("ARIAKE_INSTITUTION_ID") or "").strip()
    if env:
        return normalize_institution_id(env)
    return "UNKNOWN"


def is_team_yy(
    session: Any = None,
    client_storage: Any = None,
    *,
    institution_id: Optional[str] = None,
) -> bool:
    """True when the current user is the central reading center (Team YY)."""
    env = (os.environ.get(_CENTRAL_ENV) or "").strip().lower()
    if env in ("1", "true", "yes", "y", "on"):
        return True

    code = normalize_institution_id(
        institution_id
        if institution_id is not None
        else login_institution_id(session, client_storage)
    )
    if code == TEAM_YY_INSTITUTION_ID:
        return True

    if session is not None:
        try:
            uname = str(session.get("username") or "").strip().upper()
        except Exception:
            uname = ""
        compact = uname.replace(" ", "").replace("-", "").replace("_", "")
        if compact in ("TEAMYY",) or uname in (TEAM_YY_INSTITUTION_ID, "TEAM YY"):
            return True
    return False


def looks_like_institution_folder(name: str) -> bool:
    """True only for stable facility codes (e.g. ARIAKE_OHANACHAYA), not layout dirs."""
    n = (name or "").strip()
    if not n:
        return False
    lower = n.lower()
    if lower in {x.lower() for x in _RESERVED_TOP_LEVEL}:
        return False
    if lower in _LAYOUT_FOLDER_NAMES:
        return False
    # Reject timestamped download/output folder names
    if _TIMESTAMP_SUFFIX_RE.search(n):
        return False
    if not _INST_NAME_RE.match(n):
        return False
    # Central-reading login code is not a first-grader facility folder
    if n == TEAM_YY_INSTITUTION_ID:
        return False
    return True


def infer_institution_from_path(path: Any) -> str:
    """Best-effort institution code from export/images/{INST}/… or a folder name."""
    try:
        p = path if hasattr(path, "parts") else None
        if p is None:
            return ""
        parts = [str(x) for x in p.parts]
    except Exception:
        return ""
    # Prefer …/export/images/{INSTITUTION}/…
    for i, part in enumerate(parts[:-1]):
        if part.lower() == "images" and i + 1 < len(parts):
            cand = parts[i + 1]
            if looks_like_institution_folder(cand):
                return cand
        if part.lower() == "export" and i + 2 < len(parts) and parts[i + 1].lower() == "images":
            cand = parts[i + 2]
            if looks_like_institution_folder(cand):
                return cand
    # Fallback: any path component that looks like an institution code
    for part in reversed(parts):
        if looks_like_institution_folder(part):
            return part
    return ""


def clear_grdm_session_institutions(
    session: Any = None,
    client_storage: Any = None,
) -> None:
    """Drop graded/pending facility keys (call on logout / fresh login).

    Prevents a later grader from inheriting another session's facility context
    after handoff (logout → re-login) or a soft navigate to /login.
    """
    # Skip contains_key: Flet client_storage.contains_key() is a blocking RPC
    # (wait_for_result, up to 5s). remove() is idempotent enough for these keys.
    for store in (session, client_storage):
        if store is None:
            continue
        for key in (GRDM_GRADED_INSTITUTION_KEY, GRDM_PENDING_INSTITUTION_KEY):
            try:
                if hasattr(store, "remove"):
                    store.remove(key)
                else:
                    store.set(key, None)
            except Exception:
                try:
                    store.set(key, "")
                except Exception:
                    pass


def resolve_export_institution_id(
    session: Any = None,
    client_storage: Any = None,
) -> str:
    """Institution for MedSAM/PDF export paths.

    Prefer an in-flight GRDM pull (pending) over a committed graded id, then
    fall back to ``resolve_institution_id`` (site-lock / login). Keeps Team YY
    from writing ``export/.../TEAM_YY/`` and avoids stale graded facilities.
    """
    from src.utils.institution_config import resolve_institution_id

    if session is not None:
        for key in (GRDM_PENDING_INSTITUTION_KEY, GRDM_GRADED_INSTITUTION_KEY):
            try:
                raw = session.get(key)
            except Exception:
                raw = None
            if raw and looks_like_institution_folder(str(raw)):
                return normalize_institution_id(str(raw))
    return resolve_institution_id(session, client_storage)


def filter_institution_datasets(
    datasets: Sequence[Dict[str, str]],
    *,
    viewer_institution_id: str,
    central: bool,
) -> List[Dict[str, str]]:
    """Filter remote institution folder descriptors for the current viewer.

    Each dataset dict needs at least ``name`` (institution folder name).
    """
    if central:
        return list(datasets)
    own = normalize_institution_id(viewer_institution_id)
    if not own or own == "UNKNOWN":
        return []
    out: List[Dict[str, str]] = []
    for d in datasets:
        name = normalize_institution_id(str(d.get("name") or ""))
        if name == own:
            out.append(d)
    return out


def first_grader_remote_segments(institution_id: str) -> Tuple[str, ...]:
    """Path segments under GRDM base folder for first-grader uploads."""
    inst = normalize_institution_id(institution_id)
    if not inst or inst == "UNKNOWN":
        raise ValueError("institution_id が未設定のため GakuNin 同期先を決定できません")
    if inst == TEAM_YY_INSTITUTION_ID:
        raise ValueError(
            "Team YY（中央読影）アカウントでは第1グレーダー同期を行いません。"
            " 施設コードでログインしてください。"
        )
    return (inst,)


def second_reader_remote_segments(institution_id: str) -> Tuple[str, ...]:
    """Path segments under GRDM base for second-reader result uploads."""
    inst = normalize_institution_id(institution_id)
    if not inst or inst == "UNKNOWN":
        raise ValueError("institution_id が未設定のため第2リーダー同期先を決定できません")
    # Team YY may upload under the facility being graded — callers pass that id
    return ("second_reading", inst)
