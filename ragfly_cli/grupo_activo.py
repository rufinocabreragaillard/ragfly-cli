"""
Gestión del grupo activo del RAGfly Cliente.

El cliente sigue el mismo modelo que el dropdown del header web: el grupo
activo es un override de sesión (no persiste en BD del cloud), pero sí se
guarda localmente en `~/.ragfly/config.env` para que sobreviva entre
ejecuciones del cliente.

Funciones:
    listar_grupos_disponibles(token) -> list[dict]
    set_grupo_activo(codigo_grupo) -> None
    clear_grupo_activo() -> None
    get_grupo_activo_local() -> str | None
    cambiar_grupo_remoto(codigo_grupo, token) -> dict   # valida con backend
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import httpx

from ._http import default_headers


def _config_path() -> Path:
    """Ruta al config.env (resuelta al llamar)."""
    from .config import _get_home
    return _get_home() / "config.env"


# ── Persistencia local en ~/.ragfly/config.env ──────────────────────────────


def get_grupo_activo_local() -> Optional[str]:
    """Lee el grupo activo desde config (cargado por pydantic-settings)."""
    from .config import get_config
    return get_config().codigo_grupo or None


def set_grupo_activo(codigo_grupo: str) -> None:
    """Persiste `RAGFLY_CODIGO_GRUPO=codigo_grupo` en config.env.

    Si la línea ya existe la reemplaza; si no, la agrega al final.
    Invalida el cache de get_config() para que la próxima lectura sea fresca.
    """
    path = _config_path()
    if not path.exists():
        raise FileNotFoundError(
            f"No existe {path}. Ejecuta `ragfly setup` primero."
        )

    content = path.read_text()
    pattern = re.compile(r"^RAGFLY_CODIGO_GRUPO=.*$", re.MULTILINE)
    new_line = f"RAGFLY_CODIGO_GRUPO={codigo_grupo}"

    if pattern.search(content):
        content = pattern.sub(new_line, content)
    else:
        if not content.endswith("\n"):
            content += "\n"
        content += new_line + "\n"

    path.write_text(content)

    from .config import get_config
    get_config.cache_clear()


def clear_grupo_activo() -> None:
    """Quita RAGFLY_CODIGO_GRUPO del config.env (vuelve a grupo defecto del usuario)."""
    set_grupo_activo("")


def set_directorio_documentos(directorio: str) -> None:
    """Persiste `RAGFLY_DIRECTORIO_DOCUMENTOS` en config.env (lo usa el pipeline
    para resolver la ruta absoluta de cada archivo al extraer texto).

    Crea el config.env si no existe (puede ocurrir antes del primer `setup`).
    Invalida el cache de get_config() para que la próxima lectura sea fresca.
    """
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    content = path.read_text() if path.exists() else ""

    pattern = re.compile(r"^RAGFLY_DIRECTORIO_DOCUMENTOS=.*$", re.MULTILINE)
    new_line = f"RAGFLY_DIRECTORIO_DOCUMENTOS={directorio}"
    if pattern.search(content):
        content = pattern.sub(new_line, content)
    else:
        if content and not content.endswith("\n"):
            content += "\n"
        content += new_line + "\n"
    path.write_text(content)

    from .config import get_config
    get_config.cache_clear()


# ── Operaciones contra el backend cloud ──────────────────────────────────────


def listar_grupos_disponibles(token: str, cloud_url: str, *, timeout: int = 15) -> list[dict]:
    """Retorna la lista de grupos a los que el usuario tiene acceso.

    Cada item: `{codigo_grupo, nombre_grupo, alias_grupo}`.
    """
    r = httpx.get(
        f"{cloud_url.rstrip('/')}/auth/me",
        headers=default_headers(token=token),
        timeout=timeout,
    )
    r.raise_for_status()
    data = r.json()
    return [
        {
            "codigo_grupo": g.get("codigo_grupo"),
            "nombre_grupo": g.get("nombre_grupo"),
            "alias_grupo": g.get("alias_grupo"),
        }
        for g in data.get("grupos", [])
    ]


def cambiar_grupo_remoto(
    codigo_grupo: str, token: str, cloud_url: str, *, timeout: int = 15
) -> dict:
    """Llama POST /auth/cambiar-grupo para validar pertenencia y obtener contexto.

    Retorna el `UsuarioContexto` actualizado del backend.
    Lanza httpx.HTTPStatusError si el grupo no existe o el usuario no tiene acceso.
    """
    r = httpx.post(
        f"{cloud_url.rstrip('/')}/auth/cambiar-grupo",
        headers=default_headers(token=token, content_type=True),
        json={"codigo_grupo": codigo_grupo},
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json()
