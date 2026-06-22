"""
CloudHttpClient — wrapper HTTP unificado para la API cloud.

Encapsula el patrón repetido en `cloud_commands.py`:
    try:
        r = httpx.METODO(...)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPStatusError as e:
        _manejar_http_error(e)
    except httpx.RequestError as e:
        raise CloudError(f"Error de conexión: {e}", exit_code=2)

Ejemplo:
    from ragfly_cli.oop import CloudHttpClient
    cli = CloudHttpClient()
    me = cli.get("/auth/me")
    cli.post("/cloud/algo", body={"x": 1})
"""

from __future__ import annotations

import sys
from typing import Any, Optional

import httpx

from ragfly_cli import _runtime

# Import diferido para evitar ciclo
from ragfly_cli.cloud_commands import (
    CLOUD_URL,
    CloudError,
    _headers,
    _manejar_http_error,
)


class CloudHttpClient:
    """Cliente HTTP unificado contra la API cloud."""

    def __init__(
        self,
        url: str = CLOUD_URL,
        *,
        timeout_get: int = 30,
        timeout_write: int = 60,
    ):
        self.url = url
        self.timeout_get = timeout_get
        self.timeout_write = timeout_write

    # ── Helper interno ────────────────────────────────────────────────────────

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict] = None,
        body: Optional[dict] = None,
        token: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> Any:
        """Ejecuta el request con manejo uniforme de errores."""
        method = method.upper()
        is_write = method in ("POST", "PUT", "PATCH", "DELETE")
        final_timeout = timeout if timeout is not None else (
            self.timeout_write if is_write else self.timeout_get
        )

        try:
            kwargs: dict = {
                "params": params,
                "headers": _headers(token),
                "timeout": final_timeout,
            }
            if is_write and method != "DELETE":
                kwargs["json"] = body or {}

            url_full = f"{self.url}{path}"
            if _runtime.VERBOSE:
                qs = httpx.QueryParams(params or {})
                sufijo = f"?{qs}" if str(qs) else ""
                print(f"→ {method} {url_full}{sufijo}", file=sys.stderr)

            r = httpx.request(method, url_full, **kwargs)

            if _runtime.VERBOSE:
                print(f"← {r.status_code} {r.reason_phrase}", file=sys.stderr)

            r.raise_for_status()
            if r.status_code == 204 or not r.content:
                return None
            try:
                return r.json()
            except Exception:
                return r.text
        except httpx.HTTPStatusError as e:
            _manejar_http_error(e)
        except httpx.RequestError as e:
            raise CloudError(f"Error de conexión: {e}", exit_code=2)

    # ── Verbos HTTP ───────────────────────────────────────────────────────────

    def get(self, path: str, *, params: Optional[dict] = None, token: Optional[str] = None, timeout: Optional[int] = None) -> Any:
        return self._request("GET", path, params=params, token=token, timeout=timeout)

    def post(self, path: str, *, body: Optional[dict] = None, params: Optional[dict] = None, token: Optional[str] = None, timeout: Optional[int] = None) -> Any:
        return self._request("POST", path, body=body, params=params, token=token, timeout=timeout)

    def put(self, path: str, *, body: Optional[dict] = None, params: Optional[dict] = None, token: Optional[str] = None, timeout: Optional[int] = None) -> Any:
        return self._request("PUT", path, body=body, params=params, token=token, timeout=timeout)

    def patch(self, path: str, *, body: Optional[dict] = None, params: Optional[dict] = None, token: Optional[str] = None, timeout: Optional[int] = None) -> Any:
        return self._request("PATCH", path, body=body, params=params, token=token, timeout=timeout)

    def delete(self, path: str, *, params: Optional[dict] = None, token: Optional[str] = None, timeout: Optional[int] = None) -> Any:
        return self._request("DELETE", path, params=params, token=token, timeout=timeout)
