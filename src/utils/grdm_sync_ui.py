"""
Flet UI helpers for GakuNin RDM 同期 / 取得.

ローカル保存とは分離: ユーザーが明示的に押したときだけクラウドとやり取りする。

アクセス制御（OCTA-MIC）
------------------------
- 一般施設の第2リーダー: 自施設の第1読影フォルダのみ選択可能
- Team YY（中央読影）: 全施設の第1読影フォルダを横断選択可能
- 第1同期先: ``{base}/{institution_id}/``
- 第2同期先: ``{base}/second_reading/{institution_id}/``
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import flet as ft
from flet import Colors, Icons

from src.flet_ui.components.shared import GLASS_BG, PRIMARY, TEXT_MUTED
from src.utils import grdm_client as grdm
from src.utils.app_paths import get_base_data_dir, sanitize_path_component
from src.utils.grdm_access import (
    TEAM_YY_INSTITUTION_ID,
    filter_institution_datasets,
    first_grader_remote_segments,
    is_team_yy,
    login_institution_id,
    second_reader_remote_segments,
)
from src.utils.grdm_config import persist_grdm_destination, resolve_grdm_destination
from src.utils.grdm_secure_storage import GRDM_TOKEN_STORAGE_KEY, SecureStorage
from src.utils.institution_config import resolve_institution_id
from src.utils.second_reader import is_second_reader


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


async def clear_stored_grdm_token() -> None:
    storage = SecureStorage()
    try:
        await storage.remove(GRDM_TOKEN_STORAGE_KEY)
    except Exception:
        pass


async def ensure_grdm_token(page: ft.Page, *, write_scope_hint: bool = True) -> Optional[str]:
    """Load PAT from secure storage, revalidate, or prompt + persist on first use."""
    storage = SecureStorage()
    token: Optional[str] = None
    try:
        token = await storage.get(GRDM_TOKEN_STORAGE_KEY)
    except Exception:
        token = None

    if token:
        grdm.set_active_token(token)

        def _check():
            return grdm.check_connection()

        try:
            ok = await _with_loading(page, "保存済みトークンを確認中…", _check)
        except Exception:
            ok = False
        if ok:
            return token
        await clear_stored_grdm_token()
        _show_snack(
            page,
            "保存済みトークンが無効です。再入力してください。",
            error=True,
        )
        token = None

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

    def _check_new():
        return grdm.check_connection()

    try:
        ok = await _with_loading(page, "GakuNin RDM へ接続確認中…", _check_new)
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


def _viewer_institution(page: ft.Page) -> str:
    """Login/UI institution for ACL (must not be overridden by site-lock env)."""
    return login_institution_id(
        page.session, getattr(page, "client_storage", None)
    )


def _sync_institution_for_first_grader(page: ft.Page) -> str:
    """Match metadata export: site-lock env ARIAKE_INSTITUTION_ID wins when set."""
    return resolve_institution_id(
        page.session, getattr(page, "client_storage", None)
    )


def isolated_download_dir(project_id: str, institution_id: str) -> Path:
    """Per-pull isolated folder to avoid mixing institutions / stale files."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_proj = sanitize_path_component(project_id) or "project"
    safe_inst = sanitize_path_component(institution_id) or "UNKNOWN"
    d = get_base_data_dir() / "grdm_downloads" / safe_proj / f"{safe_inst}_{ts}"
    d.mkdir(parents=True, exist_ok=True)
    return d


async def _prompt_institution_dataset(
    page: ft.Page, datasets: List[Dict[str, str]], *, central: bool
) -> Optional[Dict[str, str]]:
    """Let the user pick one institution folder (ACL already applied)."""
    if not datasets:
        return None
    if len(datasets) == 1 and not central:
        return datasets[0]

    result: dict = {"value": None}
    done = asyncio.Event()
    options = [
        ft.dropdown.Option(d["name"], f"{d['name']}")
        for d in datasets
    ]
    dd = ft.Dropdown(
        label="第1読影データ（施設）",
        width=420,
        border_color=PRIMARY,
        options=options,
        value=datasets[0]["name"],
    )
    hint = (
        "Team YY: 全参加施設から選択できます。"
        if central
        else "自施設のデータのみ表示されています。"
    )

    async def _ok(_=None):
        name = dd.value
        result["value"] = next((d for d in datasets if d["name"] == name), None)
        page.close(dlg)
        done.set()

    async def _cancel(_=None):
        result["value"] = None
        page.close(dlg)
        done.set()

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text("GakuNin RDM — 第1読影データの選択", color=Colors.WHITE),
        content=ft.Container(
            content=ft.Column(
                [
                    ft.Text(hint, size=12, color=TEXT_MUTED),
                    dd,
                ],
                tight=True,
                spacing=12,
            ),
            width=460,
        ),
        actions=[
            ft.TextButton("キャンセル", on_click=lambda _: page.run_task(_cancel)),
            ft.ElevatedButton(
                "取得する",
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
    return result["value"]


async def run_grdm_sync(page: ft.Page, local_folder: str) -> None:
    """Upload local export folder (recursive) to role-/institution-scoped GRDM path."""
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
    project_id, base_folder_id = dest

    sr = is_second_reader(page.session)
    if sr:
        # Prefer institution of the scanned / downloaded first-grader data
        graded = (page.session.get("grdm_graded_institution_id") or "").strip()
        from src.utils.grdm_access import looks_like_institution_folder

        if graded and looks_like_institution_folder(graded):
            inst = graded
        elif is_team_yy(page.session, getattr(page, "client_storage", None)):
            prompted = await _prompt_text(
                page,
                title="第2リーダー結果のアップロード先施設",
                label="institution_id",
                hint="読影した施設コード（例: ARIAKE_OHANACHAYA）",
                initial="",
            )
            if not prompted:
                _show_snack(page, "アップロード先施設が未指定です", error=True)
                return
            inst = prompted
        else:
            # Facility second reader: use site-lock / login institution
            inst = _sync_institution_for_first_grader(page)
            if not inst or inst in ("UNKNOWN", TEAM_YY_INSTITUTION_ID):
                inst = _viewer_institution(page)
    else:
        # First grader: same resolution as metadata export (env site-lock wins)
        inst = _sync_institution_for_first_grader(page)

    try:
        segments = (
            second_reader_remote_segments(inst)
            if sr
            else first_grader_remote_segments(inst)
        )
    except ValueError as ex:
        _show_snack(page, str(ex), error=True)
        return

    def _upload():
        target_id = grdm.ensure_remote_path(
            project_id, segments, base_folder_id=base_folder_id or ""
        )
        return grdm.sync_local_to_grdm(str(folder), project_id, target_id)

    try:
        count = await _with_loading(
            page,
            f"GakuNin RDM へ同期中…\n{'/'.join(segments)}\n{folder}",
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
        scope = "第2リーダー結果" if sr else "第1読影データ"
        _show_snack(
            page,
            f"GakuNin RDMへの同期が完了しました（{scope} / {inst} / 新規 {count}件）",
        )


async def run_grdm_download(
    page: ft.Page,
    *,
    on_complete: Optional[Callable[[str], Any]] = None,
) -> Optional[str]:
    """ACL-aware download of one institution's first-grader dataset for second readers."""
    token = await ensure_grdm_token(page, write_scope_hint=False)
    if not token:
        return None

    dest = await ensure_grdm_destination(page)
    if not dest:
        return None
    project_id, base_folder_id = dest

    cs = getattr(page, "client_storage", None)
    viewer_inst = _viewer_institution(page)
    central = is_team_yy(page.session, cs, institution_id=viewer_inst)

    def _list():
        return grdm.list_institution_folders(project_id, base_folder_id or "")

    try:
        all_datasets = await _with_loading(
            page, "利用可能な第1読影データを照会中…", _list
        )
    except Exception as ex:
        _show_snack(page, f"一覧取得に失敗しました: {ex}", error=True)
        return None

    allowed = filter_institution_datasets(
        all_datasets,
        viewer_institution_id=viewer_inst,
        central=central,
    )
    if not allowed:
        if central:
            msg = "第1読影データ（施設フォルダ）が見つかりません。第1グレーダーの同期を確認してください。"
        else:
            msg = (
                f"自施設（{viewer_inst}）の第1読影データが GakuNin 上にありません。"
                " 他施設のデータにはアクセスできません。"
            )
        _show_snack(page, msg, error=True)
        return None

    chosen = await _prompt_institution_dataset(page, allowed, central=central)
    if not chosen:
        _show_snack(page, "データ選択がキャンセルされました", error=True)
        return None

    inst_name = chosen["name"]
    remote_id = chosen["id"]
    target = isolated_download_dir(project_id, inst_name)

    def _download():
        return grdm.sync_grdm_to_local(str(target), project_id, remote_id)

    try:
        count = await _with_loading(
            page,
            f"GakuNin RDM から取得中…\n{inst_name}\n→ {target}",
            _download,
        )
    except Exception as ex:
        _show_snack(page, f"取得に失敗しました: {ex}", error=True)
        return None

    # Remember which facility was pulled (for Team YY second-reader re-upload path)
    try:
        page.session.set("grdm_graded_institution_id", inst_name)
    except Exception:
        pass

    if count == 0:
        _show_snack(
            page,
            f"{inst_name}: ダウンロード対象ファイルがありません",
            error=True,
        )
        return str(target)

    _show_snack(page, f"{inst_name}: {count}件を取得しました\n{target}")

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
        tooltip=(
            "ローカル保存済みフォルダを施設スコープでアップロード。"
            " 第1→{institution}/、第2→second_reading/{institution}/"
        ),
        on_click=lambda _: page.run_task(_on_click),
    )


def make_grdm_download_button(
    page: ft.Page,
    *,
    on_complete: Optional[Callable[[str], Any]] = None,
    label: str = "GakuNin RDMから第1読影データを取得して読影開始",
) -> ft.ElevatedButton:
    """Second-reader / central reading: pull first-grader exports with ACL."""

    async def _on_click(_=None):
        await run_grdm_download(page, on_complete=on_complete)

    return ft.ElevatedButton(
        label,
        icon=Icons.CLOUD_DOWNLOAD_ROUNDED,
        bgcolor=Colors.with_opacity(0.3, Colors.TEAL_ACCENT_400),
        color=Colors.BLACK,
        tooltip=(
            "一般施設は自施設のみ、Team YY は全施設から第1読影データを選択できます。"
            " PAT は OS ネイティブの安全な領域に保存します。"
        ),
        on_click=lambda _: page.run_task(_on_click),
        width=420,
    )
