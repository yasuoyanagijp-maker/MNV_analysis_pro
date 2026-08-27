"""
Local TCP port helpers shared by packaged wrapper and (optional) dev entrypoints.

Packaged Mac/Windows apps use ``get_free_port()`` in ``wrapper.py`` /
``wrapper_win.py`` so API and Flet never collide with Cursor or fixed 8000/8550.
"""

from __future__ import annotations

import os
import socket
import time
from typing import Callable, Iterable, Optional


def get_free_port(host: str = "127.0.0.1") -> int:
    """Return an available ephemeral listen port (same contract as wrapper.py)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


def wait_for_tcp_port(
    port: int,
    *,
    host: str = "127.0.0.1",
    timeout: float = 90.0,
    poll_interval: float = 0.2,
    is_alive: Optional[Callable[[], bool]] = None,
) -> bool:
    """Return True once TCP connect to host:port succeeds.

    Used by the packaged wrapper so the login window is not shown while the
    FastAPI child is still importing numpy/cv2. ``is_alive`` (e.g. Process.is_alive)
    aborts early if the worker has already died.
    """
    deadline = time.monotonic() + max(0.0, float(timeout))
    port = int(port)
    while True:
        if is_alive is not None and not is_alive():
            return False
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            pass
        if time.monotonic() >= deadline:
            return False
        time.sleep(max(0.05, float(poll_interval)))


def port_is_free(port: int, host: str = "127.0.0.1") -> bool:
    """Return True if we can bind TCP on host:port (IPv4)."""
    if port <= 0 or port > 65535:
        return False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, int(port)))
        return True
    except OSError:
        return False


def pick_listen_port(
    preferred: int,
    *,
    host: str = "127.0.0.1",
    search_span: int = 40,
    fallback_candidates: Optional[Iterable[int]] = None,
) -> int:
    """
    Prefer ``preferred`` when free; else try nearby ports; else ``get_free_port()``.

    Used when a caller wants a stable preferred port but must not fail if busy.
    """
    preferred = int(preferred)
    if port_is_free(preferred, host=host):
        return preferred

    for offset in range(1, max(1, int(search_span)) + 1):
        candidate = preferred + offset
        if candidate > 65535:
            break
        if port_is_free(candidate, host=host):
            return candidate

    if fallback_candidates:
        for candidate in fallback_candidates:
            c = int(candidate)
            if port_is_free(c, host=host):
                return c

    return get_free_port(host=host)


def resolve_env_port_or_ephemeral(env_key: str, env: Optional[dict] = None) -> int:
    """
    If ``env_key`` is a numeric port, use it when free (else bump).
    If unset, pick an ephemeral free port — packaged wrapper default.
    Always writes the chosen port back into ``env``.
    """
    e = env if env is not None else os.environ
    raw = (e.get(env_key) or "").strip()
    if raw.isdigit():
        preferred = int(raw)
        chosen = pick_listen_port(preferred)
        if chosen != preferred:
            print(
                f"[Wrapper] {env_key}={preferred} busy → using {chosen}",
                flush=True,
            )
    else:
        chosen = get_free_port()
    e[env_key] = str(chosen)
    return chosen


def resolve_api_port(env: Optional[dict] = None) -> int:
    """ARIAKE_API_PORT if set, else prefer 8000; bump if busy — writes back into env."""
    e = env if env is not None else os.environ
    raw = (e.get("ARIAKE_API_PORT") or "").strip()
    preferred = int(raw) if raw.isdigit() else 8000
    chosen = pick_listen_port(preferred)
    if chosen != preferred:
        print(f"API: port {preferred} busy → using {chosen}", flush=True)
    e["ARIAKE_API_PORT"] = str(chosen)
    return chosen


def resolve_flet_port(*, use_web: bool = True, env: Optional[dict] = None) -> int:
    """
    FLET_PORT if set, else ephemeral (same idea as wrapper).

    Packaged launches set FLET_PORT via wrapper ``get_free_port()`` before
    ``ft.app``; this helper is for ``python main_app.py`` without the wrapper.
    """
    e = env if env is not None else os.environ
    raw = (e.get("FLET_PORT") or "").strip()
    if raw.isdigit():
        preferred = int(raw)
        chosen = pick_listen_port(preferred)
        if chosen != preferred:
            print(f"Flet: port {preferred} busy → using {chosen}", flush=True)
    else:
        chosen = get_free_port()
        print(f"Flet: using ephemeral port {chosen} (prefer: python wrapper.py)", flush=True)
    e["FLET_PORT"] = str(chosen)
    return chosen
