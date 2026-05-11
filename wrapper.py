"""
wrapper.py — ARIAKE OCTA (Flet + FastAPI version)
Replaces Streamlit wrapper with an integrated Flet + FastAPI launcher.
"""
import sys
import os
import time
import socket
import subprocess
import multiprocessing
import tempfile
import traceback
from pathlib import Path
import logging


def _launcher_log_path() -> Path:
    """Writable log path: next to EXE when frozen, else project dir; fallback %TEMP%."""
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / "aria_launcher.log")
    try:
        candidates.append(Path(__file__).resolve().parent / "aria_launcher.log")
    except NameError:
        pass
    candidates.append(Path(tempfile.gettempdir()) / "aria_launcher.log")
    for p in candidates:
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "a", encoding="utf-8"):
                pass
            return p
        except OSError:
            continue
    return Path(tempfile.gettempdir()) / "aria_launcher.log"


# PyInstaller windowed mode: stdout/stderr are None and break some libs.
# On Windows spawn, child re-imports this module; "w" would truncate the log — use "a" in workers.
_log = _launcher_log_path()
_stdio_mode = "a" if multiprocessing.parent_process() is not None else "w"
if sys.stdout is None:
    sys.stdout = open(_log, _stdio_mode, encoding="utf-8", buffering=1)
if sys.stderr is None:
    sys.stderr = open(_log, "a", encoding="utf-8", buffering=1)

def get_free_port() -> int:
    """Finds an available ephemeral port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        return int(s.getsockname()[1])

def run_api_server(port: int):
    """Worker process: Runs the FastAPI backend via uvicorn."""
    import uvicorn
    from src.api.main import app
    print(f"[Backend] Starting FastAPI on port {port}...", flush=True)
    # Explicitly disable colors to avoid isatty() calls on None stdout
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning", use_colors=False)

if __name__ == "__main__":
    multiprocessing.freeze_support()
    
    # ── DYNAMIC PATH ADJUSTMENT ───────────────────────────────────────────
    if getattr(sys, "frozen", False):
        MEIPASS = Path(sys._MEIPASS)
        # On macOS App bundles, Resources is outside MacOS/
        RESOURCES_DIR = MEIPASS.parent / "Resources"
        if RESOURCES_DIR.exists():
            BASE_DIR = RESOURCES_DIR
        else:
            BASE_DIR = MEIPASS
    else:
        BASE_DIR = Path(__file__).resolve().parent

    # Ensure BASE_DIR and src are in sys.path before child processes spawn
    if str(BASE_DIR) not in sys.path:
        sys.path.insert(0, str(BASE_DIR))
    if str(BASE_DIR / "src") not in sys.path:
        sys.path.insert(0, str(BASE_DIR / "src"))

    if sys.platform == "darwin":
        multiprocessing.set_start_method("spawn", force=True)

    # ── ENVIRONMENT CONFIGURATION ──────────────────────────────────────────
    os.environ.setdefault("ARIAKE_ACCESS_KEY", "ariake2024")
    os.environ.setdefault("ARIAKE_LOG_LEVEL", "ERROR")
    os.environ.setdefault("ARIAKE_SAVE_STAGES", "false")
    os.environ.setdefault("ARIAKE_ENABLE_ROI_REFINEMENT", "false")
    
    api_port = get_free_port()
    flet_port = get_free_port()

    # Share ports via environment for Flet frontend and BackendClient
    os.environ["ARIAKE_API_PORT"] = str(api_port)
    os.environ["FLET_PORT"] = str(flet_port)
    
    # Allow overriding via environment variable (default to 0 for Native)
    use_web = os.environ.get("FLET_USE_WEB", "0")
    if use_web not in ["0", "1"]:
        use_web = "0"
    os.environ["FLET_USE_WEB"] = use_web

    # ── SPAWN BACKEND ──────────────────────────────────────────────────────
    api_proc = multiprocessing.Process(target=run_api_server, args=(api_port,), daemon=True)
    api_proc.start()

    # Give API a moment to bind
    print(f"[Wrapper] Backend assigned to port {api_port}. Waiting for startup...", flush=True)
    time.sleep(2)

    # ── RUN FRONTEND ───────────────────────────────────────────────────────
    try:
        import flet as ft
        import main_app
        
        flet_view = ft.AppView.WEB_BROWSER if use_web == "1" else ft.AppView.FLET_APP
        print(f"[Frontend] Starting Flet ({flet_view}) on port {flet_port}...", flush=True)
        
        ft.app(
            target=main_app.main,
            view=flet_view,
            port=flet_port,
            upload_dir=str(main_app.UPLOAD_ROOT),
        )
    except KeyboardInterrupt:
        print("\n[Wrapper] KeyboardInterrupt received.", flush=True)
    except Exception as e:
        print(f"[Wrapper] Error running Flet: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
    finally:
        print("[Wrapper] Flet window closed. Shutting down backend...", flush=True)
        if api_proc.is_alive():
            api_proc.terminate()
            api_proc.join(timeout=3)
        sys.exit(0)