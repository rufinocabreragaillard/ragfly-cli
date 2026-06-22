"""
Check de versión del RAGfly Cliente.

Consulta GET /version/cliente/latest al backend y compara con la versión actual.
Si hay una versión nueva, retorna un mensaje legible para mostrar al usuario.
Si no hay nueva versión o el backend no responde, retorna None silenciosamente
(la app sigue funcionando sin red).

Uso:

    from ragfly_cli.version_check import chequear_actualizacion
    aviso = chequear_actualizacion()
    if aviso:
        click.echo(aviso, err=True)
"""

from __future__ import annotations

import re
from typing import Optional

import httpx

from . import __version__
from ._http import default_headers

_RE_VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:(a|b|rc)(\d+))?")
_RANGO_PRE = {"a": 0, "b": 1, "rc": 2}  # final (sin pre) = 3, por encima de todas


def _version_tuple(v: str) -> tuple[int, ...]:
    """Ordena versiones PEP 440 simples: 2.0.0a8 < 2.0.0a9 < 2.0.0b1 < 2.0.0rc1 < 2.0.0.

    Devuelve (major, minor, patch, rango_pre, num_pre). El sufijo alfa/beta/rc
    YA NO se ignora (antes colapsaba a (0,) y el aviso de upgrade nunca se
    disparaba entre versiones aN). Una versión final ranquea por encima de sus
    pre-releases (rango 3 > 2/1/0).
    """
    m = _RE_VERSION.match(v.strip())
    if not m:
        return (0,)
    major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3))
    rango = _RANGO_PRE.get(m.group(4), 3)
    num_pre = int(m.group(5)) if m.group(5) else 0
    return (major, minor, patch, rango, num_pre)


def chequear_actualizacion(
    *,
    cloud_url: Optional[str] = None,
    timeout: int = 5,
) -> Optional[str]:
    """Consulta /version/cliente/latest. Si hay versión nueva, retorna aviso.

    Returns:
        - str con mensaje "Hay una nueva versión..." si versión actual < latest.
        - None si está al día, si no hay red, o si el endpoint no existe (404).

    Nota: silencioso ante errores de red — la app no debe romperse por esto.
    """
    if cloud_url is None:
        try:
            from .config import get_config
            cloud_url = get_config().cloud_url
        except Exception:
            return None

    url = f"{cloud_url.rstrip('/')}/version/cliente/latest"
    try:
        r = httpx.get(url, headers=default_headers(), timeout=timeout)
    except Exception:
        return None  # sin red u otro error: silencioso

    if r.status_code != 200:
        return None

    try:
        data = r.json()
    except Exception:
        return None

    latest = data.get("version")
    if not latest:
        return None

    if _version_tuple(__version__) >= _version_tuple(latest):
        return None  # estamos al día o más nuevos

    obligatoria = data.get("obligatoria", False)
    notas = data.get("notas") or ""
    prefix = "⚠️  ACTUALIZACIÓN OBLIGATORIA" if obligatoria else "ℹ️  Hay una nueva versión disponible"

    msg = f"{prefix}: RAGfly Desktop v{latest} (tu versión: v{__version__})"
    if notas:
        msg += f"\n   {notas}"
    return msg
