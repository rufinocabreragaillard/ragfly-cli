"""Estado de runtime compartido por el CLI (flags globales).

Hoy solo lleva el flag `-v/--verbose`, que la capa HTTP (`oop/http_client.py`)
consulta para loggear método+URL+status de cada request a **stderr** — nunca a
stdout, para no contaminar la salida `-o json` que se pipea a `jq`.
"""

from __future__ import annotations

VERBOSE: bool = False


def set_verbose(value: bool) -> None:
    global VERBOSE
    VERBOSE = bool(value)
