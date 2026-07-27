#!/usr/bin/env python3
"""Local browser UI for blind MNV subtype grading (stdlib HTTP — no Flet).

NEVER reads automated_labels.csv / grading_subset_meta.csv.

Usage:
  .venv/bin/python scripts/graefe_revision/grade_server.py
  .venv/bin/python scripts/graefe_revision/grade_server.py --start-at B017 --port 8765
  scripts/graefe_revision/run_grade_ui.sh --start-at B017
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import interactive_grade as ig  # noqa: E402

PREVIEWS = ig.GRADING_DIR / "previews"
PREVIEW_MAX_PX = 400
DEFAULT_PORT = 8765

# Session-only skips (still ungraded in CSV). Never wrap-cleared.
_skipped: set[str] = set()
_lock = threading.Lock()
_START_AT: str | None = None

try:
    from PIL import Image

    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False


def _preview_path(blind_id: str) -> Path:
    return PREVIEWS / f"{blind_id}.png"


def _sorted_rows(grades) -> list:
    rows = [row for _, row in grades.iterrows()]
    rows.sort(key=lambda r: str(r["blind_id"]))
    return rows


def _next_ungraded_after(
    grades,
    after_id: str | None,
    skip_set: set[str] | None = None,
    *,
    include_after: bool = False,
):
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


def _case_payload(row, grades, manifest) -> dict[str, Any]:
    done, n = ig._progress(grades)
    if row is None:
        remaining = [
            str(r["blind_id"])
            for r in _sorted_rows(grades)
            if not ig._is_graded(r.get("expert_subtype", ""))
        ]
        return {
            "blind_id": None,
            "stratum": None,
            "done": done,
            "total": n,
            "done_label": f"{done}/{n}",
            "message": (
                f"All {n} graded. Lock CSV, then run compute_agreement.py."
                if done >= n and n > 0
                else (
                    "No further ungraded case after current (no wrap). "
                    f"Still ungraded elsewhere: {', '.join(remaining) or '(none)'}. "
                    "Restart with --start-at / ?start_at= if needed."
                )
            ),
            "subtypes": list(ig.ALLOWED_SUBTYPES),
            "remaining": remaining,
        }

    blind_id = str(row["blind_id"])
    _, mrow = ig._resolve_case(blind_id, grades, manifest)
    return {
        "blind_id": blind_id,
        "stratum": str(mrow["stratum"]),
        "file_name": str(mrow.get("file_name", "")),
        "done": done,
        "total": n,
        "done_label": f"{done}/{n}",
        "message": "",
        "subtypes": list(ig.ALLOWED_SUBTYPES),
        "preview_url": f"/preview/{blind_id}",
        "full_url": f"/full/{blind_id}",
    }


def _resolve_start(grades, start_at: str | None):
    if start_at:
        return _next_ungraded_after(
            grades, after_id=start_at, skip_set=_skipped, include_after=True
        )
    return _next_ungraded_after(grades, after_id=None, skip_set=_skipped)


def _source_image_path(blind_id: str) -> Path | None:
    """Prefer cached preview PNG; else full-res from manifest."""
    pp = _preview_path(blind_id)
    if pp.is_file():
        return pp
    try:
        grades, manifest = ig._load()
        _, mrow = ig._resolve_case(blind_id, grades, manifest)
        path = Path(str(mrow["image_path"]))
        return path if path.is_file() else None
    except SystemExit:
        return None


def _make_preview_jpeg(blind_id: str) -> tuple[bytes | None, str]:
    src = _source_image_path(blind_id)
    if src is None:
        return None, f"Preview/source missing for {blind_id}"
    if not _HAS_PIL:
        # Fallback: serve file bytes as-is when we cannot resize
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
<title>MNV Blind Grading</title>
<style>
  :root { color-scheme: light; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
  body { margin: 0; padding: 20px; background: #f5f6f8; color: #1a1a1a; }
  main { max-width: 720px; margin: 0 auto; background: #fff; border-radius: 10px;
         padding: 20px 24px 28px; box-shadow: 0 1px 4px rgba(0,0,0,.08); }
  h1 { font-size: 1.15rem; margin: 0 0 4px; }
  .meta { color: #555; font-size: .95rem; margin-bottom: 12px; }
  .status { font-weight: 700; font-size: 1.05rem; }
  .hint { font-size: .8rem; color: #777; font-style: italic; }
  #preview-wrap { background: #e8e8e8; border-radius: 8px; padding: 10px;
                  text-align: center; min-height: 120px; margin: 12px 0; }
  #preview { max-width: 400px; max-height: 400px; width: auto; height: auto; }
  label { display: block; margin: 10px 0 6px; font-size: .95rem; }
  select { font-size: 1rem; padding: 8px 10px; min-width: 220px; }
  .row { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 14px; align-items: center; }
  button, .linkbtn { font-size: .95rem; padding: 8px 14px; border-radius: 6px; cursor: pointer;
                     border: 1px solid #ccc; background: #fafafa; text-decoration: none; color: inherit; }
  button.primary { background: #1a73e8; color: #fff; border-color: #1a73e8; font-weight: 600; }
  button:disabled { opacity: .5; cursor: not-allowed; }
  #log { margin-top: 12px; font-weight: 600; color: #0d7377; min-height: 1.2em; }
  #msg { margin-top: 6px; color: #555; font-size: .9rem; min-height: 1.2em; }
  #err { margin-top: 6px; color: #b00020; font-size: .9rem; min-height: 1.2em; white-space: pre-wrap; }
</style>
</head>
<body>
<main>
  <div style="display:flex;justify-content:space-between;align-items:baseline;gap:12px;">
    <div class="status" id="status">Status: —</div>
    <div class="hint">Blind grading — no automated labels</div>
  </div>
  <h1 id="blind">Loading…</h1>
  <div class="meta" id="stratum"></div>
  <div id="preview-wrap"><img id="preview" alt="preview" hidden/></div>
  <label for="subtype">MNV subtype (select one, then Save &amp; Next):</label>
  <select id="subtype"><option value="">— select —</option></select>
  <div class="row">
    <button class="primary" id="btn-save" type="button">Save &amp; Next</button>
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
  let busy = false;

  const el = (id) => document.getElementById(id);
  const status = el("status");
  const blind = el("blind");
  const stratum = el("stratum");
  const preview = el("preview");
  const subtype = el("subtype");
  const log = el("log");
  const msg = el("msg");
  const err = el("err");
  const btnSave = el("btn-save");
  const btnSkip = el("btn-skip");
  const btnOpen = el("btn-open");

  function setBusy(v) {
    busy = v;
    btnSave.disabled = v;
    btnSkip.disabled = v;
    subtype.disabled = v;
  }

  function fillSubtypes(list) {
    const keep = subtype.value;
    subtype.innerHTML = '<option value="">— select —</option>';
    (list || []).forEach((s) => {
      const o = document.createElement("option");
      o.value = s;
      o.textContent = s;
      subtype.appendChild(o);
    });
    subtype.value = "";
    if (keep && [...subtype.options].some((o) => o.value === keep)) {
      /* intentionally clear after navigation */
    }
  }

  function showCase(data) {
    status.textContent = "Status: " + (data.done_label || "—");
    fillSubtypes(data.subtypes);
    err.textContent = "";
    if (!data.blind_id) {
      currentId = null;
      blind.textContent = data.message && data.message.indexOf("All") === 0
        ? "All graded" : "No next ungraded after current";
      stratum.textContent = "";
      preview.hidden = true;
      preview.removeAttribute("src");
      btnOpen.removeAttribute("href");
      msg.textContent = data.message || "";
      return;
    }
    currentId = data.blind_id;
    blind.textContent = data.blind_id;
    stratum.textContent = "stratum: " + (data.stratum || "");
    msg.textContent = data.message || "";
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
      err.textContent = String(e.message || e);
    } finally {
      setBusy(false);
    }
  }

  async function onSave() {
    if (busy) return;
    if (!currentId) { msg.textContent = "Nothing to save."; return; }
    const sel = subtype.value;
    if (!sel) { err.textContent = "Select a subtype before saving."; return; }
    setBusy(true);
    err.textContent = "";
    try {
      const data = await api("/api/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ blind_id: currentId, subtype: sel }),
      });
      const saved = currentId;
      showCase(data.next || data);
      log.textContent = data.next && data.next.blind_id
        ? ("Saved " + saved + " → next " + data.next.blind_id)
        : ("Saved " + saved + " → (no next after " + saved + ")");
    } catch (e) {
      err.textContent = String(e.message || e);
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
      err.textContent = String(e.message || e);
    } finally {
      setBusy(false);
    }
  }

  btnSave.addEventListener("click", onSave);
  btnSkip.addEventListener("click", onSkip);
  loadCurrent();
})();
</script>
</body>
</html>
"""


class GradeHandler(BaseHTTPRequestHandler):
    server_version = "GradeServer/1.0"

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
                    grades, manifest = ig._load()
                    row = _resolve_start(grades, start)
                    self._json(200, _case_payload(row, grades, manifest))
                return

            if path.startswith("/preview/"):
                blind_id = path[len("/preview/") :].strip("/").upper()
                data, ctype_or_err = _make_preview_jpeg(blind_id)
                if data is None:
                    self._json(404, {"error": ctype_or_err})
                    return
                ctype = ctype_or_err if ctype_or_err.startswith("image/") else "image/jpeg"
                self._send(200, data, ctype)
                return

            if path.startswith("/full/"):
                blind_id = path[len("/full/") :].strip("/").upper()
                with _lock:
                    grades, manifest = ig._load()
                    try:
                        _, mrow = ig._resolve_case(blind_id, grades, manifest)
                    except SystemExit as exc:
                        self._json(404, {"error": str(exc)})
                        return
                    image_path = Path(str(mrow["image_path"]))
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
                if not blind_id or not subtype:
                    self._json(400, {"error": "blind_id and subtype required"})
                    return
                with _lock:
                    grades, manifest = ig._load()
                    try:
                        # cmd_set prints; capture via redirect would be noisy — call then reload
                        ig.cmd_set(grades, blind_id, subtype, notes=None)
                    except SystemExit as exc:
                        self._json(400, {"error": str(exc)})
                        return
                    _skipped.discard(blind_id)
                    grades, manifest = ig._load()
                    nxt = _next_ungraded_after(
                        grades, after_id=blind_id, skip_set=_skipped, include_after=False
                    )
                    self._json(
                        200,
                        {
                            "ok": True,
                            "saved": blind_id,
                            "subtype": subtype,
                            "next": _case_payload(nxt, grades, manifest),
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
                    _skipped.add(blind_id)
                    grades, manifest = ig._load()
                    nxt = _next_ungraded_after(
                        grades, after_id=blind_id, skip_set=_skipped, include_after=False
                    )
                    self._json(
                        200,
                        {
                            "ok": True,
                            "skipped": blind_id,
                            "next": _case_payload(nxt, grades, manifest),
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
    parser = argparse.ArgumentParser(description="Blind MNV grading — local browser server")
    parser.add_argument(
        "--start-at",
        metavar="B0xx",
        default=None,
        help="Resume at first ungraded blind_id >= this id (e.g. B017)",
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Listen port (default 8765)")
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

    # Resolve initial case for URL / messaging
    grades, _ = ig._load()
    row = _resolve_start(grades, _START_AT)
    done, n = ig._progress(grades)
    initial = str(row["blind_id"]) if row is not None else None

    host = "127.0.0.1"
    port = int(args.port)
    q = f"?start_at={_START_AT}" if _START_AT else ""
    url = f"http://{host}:{port}/{q}"

    print(f"Progress: {done}/{n}")
    print(f"Initial case: {initial or '(none)'}")
    print(f"Serving on {url}")
    print("Press Ctrl+C to stop.")

    httpd = HTTPServer((host, port), GradeHandler)

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
