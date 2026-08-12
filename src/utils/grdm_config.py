"""
GakuNin RDM アップロード先設定 (project_id / folder_id)。

PAT とは異なりプロジェクトID・フォルダIDは秘密情報ではないため、
環境変数および Flet client_storage に保存してよい。
ハードコードはしない。
"""

from __future__ import annotations

import os
from typing import Any, Optional, Tuple

_PROJECT_ENV = "GRDM_PROJECT_ID"
_FOLDER_ENV = "GRDM_FOLDER_ID"
_PROJECT_STORAGE_KEY = "grdm_project_id"
_FOLDER_STORAGE_KEY = "grdm_folder_id"


def resolve_grdm_destination(
    session: Any = None,
    client_storage: Any = None,
) -> Tuple[str, str]:
    """Return (project_id, folder_id). folder_id may be empty (project root)."""
    project_id = _first_nonempty(
        _session_get(session, _PROJECT_STORAGE_KEY),
        _client_get(client_storage, _PROJECT_STORAGE_KEY),
        os.environ.get(_PROJECT_ENV),
    )
    folder_id = _first_nonempty(
        _session_get(session, _FOLDER_STORAGE_KEY),
        _client_get(client_storage, _FOLDER_STORAGE_KEY),
        os.environ.get(_FOLDER_ENV),
    )
    return project_id, folder_id


def persist_grdm_destination(
    project_id: str,
    folder_id: str = "",
    session: Any = None,
    client_storage: Any = None,
) -> Tuple[str, str]:
    """Normalize and persist destination ids. Returns stored (project_id, folder_id)."""
    project_id = (project_id or "").strip()
    folder_id = (folder_id or "").strip()
    if session is not None:
        try:
            session.set(_PROJECT_STORAGE_KEY, project_id)
            session.set(_FOLDER_STORAGE_KEY, folder_id)
        except Exception:
            pass
    if client_storage is not None:
        try:
            client_storage.set(_PROJECT_STORAGE_KEY, project_id)
            client_storage.set(_FOLDER_STORAGE_KEY, folder_id)
        except Exception:
            pass
    return project_id, folder_id


def load_persisted_grdm_destination(
    session: Any = None,
    client_storage: Any = None,
) -> Tuple[str, str]:
    """Fill UI controls without requiring both values to be set."""
    return resolve_grdm_destination(session, client_storage)


def _session_get(session: Any, key: str) -> Optional[str]:
    if session is None:
        return None
    try:
        val = session.get(key)
    except Exception:
        return None
    if val is None:
        return None
    s = str(val).strip()
    return s or None


def _client_get(client_storage: Any, key: str) -> Optional[str]:
    if client_storage is None:
        return None
    try:
        val = client_storage.get(key)
    except Exception:
        return None
    if val is None:
        return None
    s = str(val).strip()
    return s or None


def _first_nonempty(*values: Optional[str]) -> str:
    for v in values:
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""
