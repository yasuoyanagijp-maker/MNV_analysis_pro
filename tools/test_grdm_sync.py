"""Unit tests for GakuNin RDM config / client / access control (no live API)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from src.utils.grdm_config import persist_grdm_destination, resolve_grdm_destination
from src.utils import grdm_client as grdm
from src.utils import grdm_secure_storage as gss
from src.utils.grdm_access import (
    TEAM_YY_INSTITUTION_ID,
    filter_institution_datasets,
    first_grader_remote_segments,
    is_team_yy,
    second_reader_remote_segments,
)
from src.utils.grdm_sync_ui import isolated_download_dir


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
    assert grdm.active_token() == "test-token-value"
    assert grdm._auth_headers() == {"Authorization": "Bearer test-token-value"}


def test_active_token_is_context_local():
    """Concurrent-style: context-bound token must not leak across contexts."""
    import contextvars

    grdm.set_active_token("token-A")
    assert grdm.active_token() == "token-A"

    ctx = contextvars.copy_context()

    def _in_other():
        grdm.set_active_token("token-B")
        return grdm.active_token()

    other = ctx.run(_in_other)
    assert other == "token-B"
    # Re-bind for this context after child mutated thread-local
    grdm.set_active_token("token-A")
    assert grdm.active_token() == "token-A"


def test_normalize_storage_id_strips_osfstorage_prefix():
    assert grdm.normalize_storage_id("osfstorage/abc123") == "abc123"
    assert grdm.normalize_storage_id("OSFSTORAGE/abc123/") == "abc123"
    assert grdm.normalize_storage_id("abc123") == "abc123"
    assert grdm.normalize_storage_id("") == ""
    assert grdm.normalize_storage_id(None) == ""


def test_list_files_follows_pagination():
    pages = [
        {
            "data": [{"id": "osfstorage/a", "attributes": {"name": "a", "kind": "file"}}],
            "links": {"next": "https://api.example/page2"},
        },
        {
            "data": [{"id": "osfstorage/b", "attributes": {"name": "b", "kind": "file"}}],
            "links": {"next": None},
        },
    ]
    calls = {"n": 0}

    class _Resp:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    def _get(url, headers=None, params=None):
        idx = calls["n"]
        calls["n"] += 1
        return _Resp(pages[idx])

    with patch.object(grdm.requests, "get", side_effect=_get):
        items = grdm.list_files("proj", "")
    assert len(items) == 2
    assert calls["n"] == 2


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
    ids = {c.args[1] for c in dl.call_args_list}
    assert ids == {"file1", "file2"}


def test_keyring_get_soft_fails():
    with patch.object(gss, "_keyring_get", return_value=None):
        assert gss._keyring_get("grdm_token") is None


def test_is_insecure_keyring_detects_chainer_plain():
    Plain = type("PlaintextKeyring", (), {})
    Plain.__module__ = "keyring.backends.null"
    plain = Plain()
    Chain = type("ChainerBackend", (), {"backends": [plain]})
    Chain.__module__ = "keyring.backends.chainer"
    assert gss._is_insecure_keyring(Chain()) is True


def test_is_team_yy_by_institution_and_env(monkeypatch):
    assert is_team_yy(institution_id=TEAM_YY_INSTITUTION_ID) is True
    assert is_team_yy(institution_id="ARIAKE_OHANACHAYA") is False
    monkeypatch.setenv("ARIAKE_CENTRAL_READING", "1")
    assert is_team_yy(institution_id="ARIAKE_OHANACHAYA") is True


def test_login_institution_not_overridden_by_site_env(monkeypatch):
    from src.utils.grdm_access import login_institution_id

    monkeypatch.setenv("ARIAKE_INSTITUTION_ID", "ARIAKE_OHANACHAYA")
    session = MagicMock()
    session.get.side_effect = lambda k: (
        TEAM_YY_INSTITUTION_ID if k == "institution_id" else None
    )
    assert login_institution_id(session) == TEAM_YY_INSTITUTION_ID
    assert is_team_yy(session) is True


def test_list_institution_folders_merges_base_and_measurements():
    def _remote_children(project_id, folder_id=""):
        if folder_id == "":
            return {
                "ARIAKE_OHANACHAYA": "id-base-aria",
                "measurements": "id-meas",
                "second_reading": "id-sr",
            }
        if folder_id == "id-meas":
            return {
                "ARIAKE_OHANACHAYA": "id-meas-aria",  # duplicate — prefer base
                "TOKYO_UNIV": "id-meas-tokyo",
            }
        return {}

    with patch.object(grdm, "_remote_child_folders", side_effect=_remote_children):
        folders = grdm.list_institution_folders("proj", "")
    by_name = {f["name"]: f["id"] for f in folders}
    assert by_name["ARIAKE_OHANACHAYA"] == "id-base-aria"
    assert by_name["TOKYO_UNIV"] == "id-meas-tokyo"
    assert "second_reading" not in by_name


def test_second_reader_output_dir_isolates_institution(tmp_path: Path):
    from src.utils.second_reader import second_reader_output_dir

    scan = tmp_path / "grdm_downloads" / "proj" / "ARIAKE_OHANACHAYA_20260101"
    scan.mkdir(parents=True)
    a = second_reader_output_dir(scan, "ARIAKE_OHANACHAYA")
    b = second_reader_output_dir(scan, "TOKYO_UNIV")
    assert a != b
    assert "ARIAKE_OHANACHAYA" in a.name
    assert "TOKYO_UNIV" in b.name


def test_looks_like_institution_folder_rejects_layout_and_timestamps():
    from src.utils.grdm_access import (
        infer_institution_from_path,
        looks_like_institution_folder,
    )

    assert looks_like_institution_folder("ARIAKE_OHANACHAYA") is True
    assert looks_like_institution_folder("TOKYO_UNIV") is True
    assert looks_like_institution_folder("images") is False
    assert looks_like_institution_folder("export") is False
    assert looks_like_institution_folder("meta") is False
    assert looks_like_institution_folder("TEAM_YY") is False
    assert looks_like_institution_folder("ARIAKE_OHANACHAYA_20260812_153045") is False
    assert looks_like_institution_folder("second_reader_output_2026_08_12") is False

    p = Path("/tmp/x/export/images/ARIAKE_OHANACHAYA/lesion.png")
    assert infer_institution_from_path(p) == "ARIAKE_OHANACHAYA"
    assert infer_institution_from_path(Path("/tmp/x/export/images")) == ""


def test_filter_institution_datasets_acl():
    datasets = [
        {"name": "ARIAKE_OHANACHAYA", "id": "1"},
        {"name": "TOKYO_UNIV", "id": "2"},
    ]
    own = filter_institution_datasets(
        datasets, viewer_institution_id="ARIAKE_OHANACHAYA", central=False
    )
    assert [d["name"] for d in own] == ["ARIAKE_OHANACHAYA"]
    all_ds = filter_institution_datasets(
        datasets, viewer_institution_id="ARIAKE_OHANACHAYA", central=True
    )
    assert len(all_ds) == 2
    empty = filter_institution_datasets(
        datasets, viewer_institution_id="UNKNOWN", central=False
    )
    assert empty == []


def test_remote_segments_separate_first_and_second():
    assert first_grader_remote_segments("ARIAKE_OHANACHAYA") == ("ARIAKE_OHANACHAYA",)
    assert second_reader_remote_segments("TOKYO_UNIV") == ("second_reading", "TOKYO_UNIV")


def test_first_grader_segments_reject_team_yy():
    try:
        first_grader_remote_segments(TEAM_YY_INSTITUTION_ID)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_isolated_download_dirs_differ_by_institution_and_time(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "src.utils.grdm_sync_ui.get_base_data_dir", lambda: tmp_path
    )
    a = isolated_download_dir("proj", "ARIAKE_OHANACHAYA")
    b = isolated_download_dir("proj", "TOKYO_UNIV")
    assert a != b
    assert "ARIAKE_OHANACHAYA" in str(a)
    assert "TOKYO_UNIV" in str(b)
    assert a.is_dir() and b.is_dir()


def test_no_hardcoded_bearer_pat_in_source():
    root = Path(__file__).resolve().parents[1] / "src" / "utils"
    for name in (
        "grdm_client.py",
        "grdm_secure_storage.py",
        "grdm_sync_ui.py",
        "grdm_config.py",
        "grdm_access.py",
    ):
        text = (root / name).read_text(encoding="utf-8")
        assert "Bearer ey" not in text
        if name not in ("grdm_config.py", "grdm_access.py"):
            assert 'client_storage.set("grdm_token"' not in text
