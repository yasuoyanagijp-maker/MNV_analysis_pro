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

_INST_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,64}$")


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
    n = (name or "").strip()
    if not n or n.lower() in {x.lower() for x in _RESERVED_TOP_LEVEL}:
        return False
    # Prefer UPPER_SNAKE institution codes; also allow mixed if normalized matches
    if _INST_NAME_RE.match(n):
        return True
    norm = normalize_institution_id(n)
    return bool(norm) and norm != "UNKNOWN" and norm == n.upper().replace("-", "_")


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
