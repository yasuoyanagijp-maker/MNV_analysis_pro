"""
GakuNin RDM (rdm.nii.ac.jp) 簡易APIクライアント

GakuNin RDMはOSF(Open Science Framework)をベースに構築されているため、
API仕様の詳細は https://developer.osf.io/ も参照のこと。

想定用途: OCTA-MIC(YCU正式研究プロジェクト)でのデータ授受専用。
第1グレーダーのエクスポート同期、および第2リーダー（中央読影含む）の取得に使う。

--- Fletアプリでの認証情報の扱いについて ---
このモジュール自体は認証情報の永続化を行わない(フレームワーク非依存に保つため)。
配布するFletアプリ側で OS ネイティブの安全な領域
(iOS/macOS: Keychain, Windows: Credential Manager, Linux: libsecret,
Android: Keystore) に保存したトークンを起動時に取得し、
set_active_token() でこのモジュールに渡す運用にする。

Fletの素のclient_storage(shared_preferences)は平文JSON/SharedPreferences相当なので
トークン保存には使わないこと。

PATの取得方法(各施設の担当者向け案内):
  1. https://rdm.nii.ac.jp/settings/tokens/ にアクセス
  2. 「Create token」→ スコープを選択
     - アップロードも行うなら osf.full_write
     - 参照のみなら osf.full_read
  3. 発行されたトークンをアプリの初回設定画面に貼り付ける(再表示されないので注意)

ローカル開発時(自分のPCで直接このスクリプトを動かす場合)は.envでも可:
  GRDM_TOKEN=xxxxxxxx
  GRDM_PROJECT_ID=xxxxx

依存パッケージ:
  pip install requests python-dotenv --break-system-packages
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import requests
from dotenv import load_dotenv

load_dotenv()

API_BASE = "https://api.rdm.nii.ac.jp/v2"
FILES_BASE = "https://files.rdm.nii.ac.jp/v1/resources"

TOKEN = os.environ.get("GRDM_TOKEN")
DEFAULT_PROJECT_ID = os.environ.get("GRDM_PROJECT_ID")
HEADERS = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}


def set_active_token(token: str) -> None:
    """Fletアプリ側でsecure storageから取り出したトークンをセットする。
    アプリ起動時・設定画面での保存直後に呼ぶ。
    """
    global TOKEN, HEADERS
    TOKEN = token
    HEADERS = {"Authorization": f"Bearer {TOKEN}"}


def normalize_storage_id(raw: Optional[str]) -> str:
    """JSON API の id (例: ``osfstorage/<guid>``) を WaterButler パス用に正規化する。

    WaterButler URL は既に ``/providers/osfstorage/`` を含むため、
    先頭の ``osfstorage/`` プレフィックスを除去する。
    """
    s = (raw or "").strip().strip("/")
    lower = s.lower()
    if lower.startswith("osfstorage/"):
        s = s[len("osfstorage/") :]
    return s.strip("/")


def list_projects() -> list:
    """アクセス可能なプロジェクト(node)一覧を取得"""
    resp = requests.get(f"{API_BASE}/nodes/", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()["data"]


def list_files(project_id: str, folder_id: str = "") -> list:
    """プロジェクト直下、または指定フォルダ内のファイル/フォルダ一覧を取得（全ページ）。

    folder_id省略時はルート(osfstorage直下)を返す。
    OSF/GakuNin RDM の JSON:API ページネーション（links.next）を辿る。

    戻り値の各要素の ["id"] は ``normalize_storage_id()`` してから
    download_file / upload先 folder_id として使うこと。
    """
    fid = normalize_storage_id(folder_id)
    suffix = f"{fid}/" if fid else ""
    url: Optional[str] = f"{API_BASE}/nodes/{project_id}/files/osfstorage/{suffix}"
    params: Optional[Dict[str, Any]] = {"page[size]": 100}
    items: List[dict] = []
    while url:
        resp = requests.get(url, headers=HEADERS, params=params)
        resp.raise_for_status()
        payload = resp.json()
        chunk = payload.get("data") or []
        if isinstance(chunk, list):
            items.extend(chunk)
        next_url = (payload.get("links") or {}).get("next")
        url = next_url if next_url else None
        params = None  # next URL already encodes page cursor
    return items


def ensure_remote_path(
    project_id: str, segments: Sequence[str], base_folder_id: str = ""
) -> str:
    """Create nested folders under base_folder_id; return the deepest folder id."""
    current = normalize_storage_id(base_folder_id)
    for name in segments:
        name = str(name or "").strip()
        if not name:
            continue
        existing = _remote_child_folders(project_id, current)
        if name in existing:
            current = existing[name]
            continue
        created = create_folder(project_id, name, parent_folder_id=current)
        nid = _extract_node_id(created)
        if not nid and isinstance(created, dict):
            nid = normalize_storage_id(str(created.get("id") or ""))
        if not nid:
            existing = _remote_child_folders(project_id, current)
            nid = existing.get(name, "")
        if not nid:
            raise RuntimeError(f"リモートフォルダを作成できませんでした: {name}")
        current = nid
    return current


def list_institution_folders(
    project_id: str, base_folder_id: str = ""
) -> List[Dict[str, str]]:
    """List candidate first-grader institution folders under the GRDM base.

    If a ``measurements`` child exists, prefer listing inside it (legacy layout).
    Skips reserved names such as ``second_reading``.
    """
    from src.utils.grdm_access import looks_like_institution_folder

    base = normalize_storage_id(base_folder_id)
    children = _remote_child_folders(project_id, base)
    list_root = base
    if "measurements" in children:
        list_root = children["measurements"]
        children = _remote_child_folders(project_id, list_root)

    out: List[Dict[str, str]] = []
    for name, fid in sorted(children.items()):
        if not looks_like_institution_folder(name):
            continue
        out.append({"name": name, "id": fid, "parent_id": list_root})
    return out


def create_folder(project_id: str, folder_name: str, parent_folder_id: str = "") -> dict:
    """フォルダを作成。parent_folder_id省略時はルート直下に作成。

    既に同名フォルダがある場合(HTTP 409)は list_files から既存を返す。
    """
    parent = normalize_storage_id(parent_folder_id)
    suffix = f"{parent}/" if parent else ""
    url = f"{FILES_BASE}/{project_id}/providers/osfstorage/{suffix}"
    resp = requests.put(
        url,
        headers=HEADERS,
        params={"kind": "folder", "name": folder_name},
    )
    if resp.status_code == 409:
        for item in list_files(project_id, parent):
            attrs = item.get("attributes") or {}
            if attrs.get("kind") == "folder" and attrs.get("name") == folder_name:
                return item
        resp.raise_for_status()
    resp.raise_for_status()
    return resp.json()


def _extract_node_id(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    data = payload.get("data") if "data" in payload else payload
    if isinstance(data, dict):
        return normalize_storage_id(str(data.get("id") or ""))
    return ""


def upload_file(
    project_id: str,
    local_path: str,
    folder_id: str = "",
    remote_name: Optional[str] = None,
    *,
    skip_if_exists: bool = True,
) -> dict:
    """ファイルをアップロード。folder_id省略時はルート直下に置く。

    skip_if_exists=True（既定）のとき、HTTP 409（同名ファイル既存）は
    ``{"skipped": True, "reason": "already_exists"}`` を返して継続可能にする。
    """
    local_path = Path(local_path)
    remote_name = remote_name or local_path.name
    parent = normalize_storage_id(folder_id)
    suffix = f"{parent}/" if parent else ""
    url = f"{FILES_BASE}/{project_id}/providers/osfstorage/{suffix}"
    with open(local_path, "rb") as f:
        resp = requests.put(
            url,
            headers=HEADERS,
            params={"kind": "file", "name": remote_name},
            data=f,
        )
    if resp.status_code == 409 and skip_if_exists:
        return {"skipped": True, "reason": "already_exists", "name": remote_name}
    resp.raise_for_status()
    return resp.json()


def download_file(project_id: str, file_id: str, local_path: str) -> None:
    """list_filesで取得したidを指定してファイルをダウンロード"""
    fid = normalize_storage_id(file_id)
    url = f"{FILES_BASE}/{project_id}/providers/osfstorage/{fid}"
    resp = requests.get(url, headers=HEADERS)
    resp.raise_for_status()
    dest = Path(local_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(resp.content)


def setup_institution_structure(project_id: str) -> None:
    """施設ごとのプロジェクトに、標準フォルダ構成を一括作成する
    (raw_images / measurements / second_reading)
    """
    for name in ["raw_images", "measurements", "second_reading"]:
        create_folder(project_id, name)
        print(f"作成完了: {name}")


def _remote_child_folders(project_id: str, folder_id: str) -> Dict[str, str]:
    """name -> normalized storage id for folders under folder_id."""
    out: Dict[str, str] = {}
    for item in list_files(project_id, folder_id):
        attrs = item.get("attributes") or {}
        if attrs.get("kind") == "folder" and attrs.get("name"):
            out[str(attrs["name"])] = normalize_storage_id(str(item.get("id") or ""))
    return out


def sync_local_to_grdm(local_folder: str, project_id: str, folder_id: str = "") -> int:
    """ローカルフォルダの中身（サブフォルダ含む）をGakuNin RDMへアップロードする。

    ``export/`` 配下の MedSAM / PDF なども再帰的に送る。
    同名ファイルが既にある場合はスキップして続行する。

    Returns
    -------
    int
        新規アップロードしたファイル件数（スキップは含まない）
    """
    local_folder = Path(local_folder)
    if not local_folder.is_dir():
        raise FileNotFoundError(f"同期先フォルダが見つかりません: {local_folder}")

    uploaded, _skipped = _sync_local_tree(local_folder, project_id, normalize_storage_id(folder_id))
    print(f"{uploaded}件のファイルを同期しました（スキップ除く）")
    return uploaded


def _sync_local_tree(
    local_folder: Path, project_id: str, folder_id: str
) -> Tuple[int, int]:
    uploaded = 0
    skipped = 0

    files = sorted(f for f in local_folder.iterdir() if f.is_file())
    dirs = sorted(d for d in local_folder.iterdir() if d.is_dir())
    if not files and not dirs:
        print("同期対象のファイルはありません")
        return 0, 0

    remote_folders = _remote_child_folders(project_id, folder_id) if dirs else {}

    for f in files:
        print(f"アップロード中: {f.name}")
        result = upload_file(project_id, str(f), folder_id=folder_id)
        if result.get("skipped"):
            skipped += 1
            print(f"  スキップ（既存）: {f.name}")
        else:
            uploaded += 1

    for d in dirs:
        remote_id = remote_folders.get(d.name)
        if not remote_id:
            created = create_folder(project_id, d.name, parent_folder_id=folder_id)
            remote_id = _extract_node_id(created) or normalize_storage_id(
                str((created.get("id") if isinstance(created, dict) else "") or "")
            )
            if not remote_id and isinstance(created, dict):
                # create_folder may return a list_files item directly on 409
                remote_id = normalize_storage_id(str(created.get("id") or ""))
            if not remote_id:
                # refresh listing
                remote_folders = _remote_child_folders(project_id, folder_id)
                remote_id = remote_folders.get(d.name, "")
            if not remote_id:
                raise RuntimeError(f"リモートフォルダを作成できませんでした: {d.name}")
            remote_folders[d.name] = remote_id
        u, s = _sync_local_tree(d, project_id, remote_id)
        uploaded += u
        skipped += s

    return uploaded, skipped


def sync_grdm_to_local(local_folder: str, project_id: str, folder_id: str = "") -> int:
    """GakuNin RDM 上のフォルダ内容をローカルへ再帰ダウンロードする。

    第2リーダーが第1グレーダーの export 束を取得する用途を想定。

    Returns
    -------
    int
        ダウンロードしたファイル件数
    """
    dest_root = Path(local_folder)
    dest_root.mkdir(parents=True, exist_ok=True)
    count = _download_tree(dest_root, project_id, normalize_storage_id(folder_id))
    print(f"{count}件のファイルをダウンロードしました")
    return count


def _download_tree(local_folder: Path, project_id: str, folder_id: str) -> int:
    count = 0
    for item in list_files(project_id, folder_id):
        attrs = item.get("attributes") or {}
        name = attrs.get("name")
        kind = attrs.get("kind")
        item_id = normalize_storage_id(str(item.get("id") or ""))
        if not name or not item_id:
            continue
        if kind == "folder":
            sub = local_folder / str(name)
            sub.mkdir(parents=True, exist_ok=True)
            count += _download_tree(sub, project_id, item_id)
        else:
            target = local_folder / str(name)
            print(f"ダウンロード中: {target}")
            download_file(project_id, item_id, str(target))
            count += 1
    return count


def check_connection() -> bool:
    """set_active_token()の直後に呼び、トークンが有効かどうかを確認する。
    Fletアプリの「接続テスト」ボタンから使う想定。
    """
    try:
        projects = list_projects()
        return len(projects) >= 0
    except requests.HTTPError:
        return False


if __name__ == "__main__":
    # ローカル開発時の動作確認(.env読み込み前提)
    if not TOKEN:
        print(".envにGRDM_TOKENが設定されていません")
    else:
        for p in list_projects():
            print(p["id"], "-", p["attributes"]["title"])
