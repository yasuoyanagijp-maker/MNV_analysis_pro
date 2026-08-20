"""
Flet UI helpers for GakuNin RDM 同期 / 取得.

ローカル保存とは分離: ユーザーが明示的に押したときだけクラウドとやり取りする。

アクセス制御（OCTA-MIC）
------------------------
- 一般施設の第2リーダー: 自施設の第1読影フォルダのみ選択可能
- Team YY（中央読影）: 全施設の第1読影フォルダを横断選択可能
- 第1同期先: ``{base}/{institution_id}/``
- 第2同期先: ``{base}/second_reading/{institution_id}/``
- 最終読影同期先: ``{base}/final_reading/{institution_id}/``
"""

from __future__ import annotations

import asyncio
import contextvars
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
    final_reader_remote_segments,
    first_grader_remote_segments,
    is_team_yy,
    login_institution_id,
    looks_like_institution_folder,
    second_reader_remote_segments,
)
from src.utils.grdm_config import (
    DEFAULT_GRDM_PROJECT_ID,
    normalize_grdm_project_id,
    persist_grdm_destination,
    resolve_grdm_destination,
)
from src.utils.grdm_secure_storage import GRDM_TOKEN_STORAGE_KEY, SecureStorage
from src.utils.institution_config import normalize_institution_id, resolve_institution_id
from src.utils.second_reader import is_final_reader, is_second_reader

_GRDM_LOG = Path("/tmp/ariake_flet.log")


def _grdm_log(message: str) -> None:
    line = f"[GRDM] {message}"
    print(line, flush=True)
    try:
        with _GRDM_LOG.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


# When set, _show_snack routes to the results-row status instead of a SnackBar.
_notify_override: contextvars.ContextVar[Optional[Callable[..., None]]] = (
    contextvars.ContextVar("grdm_notify", default=None)
)

_BTN_IDLE_BG = Colors.with_opacity(0.25, Colors.TEAL_ACCENT_400)
_BTN_IDLE_FG = Colors.TEAL_ACCENT_100
_BTN_OK_BG = Colors.GREEN_700
_BTN_OK_FG = Colors.WHITE
_BTN_ERR_BG = Colors.RED_700
_BTN_ERR_FG = Colors.WHITE
_BTN_BUSY_BG = Colors.AMBER_700
_BTN_BUSY_FG = Colors.BLACK


def _show_snack(page: ft.Page, message: str, *, error: bool = False) -> None:
    cb = getattr(page, "_grdm_sync_notify", None) or _notify_override.get()
    if cb is not None:
        cb(message, error=error)
        return
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
            grdm.set_active_token(token)
            return grdm.check_connection()

        try:
            ok = await _with_loading(page, "保存済みトークンを確認中…", _check)
        except Exception as ex:
            _grdm_log(f"stored token check raised: {ex}")
            ok = False
        if ok:
            return token
        _grdm_log("stored token rejected by GakuNin API")
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
        _grdm_log("PAT prompt cancelled or empty")
        _show_snack(
            page,
            "GakuNin RDM の PAT が未入力です。同期するにはトークンが必要です。",
            error=True,
        )
        return None

    grdm.set_active_token(token)

    def _check_new():
        grdm.set_active_token(token)
        return grdm.check_connection()

    try:
        ok = await _with_loading(page, "GakuNin RDM へ接続確認中…", _check_new)
    except Exception as ex:
        _grdm_log(f"connection check raised: {ex}")
        _show_snack(page, f"GakuNin RDM 接続失敗: {ex}", error=True)
        return None

    if not ok:
        _grdm_log("connection check returned False (invalid PAT or API error)")
        _show_snack(page, "GakuNin RDM 接続失敗。トークンを確認してください", error=True)
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
    """Resolve project_id/folder_id; default or re-prompt when missing/invalid."""
    cs = getattr(page, "client_storage", None)
    project_id, folder_id = resolve_grdm_destination(page.session, cs)
    raw = (project_id or "").strip()
    normalized = normalize_grdm_project_id(raw)

    if not raw:
        persist_grdm_destination(
            DEFAULT_GRDM_PROJECT_ID, folder_id, page.session, cs
        )
        _grdm_log(
            f"project_id empty; using default {DEFAULT_GRDM_PROJECT_ID}"
        )
        return DEFAULT_GRDM_PROJECT_ID, folder_id

    if normalized:
        if normalized != raw:
            persist_grdm_destination(normalized, folder_id, page.session, cs)
        return normalized, folder_id

    _grdm_log(f"project_id invalid (not an OSF node id): {raw[:40]!r}")
    while True:
        entered = await _prompt_text(
            page,
            title="GakuNin RDM プロジェクトIDが不正です",
            label="project_id",
            hint=(
                "node id（英数字5〜8文字）。プロジェクト名は不可。"
                f" 空欄なら既定 {DEFAULT_GRDM_PROJECT_ID}"
            ),
            initial=DEFAULT_GRDM_PROJECT_ID,
        )
        if not entered:
            _grdm_log("project_id re-entry cancelled")
            _show_snack(
                page,
                "GakuNin RDM の project_id が未設定です。"
                " 英数字5〜8文字の node id を入力してください"
                f"（既定: {DEFAULT_GRDM_PROJECT_ID}）。",
                error=True,
            )
            return None
        normalized = normalize_grdm_project_id(entered)
        if normalized:
            persist_grdm_destination(normalized, folder_id, page.session, cs)
            _grdm_log(f"project_id accepted after re-entry: {normalized}")
            return normalized, folder_id
        _grdm_log(f"project_id re-entry still invalid: {entered.strip()[:40]!r}")
        _show_snack(
            page,
            "project_id は英数字5〜8文字の node id です"
            f"（例: {DEFAULT_GRDM_PROJECT_ID}）。プロジェクト名は使えません。",
            error=True,
        )


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


async def _institution_for_role_upload(
    page: ft.Page, *, role_label: str
) -> Optional[str]:
    """Facility code for second/final uploads. Team YY must pick a site."""
    graded = (page.session.get("grdm_graded_institution_id") or "").strip()
    if graded and looks_like_institution_folder(graded):
        return graded

    if is_team_yy(page.session, getattr(page, "client_storage", None)):
        prompted = await _prompt_text(
            page,
            title=f"{role_label}のアップロード先施設",
            label="institution_id",
            hint="読影した施設コード（例: ARIAKE_OHANACHAYA）。TEAM_YY は不可。",
            initial="",
        )
        if not prompted:
            _grdm_log(f"upload institution missing ({role_label}, Team YY)")
            _show_snack(page, "アップロード先施設が未指定です", error=True)
            return None
        inst = normalize_institution_id(prompted)
        if not looks_like_institution_folder(inst):
            _grdm_log(
                f"upload institution invalid ({role_label}): {prompted.strip()[:40]!r}"
            )
            _show_snack(
                page,
                "施設コードが不正です。TEAM_YY ではなく参加施設コードを指定してください。",
                error=True,
            )
            return None
        return inst

    inst = _sync_institution_for_first_grader(page)
    if not inst or inst in ("UNKNOWN", TEAM_YY_INSTITUTION_ID):
        inst = _viewer_institution(page)
    return inst


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


async def run_grdm_sync(
    page: ft.Page,
    local_folder: str,
    *,
    on_status: Optional[Callable[..., None]] = None,
) -> None:
    """Upload local export folder (recursive) to role-/institution-scoped GRDM path."""
    _grdm_log(f"sync requested folder={local_folder}")
    token_cv = None
    prev_notify = getattr(page, "_grdm_sync_notify", None)
    if on_status is not None:
        bound = lambda message, error=False: on_status(
            message, error=error, busy=False
        )
        page._grdm_sync_notify = bound
        token_cv = _notify_override.set(bound)
        on_status("GakuNin RDM へ同期中…", error=False, busy=True)
    try:
        await _run_grdm_sync_body(page, local_folder)
    finally:
        page._grdm_sync_notify = prev_notify
        if token_cv is not None:
            _notify_override.reset(token_cv)


async def _run_grdm_sync_body(page: ft.Page, local_folder: str) -> None:
    folder = Path(local_folder) if local_folder else None
    if folder is None or not folder.is_dir():
        _grdm_log(f"local folder missing: {local_folder}")
        _show_snack(
            page,
            f"エクスポート先フォルダが見つかりません: {local_folder}",
            error=True,
        )
        return

    token = await ensure_grdm_token(page, write_scope_hint=True)
    if not token:
        _grdm_log("sync aborted: no PAT")
        return

    dest = await ensure_grdm_destination(page)
    if not dest:
        _grdm_log("sync aborted: no project_id")
        return
    project_id, base_folder_id = dest

    sr = is_second_reader(page.session)
    fr = is_final_reader(page.session)
    if fr:
        inst = await _institution_for_role_upload(page, role_label="最終読影結果")
        if not inst:
            return
        segment_fn = final_reader_remote_segments
        scope = "最終読影データ"
    elif sr:
        inst = await _institution_for_role_upload(page, role_label="第2リーダー結果")
        if not inst:
            return
        segment_fn = second_reader_remote_segments
        scope = "第2リーダー結果"
    else:
        inst = _sync_institution_for_first_grader(page)
        segment_fn = first_grader_remote_segments
        scope = "第1読影データ"

    try:
        segments = segment_fn(inst)
    except ValueError as ex:
        _grdm_log(f"sync rejected: {ex}")
        _show_snack(page, str(ex), error=True)
        return

    def _upload():
        grdm.set_active_token(token)
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
        _grdm_log(f"sync failed: {ex}")
        _show_snack(page, f"GakuNin RDM 同期に失敗しました: {ex}", error=True)
        return

    if count == 0:
        _grdm_log(f"sync uploaded 0 files path={'/'.join(segments)}")
        _show_snack(
            page,
            "同期対象のファイルはありません（空フォルダ）",
            error=True,
        )
    else:
        _grdm_log(
            f"sync ok n={count} project={project_id} path={'/'.join(segments)}"
        )
        _show_snack(
            page,
            f"GakuNin RDMへの同期が完了しました（{scope} / {inst} / {count}件）",
        )


async def run_grdm_download(
    page: ft.Page,
    *,
    on_complete: Optional[Callable[[str], Any]] = None,
) -> Optional[str]:
    """ACL-aware download of one institution's first-grader dataset for second readers."""
    token = await ensure_grdm_token(page, write_scope_hint=False)
    if not token:
        _grdm_log("download aborted: no PAT")
        return None

    dest = await ensure_grdm_destination(page)
    if not dest:
        _grdm_log("download aborted: no project_id")
        return None
    project_id, base_folder_id = dest

    cs = getattr(page, "client_storage", None)
    viewer_inst = _viewer_institution(page)
    central = is_team_yy(page.session, cs, institution_id=viewer_inst)

    def _list():
        grdm.set_active_token(token)
        return grdm.list_institution_folders(project_id, base_folder_id or "")

    try:
        all_datasets = await _with_loading(
            page, "利用可能な第1読影データを照会中…", _list
        )
    except Exception as ex:
        _grdm_log(f"list institution folders failed: {ex}")
        _show_snack(page, f"GakuNin RDM 一覧取得に失敗しました: {ex}", error=True)
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
        _grdm_log(f"download rejected: {msg}")
        _show_snack(page, msg, error=True)
        return None

    chosen = await _prompt_institution_dataset(page, allowed, central=central)
    if not chosen:
        _grdm_log("download cancelled: no institution selected")
        _show_snack(page, "データ選択がキャンセルされました", error=True)
        return None

    inst_name = chosen["name"]
    remote_id = chosen["id"]
    target = isolated_download_dir(project_id, inst_name)

    def _download():
        grdm.set_active_token(token)
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

    if not count:
        _show_snack(
            page,
            f"{inst_name}: ダウンロード対象ファイルがありません",
            error=True,
        )
        return None

    _show_snack(page, f"{inst_name}: {count}件を取得しました\n{target}")

    # Publish pending facility BEFORE on_complete so second_reader_output_dir
    # does not reuse a stale graded id while the queue is built.
    try:
        page.session.set("grdm_pending_institution_id", inst_name)
    except Exception:
        pass

    if on_complete is not None:
        result = on_complete(str(target))
        if asyncio.iscoroutine(result):
            result = await result
        if result is not True:
            try:
                from src.flet_ui.components.shared import session_discard

                session_discard(page.session, "grdm_pending_institution_id")
            except Exception:
                try:
                    page.session.set("grdm_pending_institution_id", "")
                except Exception:
                    pass
            _show_snack(
                page,
                f"{inst_name}: 取得はできましたが第2リーダー用スキャンに失敗しました。"
                " 施設IDは更新していません。",
                error=True,
            )
            return None

    # Commit graded facility; clear pending
    try:
        page.session.set("grdm_graded_institution_id", inst_name)
        page.session.set("grdm_pending_institution_id", "")
    except Exception:
        pass
    return str(target)


def _apply_sync_status(
    page: ft.Page,
    btn: ft.ElevatedButton,
    label: ft.Text,
    message: str,
    *,
    error: bool = False,
    busy: bool = False,
) -> None:
    label.value = message or ""
    if busy:
        btn.bgcolor = _BTN_BUSY_BG
        btn.color = _BTN_BUSY_FG
        label.color = Colors.AMBER_200
    elif error:
        btn.bgcolor = _BTN_ERR_BG
        btn.color = _BTN_ERR_FG
        label.color = Colors.RED_300
    else:
        btn.bgcolor = _BTN_OK_BG
        btn.color = _BTN_OK_FG
        label.color = Colors.GREEN_300
    try:
        page.update()
    except Exception:
        pass


def make_grdm_sync_button(page: ft.Page, get_local_folder: Callable[[], Path]) -> ft.Control:
    """Factory for the results-screen sync button + inline status (no SnackBar)."""
    btn = ft.ElevatedButton(
        "GakuNin RDMへ同期",
        icon=Icons.CLOUD_UPLOAD_ROUNDED,
        bgcolor=_BTN_IDLE_BG,
        color=_BTN_IDLE_FG,
        tooltip=(
            "ローカル保存済みフォルダを施設スコープでアップロード。"
            " 第1→{institution}/、第2→second_reading/{institution}/、"
            "最終→final_reading/{institution}/"
        ),
    )
    status = ft.Text(
        "",
        size=12,
        color=TEXT_MUTED,
        selectable=True,
        width=520,
        max_lines=3,
    )

    def _on_status(message: str, *, error: bool = False, busy: bool = False) -> None:
        _apply_sync_status(page, btn, status, message, error=error, busy=busy)

    async def _on_click(_=None):
        await run_grdm_sync(
            page, str(get_local_folder()), on_status=_on_status
        )

    btn.on_click = lambda _: page.run_task(_on_click)
    return ft.Row(
        [btn, status],
        spacing=12,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        wrap=False,
        tight=True,
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
