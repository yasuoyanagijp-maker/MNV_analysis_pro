#!/usr/bin/env python3
"""Local browser UI for regrading UI-暴走 / discordance cases (stdlib HTTP).

Cycles only through documentation/graefe_revision/grading/regrade_queue.csv.
Shows preview + current expert label + automated label (correction mode, not blind).
Saves update BOTH expert_grades_blind.csv and expert_grades_locked.csv.
Logs old→new to regrade_log.csv.

Usage:
  .venv/bin/python scripts/graefe_revision/regrade_server.py
  .venv/bin/python scripts/graefe_revision/regrade_server.py --port 8766
  scripts/graefe_revision/run_regrade_ui.sh
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import threading
import traceback
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import pandas as pd

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import interactive_grade as ig  # noqa: E402

GRADING_DIR = ig.GRADING_DIR
QUEUE = GRADING_DIR / "regrade_queue.csv"
LOG = GRADING_DIR / "regrade_log.csv"
LOCKED = GRADING_DIR / "expert_grades_locked.csv"
BLIND = ig.GRADES
PREVIEWS = GRADING_DIR / "previews"
PREVIEW_MAX_PX = 400
DEFAULT_PORT = 8766

_skipped: set[str] = set()
_confirmed: set[str] = set()  # session: kept same label or saved
_lock = threading.Lock()
_START_AT: str | None = None

try:
    from PIL import Image

    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False


def _load_queue() -> pd.DataFrame:
    if not QUEUE.is_file():
        raise SystemExit(f"Missing queue: {QUEUE}")
    q = pd.read_csv(QUEUE, dtype=str).fillna("")
    if "blind_id" not in q.columns:
        raise SystemExit("regrade_queue.csv needs blind_id column")
    return q


def _sorted_queue_ids(queue: pd.DataFrame) -> list[str]:
    if "queue_order" in queue.columns:
        q = queue.copy()
        q["_ord"] = pd.to_numeric(q["queue_order"], errors="coerce")
        q = q.sort_values(["_ord", "blind_id"], kind="mergesort")
        return [str(b) for b in q["blind_id"].tolist()]
    return sorted(str(b) for b in queue["blind_id"].tolist())


def _queue_row(queue: pd.DataFrame, blind_id: str) -> pd.Series:
    rows = queue.loc[queue["blind_id"] == blind_id]
    if rows.empty:
        raise SystemExit(f"{blind_id} not in regrade_queue")
    return rows.iloc[0]


def _load_locked() -> pd.DataFrame:
    return pd.read_csv(LOCKED, dtype=str).fillna("")


def _progress(queue: pd.DataFrame) -> tuple[int, int]:
    ids = _sorted_queue_ids(queue)
    n = len(ids)
    done = sum(1 for b in ids if b in _confirmed)
    return done, n


def _next_in_queue(
    queue: pd.DataFrame,
    after_id: str | None,
    *,
    include_after: bool = False,
) -> str | None:
    """Next queue id not yet confirmed this session (and not skipped). No wrap.

    Advances by *queue_order* position (not lexicographic blind_id), so e.g. after
    B048 the next case is B002 when that is the next row in regrade_queue.csv.
    """
    ids = _sorted_queue_ids(queue)
    if after_id is None:
        start_idx = 0
    elif after_id in ids:
        idx = ids.index(after_id)
        start_idx = idx if include_after else idx + 1
    else:
        # --start-at / ?start_at= for an id not in this queue: first id >= token
        # in queue order by blind_id string (stable fallback).
        start_idx = next((i for i, b in enumerate(ids) if b >= after_id), len(ids))
    for bid in ids[start_idx:]:
        if bid in _confirmed or bid in _skipped:
            continue
        return bid
    return None


def _resolve_start(queue: pd.DataFrame, start_at: str | None) -> str | None:
    if start_at:
        return _next_in_queue(queue, after_id=start_at, include_after=True)
    return _next_in_queue(queue, after_id=None)


def _case_payload(blind_id: str | None, queue: pd.DataFrame) -> dict[str, Any]:
    done, n = _progress(queue)
    remaining = [
        b
        for b in _sorted_queue_ids(queue)
        if b not in _confirmed and b not in _skipped
    ]
    if blind_id is None:
        return {
            "blind_id": None,
            "stratum": None,
            "expert_subtype": None,
            "automated_subtype": None,
            "done": done,
            "total": n,
            "done_label": f"{done}/{n}",
            "message": (
                f"Queue finished ({done}/{n} confirmed this session). "
                "Re-run κ when ready:\n"
                "  .venv/bin/python scripts/graefe_revision/compute_agreement.py"
                if done >= n and n > 0
                else (
                    "No further queue case after current (no wrap). "
                    f"Remaining: {', '.join(remaining) or '(none)'}. "
                    "Restart with --start-at / ?start_at= if needed."
                )
            ),
            "subtypes": list(ig.ALLOWED_SUBTYPES),
            "remaining": remaining,
        }

    qrow = _queue_row(queue, blind_id)
    grades, _ = ig._load()
    locked = _load_locked()
    grow = grades.loc[grades["blind_id"] == blind_id]
    lrow = locked.loc[locked["blind_id"] == blind_id]
    expert = (
        str(grow.iloc[0]["expert_subtype"]).strip()
        if not grow.empty
        else str(qrow.get("expert_subtype", "")).strip()
    )
    if not grow.empty and not lrow.empty:
        le = str(lrow.iloc[0]["expert_subtype"]).strip()
        if le and le != expert:
            expert = le  # prefer locked if diverge (should not happen)

    return {
        "blind_id": blind_id,
        "stratum": str(qrow.get("stratum", "")),
        "file_name": str(qrow.get("file_name", "")),
        "discordance": str(qrow.get("discordance", "")),
        "expert_subtype": expert,
        "automated_subtype": str(qrow.get("automated_subtype", "")),
        "done": done,
        "total": n,
        "done_label": f"{done}/{n}",
        "message": "",
        "subtypes": list(ig.ALLOWED_SUBTYPES),
        "preview_url": f"/preview/{blind_id}",
        "full_url": f"/full/{blind_id}",
        "remaining": remaining,
    }


def _append_log(
    blind_id: str,
    old: str,
    new: str,
    automated: str,
    action: str,
    notes: str = "",
) -> None:
    row = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "blind_id": blind_id,
        "old_expert_subtype": old,
        "new_expert_subtype": new,
        "automated_subtype": automated,
        "action": action,
        "notes": notes,
    }
    if LOG.is_file():
        log_df = pd.read_csv(LOG, dtype=str).fillna("")
    else:
        log_df = pd.DataFrame(columns=list(row.keys()))
    log_df = pd.concat([log_df, pd.DataFrame([row])], ignore_index=True)
    log_df.to_csv(LOG, index=False)


def _update_both_csvs(blind_id: str, subtype: str) -> str:
    """Update blind + locked CSVs. Returns previous expert subtype."""
    subtype = ig._normalize_subtype(subtype)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    grades = pd.read_csv(BLIND, dtype=str).fillna("")
    idx = grades.index[grades["blind_id"] == blind_id]
    if len(idx) == 0:
        raise SystemExit(f"Unknown blind_id in blind CSV: {blind_id}")
    i = idx[0]
    prev = str(grades.at[i, "expert_subtype"]).strip()
    grades.at[i, "expert_subtype"] = subtype
    grades.at[i, "grader"] = grades.at[i, "grader"] or "YY"
    grades.at[i, "graded_at"] = now
    grades.to_csv(BLIND, index=False)

    locked = _load_locked()
    lidx = locked.index[locked["blind_id"] == blind_id]
    if len(lidx) == 0:
        raise SystemExit(f"Unknown blind_id in locked CSV: {blind_id}")
    li = lidx[0]
    locked.at[li, "expert_subtype"] = subtype
    locked.at[li, "grader"] = locked.at[li, "grader"] or "YY"
    locked.at[li, "graded_at"] = now
    locked.to_csv(LOCKED, index=False)

    return prev


def _preview_path(blind_id: str) -> Path:
    return PREVIEWS / f"{blind_id}.png"


def _source_image_path(blind_id: str, queue: pd.DataFrame) -> Path | None:
    pp = _preview_path(blind_id)
    if pp.is_file():
        return pp
    try:
        qrow = _queue_row(queue, blind_id)
        path = Path(str(qrow.get("image_path", "")))
        return path if path.is_file() else None
    except SystemExit:
        return None


def _make_preview_jpeg(blind_id: str, queue: pd.DataFrame) -> tuple[bytes | None, str]:
    src = _source_image_path(blind_id, queue)
    if src is None:
        return None, f"Preview/source missing for {blind_id}"
    if not _HAS_PIL:
        try:
            raw = src.read_bytes()
        except OSError as exc:
            return None, f"Preview read failed: {exc}"
        suffix = src.suffix.lower()
        ctype = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".tif": "image/tiff",
            ".tiff": "image/tiff",
        }.get(suffix, "application/octet-stream")
        return raw, ctype
    try:
        with Image.open(src) as im:
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
            return buf.getvalue(), "image/jpeg"
    except Exception as exc:  # noqa: BLE001
        return None, f"Preview load failed: {exc}"


HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>MNV Regrade (discordance)</title>
<style>
  :root { color-scheme: light; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
  body { margin: 0; padding: 20px; background: #f5f6f8; color: #1a1a1a; }
  main { max-width: 720px; margin: 0 auto; background: #fff; border-radius: 10px;
         padding: 20px 24px 28px; box-shadow: 0 1px 4px rgba(0,0,0,.08); }
  h1 { font-size: 1.15rem; margin: 0 0 4px; }
  .meta { color: #555; font-size: .95rem; margin-bottom: 8px; }
  .status { font-weight: 700; font-size: 1.05rem; }
  .hint { font-size: .8rem; color: #777; font-style: italic; }
  .labels { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 10px 0 4px; }
  .label-box { background: #f0f4f8; border-radius: 8px; padding: 10px 12px; }
  .label-box.auto { background: #fff8e6; border: 1px solid #f0d78c; }
  .label-box .k { font-size: .75rem; color: #666; text-transform: uppercase; letter-spacing: .03em; }
  .label-box .v { font-size: 1.05rem; font-weight: 700; margin-top: 2px; }
  #preview-wrap { background: #e8e8e8; border-radius: 8px; padding: 10px;
                  text-align: center; min-height: 120px; margin: 12px 0; }
  #preview { max-width: 400px; max-height: 400px; width: auto; height: auto; }
  label { display: block; margin: 10px 0 6px; font-size: .95rem; }
  select { font-size: 1rem; padding: 8px 10px; min-width: 220px; }
  .row { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 14px; align-items: center; }
  button, .linkbtn { font-size: .95rem; padding: 8px 14px; border-radius: 6px; cursor: pointer;
                     border: 1px solid #ccc; background: #fafafa; text-decoration: none; color: inherit; }
  button.primary { background: #1a73e8; color: #fff; border-color: #1a73e8; font-weight: 600; }
  button.keep { background: #0d7377; color: #fff; border-color: #0d7377; font-weight: 600; }
  button:disabled { opacity: .5; cursor: not-allowed; }
  #log { margin-top: 12px; font-weight: 600; color: #0d7377; min-height: 1.2em; }
  #msg { margin-top: 6px; color: #555; font-size: .9rem; min-height: 1.2em; white-space: pre-wrap; }
  #err { margin-top: 6px; color: #b00020; font-size: .9rem; min-height: 1.2em; white-space: pre-wrap; }
</style>
</head>
<body>
<main>
  <div style="display:flex;justify-content:space-between;align-items:baseline;gap:12px;">
    <div class="status" id="status">Status: —</div>
    <div class="hint">Regrade — automated label shown</div>
  </div>
  <h1 id="blind">Loading…</h1>
  <div class="meta" id="stratum"></div>
  <div class="labels">
    <div class="label-box">
      <div class="k">Current expert</div>
      <div class="v" id="expert">—</div>
    </div>
    <div class="label-box auto">
      <div class="k">Automated</div>
      <div class="v" id="auto">—</div>
    </div>
  </div>
  <div id="preview-wrap"><img id="preview" alt="preview" hidden/></div>
  <label for="subtype">New expert subtype (or Keep current):</label>
  <select id="subtype"><option value="">— select —</option></select>
  <div class="row">
    <button class="primary" id="btn-save" type="button">Save &amp; Next</button>
    <button class="keep" id="btn-keep" type="button">Keep &amp; Next</button>
    <button id="btn-skip" type="button">Skip</button>
    <a class="linkbtn" id="btn-open" href="#" target="_blank" rel="noopener">Open full-res</a>
  </div>
  <div id="log"></div>
  <div id="msg"></div>
  <div id="err"></div>
</main>
<script>
(function () {
  const params = new URLSearchParams(location.search);
  const startAt = (params.get("start_at") || "").trim().toUpperCase() || null;
  let currentId = null;
  let currentExpert = null;
  let busy = false;

  const el = (id) => document.getElementById(id);
  const status = el("status");
  const blind = el("blind");
  const stratum = el("stratum");
  const expert = el("expert");
  const auto = el("auto");
  const preview = el("preview");
  const subtype = el("subtype");
  const log = el("log");
  const msg = el("msg");
  const err = el("err");
  const btnSave = el("btn-save");
  const btnKeep = el("btn-keep");
  const btnSkip = el("btn-skip");
  const btnOpen = el("btn-open");

  function setBusy(v) {
    busy = v;
    btnSave.disabled = v;
    btnKeep.disabled = v;
    btnSkip.disabled = v;
    subtype.disabled = v;
  }

  function fillSubtypes(list, preselect) {
    subtype.innerHTML = '<option value="">— select —</option>';
    (list || []).forEach((s) => {
      const o = document.createElement("option");
      o.value = s;
      o.textContent = s;
      subtype.appendChild(o);
    });
    subtype.value = (preselect && [...subtype.options].some((o) => o.value === preselect))
      ? preselect : "";
  }

  function showCase(data) {
    status.textContent = "Status: " + (data.done_label || "—");
    err.textContent = "";
    if (!data.blind_id) {
      currentId = null;
      currentExpert = null;
      blind.textContent = "Queue done";
      stratum.textContent = "";
      expert.textContent = "—";
      auto.textContent = "—";
      preview.hidden = true;
      preview.removeAttribute("src");
      btnOpen.removeAttribute("href");
      fillSubtypes(data.subtypes, "");
      msg.textContent = data.message || "";
      return;
    }
    currentId = data.blind_id;
    currentExpert = data.expert_subtype || "";
    blind.textContent = data.blind_id;
    stratum.textContent = "stratum: " + (data.stratum || "")
      + (data.discordance ? "  ·  " + data.discordance : "");
    expert.textContent = data.expert_subtype || "—";
    auto.textContent = data.automated_subtype || "—";
    msg.textContent = data.message || "";
    fillSubtypes(data.subtypes, data.expert_subtype || "");
    preview.hidden = false;
    preview.src = data.preview_url + "?t=" + Date.now();
    btnOpen.href = data.full_url;
  }

  async function api(path, opts) {
    const res = await fetch(path, opts);
    const text = await res.text();
    let data;
    try { data = JSON.parse(text); } catch (_) {
      throw new Error(res.status + " " + text.slice(0, 200));
    }
    if (!res.ok) {
      throw new Error(data.error || ("HTTP " + res.status));
    }
    return data;
  }

  function netErr(e) {
    const m = String(e && e.message ? e.message : e);
    // Safari: "Load failed"; Chromium: "Failed to fetch"
    if (m === "Load failed" || m === "Failed to fetch" || /NetworkError/i.test(m)) {
      return "Cannot reach regrade server at " + location.origin
        + " — start: scripts/graefe_revision/run_regrade_ui.sh";
    }
    return m;
  }

  async function loadCurrent() {
    setBusy(true);
    try {
      const q = startAt ? ("?start_at=" + encodeURIComponent(startAt)) : "";
      const data = await api("/api/current" + q);
      showCase(data);
      log.textContent = data.blind_id
        ? ("Loaded " + data.blind_id)
        : (data.message || "No case");
    } catch (e) {
      err.textContent = netErr(e);
    } finally {
      setBusy(false);
    }
  }

  async function onSave(keep) {
    if (busy) return;
    if (!currentId) { msg.textContent = "Nothing to save."; return; }
    const sel = keep ? (currentExpert || "") : subtype.value;
    if (!sel) { err.textContent = "Select a subtype before saving."; return; }
    setBusy(true);
    err.textContent = "";
    try {
      const data = await api("/api/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          blind_id: currentId,
          subtype: sel,
          keep: !!keep,
        }),
      });
      const saved = currentId;
      const changed = data.changed;
      showCase(data.next || data);
      log.textContent = (changed
          ? ("Changed " + saved + ": " + data.old_subtype + " → " + data.subtype)
          : ("Kept " + saved + " as " + data.subtype))
        + (data.next && data.next.blind_id
            ? (" → next " + data.next.blind_id)
            : (" → (no next after " + saved + ")"));
    } catch (e) {
      err.textContent = netErr(e);
      log.textContent = "Save failed for " + currentId;
    } finally {
      setBusy(false);
    }
  }

  async function onSkip() {
    if (busy) return;
    if (!currentId) { msg.textContent = "Nothing to skip."; return; }
    setBusy(true);
    err.textContent = "";
    try {
      const data = await api("/api/skip", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ blind_id: currentId }),
      });
      const skipped = currentId;
      showCase(data.next || data);
      log.textContent = data.next && data.next.blind_id
        ? ("Skipped " + skipped + " → next " + data.next.blind_id)
        : ("Skipped " + skipped + " → (no next after " + skipped + ")");
    } catch (e) {
      err.textContent = netErr(e);
    } finally {
      setBusy(false);
    }
  }

  btnSave.addEventListener("click", () => onSave(false));
  btnKeep.addEventListener("click", () => onSave(true));
  btnSkip.addEventListener("click", onSkip);
  loadCurrent();
})();
</script>
</body>
</html>
"""


class RegradeHandler(BaseHTTPRequestHandler):
    server_version = "RegradeServer/1.0"

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj: dict) -> None:
        raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._send(code, raw, "application/json; charset=utf-8")

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError("JSON body must be an object")
        return data

    def do_GET(self) -> None:  # noqa: N802
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            qs = parse_qs(parsed.query)

            if path in ("/", "/index.html"):
                body = HTML_PAGE.encode("utf-8")
                self._send(200, body, "text/html; charset=utf-8")
                return

            if path == "/api/current":
                start = (qs.get("start_at") or [None])[0]
                if start:
                    start = str(start).strip().upper()
                elif _START_AT:
                    start = _START_AT
                with _lock:
                    queue = _load_queue()
                    bid = _resolve_start(queue, start)
                    self._json(200, _case_payload(bid, queue))
                return

            if path.startswith("/preview/"):
                blind_id = path[len("/preview/") :].strip("/").upper()
                with _lock:
                    queue = _load_queue()
                    data, ctype_or_err = _make_preview_jpeg(blind_id, queue)
                if data is None:
                    self._json(404, {"error": ctype_or_err})
                    return
                ctype = ctype_or_err if ctype_or_err.startswith("image/") else "image/jpeg"
                self._send(200, data, ctype)
                return

            if path.startswith("/full/"):
                blind_id = path[len("/full/") :].strip("/").upper()
                with _lock:
                    queue = _load_queue()
                    try:
                        qrow = _queue_row(queue, blind_id)
                    except SystemExit as exc:
                        self._json(404, {"error": str(exc)})
                        return
                    image_path = Path(str(qrow.get("image_path", "")))
                if not image_path.is_file():
                    # fallback via manifest
                    grades, manifest = ig._load()
                    try:
                        _, mrow = ig._resolve_case(blind_id, grades, manifest)
                        image_path = Path(str(mrow["image_path"]))
                    except SystemExit as exc:
                        self._json(404, {"error": str(exc)})
                        return
                if not image_path.is_file():
                    self._json(404, {"error": f"Image missing: {image_path}"})
                    return
                raw = image_path.read_bytes()
                suffix = image_path.suffix.lower()
                ctype = {
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".png": "image/png",
                    ".tif": "image/tiff",
                    ".tiff": "image/tiff",
                }.get(suffix, "application/octet-stream")
                self._send(200, raw, ctype)
                return

            self._json(404, {"error": f"Not found: {path}"})
        except Exception as exc:  # noqa: BLE001
            self._json(500, {"error": str(exc), "trace": traceback.format_exc(limit=3)})

    def do_POST(self) -> None:  # noqa: N802
        try:
            parsed = urlparse(self.path)
            path = parsed.path

            if path == "/api/save":
                body = self._read_json()
                blind_id = str(body.get("blind_id", "")).strip().upper()
                subtype = str(body.get("subtype", "")).strip()
                keep = bool(body.get("keep", False))
                if not blind_id or not subtype:
                    self._json(400, {"error": "blind_id and subtype required"})
                    return
                with _lock:
                    queue = _load_queue()
                    if blind_id not in set(_sorted_queue_ids(queue)):
                        self._json(400, {"error": f"{blind_id} not in regrade_queue"})
                        return
                    qrow = _queue_row(queue, blind_id)
                    automated = str(qrow.get("automated_subtype", ""))
                    try:
                        prev = _update_both_csvs(blind_id, subtype)
                    except SystemExit as exc:
                        self._json(400, {"error": str(exc)})
                        return
                    changed = prev != ig._normalize_subtype(subtype)
                    action = "keep" if keep and not changed else ("change" if changed else "confirm")
                    _append_log(blind_id, prev, ig._normalize_subtype(subtype), automated, action)
                    _skipped.discard(blind_id)
                    _confirmed.add(blind_id)
                    nxt = _next_in_queue(queue, after_id=blind_id, include_after=False)
                    self._json(
                        200,
                        {
                            "ok": True,
                            "saved": blind_id,
                            "old_subtype": prev,
                            "subtype": ig._normalize_subtype(subtype),
                            "changed": changed,
                            "next": _case_payload(nxt, queue),
                        },
                    )
                return

            if path == "/api/skip":
                body = self._read_json()
                blind_id = str(body.get("blind_id", "")).strip().upper()
                if not blind_id:
                    self._json(400, {"error": "blind_id required"})
                    return
                with _lock:
                    queue = _load_queue()
                    qrow = _queue_row(queue, blind_id) if blind_id in set(_sorted_queue_ids(queue)) else None
                    automated = str(qrow.get("automated_subtype", "")) if qrow is not None else ""
                    expert = str(qrow.get("expert_subtype", "")) if qrow is not None else ""
                    _append_log(blind_id, expert, expert, automated, "skip")
                    _skipped.add(blind_id)
                    nxt = _next_in_queue(queue, after_id=blind_id, include_after=False)
                    self._json(
                        200,
                        {
                            "ok": True,
                            "skipped": blind_id,
                            "next": _case_payload(nxt, queue),
                        },
                    )
                return

            self._json(404, {"error": f"Not found: {path}"})
        except ValueError as exc:
            self._json(400, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            self._json(500, {"error": str(exc), "trace": traceback.format_exc(limit=3)})


def main() -> None:
    global _START_AT
    parser = argparse.ArgumentParser(description="MNV discordance regrade — local browser server")
    parser.add_argument(
        "--start-at",
        metavar="B0xx",
        default=None,
        help="Resume at first queue blind_id >= this id",
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Listen port (default 8766)")
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Do not open the browser automatically",
    )
    args = parser.parse_args()

    if args.start_at is not None:
        start = str(args.start_at).strip().upper()
        if not start.startswith("B") or len(start) < 2:
            raise SystemExit(f"Invalid --start-at {args.start_at!r}; expected e.g. B020")
        _START_AT = start

    queue = _load_queue()
    bid = _resolve_start(queue, _START_AT)
    done, n = _progress(queue)

    host = "127.0.0.1"
    port = int(args.port)
    q = f"?start_at={_START_AT}" if _START_AT else ""
    url = f"http://{host}:{port}/{q}"

    print(f"Queue: {QUEUE}")
    print(f"Primary filter (expert=Glomerular & auto∈{{Dead tree,Tree in bud}}): see queue note")
    print(f"Queue size: {n}  (session confirmed: {done})")
    print(f"Initial case: {bid or '(none)'}")
    print(f"Blind IDs: {', '.join(_sorted_queue_ids(queue))}")
    print(f"Serving on {url}")
    print("After regrade, recompute κ with:")
    print("  .venv/bin/python scripts/graefe_revision/compute_agreement.py")
    print("Press Ctrl+C to stop.")

    httpd = HTTPServer((host, port), RegradeHandler)

    if not args.no_open:
        import subprocess
        import time
        import webbrowser

        def _open() -> None:
            time.sleep(0.35)
            try:
                webbrowser.open(url)
            except Exception:
                subprocess.run(["open", url], check=False)

        threading.Thread(target=_open, daemon=True).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
