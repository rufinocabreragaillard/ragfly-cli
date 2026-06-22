"""
Comandos cloud — cliente HTTP contra la API REST de Railway.

API pública:
    obtener_token()          → str   (lee JWT o lanza RuntimeError)
    cloud_get(path, **kw)    → dict  (GET autenticado)
    cloud_post(path, **kw)   → dict  (POST autenticado)
    CLOUD_URL                → str

Clases auxiliares:
    CloudError               — error de red/API con exit_code
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx

from . import keyring_store

# ── Constantes ───────────────────────────────────────────────────────────────

CLOUD_URL = "https://api.ragfly.ai"
LEGACY_CREDENTIALS_PATH = Path.home() / ".ragfly" / "credentials.json"


# ── Excepciones ───────────────────────────────────────────────────────────────

class CloudError(Exception):
    """Error de red o de la API cloud."""

    def __init__(self, mensaje: str, exit_code: int = 2):
        super().__init__(mensaje)
        self.exit_code = exit_code


# ── Auth ──────────────────────────────────────────────────────────────────────

def _migrar_legacy_json_a_keyring() -> str | None:
    """Si existe ~/.ragfly/credentials.json (v1.0.x), lo migra al keyring
    del SO y lo borra. Retorna el token migrado, o None si no había."""
    if not LEGACY_CREDENTIALS_PATH.exists():
        return None
    try:
        creds = json.loads(LEGACY_CREDENTIALS_PATH.read_text())
        token = creds.get("access_token", "")
        email = creds.get("email", "")
        if token:
            keyring_store.guardar(token, email)
        LEGACY_CREDENTIALS_PATH.unlink()
        return token or None
    except Exception:
        return None


def obtener_token() -> str:
    """Resuelve el token de autenticación, en orden de precedencia:

    1. ``RAGFLY_TOKEN`` del entorno — API key (``slm_live_...``) o JWT. Pensado
       para CI/automatización headless, donde no hay keyring del SO.
    2. El JWT guardado en el keyring del SO por ``ragfly login``.

    La validez se delega al backend: cualquier 401 dispara logout en el shell.
    """
    env_token = os.environ.get("RAGFLY_TOKEN", "").strip()
    if env_token:
        return env_token
    token = keyring_store.leer_token() or _migrar_legacy_json_a_keyring()
    if not token:
        raise CloudError(
            "No has iniciado sesión. Ejecutá `ragfly login` o exportá RAGFLY_TOKEN.",
            exit_code=1,
        )
    return token


def guardar_credenciales(token: str, email: str, expires_in: int = 3600) -> None:
    """Guarda JWT en el keyring del SO. `expires_in` se ignora (firma compat)."""
    keyring_store.guardar(token, email)


def borrar_credenciales() -> None:
    """Borra JWT del keyring (logout). Limpia también el JSON legacy si quedó."""
    keyring_store.borrar()
    try:
        if LEGACY_CREDENTIALS_PATH.exists():
            LEGACY_CREDENTIALS_PATH.unlink()
    except Exception:
        pass


def ya_esta_logueado() -> bool:
    """True si hay token en el keyring (no valida vivo — eso lo hace /auth/me)."""
    try:
        obtener_token()
        return True
    except CloudError:
        return False


def cargar_contexto_actual() -> dict:
    """Llama a /auth/me y retorna el contexto del usuario logueado."""
    return cloud_get("/auth/me")


# ── HTTP helpers ─────────────────────────────────────────────────────────────

def _headers(token: str | None = None) -> dict[str, str]:
    """Headers estándar para cualquier request al cloud.

    Incluye X-Client-Version desde ragfly.__version__ — backend lo loggea
    siempre y en el futuro puede rechazar versiones incompatibles (gated por
    env ENFORCE_CLIENT_VERSION en backend).
    """
    from ragfly_cli import __version__ as _client_version

    t = token or obtener_token()
    return {
        "Authorization": f"Bearer {t}",
        "Content-Type": "application/json",
        "X-Client-Version": _client_version,
    }


def cloud_get(
    path: str,
    params: dict | None = None,
    token: str | None = None,
    timeout: int = 30,
) -> Any:
    """GET autenticado contra CLOUD_URL/path. Retorna JSON parseado.

    Wrapper retrocompatible sobre `CloudHttpClient` (ragfly.oop).
    """
    from ragfly_cli.oop import CloudHttpClient
    return CloudHttpClient(timeout_get=timeout).get(path, params=params, token=token)


def cloud_post(
    path: str,
    body: dict | None = None,
    params: dict | None = None,
    token: str | None = None,
    timeout: int = 60,
) -> Any:
    """POST autenticado contra CLOUD_URL/path. Retorna JSON parseado.

    Wrapper retrocompatible sobre `CloudHttpClient` (ragfly.oop).
    """
    from ragfly_cli.oop import CloudHttpClient
    return CloudHttpClient(timeout_write=timeout).post(path, body=body, params=params, token=token)


def _manejar_http_error(e: httpx.HTTPStatusError) -> None:
    status = e.response.status_code
    try:
        detalle = e.response.json().get("detail", str(e))
    except Exception:
        detalle = e.response.text[:200] or str(e)

    if status == 401:
        raise CloudError("No autorizado. Ejecuta: ragfly login", exit_code=1)
    if status == 403:
        raise CloudError(f"Sin permisos: {detalle}", exit_code=1)
    if status == 404:
        raise CloudError(f"No encontrado: {detalle}", exit_code=1)
    if status == 422:
        raise CloudError(f"Datos inválidos: {detalle}", exit_code=1)
    raise CloudError(f"Error {status}: {detalle}", exit_code=2)


# ── Login helper ─────────────────────────────────────────────────────────────

def login(email: str, password: str) -> dict:
    """Autentica contra /auth/login y retorna el contexto del usuario."""
    try:
        r = httpx.post(
            f"{CLOUD_URL}/auth/login",
            json={"email": email, "password": password},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (401, 403):
            raise CloudError("Email o contraseña incorrectos.", exit_code=1)
        _manejar_http_error(e)
    except httpx.RequestError as e:
        raise CloudError(f"No se pudo conectar al servidor: {e}", exit_code=2)

    token = data.get("access_token") or data.get("token", "")
    if not token:
        raise CloudError("El servidor no retornó un token.", exit_code=2)

    expires_in = data.get("expires_in", 3600)
    guardar_credenciales(token, email, expires_in)
    return data
