"""
wrapper_win.py — ARIAKE OCTA Windows (Flet + FastAPI version)
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


def _plan1_enabled() -> bool:
    raw = (os.environ.get("ARIAKE_WIN_PERF_PLAN1") or "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    return sys.platform == "win32"


def _apply_plan1_env_early() -> bool:
    """Pin BLAS/OpenMP before numpy is imported (spawned API child re-imports this file)."""
    if not _plan1_enabled():
        return False
    n = (os.environ.get("ARIAKE_BLAS_THREADS") or "1").strip()
    if not n.isdigit() or int(n) < 1:
        n = "1"
    for key in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "BLIS_NUM_THREADS",
    ):
        os.environ[key] = n
    return True


_PLAN1 = _apply_plan1_env_early()
_LOG_BUFFERING = 8192 if _PLAN1 else 1


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


def _stream_is_console(stream) -> bool:
    if stream is None:
        return False
    try:
        return stream.isatty()
    except Exception:
        return False


# PyInstaller windowed (runw): often no console AND stdout/stderr are not None — still not a TTY.
# On Windows frozen EXE, always mirror to aria_launcher.log unless a real console (DEBUG build).
_log = _launcher_log_path()
_stdio_mode = "a" if multiprocessing.parent_process() is not None else "w"
if getattr(sys, "frozen", False) and sys.platform == "win32":
    if not (_stream_is_console(sys.stdout) and _stream_is_console(sys.stderr)):
        sys.stdout = open(_log, _stdio_mode, encoding="utf-8", buffering=_LOG_BUFFERING)
        sys.stderr = open(_log, "a", encoding="utf-8", buffering=_LOG_BUFFERING)
else:
    if sys.stdout is None:
        sys.stdout = open(_log, _stdio_mode, encoding="utf-8", buffering=_LOG_BUFFERING)
    if sys.stderr is None:
        sys.stderr = open(_log, "a", encoding="utf-8", buffering=_LOG_BUFFERING)

def get_free_port() -> int:
    """Finds an available ephemeral port (shared with src.utils.local_ports)."""
    try:
        from src.utils.local_ports import get_free_port as _shared

        return _shared()
    except ImportError:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            s.listen(1)
            return int(s.getsockname()[1])


def _resolve_launch_port(env_key: str) -> int:
    """Prefer env port when free; bump if busy; else ephemeral."""
    try:
        from src.utils.local_ports import resolve_env_port_or_ephemeral

        return resolve_env_port_or_ephemeral(env_key)
    except ImportError:
        raw = (os.environ.get(env_key) or "").strip()
        if raw.isdigit():
            return int(raw)
        return get_free_port()

def run_api_server(port: int):
    """Worker process: Runs the FastAPI backend via uvicorn."""
    import uvicorn
    from src.api.main import app
    print(f"[Backend] Starting FastAPI on port {port}...", flush=True)
    # Explicitly disable colors to avoid isatty() calls on None stdout
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning", use_colors=False)

if __name__ == "__main__":
    multiprocessing.freeze_support()

    # Double-click / shortcut: cwd is often not the EXE folder — align for relative paths & Flet
    if getattr(sys, "frozen", False):
        _exe_dir = Path(sys.executable).resolve().parent
        try:
            os.chdir(_exe_dir)
        except OSError:
            pass
    
    # ── DYNAMIC PATH ADJUSTMENT ───────────────────────────────────────────
    if getattr(sys, "frozen", False):
        BASE_DIR = Path(sys._MEIPASS)
    else:
        BASE_DIR = Path(__file__).resolve().parent

    # Ensure BASE_DIR and src are in sys.path before child processes spawn
    if str(BASE_DIR) not in sys.path:
        sys.path.insert(0, str(BASE_DIR))
    if str(BASE_DIR / "src") not in sys.path:
        sys.path.insert(0, str(BASE_DIR / "src"))

    print(
        f"[Wrapper] cwd={os.getcwd()} executable={sys.executable} log={_log}",
        flush=True,
    )

    if sys.platform == "darwin":
        multiprocessing.set_start_method("spawn", force=True)

    # ── ENVIRONMENT CONFIGURATION ──────────────────────────────────────────
    os.environ.setdefault("ARIAKE_ACCESS_KEY", "ariake2024")
    os.environ.setdefault("ARIAKE_LOG_LEVEL", "ERROR")
    os.environ.setdefault("ARIAKE_SAVE_STAGES", "false")
    os.environ.setdefault("ARIAKE_ENABLE_ROI_REFINEMENT", "false")
    
    api_port = _resolve_launch_port("ARIAKE_API_PORT")
    flet_port = _resolve_launch_port("FLET_PORT")

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
        try:
            import ctypes

            msg = f"{type(e).__name__}: {e}"[:900]
            ctypes.windll.user32.MessageBoxW(0, msg, "ARIAKE OCTA Pro", 0x10)
        except Exception:
            pass
    finally:
        print("[Wrapper] Flet window closed. Shutting down backend...", flush=True)
        if api_proc.is_alive():
            api_proc.terminate()
            api_proc.join(timeout=3)
        sys.exit(0)
