"""
Capa OOP del cliente — clases reutilizables para reducir duplicación.

Componentes:
  - CloudHttpClient — wrapper HTTP unificado contra la API cloud (GET/POST/PUT/DELETE)
  - CliCommand — base class para comandos CLI con manejo uniforme de errores
"""

from ragfly_cli.oop.http_client import CloudHttpClient
from ragfly_cli.oop.cli_command import CliCommand

__all__ = ["CloudHttpClient", "CliCommand"]
