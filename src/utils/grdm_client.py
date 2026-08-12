"""
GakuNin RDM (rdm.nii.ac.jp) 簡易APIクライアント

GakuNin RDMはOSF(Open Science Framework)をベースに構築されているため、
API仕様の詳細は https://developer.osf.io/ も参照のこと。

想定用途: OCTA-MIC(YCU正式研究プロジェクト)でのデータ授受専用。

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
from typing import List, Optional

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


def list_projects() -> list:
    """アクセス可能なプロジェクト(node)一覧を取得"""
    resp = requests.get(f"{API_BASE}/nodes/", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()["data"]


def list_files(project_id: str, folder_id: str = "") -> list:
    """プロジェクト直下、または指定フォルダ内のファイル/フォルダ一覧を取得
    folder_id省略時はルート(osfstorage直下)を返す
    戻り値の各要素の ["id"] を download_file / upload先folder_idとして使う
    """
    suffix = f"{folder_id}/" if folder_id else ""
    url = f"{API_BASE}/nodes/{project_id}/files/osfstorage/{suffix}"
    resp = requests.get(url, headers=HEADERS)
    resp.raise_for_status()
    return resp.json()["data"]


def create_folder(project_id: str, folder_name: str, parent_folder_id: str = "") -> dict:
    """フォルダを作成。parent_folder_id省略時はルート直下に作成"""
    suffix = f"{parent_folder_id}/" if parent_folder_id else ""
    url = f"{FILES_BASE}/{project_id}/providers/osfstorage/{suffix}"
    resp = requests.put(
        url,
        headers=HEADERS,
        params={"kind": "folder", "name": folder_name},
    )
    resp.raise_for_status()
    return resp.json()


def upload_file(
    project_id: str,
    local_path: str,
    folder_id: str = "",
    remote_name: Optional[str] = None,
) -> dict:
    """ファイルをアップロード。folder_id省略時はルート直下に置く"""
    local_path = Path(local_path)
    remote_name = remote_name or local_path.name
    suffix = f"{folder_id}/" if folder_id else ""
    url = f"{FILES_BASE}/{project_id}/providers/osfstorage/{suffix}"
    with open(local_path, "rb") as f:
        resp = requests.put(
            url,
            headers=HEADERS,
            params={"kind": "file", "name": remote_name},
            data=f,
        )
    resp.raise_for_status()
    return resp.json()


def download_file(project_id: str, file_id: str, local_path: str) -> None:
    """list_filesで取得したidを指定してファイルをダウンロード"""
    url = f"{FILES_BASE}/{project_id}/providers/osfstorage/{file_id}"
    resp = requests.get(url, headers=HEADERS)
    resp.raise_for_status()
    Path(local_path).write_bytes(resp.content)


def setup_institution_structure(project_id: str) -> None:
    """施設ごとのプロジェクトに、標準フォルダ構成を一括作成する
    (raw_images / measurements / second_reading)
    """
    for name in ["raw_images", "measurements", "second_reading"]:
        create_folder(project_id, name)
        print(f"作成完了: {name}")


def sync_local_to_grdm(local_folder: str, project_id: str, folder_id: str = "") -> int:
    """ローカルフォルダの中身をGakuNin RDMへまとめてアップロードする。
    「クラウドへ同期」ボタンから呼ぶことを想定。
    既にアップロード済みかどうかの厳密な差分チェックはしていないため、
    運用では送信済みファイルを別ディレクトリへ移動する等の工夫を推奨。

    Returns
    -------
    int
        アップロードしたファイル件数
    """
    local_folder = Path(local_folder)
    if not local_folder.is_dir():
        raise FileNotFoundError(f"同期先フォルダが見つかりません: {local_folder}")
    files: List[Path] = [f for f in local_folder.iterdir() if f.is_file()]
    if not files:
        print("同期対象のファイルはありません")
        return 0
    for f in files:
        print(f"アップロード中: {f.name}")
        upload_file(project_id, str(f), folder_id=folder_id)
    print(f"{len(files)}件のファイルを同期しました")
    return len(files)


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
