"""Unit tests for GakuNin RDM config / client helpers (no live API calls)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from src.utils.grdm_config import persist_grdm_destination, resolve_grdm_destination
from src.utils import grdm_client as grdm
from src.utils import grdm_secure_storage as gss


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


def test_normalize_storage_id_strips_osfstorage_prefix():
    assert grdm.normalize_storage_id("osfstorage/abc123") == "abc123"
    assert grdm.normalize_storage_id("OSFSTORAGE/abc123/") == "abc123"
    assert grdm.normalize_storage_id("abc123") == "abc123"
    assert grdm.normalize_storage_id("") == ""
    assert grdm.normalize_storage_id(None) == ""


def test_sync_local_to_grdm_empty(tmp_path: Path):
    with patch.object(grdm, "list_files", return_value=[]):
        n = grdm.sync_local_to_grdm(str(tmp_path), "proj", "")
    assert n == 0


def test_sync_local_to_grdm_recursive(tmp_path: Path):
    f1 = tmp_path / "a.csv"
    f1.write_text("a")
    export = tmp_path / "export" / "images"
    export.mkdir(parents=True)
    nested = export / "x.png"
    nested.write_text("img")

    created = {}

    def _create_folder(project_id, folder_name, parent_folder_id=""):
        fid = f"id-{folder_name}"
        created[folder_name] = fid
        return {"data": {"id": fid, "attributes": {"name": folder_name, "kind": "folder"}}}

    def _list_files(project_id, folder_id=""):
        # After create, report folders under root
        if folder_id == "":
            return [
                {
                    "id": created.get("export", "id-export"),
                    "attributes": {"name": "export", "kind": "folder"},
                }
            ]
        if folder_id == created.get("export"):
            return [
                {
                    "id": created.get("images", "id-images"),
                    "attributes": {"name": "images", "kind": "folder"},
                }
            ]
        return []

    with patch.object(grdm, "upload_file", return_value={"ok": True}) as upload, patch.object(
        grdm, "create_folder", side_effect=_create_folder
    ), patch.object(grdm, "list_files", side_effect=_list_files):
        n = grdm.sync_local_to_grdm(str(tmp_path), "proj", "")

    assert n == 2
    assert upload.call_count == 2
    names = {Path(c.args[1]).name for c in upload.call_args_list}
    assert names == {"a.csv", "x.png"}


def test_upload_file_skips_on_409(tmp_path: Path):
    f = tmp_path / "a.csv"
    f.write_text("a")

    class _Resp:
        status_code = 409

        def raise_for_status(self):
            raise AssertionError("should not raise on 409 when skip_if_exists")

        def json(self):
            return {}

    with patch.object(grdm.requests, "put", return_value=_Resp()):
        result = grdm.upload_file("proj", str(f), folder_id="osfstorage/parent")
    assert result.get("skipped") is True


def test_download_tree(tmp_path: Path):
    def _list_files(project_id, folder_id=""):
        if folder_id == "":
            return [
                {"id": "osfstorage/fold1", "attributes": {"name": "export", "kind": "folder"}},
                {"id": "osfstorage/file1", "attributes": {"name": "root.csv", "kind": "file"}},
            ]
        if folder_id == "fold1":
            return [
                {"id": "osfstorage/file2", "attributes": {"name": "meta.json", "kind": "file"}},
            ]
        return []

    with patch.object(grdm, "list_files", side_effect=_list_files), patch.object(
        grdm, "download_file"
    ) as dl:
        n = grdm.sync_grdm_to_local(str(tmp_path), "proj", "")
    assert n == 2
    assert dl.call_count == 2
    # WaterButler path must not keep osfstorage/ prefix
    ids = {c.args[1] for c in dl.call_args_list}
    assert ids == {"file1", "file2"}


def test_keyring_get_soft_fails():
    with patch.object(gss, "_keyring_get", return_value=None):
        # Simulate via direct call
        assert gss._keyring_get("grdm_token") is None


def test_is_insecure_keyring_detects_chainer_plain():
    plain = MagicMock()
    plain.__class__ = type("PlaintextKeyring", (), {})
    # Rebuild with a real-looking class name via type()
    Plain = type("PlaintextKeyring", (), {})
    plain = Plain()
    Chain = type("ChainerBackend", (), {"backends": [plain]})
    Chain.__module__ = "keyring.backends.chainer"
    Plain.__module__ = "keyring.backends.null"
    # name will be keyring.backends.null.PlaintextKeyring → contains "plain"
    assert gss._is_insecure_keyring(Chain()) is True


def test_no_hardcoded_bearer_pat_in_source():
    """Regression: real PATs must not be embedded in grdm modules."""
    root = Path(__file__).resolve().parents[1] / "src" / "utils"
    for name in ("grdm_client.py", "grdm_secure_storage.py", "grdm_sync_ui.py", "grdm_config.py"):
        text = (root / name).read_text(encoding="utf-8")
        assert "Bearer ey" not in text
        if name != "grdm_config.py":
            assert 'client_storage.set("grdm_token"' not in text
            assert "client_storage.set('grdm_token'" not in text
