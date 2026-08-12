"""Unit tests for GakuNin RDM config / client helpers (no live API calls)."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.utils.grdm_config import persist_grdm_destination, resolve_grdm_destination
from src.utils import grdm_client as grdm


def test_resolve_grdm_destination_from_env(monkeypatch):
    monkeypatch.setenv("GRDM_PROJECT_ID", "projABC")
    monkeypatch.setenv("GRDM_FOLDER_ID", "foldXYZ")
    project_id, folder_id = resolve_grdm_destination()
    assert project_id == "projABC"
    assert folder_id == "foldXYZ"


def test_persist_and_resolve_via_session():
    session = MagicMock()
    store = {}

    def _set(k, v):
        store[k] = v

    def _get(k):
        return store.get(k)

    session.set.side_effect = _set
    session.get.side_effect = _get

    persist_grdm_destination("node1", "dir2", session=session, client_storage=None)
    project_id, folder_id = resolve_grdm_destination(session=session)
    assert project_id == "node1"
    assert folder_id == "dir2"


def test_set_active_token_updates_headers():
    grdm.set_active_token("test-token-value")
    assert grdm.TOKEN == "test-token-value"
    assert grdm.HEADERS.get("Authorization") == "Bearer test-token-value"


def test_sync_local_to_grdm_empty(tmp_path: Path):
    n = grdm.sync_local_to_grdm(str(tmp_path), "proj", "")
    assert n == 0


def test_sync_local_to_grdm_uploads_files(tmp_path: Path):
    f1 = tmp_path / "a.csv"
    f2 = tmp_path / "b.csv"
    f1.write_text("a")
    f2.write_text("b")
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "nested.csv").write_text("n")

    with patch.object(grdm, "upload_file", return_value={}) as upload:
        n = grdm.sync_local_to_grdm(str(tmp_path), "proj", "fold")
    assert n == 2
    assert upload.call_count == 2
    names = {Path(c.args[1]).name for c in upload.call_args_list}
    assert names == {"a.csv", "b.csv"}


def test_no_hardcoded_bearer_pat_in_source():
    """Regression: real PATs must not be embedded in grdm modules."""
    root = Path(__file__).resolve().parents[1] / "src" / "utils"
    for name in ("grdm_client.py", "grdm_secure_storage.py", "grdm_sync_ui.py", "grdm_config.py"):
        text = (root / name).read_text(encoding="utf-8")
        assert "Bearer ey" not in text
        # client_storage must never be used for the PAT
        if name != "grdm_config.py":
            assert 'client_storage.set("grdm_token"' not in text
            assert "client_storage.set('grdm_token'" not in text
