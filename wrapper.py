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
import threading
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
    """Worker: Runs the FastAPI backend via uvicorn."""
    import uvicorn
    from src.api.main import app
    print(f"[Backend] Starting FastAPI on port {port}...", flush=True)
    # Explicitly disable colors to avoid isatty() calls on None stdout
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning", use_colors=False)


def _start_backend(port: int):
    """Start FastAPI.

    Frozen macOS apps that spawn a child under Hardened Runtime are SIGKILL'd
    (CODESIGNING Invalid Page). Run the engine in a daemon thread on Darwin so
    login does not depend on Apple notarization.
    """
    if sys.platform == "darwin":
        worker = threading.Thread(
            target=run_api_server,
            args=(port,),
            daemon=True,
            name="ariaike-api",
        )
        worker.start()
        return worker
    proc = multiprocessing.Process(target=run_api_server, args=(port,), daemon=True)
    proc.start()
    return proc


_MAC_NSAPP = None


def _mac_nsapp_init() -> bool:
    """Create NSApplication and finishLaunching on the main thread.

    Every click of ARIAKE_OCTA.app from /Applications bounces the Dock until
    *this* process runs a Cocoa event loop. Flet is a separate ``Flet.app``
    (``open -n -W``); its window does not count. A background-thread run loop
    also does not count — Launch Services watches the main thread.
    """
    global _MAC_NSAPP
    if sys.platform != "darwin":
        return False
    if _MAC_NSAPP is not None:
        return True
    try:
        import ctypes

        ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/AppKit.framework/AppKit"
        )
        objc = ctypes.cdll.LoadLibrary("/usr/lib/libobjc.A.dylib")
        cf = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
        )

        objc.sel_registerName.restype = ctypes.c_void_p
        objc.sel_registerName.argtypes = [ctypes.c_char_p]
        objc.objc_getClass.restype = ctypes.c_void_p
        objc.objc_getClass.argtypes = [ctypes.c_char_p]

        def _msg(obj, sel, restype=ctypes.c_void_p, extra_types=(), extra_args=()):
            proto = ctypes.CFUNCTYPE(
                restype, ctypes.c_void_p, ctypes.c_void_p, *extra_types
            )
            fn = proto(("objc_msgSend", objc))
            return fn(obj, sel, *extra_args)

        nsapp_cls = objc.objc_getClass(b"NSApplication")
        if not nsapp_cls:
            print("[Wrapper] NSApplication class missing; Dock bounce may continue.", flush=True)
            return False
        app = _msg(nsapp_cls, objc.sel_registerName(b"sharedApplication"))
        if not app:
            print("[Wrapper] NSApplication.sharedApplication failed.", flush=True)
            return False
        # NSApplicationActivationPolicyRegular = 0 (keep our Dock icon).
        _msg(
            app,
            objc.sel_registerName(b"setActivationPolicy:"),
            restype=ctypes.c_long,
            extra_types=(ctypes.c_long,),
            extra_args=(0,),
        )
        _msg(app, objc.sel_registerName(b"finishLaunching"), restype=None)

        mode = ctypes.c_void_p.in_dll(cf, "kCFRunLoopDefaultMode")
        cf.CFRunLoopRunInMode.restype = ctypes.c_int32
        cf.CFRunLoopRunInMode.argtypes = [
            ctypes.c_void_p,
            ctypes.c_double,
            ctypes.c_int,
        ]
        _MAC_NSAPP = {"cf": cf, "mode": mode, "app": app, "objc": objc}
        print("[Wrapper] NSApplication finishLaunching (Dock bounce should stop).", flush=True)
        return True
    except Exception as exc:
        print(f"[Wrapper] Dock bounce signal failed: {exc}", flush=True)
        return False


def _mac_pump_main_until(alive_fn, timeout=None) -> None:
    """Run the main-thread CFRunLoop until alive_fn is false (every launch)."""
    started = time.monotonic()
    ns = _MAC_NSAPP
    if ns is None:
        while alive_fn():
            if timeout is not None and (time.monotonic() - started) >= timeout:
                break
            time.sleep(0.05)
        return
    cf, mode = ns["cf"], ns["mode"]
    while alive_fn():
        if timeout is not None and (time.monotonic() - started) >= timeout:
            break
        cf.CFRunLoopRunInMode(mode, 0.1, 1)


def _mac_signal_nsapp_launched(*, pump: bool = True) -> bool:
    """Init NSApp + one main-thread pump. ``pump`` kept for the Mac build smoke."""
    ok = _mac_nsapp_init()
    if ok and _MAC_NSAPP is not None:
        _MAC_NSAPP["cf"].CFRunLoopRunInMode(_MAC_NSAPP["mode"], 0.05, 1)
        if not pump:
            return True
    return ok


def _run_on_worker_pump_main(fn, name: str):
    """Run fn off-main; keep pumping Cocoa on the main thread (every Dock click)."""
    if sys.platform != "darwin":
        return fn()
    box = {"exc": None, "rv": None}

    def _target():
        try:
            box["rv"] = fn()
        except Exception as exc:
            box["exc"] = exc
            traceback.print_exc()

    worker = threading.Thread(target=_target, name=name, daemon=True)
    worker.start()
    _mac_pump_main_until(worker.is_alive)
    worker.join(timeout=5)
    if box["exc"] is not None:
        raise box["exc"]
    return box["rv"]


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
        # Every /Applications click: this process is the bouncing Dock icon.
        _mac_signal_nsapp_launched()

    # ── ENVIRONMENT CONFIGURATION ──────────────────────────────────────────
    os.environ.setdefault("ARIAKE_ACCESS_KEY", "ariake2024")
    os.environ.setdefault("ARIAKE_LOG_LEVEL", "ERROR")
    os.environ.setdefault("ARIAKE_SAVE_STAGES", "false")
    os.environ.setdefault("ARIAKE_ENABLE_ROI_REFINEMENT", "false")
    
    # Ephemeral ports by default. If ARIAKE_API_PORT / FLET_PORT are set for
    # debugging, still fall back when those ports are already taken.
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
    api_proc = _start_backend(api_port)

    print(f"[Wrapper] Backend assigned to port {api_port}. Waiting for startup...", flush=True)
    try:
        from src.utils.local_ports import wait_for_tcp_port

        def _wait_api():
            return wait_for_tcp_port(
                api_port, timeout=90.0, is_alive=api_proc.is_alive
            )

        api_ready = _run_on_worker_pump_main(_wait_api, "api-wait")
    except ImportError:
        if sys.platform == "darwin":
            _mac_pump_main_until(lambda: True, timeout=2.0)
            api_ready = True
        else:
            time.sleep(2)
            api_ready = True
    if not api_ready:
        print(
            "[Wrapper] WARNING: FastAPI did not become ready. Login may show "
            "'Connection Error: All connection attempts failed'.",
            flush=True,
        )

    # ── RUN FRONTEND ───────────────────────────────────────────────────────
    try:
        import flet as ft
        import main_app
        
        flet_view = ft.AppView.WEB_BROWSER if use_web == "1" else ft.AppView.FLET_APP
        print(f"[Frontend] Starting Flet ({flet_view}) on port {flet_port}...", flush=True)
        if use_web == "1":
            print(
                f"[Frontend] Open http://127.0.0.1:{flet_port} if the browser does not open.",
                flush=True,
            )
        
        ft_kwargs = dict(
            target=main_app.main,
            view=flet_view,
            port=flet_port,
            upload_dir=str(main_app.UPLOAD_ROOT),
        )
        if use_web == "1":
            ft_kwargs["host"] = os.environ.get("FLET_SERVER_IP", "127.0.0.1")
            renderer = (os.environ.get("FLET_WEB_RENDERER") or "canvaskit").strip().lower()
            if renderer == "html":
                renderer = "canvaskit"
            ft_kwargs["web_renderer"] = renderer
        if sys.platform == "darwin":
            # ft.app blocks on asyncio + ``open Flet.app -W``. Keep CFRunLoop
            # on the main thread so bounce stops and stays stopped.
            _run_on_worker_pump_main(lambda: ft.app(**ft_kwargs), "flet-frontend")
        else:
            ft.app(**ft_kwargs)
    except KeyboardInterrupt:
        print("\n[Wrapper] KeyboardInterrupt received.", flush=True)
    except Exception as e:
        print(f"[Wrapper] Error running Flet: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
    finally:
        print("[Wrapper] Flet window closed. Shutting down backend...", flush=True)
        if isinstance(api_proc, multiprocessing.Process) and api_proc.is_alive():
            api_proc.terminate()
            api_proc.join(timeout=3)
        sys.exit(0)