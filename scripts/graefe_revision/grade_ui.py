#!/usr/bin/env python3
"""DEPRECATED — use grade_server.py (local browser UI). Do not launch this Flet app.

Flet UI for blind MNV subtype grading (conservative, no auto-advance loops).
Prefer: scripts/graefe_revision/run_grade_ui.sh  →  grade_server.py

NEVER reads automated_labels.csv / grading_subset_meta.csv.

Safety (hard rules):
  - Single-instance lock file (.grade_ui.lock); refuse to start if held
  - Save ONLY on explicit "Save & Next" click (RadioGroup selection alone never saves)
  - After save/skip: advance to next ungraded AFTER current id (B00x order) — NO wrap
  - 500ms debounce after save/skip; buttons disabled while busy
  - Preview downscaled to max 400px (avoids huge base64 freeze)
  - Mutate controls in place; never rebuild RadioGroup mid-event
  - All exceptions shown in UI text; never auto-retry
  - Optional: --start-at B020

Launch (manual only — do not auto-start from agents):
  scripts/graefe_revision/run_grade_ui.sh
  scripts/graefe_revision/run_grade_ui.sh --start-at B020
  .venv/bin/python scripts/graefe_revision/grade_ui.py --start-at B017
"""

from __future__ import annotations

import argparse
import atexit
import base64
import io
import os
import sys
import time
import traceback
from pathlib import Path

import flet as ft
import pandas as pd
from PIL import Image

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import interactive_grade as ig  # noqa: E402

PREVIEWS = ig.GRADING_DIR / "previews"
LOCK_PATH = ig.GRADING_DIR / ".grade_ui.lock"
PREVIEW_MAX_PX = 400
DEBOUNCE_MS = 500

# Session-only skips (still ungraded in CSV). Never auto-cleared to re-loop.
_skipped: set[str] = set()

# CLI (set in __main__ before ft.app)
_START_AT: str | None = None


def _preview_path(blind_id: str) -> Path:
    return PREVIEWS / f"{blind_id}.png"


def _sorted_rows(grades: pd.DataFrame) -> list[pd.Series]:
    """Return rows sorted by blind_id (B001..B054 lexicographic = numeric)."""
    rows = [row for _, row in grades.iterrows()]
    rows.sort(key=lambda r: str(r["blind_id"]))
    return rows


def _next_ungraded_after(
    grades: pd.DataFrame,
    after_id: str | None,
    skip_set: set[str] | None = None,
    *,
    include_after: bool = False,
) -> pd.Series | None:
    """Next ungraded in B00x order strictly after after_id (or >= if include_after).

    NEVER wraps to the first ungraded in the file.
    """
    skip_set = skip_set or set()
    for row in _sorted_rows(grades):
        bid = str(row["blind_id"])
        if after_id is not None:
            if include_after:
                if bid < after_id:
                    continue
            else:
                if bid <= after_id:
                    continue
        if ig._is_graded(row.get("expert_subtype", "")):
            continue
        if bid in skip_set:
            continue
        return row
    return None


def _acquire_lock() -> None:
    """Refuse to start if another live grade_ui holds the lock."""
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    if LOCK_PATH.is_file():
        try:
            old_pid = int(LOCK_PATH.read_text(encoding="utf-8").strip().splitlines()[0])
        except (ValueError, OSError, IndexError):
            old_pid = None
        if old_pid is not None:
            try:
                os.kill(old_pid, 0)  # signal 0: existence check
            except OSError:
                pass  # stale lock
            else:
                raise SystemExit(
                    f"Another grade_ui instance appears running (pid {old_pid}).\n"
                    f"Lock: {LOCK_PATH}\n"
                    "If you are sure it is dead: rm "
                    f"{LOCK_PATH}"
                )
        # stale → remove
        try:
            LOCK_PATH.unlink(missing_ok=True)
        except OSError:
            pass

    LOCK_PATH.write_text(f"{os.getpid()}\n", encoding="utf-8")

    def _release() -> None:
        try:
            if LOCK_PATH.is_file():
                text = LOCK_PATH.read_text(encoding="utf-8").strip()
                if text.startswith(str(os.getpid())):
                    LOCK_PATH.unlink(missing_ok=True)
        except OSError:
            pass

    atexit.register(_release)


def _load_preview_b64(blind_id: str) -> tuple[str | None, str]:
    """Return (base64_jpeg_or_none, error_or_empty). Max edge PREVIEW_MAX_PX."""
    pp = _preview_path(blind_id)
    if not pp.is_file():
        return None, f"Preview missing: {pp} — use Open full-res"
    try:
        with Image.open(pp) as im:
            im = im.convert("RGB")
            w, h = im.size
            scale = min(1.0, PREVIEW_MAX_PX / max(w, h))
            if scale < 1.0:
                im = im.resize(
                    (max(1, int(w * scale)), max(1, int(h * scale))),
                    Image.Resampling.LANCZOS,
                )
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=75, optimize=True)
            raw = buf.getvalue()
        return base64.b64encode(raw).decode("ascii"), ""
    except Exception as exc:  # noqa: BLE001 — show in UI, never retry
        return None, f"Preview load failed: {exc}"


def main(page: ft.Page) -> None:
    page.title = "MNV Blind Grading"
    page.window.width = 780
    page.window.height = 860
    page.padding = 16
    page.theme_mode = ft.ThemeMode.LIGHT

    status_text = ft.Text("", size=16, weight=ft.FontWeight.BOLD)
    blind_text = ft.Text("", size=22, weight=ft.FontWeight.BOLD)
    stratum_text = ft.Text("", size=14, color=ft.Colors.BLUE_GREY_700)
    log_text = ft.Text("", size=13, color=ft.Colors.TEAL_800, weight=ft.FontWeight.BOLD)
    msg_text = ft.Text("", size=13, color=ft.Colors.BLUE_GREY_600)
    err_text = ft.Text("", size=13, color=ft.Colors.RED_700)

    preview = ft.Image(
        src_base64="",
        width=PREVIEW_MAX_PX,
        height=PREVIEW_MAX_PX,
        fit=ft.ImageFit.CONTAIN,
        border_radius=8,
        visible=False,
    )

    # RadioGroup: more stable than Dropdown in Flet 0.28 (no value-reset storms)
    subtype_rg = ft.RadioGroup(
        content=ft.Column(
            [ft.Radio(value=s, label=s) for s in ig.ALLOWED_SUBTYPES],
            tight=True,
            spacing=2,
        ),
        value=None,
    )

    btn_save = ft.FilledButton("Save & Next", icon=ft.Icons.SAVE)
    btn_skip = ft.OutlinedButton("Skip", icon=ft.Icons.SKIP_NEXT)
    btn_open = ft.OutlinedButton("Open full-res image", icon=ft.Icons.OPEN_IN_NEW)

    state: dict[str, object] = {
        "blind_id": None,
        "busy": False,
        "last_action_mono": 0.0,
        "preview_b64": None,
    }

    def set_busy(busy: bool) -> None:
        state["busy"] = busy
        btn_save.disabled = busy
        btn_skip.disabled = busy
        btn_open.disabled = busy
        subtype_rg.disabled = busy

    def blocked_by_debounce() -> bool:
        elapsed_ms = (time.monotonic() - float(state["last_action_mono"])) * 1000.0
        return elapsed_ms < DEBOUNCE_MS

    def mark_action() -> None:
        state["last_action_mono"] = time.monotonic()

    def refresh_status() -> None:
        grades, _ = ig._load()
        done, n = ig._progress(grades)
        if n == ig.TOTAL_EXPECTED:
            status_text.value = f"Status: {done}/{ig.TOTAL_EXPECTED}"
        else:
            status_text.value = f"Status: {done}/{n}"

    def set_preview(blind_id: str) -> None:
        b64, err = _load_preview_b64(blind_id)
        if b64 is None:
            preview.src_base64 = ""
            preview.visible = False
            state["preview_b64"] = None
            msg_text.value = err
            return
        if state.get("preview_b64") == b64:
            preview.visible = True
            msg_text.value = ""
            return
        state["preview_b64"] = b64
        preview.src_base64 = b64
        preview.visible = True
        msg_text.value = ""

    def show_case(row: pd.Series | None, grades: pd.DataFrame, manifest: pd.DataFrame) -> None:
        refresh_status()
        # Clear selection without destroying RadioGroup (mutate value only)
        subtype_rg.value = None
        err_text.value = ""
        if row is None:
            state["blind_id"] = None
            blind_text.value = "No next ungraded after current"
            stratum_text.value = ""
            preview.src_base64 = ""
            preview.visible = False
            state["preview_b64"] = None
            done, n = ig._progress(grades)
            if done >= n and n > 0:
                blind_text.value = "All graded"
                msg_text.value = f"{done}/{n} complete. Lock CSV, then run compute_agreement.py."
            else:
                remaining = [
                    str(r["blind_id"])
                    for r in _sorted_rows(grades)
                    if not ig._is_graded(r.get("expert_subtype", ""))
                ]
                msg_text.value = (
                    "No further ungraded case after current (no wrap). "
                    f"Still ungraded elsewhere: {', '.join(remaining) or '(none)'}. "
                    "Restart with --start-at if needed."
                )
            page.update()
            return

        blind_id = str(row["blind_id"])
        state["blind_id"] = blind_id
        _, mrow = ig._resolve_case(blind_id, grades, manifest)
        blind_text.value = blind_id
        stratum_text.value = f"stratum: {mrow['stratum']}"
        set_preview(blind_id)
        page.update()

    def load_current(
        after_id: str | None = None,
        *,
        include_after: bool = False,
        use_skip: bool = True,
    ) -> str | None:
        """Load next case. Returns next blind_id or None. Never wraps."""
        grades, manifest = ig._load()
        skip = _skipped if use_skip else set()
        nxt = _next_ungraded_after(
            grades, after_id=after_id, skip_set=skip, include_after=include_after
        )
        show_case(nxt, grades, manifest)
        return None if nxt is None else str(nxt["blind_id"])

    def on_save(_e: ft.ControlEvent) -> None:
        if state["busy"] or blocked_by_debounce():
            return
        blind_id = state["blind_id"]
        if not isinstance(blind_id, str) or not blind_id:
            msg_text.value = "Nothing to save."
            page.update()
            return
        selected = subtype_rg.value
        if not selected or not str(selected).strip():
            err_text.value = "Select a subtype before saving."
            msg_text.value = ""
            page.update()
            return

        set_busy(True)
        mark_action()
        page.update()
        try:
            grades, _ = ig._load()
            try:
                ig.cmd_set(grades, blind_id, str(selected), notes=None)
            except SystemExit as exc:
                err_text.value = str(exc)
                log_text.value = f"Save failed for {blind_id}"
                return
            _skipped.discard(blind_id)
            nxt_id = load_current(after_id=blind_id, include_after=False)
            if nxt_id:
                log_text.value = f"Saved {blind_id} → next {nxt_id}"
            else:
                log_text.value = f"Saved {blind_id} → (no next after {blind_id})"
            err_text.value = ""
        except Exception as exc:  # noqa: BLE001
            err_text.value = f"Save error: {exc}"
            log_text.value = traceback.format_exc(limit=3)
            # never auto-retry
        finally:
            set_busy(False)
            mark_action()
            page.update()

    def on_skip(_e: ft.ControlEvent) -> None:
        if state["busy"] or blocked_by_debounce():
            return
        blind_id = state["blind_id"]
        if not isinstance(blind_id, str) or not blind_id:
            msg_text.value = "Nothing to skip."
            page.update()
            return
        set_busy(True)
        mark_action()
        page.update()
        try:
            _skipped.add(blind_id)
            nxt_id = load_current(after_id=blind_id, include_after=False)
            if nxt_id:
                log_text.value = f"Skipped {blind_id} → next {nxt_id}"
            else:
                log_text.value = f"Skipped {blind_id} → (no next after {blind_id})"
            err_text.value = ""
        except Exception as exc:  # noqa: BLE001
            err_text.value = f"Skip error: {exc}"
            log_text.value = traceback.format_exc(limit=3)
        finally:
            set_busy(False)
            mark_action()
            page.update()

    def on_open(_e: ft.ControlEvent) -> None:
        if state["busy"] or blocked_by_debounce():
            return
        blind_id = state["blind_id"]
        if not isinstance(blind_id, str) or not blind_id:
            msg_text.value = "No case loaded."
            page.update()
            return
        set_busy(True)
        page.update()
        try:
            grades, manifest = ig._load()
            try:
                ig.cmd_open(grades, manifest, blind_id)
                msg_text.value = f"Opened full-res: {blind_id}"
                err_text.value = ""
            except SystemExit as exc:
                err_text.value = str(exc)
        except Exception as exc:  # noqa: BLE001
            err_text.value = f"Open error: {exc}"
        finally:
            set_busy(False)
            page.update()

    btn_save.on_click = on_save
    btn_skip.on_click = on_skip
    btn_open.on_click = on_open

    page.add(
        ft.Column(
            [
                ft.Row(
                    [
                        status_text,
                        ft.Text("Blind grading — no automated labels", size=12, italic=True),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Divider(),
                blind_text,
                stratum_text,
                ft.Container(
                    content=preview,
                    alignment=ft.alignment.center,
                    bgcolor=ft.Colors.GREY_200,
                    border_radius=8,
                    padding=8,
                ),
                ft.Text("MNV subtype (select one, then Save & Next):", size=13),
                subtype_rg,
                ft.Row([btn_save, btn_skip, btn_open], spacing=12),
                log_text,
                msg_text,
                err_text,
            ],
            spacing=10,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )
    )

    # Initial load: --start-at X → first ungraded with id >= X; else first ungraded overall.
    try:
        if _START_AT:
            nxt = load_current(after_id=_START_AT, include_after=True)
            log_text.value = (
                f"Start-at {_START_AT} → {nxt}" if nxt else f"Start-at {_START_AT} → (none)"
            )
            page.update()
        else:
            nxt = load_current(after_id=None)
            if nxt:
                log_text.value = f"Started at first ungraded → {nxt}"
                page.update()
    except Exception as exc:  # noqa: BLE001
        err_text.value = f"Startup error: {exc}"
        log_text.value = traceback.format_exc(limit=5)
        page.update()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Blind MNV subtype grading UI (Flet)")
    p.add_argument(
        "--start-at",
        metavar="B0xx",
        default=None,
        help="Resume at first ungraded blind_id >= this id (e.g. B020)",
    )
    return p.parse_args(argv)


if __name__ == "__main__":
    print(
        "DEPRECATED — use grade_server.py / run_grade_ui.sh (browser UI).\n"
        "Continuing with Flet anyway…",
        file=sys.stderr,
    )
    args = _parse_args()
    if args.start_at is not None:
        start = str(args.start_at).strip().upper()
        if not start.startswith("B") or len(start) < 2:
            raise SystemExit(f"Invalid --start-at {args.start_at!r}; expected e.g. B020")
        _START_AT = start
    _acquire_lock()
    ft.app(target=main)
