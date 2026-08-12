"""
Flet UI helpers for GakuNin RDM 同期 / 取得.

ローカル保存とは分離: ユーザーが明示的に押したときだけクラウドとやり取りする。
第1グレーダー: エクスポート先をアップロード。
第2リーダー（施設内・中央読影 Team YY）: 第1読影データをダウンロードしてから読影開始。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable, Optional

import flet as ft
from flet import Colors, Icons

from src.flet_ui.components.shared import GLASS_BG, PRIMARY, TEXT_MUTED
from src.utils import grdm_client as grdm
from src.utils.app_paths import get_base_data_dir
from src.utils.grdm_config import persist_grdm_destination, resolve_grdm_destination
from src.utils.grdm_secure_storage import GRDM_TOKEN_STORAGE_KEY, SecureStorage


def _show_snack(page: ft.Page, message: str, *, error: bool = False) -> None:
    bar = ft.SnackBar(
        content=ft.Text(message, color=Colors.WHITE),
        bgcolor=Colors.RED_700 if error else Colors.GREEN_700,
        open=True,
    )
    page.open(bar)
    page.update()


async def _prompt_text(
    page: ft.Page,
    *,
    title: str,
    label: str,
    hint: str = "",
    password: bool = False,
    initial: str = "",
) -> Optional[str]:
    """Modal text prompt. Returns None if cancelled / empty."""
    field = ft.TextField(
        label=label,
        hint_text=hint,
        value=initial or "",
        password=password,
        can_reveal_password=password,
        border_color=PRIMARY,
        autofocus=True,
        width=480,
    )
    result: dict = {"value": None}
    done = asyncio.Event()

    async def _ok(_=None):
        result["value"] = (field.value or "").strip()
        page.close(dlg)
        done.set()

    async def _cancel(_=None):
        result["value"] = None
        page.close(dlg)
        done.set()

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text(title, color=Colors.WHITE),
        content=ft.Container(content=field, width=500),
        actions=[
            ft.TextButton("キャンセル", on_click=lambda _: page.run_task(_cancel)),
            ft.ElevatedButton(
                "OK",
                bgcolor=PRIMARY,
                color=Colors.BLACK,
                on_click=lambda _: page.run_task(_ok),
            ),
        ],
        bgcolor=GLASS_BG,
    )
    page.open(dlg)
    page.update()
    await done.wait()
    return result["value"] or None


async def _with_loading(page: ft.Page, message: str, work: Callable[[], Any]) -> Any:
    """Show a modal ProgressRing while ``work`` runs in a thread."""
    status = ft.Text(message, color=TEXT_MUTED, size=13)
    dlg = ft.AlertDialog(
        modal=True,
        content=ft.Container(
            content=ft.Column(
                [
                    ft.ProgressRing(width=40, height=40, stroke_width=4, color=PRIMARY),
                    status,
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=16,
                tight=True,
            ),
            padding=20,
            width=360,
        ),
        bgcolor=GLASS_BG,
    )
    page.open(dlg)
    page.update()
    try:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, work)
    finally:
        try:
            page.close(dlg)
        except Exception:
            pass
        page.update()


async def ensure_grdm_token(page: ft.Page, *, write_scope_hint: bool = True) -> Optional[str]:
    """Load PAT from secure storage, or prompt + verify + persist on first use.

    Keyring read failures are treated as "no token" so the dialog still appears
    (needed on Linux without libsecret / locked Secret Service).
    """
    storage = SecureStorage()
    token: Optional[str] = None
    try:
        token = await storage.get(GRDM_TOKEN_STORAGE_KEY)
    except Exception:
        token = None

    if token:
        grdm.set_active_token(token)
        return token

    scope_hint = (
        "osf.full_write 推奨（アップロード）"
        if write_scope_hint
        else "osf.full_read 以上（ダウンロード）"
    )
    token = await _prompt_text(
        page,
        title="GakuNin RDM Personal Access Token",
        label="Personal Access Token (PAT)",
        hint=f"https://rdm.nii.ac.jp/settings/tokens/ で発行（{scope_hint}）",
        password=True,
    )
    if not token:
        _show_snack(page, "トークン入力がキャンセルされました", error=True)
        return None

    grdm.set_active_token(token)

    def _check():
        return grdm.check_connection()

    try:
        ok = await _with_loading(page, "GakuNin RDM へ接続確認中…", _check)
    except Exception as ex:
        _show_snack(page, f"接続失敗: {ex}", error=True)
        return None

    if not ok:
        _show_snack(page, "接続失敗。トークンを確認してください", error=True)
        return None

    try:
        await storage.set(GRDM_TOKEN_STORAGE_KEY, token)
    except Exception as ex:
        _show_snack(
            page,
            f"接続は成功しましたがトークン保存に失敗しました（今セッションのみ有効）: {ex}",
            error=True,
        )
        return token

    _show_snack(page, "GakuNin RDM への接続に成功しました。トークンを安全に保存しました。")
    return token


async def ensure_grdm_destination(page: ft.Page) -> Optional[tuple]:
    """Resolve project_id/folder_id from settings; prompt for project_id if missing."""
    cs = getattr(page, "client_storage", None)
    project_id, folder_id = resolve_grdm_destination(page.session, cs)
    if not project_id:
        project_id = await _prompt_text(
            page,
            title="GakuNin RDM プロジェクトID",
            label="project_id",
            hint="ダッシュボード Advanced Settings でも変更できます",
        )
        if not project_id:
            _show_snack(
                page,
                "project_id が未設定です。Advanced Settings で設定してください。",
                error=True,
            )
            return None
        persist_grdm_destination(project_id, folder_id, page.session, cs)
    return project_id, folder_id


async def run_grdm_sync(page: ft.Page, local_folder: str) -> None:
    """Upload local export folder (recursive) to GakuNin RDM."""
    folder = Path(local_folder) if local_folder else None
    if folder is None or not folder.is_dir():
        _show_snack(
            page,
            f"エクスポート先フォルダが見つかりません: {local_folder}",
            error=True,
        )
        return

    token = await ensure_grdm_token(page, write_scope_hint=True)
    if not token:
        return

    dest = await ensure_grdm_destination(page)
    if not dest:
        return
    project_id, folder_id = dest

    def _upload():
        return grdm.sync_local_to_grdm(str(folder), project_id, folder_id or "")

    try:
        count = await _with_loading(
            page,
            f"GakuNin RDM へ同期中…\n{folder}",
            _upload,
        )
    except Exception as ex:
        _show_snack(page, f"同期に失敗しました: {ex}", error=True)
        return

    if count == 0:
        _show_snack(
            page,
            "新規同期ファイルはありません（空フォルダ、または全て既存でスキップ）",
            error=True,
        )
    else:
        _show_snack(page, f"GakuNin RDMへの同期が完了しました（新規 {count}件）")


def default_grdm_download_dir() -> Path:
    d = get_base_data_dir() / "grdm_downloads"
    d.mkdir(parents=True, exist_ok=True)
    return d


async def run_grdm_download(
    page: ft.Page,
    local_folder: Optional[str] = None,
    *,
    on_complete: Optional[Callable[[str], Any]] = None,
) -> Optional[str]:
    """Download configured GRDM folder to local disk (for second readers).

    Returns the local path on success, else None.
    If ``on_complete`` is set (e.g. start second-reader scan), it is awaited/called
    with the download directory path.
    """
    token = await ensure_grdm_token(page, write_scope_hint=False)
    if not token:
        return None

    dest = await ensure_grdm_destination(page)
    if not dest:
        return None
    project_id, folder_id = dest

    target = Path(local_folder) if local_folder else default_grdm_download_dir()
    target.mkdir(parents=True, exist_ok=True)

    def _download():
        return grdm.sync_grdm_to_local(str(target), project_id, folder_id or "")

    try:
        count = await _with_loading(
            page,
            f"GakuNin RDM から取得中…\n→ {target}",
            _download,
        )
    except Exception as ex:
        _show_snack(page, f"取得に失敗しました: {ex}", error=True)
        return None

    if count == 0:
        _show_snack(
            page,
            "ダウンロード対象がありません（project_id / folder_id を確認してください）",
            error=True,
        )
        return str(target)

    _show_snack(page, f"GakuNin RDMから {count}件を取得しました\n{target}")

    if on_complete is not None:
        result = on_complete(str(target))
        if asyncio.iscoroutine(result):
            await result
    return str(target)


def make_grdm_sync_button(page: ft.Page, get_local_folder: Callable[[], Path]) -> ft.ElevatedButton:
    """Factory for the results-screen sync button (does not alter local export)."""

    async def _on_click(_=None):
        await run_grdm_sync(page, str(get_local_folder()))

    return ft.ElevatedButton(
        "GakuNin RDMへ同期",
        icon=Icons.CLOUD_UPLOAD_ROUNDED,
        bgcolor=Colors.with_opacity(0.25, Colors.TEAL_ACCENT_400),
        color=Colors.TEAL_ACCENT_100,
        tooltip="ローカル保存済みのエクスポート先フォルダ（サブフォルダ含む）を"
        " GakuNin RDM へアップロードします（PATはOSネイティブの安全な領域に保存）",
        on_click=lambda _: page.run_task(_on_click),
    )


def make_grdm_download_button(
    page: ft.Page,
    *,
    on_complete: Optional[Callable[[str], Any]] = None,
    label: str = "GakuNin RDMから第1読影データを取得",
) -> ft.ElevatedButton:
    """Second-reader / central reading: pull first-grader exports from GRDM."""

    async def _on_click(_=None):
        await run_grdm_download(page, on_complete=on_complete)

    return ft.ElevatedButton(
        label,
        icon=Icons.CLOUD_DOWNLOAD_ROUNDED,
        bgcolor=Colors.with_opacity(0.3, Colors.TEAL_ACCENT_400),
        color=Colors.BLACK,
        tooltip="設定の project_id / folder_id から第1グレーダー成果物を取得します。"
        " 中央読影（Team YY）・施設内第2リーダーの双方が同じ PAT 設定で利用できます。",
        on_click=lambda _: page.run_task(_on_click),
        width=400,
    )
