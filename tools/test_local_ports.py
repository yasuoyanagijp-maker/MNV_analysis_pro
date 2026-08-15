"""Tests for local listen-port selection (shared with wrapper)."""

from __future__ import annotations

import socket

from src.utils.local_ports import get_free_port, pick_listen_port, port_is_free, resolve_flet_port


def test_get_free_port_is_bindable():
    port = get_free_port()
    assert 1024 <= port <= 65535
    assert port_is_free(port)


def test_port_is_free_false_when_bound():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 0))
        busy = int(sock.getsockname()[1])
        assert not port_is_free(busy)
        alt = pick_listen_port(busy)
        assert alt != busy
        assert port_is_free(alt)


def test_resolve_env_port_bumps_when_busy():
    from src.utils.local_ports import resolve_env_port_or_ephemeral

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 0))
        busy = int(sock.getsockname()[1])
        env = {"ARIAKE_API_PORT": str(busy)}
        chosen = resolve_env_port_or_ephemeral("ARIAKE_API_PORT", env=env)
        assert chosen != busy
        assert env["ARIAKE_API_PORT"] == str(chosen)


def test_resolve_env_port_ephemeral_when_unset():
    from src.utils.local_ports import resolve_env_port_or_ephemeral

    env = {}
    chosen = resolve_env_port_or_ephemeral("FLET_PORT", env=env)
    assert env["FLET_PORT"] == str(chosen)
    assert port_is_free(chosen)
