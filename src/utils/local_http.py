"""Loopback FastAPI HTTP helpers.

University / hospital PCs often set HTTP_PROXY. httpx honors that by default and
then login to 127.0.0.1 fails with "All connection attempts failed" even though
the password and institution code are correct.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict

import httpx

LOGIN_ENGINE_UNREACHABLE = (
    "Connection Error: 解析エンジンに接続できません"
    "（パスワード・施設コードの誤りではありません）。"
    "アプリを完全に終了して再起動し、ログイン画面が出てから少し待って再度お試しください。"
)


def local_async_client(**kwargs) -> httpx.AsyncClient:
    """httpx client for 127.0.0.1 FastAPI. Never use the process HTTP proxy."""
    kwargs.setdefault("trust_env", False)
    return httpx.AsyncClient(**kwargs)


async def login_via_local_api(
    base_url: str,
    username: str,
    password: str,
    *,
    attempts: int = 8,
) -> Dict[str, Any]:
    """POST /login with short retries while the engine is still binding."""
    payload = {"researcher_name": username, "password": password}
    last_err = None
    tries = max(1, int(attempts))
    for i in range(tries):
        try:
            async with local_async_client(timeout=8.0) as client:
                response = await client.post(f"{base_url}/login", json=payload)
                return response.json()
        except Exception as exc:
            last_err = exc
            if i + 1 < tries:
                await asyncio.sleep(0.4)
    detail = str(last_err) if last_err else "unreachable"
    return {
        "success": False,
        "message": f"{LOGIN_ENGINE_UNREACHABLE} ({detail})",
    }
