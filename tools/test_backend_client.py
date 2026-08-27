"""Local FastAPI client: ignore HTTP proxy, retry login, clear connection errors."""

from __future__ import annotations

import asyncio

import httpx

from src.utils.local_http import (
    LOGIN_ENGINE_UNREACHABLE,
    local_async_client,
    login_via_local_api,
)


def test_local_async_client_disables_proxy_env():
    http = local_async_client()
    try:
        assert http._trust_env is False
    finally:
        asyncio.run(http.aclose())


def test_login_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}

    class _Resp:
        def json(self):
            return {"success": True, "message": "Welcome, researcher.", "username": "Takizawa"}

    class _FakeAsyncClient:
        def __init__(self, **kwargs):
            assert kwargs.get("trust_env") is False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json=None):
            calls["n"] += 1
            if calls["n"] < 3:
                raise httpx.ConnectError("All connection attempts failed")
            return _Resp()

    monkeypatch.setattr("src.utils.local_http.httpx.AsyncClient", _FakeAsyncClient)
    result = asyncio.run(login_via_local_api("http://127.0.0.1:9", "Takizawa", "ariake2024"))
    assert result["success"] is True
    assert calls["n"] == 3


def test_login_connection_error_is_not_credential_failure(monkeypatch):
    class _FakeAsyncClient:
        def __init__(self, **kwargs):
            assert kwargs.get("trust_env") is False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json=None):
            raise httpx.ConnectError("All connection attempts failed")

    monkeypatch.setattr("src.utils.local_http.httpx.AsyncClient", _FakeAsyncClient)
    result = asyncio.run(
        login_via_local_api("http://127.0.0.1:9", "Takizawa", "ariake2024", attempts=2)
    )
    assert result["success"] is False
    assert "パスワード" in result["message"]
    assert LOGIN_ENGINE_UNREACHABLE in result["message"]
    assert "All connection attempts failed" in result["message"]
    assert "Invalid credentials" not in result["message"]
