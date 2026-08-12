"""
GakuNin RDM Personal Access Token の安全な永続化。

設計方針
--------
- PAT をソースコード・client_storage・平文ファイルに保存しない。
- 可能な場合は ``flet_secure_storage.SecureStorage`` を使う
  (Flet ≥0.80 / Keychain·Credential Manager·libsecret·Keystore)。
- 本アプリは Flet 0.28.3 固定のため ``flet-secure-storage`` と同時インストール不可。
  その場合は同等の OS ネイティブ領域を使う ``keyring`` にフォールバックする。

API は flet-secure-storage の SecureStorage に合わせた async get/set。
"""

from __future__ import annotations

from typing import Any, Optional

_TOKEN_KEY = "grdm_token"
_SERVICE_NAME = "ARIAKE_OCTA_GRDM"


class SecureStorage:
    """OS ネイティブの安全な領域へ key/value を保存する薄いラッパー。"""

    def __init__(self) -> None:
        self._fss = None
        try:
            import flet_secure_storage as fss  # type: ignore

            self._fss = fss.SecureStorage()
        except Exception:
            self._fss = None

    async def get(self, key: str) -> Optional[str]:
        """Return stored value, or None if missing / backend unavailable.

        Keyring failures must not block the PAT prompt on first use.
        """
        if self._fss is not None:
            try:
                value = await self._fss.get(key)
                if value:
                    return str(value)
            except Exception:
                pass
        return _keyring_get(key)

    async def set(self, key: str, value: str) -> None:
        if self._fss is not None:
            try:
                await self._fss.set(key, value)
                return
            except Exception:
                pass
        _keyring_set(key, value)

    async def remove(self, key: str) -> None:
        if self._fss is not None:
            try:
                await self._fss.remove(key)
            except Exception:
                pass
        _keyring_delete(key)


def _keyring_backend_name(backend: Any) -> str:
    return f"{type(backend).__module__}.{type(backend).__name__}"


def _iter_keyring_backends(backend: Any):
    """Yield backend and any chained children (ChainerBackend etc.)."""
    yield backend
    for attr in ("backends", "_backends"):
        chain = getattr(backend, attr, None)
        if not chain:
            continue
        try:
            children = list(chain)
        except TypeError:
            continue
        for child in children:
            yield from _iter_keyring_backends(child)


def _is_insecure_keyring(backend: Any) -> bool:
    """Reject plaintext / fail / known file-based insecure backends (incl. chain)."""
    insecure_markers = (
        "plain",
        "fail",
        "keyrings.alt.file",
        "plaintextkeyring",
        "file.keyring",
        "filekeyring",
    )
    for b in _iter_keyring_backends(backend):
        name = _keyring_backend_name(b).lower()
        if any(m in name for m in insecure_markers):
            return True
        # Some file backends expose a path attribute
        for path_attr in ("file_path", "filename", "path"):
            p = getattr(b, path_attr, None)
            if p and "keyring" in str(p).lower():
                # Heuristic: password file under a keyring path → insecure for PAT
                if any(x in name for x in ("file", "plain", "alt")):
                    return True
    return False


def _keyring_get(key: str) -> Optional[str]:
    """Soft-fail: return None when keyring is unavailable so UI can prompt for PAT."""
    try:
        import keyring
    except Exception:
        return None

    try:
        return keyring.get_password(_SERVICE_NAME, key)
    except Exception:
        return None


def _keyring_set(key: str, value: str) -> None:
    import keyring

    backend = keyring.get_keyring()
    backend_name = _keyring_backend_name(backend)
    if _is_insecure_keyring(backend):
        raise RuntimeError(
            "安全なキーリングが利用できません"
            f"（backend={backend_name}）。"
            "macOS/Windows はそのまま、Linux では libsecret と"
            " gnome-keyring / kwallet 等を有効にしてください。"
            " 平文ファイルへの PAT 保存は行いません。"
        )
    try:
        keyring.set_password(_SERVICE_NAME, key, value)
    except Exception as ex:
        raise RuntimeError(
            "OS セキュアストレージへトークンを保存できませんでした"
            f"（backend={backend_name}）: {ex}"
        ) from ex


def _keyring_delete(key: str) -> None:
    try:
        import keyring
    except Exception:
        return

    try:
        keyring.delete_password(_SERVICE_NAME, key)
    except Exception:
        pass


# Convenience alias matching the sample integration code
GRDM_TOKEN_STORAGE_KEY = _TOKEN_KEY
