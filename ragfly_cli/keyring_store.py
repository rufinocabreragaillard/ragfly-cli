"""
Almacén persistente del JWT y email del usuario en el keyring del SO.

- macOS: Keychain (Acceso a Llaveros)
- Windows: Credential Manager
- Linux: libsecret / Secret Service

Doc 10 § 6 (SSO γ): el JWT se persiste fuera de SQLite y fuera del filesystem
plano del usuario. Vive en el keyring del SO, accesible solo por la app y el
usuario logueado en la sesión del SO.
"""

from __future__ import annotations

import keyring
from keyring.errors import KeyringError

SERVICE = "ragfly-ragflydesktop"
KEY_TOKEN = "jwt"
KEY_EMAIL = "email"


class KeyringStoreError(Exception):
    """El keyring del SO no está disponible o falló al guardar la sesión.

    Típico en entornos headless/CI (sin Keychain/libsecret). El llamador debe
    capturarlo y sugerir el flujo por `RAGFLY_TOKEN`.
    """

# Cache en RAM por sesión del proceso. Evita re-leer el Keychain en cada
# llamada (cada lectura dispara un prompt del llavero cuando la app está
# firmada ad-hoc, como en builds de desarrollo). Se lee una sola vez y se
# refresca al guardar/borrar. Sentinela _NO_LEIDO distingue "no leído aún"
# de "leído y vacío".
_NO_LEIDO = object()
_cache_token: object | str | None = _NO_LEIDO
_cache_email: object | str | None = _NO_LEIDO


def guardar(token: str, email: str) -> None:
    """Persiste JWT+email en el keyring del SO.

    Lanza `KeyringStoreError` si el keyring no está disponible (headless/CI) o
    falla, sin dejar sesión parcial.
    """
    global _cache_token, _cache_email
    try:
        keyring.set_password(SERVICE, KEY_TOKEN, token)
        keyring.set_password(SERVICE, KEY_EMAIL, email)
    except Exception as e:  # KeyringError y backends sin llavero (NoKeyringError, etc.)
        # Rollback best-effort para no dejar sesión parcial (token sin email).
        try:
            keyring.delete_password(SERVICE, KEY_TOKEN)
        except Exception:
            pass
        raise KeyringStoreError(str(e)) from e
    _cache_token = token
    _cache_email = email


def leer_token() -> str | None:
    global _cache_token
    if _cache_token is not _NO_LEIDO:
        return _cache_token  # type: ignore[return-value]
    try:
        _cache_token = keyring.get_password(SERVICE, KEY_TOKEN)
    except KeyringError:
        _cache_token = None
    return _cache_token  # type: ignore[return-value]


def leer_email() -> str | None:
    global _cache_email
    if _cache_email is not _NO_LEIDO:
        return _cache_email  # type: ignore[return-value]
    try:
        _cache_email = keyring.get_password(SERVICE, KEY_EMAIL)
    except KeyringError:
        _cache_email = None
    return _cache_email  # type: ignore[return-value]


def borrar() -> None:
    global _cache_token, _cache_email
    for k in (KEY_TOKEN, KEY_EMAIL):
        try:
            keyring.delete_password(SERVICE, k)
        except KeyringError:
            pass
    _cache_token = None
    _cache_email = None
