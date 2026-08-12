"""
GakuNin RDM Personal Access Token の安全な永続化。

設計方針
--------
- PAT をソースコード・client_storage・平文ファイルに保存しない。
- 可能な場合は ``flet_secure_storage.SecureStorage`` を使う
  (Flet ≥0.80 / Keychain・Credential Manager・libsecret・Keystore)。
- 本アプリは Flet 0.28.3 固定のため ``flet-secure-storage`` と同時インストール不可。
  その場合は同等の OS ネイティブ領域を使う ``keyring`` にフォールバックする。

API は flet-secure-storage の SecureStorage に合わせた async get/set。
"""

from __future__ import annotations

from typing import Optional

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


def _keyring_get(key: str) -> Optional[str]:
    import keyring

    try:
        value = keyring.get_password(_SERVICE_NAME, key)
    except Exception as ex:
        raise RuntimeError(
            "OS セキュアストレージからトークンを読めませんでした"
            f"（keyring backend={type(keyring.get_keyring()).__name__}）: {ex}"
        ) from ex
    return value


def _keyring_set(key: str, value: str) -> None:
    import keyring

    backend = keyring.get_keyring()
    backend_name = type(backend).__module__ + "." + type(backend).__name__
    # Plaintext file backends are unacceptable for PAT storage.
    if "plain" in backend_name.lower() or "fail" in backend_name.lower():
        raise RuntimeError(
            "安全なキーリングが利用できません"
            f"（backend={backend_name}）。"
            "macOS/Windows はそのまま、Linux では libsecret と"
            " gnome-keyring / kwallet 等を有効にしてください。"
        )
    try:
        keyring.set_password(_SERVICE_NAME, key, value)
    except Exception as ex:
        raise RuntimeError(
            "OS セキュアストレージへトークンを保存できませんでした"
            f"（backend={backend_name}）: {ex}"
        ) from ex


def _keyring_delete(key: str) -> None:
    import keyring

    try:
        keyring.delete_password(_SERVICE_NAME, key)
    except keyring.errors.PasswordDeleteError:
        pass
    except Exception:
        pass


# Convenience alias matching the sample integration code
GRDM_TOKEN_STORAGE_KEY = _TOKEN_KEY
