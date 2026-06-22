"""
CliCommand — base class para comandos CLI con manejo uniforme de errores.

Encapsula el patrón repetido en `cli.py`:
    try:
        data = operacion()
    except CloudError as e:
        err_console.print(f"[red]✗ {e}[/red]")
        raise SystemExit(e.exit_code)

Ejemplo:
    from ragfly_cli.oop import CliCommand

    class MiComando(CliCommand):
        def ejecutar(self, x):
            data = self.protegido(lambda: cloud_get(f"/algo/{x}"))
            self.exito(f"Listo: {data}")

    MiComando().ejecutar("foo")
"""

from __future__ import annotations

import sys
from typing import Any, Callable, NoReturn

from rich.console import Console

from ragfly_cli.cloud_commands import CloudError


class CliCommand:
    """Base class para comandos CLI con consoles + helpers de output."""

    def __init__(self):
        self.console = Console()
        self.err_console = Console(stderr=True)

    # ── Output helpers ────────────────────────────────────────────────────────

    def exito(self, mensaje: str) -> None:
        self.console.print(f"[green]✓ {mensaje}[/green]")

    def error(self, mensaje: str) -> None:
        self.err_console.print(f"[red]✗ {mensaje}[/red]")

    def info(self, mensaje: str) -> None:
        self.console.print(f"[dim]{mensaje}[/dim]")

    def aviso(self, mensaje: str) -> None:
        self.console.print(f"[yellow]⚠ {mensaje}[/yellow]")

    def linea(self) -> None:
        self.console.print()

    # ── Ejecución protegida ───────────────────────────────────────────────────

    def protegido(
        self,
        fn: Callable[..., Any],
        *args,
        on_unexpected_exit_code: int = 2,
        **kwargs,
    ) -> Any:
        """
        Ejecuta `fn(*args, **kwargs)` capturando CloudError y excepciones imprevistas;
        imprime el error y termina con SystemExit usando el exit_code apropiado.
        """
        try:
            return fn(*args, **kwargs)
        except CloudError as e:
            self.error(str(e))
            raise SystemExit(e.exit_code)
        except SystemExit:
            raise
        except KeyboardInterrupt:
            self.aviso("Interrumpido.")
            raise SystemExit(130)
        except Exception as e:
            self.error(f"Error inesperado: {e}")
            raise SystemExit(on_unexpected_exit_code)

    def salir(self, mensaje: str, exit_code: int = 1) -> NoReturn:
        """Imprime el error y sale con el código dado."""
        self.error(mensaje)
        raise SystemExit(exit_code)
