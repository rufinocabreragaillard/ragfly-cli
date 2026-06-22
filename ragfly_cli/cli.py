"""
CLI principal de RAGfly — Cliente local y Cloud.

Comandos locales:
  ragfly version       — Versión del cliente
  ragfly estado        — Estado de la BD local
  ragfly setup         — Configuración inicial
  ragfly escanear      — Escanear directorio de documentos
  ragfly procesar      — Procesar documentos (CHUNKEAR; el cloud vectoriza)
  ragfly sync          — Sincronizar con el cloud
  ragfly api           — API local para integración
  ragfly gui           — Interfaz gráfica nativa (PySide6)

Comandos cloud:
  ragfly login         — Autenticar contra el cloud
  ragfly logout        — Cerrar sesión
  ragfly cloud me      — Ver contexto activo
  ragfly cloud documento listar/ver
  ragfly cloud espacio  listar/ver
  ragfly cloud cola     ver/ejecuciones
  ragfly cloud habilidad listar/ver/ejecutar
"""

import json
import sys

import click
import httpx
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from . import __version__
from ._http import default_headers

console = Console()
err_console = Console(stderr=True)


# ════════════════════════════════════════════════════════════════════════════
# Grupo raíz
# ════════════════════════════════════════════════════════════════════════════

@click.group()
def app():
    """RAGfly — Cliente local y Cloud."""
    pass


# ════════════════════════════════════════════════════════════════════════════
# Comandos globales: login / logout
# ════════════════════════════════════════════════════════════════════════════

@app.command()
@click.option("--email", "-e", default=None, help="Email (para uso no interactivo)")
@click.option("--password-stdin", is_flag=True, help="Lee la contraseña desde stdin")
def login(email: str | None, password_stdin: bool):
    """Autenticarse contra el cloud y guardar sesión."""
    from .cloud_commands import login as _login, CloudError

    console.print()
    if not email:
        email = click.prompt("  Email")

    if password_stdin:
        password = sys.stdin.readline().rstrip("\n")
    else:
        password = click.prompt("  Contraseña", hide_input=True)

    console.print()
    console.print("[dim]  Conectando...[/dim]", end="")

    try:
        data = _login(email, password)
    except CloudError as e:
        console.print()
        err_console.print(f"[red]✗ {e}[/red]")
        raise SystemExit(e.exit_code)

    console.print()
    console.print(f"[green]✓ Sesión iniciada como[/green] {email}")

    grupo = (
        data.get("grupo_activo")
        or data.get("usuario", {}).get("grupo_por_defecto", "")
        or "—"
    )
    entidad = (
        data.get("entidad_activa")
        or data.get("usuario", {}).get("entidad_por_defecto", "")
        or "—"
    )
    console.print(f"  Grupo activo:   {grupo}")
    console.print(f"  Entidad activa: {entidad}")
    console.print(f"  Sesión guardada en [dim]keyring del SO[/dim]")
    console.print()


@app.command()
def logout():
    """Cerrar sesión (elimina el JWT del keyring)."""
    from .cloud_commands import borrar_credenciales, ya_esta_logueado

    if ya_esta_logueado():
        borrar_credenciales()
        console.print("[green]✓ Sesión cerrada.[/green]")
    else:
        console.print("[yellow]No había sesión activa.[/yellow]")


# ════════════════════════════════════════════════════════════════════════════
# Sub-grupo: cloud
# ════════════════════════════════════════════════════════════════════════════

@app.group()
def cloud():
    """Operaciones contra el cloud de RAGfly (requiere ragfly login)."""
    pass


@cloud.command("me")
@click.option("-o", "--output", type=click.Choice(["tabla", "json"]), default="tabla")
def cloud_me(output: str):
    """Ver el contexto activo del usuario autenticado."""
    from .cloud_commands import cloud_get
    from .oop import CliCommand

    cmd = CliCommand()
    data = cmd.protegido(cloud_get, "/auth/me")

    if output == "json":
        console.print(json.dumps(data, indent=2, ensure_ascii=False))
        return

    console.print()
    # /auth/me retorna campos en el nivel raíz: codigo_usuario, nombre, grupo_activo, etc.
    tabla = Table(show_header=False, border_style="dim")
    tabla.add_column("Campo", style="bold")
    tabla.add_column("Valor")
    tabla.add_row("Usuario", data.get("codigo_usuario") or data.get("email", "—"))
    tabla.add_row("Nombre", data.get("nombre") or data.get("nombre_completo", "—"))
    tabla.add_row("Rol principal", data.get("rol_principal", "—"))
    tabla.add_row("Grupo activo", str(data.get("grupo_activo") or data.get("nombre_grupo", "—")))
    tabla.add_row("Entidad activa", str(data.get("entidad_activa") or data.get("nombre_entidad", "—")))
    console.print(tabla)
    console.print()


# ── cloud grupo ──────────────────────────────────────────────────────────────

@cloud.group("grupo")
def cloud_grupo():
    """Gestionar el grupo activo del cliente (paridad con dropdown del header web)."""
    pass


@cloud_grupo.command("listar")
@click.option("-o", "--output", type=click.Choice(["tabla", "json"]), default="tabla")
def cloud_grupo_listar(output: str):
    """Listar grupos disponibles para el usuario autenticado."""
    from .cloud_commands import obtener_token
    from .config import get_config
    from .grupo_activo import listar_grupos_disponibles, get_grupo_activo_local
    from .oop import CliCommand

    cmd = CliCommand()

    def _accion():
        token = obtener_token()
        return listar_grupos_disponibles(token, get_config().cloud_url)

    grupos = cmd.protegido(_accion)
    activo = get_grupo_activo_local()

    if output == "json":
        console.print(json.dumps({"activo": activo, "grupos": grupos}, indent=2, ensure_ascii=False))
        return

    console.print()
    if not grupos:
        console.print("[yellow]Sin grupos asignados.[/yellow]")
        return

    t = Table(title="Grupos disponibles", border_style="dim")
    t.add_column("", width=2)
    t.add_column("Código", style="bold")
    t.add_column("Nombre")
    t.add_column("Alias", style="dim")
    for g in grupos:
        marca = "[green]●[/green]" if g["codigo_grupo"] == activo else " "
        t.add_row(marca, g["codigo_grupo"], g.get("nombre_grupo") or "—", g.get("alias_grupo") or "—")
    console.print(t)
    if activo:
        console.print(f"  [dim]Grupo activo local: {activo}[/dim]")
    else:
        console.print("  [dim]Sin grupo activo local — usando defecto del usuario.[/dim]")
    console.print()


@cloud_grupo.command("cambiar")
@click.argument("codigo_grupo")
def cloud_grupo_cambiar(codigo_grupo: str):
    """Cambiar el grupo activo del cliente. Valida con el backend antes de persistir."""
    from .cloud_commands import obtener_token
    from .config import get_config
    from .grupo_activo import cambiar_grupo_remoto, set_grupo_activo
    from .oop import CliCommand

    cmd = CliCommand()

    def _accion():
        token = obtener_token()
        return cambiar_grupo_remoto(codigo_grupo, token, get_config().cloud_url)

    contexto = cmd.protegido(_accion)
    set_grupo_activo(codigo_grupo)

    nombre = contexto.get("nombre_grupo") or codigo_grupo
    console.print(f"[green]✓ Grupo activo cambiado a:[/green] [bold]{codigo_grupo}[/bold] ({nombre})")
    entidad = contexto.get("entidad_activa")
    if entidad:
        console.print(f"  Entidad activa: {entidad}")


@cloud_grupo.command("limpiar")
def cloud_grupo_limpiar():
    """Quitar el grupo activo local — vuelve al grupo por defecto del usuario."""
    from .grupo_activo import clear_grupo_activo, get_grupo_activo_local

    actual = get_grupo_activo_local()
    if not actual:
        console.print("[yellow]No hay grupo activo local configurado.[/yellow]")
        return
    clear_grupo_activo()
    console.print(f"[green]✓ Grupo activo local '{actual}' eliminado.[/green]")
    console.print("  El cliente usará el grupo por defecto del usuario en la próxima request.")


# ── cloud documento ──────────────────────────────────────────────────────────

@cloud.group("documento")
def cloud_documento():
    """Gestionar documentos en el cloud."""
    pass


@cloud_documento.command("listar")
@click.option("--estado", default=None, help="Filtrar por estado (ej. VECTORIZADO)")
@click.option("--limite", default=20, show_default=True)
@click.option("--pagina", default=1, show_default=True)
@click.option("-o", "--output", type=click.Choice(["tabla", "json", "csv"]), default="tabla")
def cloud_documento_listar(estado: str | None, limite: int, pagina: int, output: str):
    """Listar documentos del grupo activo."""
    from .cloud_commands import cloud_get
    from .oop import CliCommand

    params: dict = {"limite": limite, "pagina": pagina}
    if estado:
        params["estado"] = estado

    cmd = CliCommand()
    data = cmd.protegido(cloud_get, "/documentos/paginado", params=params)

    items = data.get("items", data) if isinstance(data, dict) else data

    if output == "json":
        console.print(json.dumps(items, indent=2, ensure_ascii=False, default=str))
        return

    if output == "csv":
        console.print("codigo,nombre,estado,ubicacion")
        for d in items:
            console.print(
                f"{d.get('codigo_documento','')},{d.get('nombre_documento','')}"
                f",{d.get('codigo_estado_doc','')},{d.get('nombre_ubicacion','')}"
            )
        return

    console.print()
    t = Table(title=f"Documentos (pág. {pagina})", border_style="dim")
    t.add_column("Código", style="dim", no_wrap=True)
    t.add_column("Nombre")
    t.add_column("Estado")
    t.add_column("Ubicación")
    t.add_column("Tamaño", justify="right")

    for d in items:
        estado_val = d.get("codigo_estado_doc", "—")
        color = {"VECTORIZADO": "green", "ESCANEADO": "cyan", "CARGADO": "yellow",
                 "REVISAR": "red", "CHUNKEADO": "blue"}.get(estado_val, "white")
        t.add_row(
            str(d.get("codigo_documento", "—")),
            d.get("nombre_documento", "—")[:50],
            f"[{color}]{estado_val}[/{color}]",
            d.get("nombre_ubicacion") or d.get("codigo_ubicacion", "—"),
            _fmt_bytes(d.get("tamano_bytes")),
        )
    console.print(t)

    total = data.get("total") if isinstance(data, dict) else None
    if total:
        console.print(f"  [dim]Total: {total} | Página {pagina}[/dim]")
    console.print()


@cloud_documento.command("ver")
@click.argument("codigo")
@click.option("-o", "--output", type=click.Choice(["tabla", "json"]), default="tabla")
def cloud_documento_ver(codigo: str, output: str):
    """Ver detalle de un documento."""
    from .cloud_commands import cloud_get
    from .oop import CliCommand

    cmd = CliCommand()
    data = cmd.protegido(cloud_get, f"/documentos/{codigo}")

    if output == "json":
        console.print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
        return

    console.print()
    t = Table(show_header=False, border_style="dim", title=f"Documento {codigo}")
    t.add_column("Campo", style="bold")
    t.add_column("Valor")
    t.add_row("Código", str(data.get("codigo_documento", "—")))
    t.add_row("Nombre", data.get("nombre_documento", "—"))
    t.add_row("Estado", data.get("codigo_estado_doc", "—"))
    t.add_row("Ubicación", data.get("nombre_ubicacion") or data.get("codigo_ubicacion", "—"))
    t.add_row("Tamaño", _fmt_bytes(data.get("tamano_bytes")))
    t.add_row("Páginas", str(data.get("total_paginas", "—")))
    t.add_row("Chunks", str(data.get("total_chunks", "—")))
    t.add_row("Creado", str(data.get("fecha_creacion", "—"))[:19])
    t.add_row("Procesado", str(data.get("fecha_actualizacion", "—"))[:19])
    if data.get("resumen_documento"):
        t.add_row("Resumen", data["resumen_documento"][:120])
    console.print(t)
    console.print()


# ── cloud espacio ────────────────────────────────────────────────────────────

@cloud.group("espacio")
def cloud_espacio():
    """Gestionar Espacios de Trabajo en el cloud."""
    pass


@cloud_espacio.command("listar")
@click.option("--limite", default=20, show_default=True)
@click.option("-o", "--output", type=click.Choice(["tabla", "json"]), default="tabla")
def cloud_espacio_listar(limite: int, output: str):
    """Listar Espacios de Trabajo del grupo activo."""
    from .cloud_commands import cloud_get
    from .oop import CliCommand

    cmd = CliCommand()
    data = cmd.protegido(cloud_get, "/espacios-trabajo/paginado", params={"limite": limite})

    items = data.get("items", data) if isinstance(data, dict) else data

    if output == "json":
        console.print(json.dumps(items, indent=2, ensure_ascii=False, default=str))
        return

    console.print()
    t = Table(title="Espacios de Trabajo", border_style="dim")
    t.add_column("ID", justify="right", style="dim")
    t.add_column("Nombre")
    t.add_column("Descripción")
    t.add_column("Docs", justify="right")
    t.add_column("Creado")

    for e in items:
        t.add_row(
            str(e.get("id_espacio", "—")),
            e.get("nombre_espacio", "—")[:40],
            (e.get("descripcion") or "")[:40],
            str(e.get("n_documentos", "—")),
            str(e.get("fecha_creacion", "—"))[:10],
        )
    console.print(t)
    console.print()


@cloud_espacio.command("ver")
@click.argument("id_espacio", type=int)
@click.option("--limite", default=20, show_default=True)
@click.option("-o", "--output", type=click.Choice(["tabla", "json"]), default="tabla")
def cloud_espacio_ver(id_espacio: int, limite: int, output: str):
    """Ver detalle de un Espacio de Trabajo con sus documentos."""
    from .cloud_commands import cloud_get
    from .oop import CliCommand

    cmd = CliCommand()
    # No hay GET /{id} suelto — buscamos en paginado y filtramos
    espacios_data = cmd.protegido(cloud_get, "/espacios-trabajo/paginado", params={"limite": 200})
    items_esp = espacios_data.get("items", espacios_data) if isinstance(espacios_data, dict) else espacios_data
    espacio = next((e for e in items_esp if e.get("id_espacio") == id_espacio), None)
    if not espacio:
        cmd.salir(f"Espacio #{id_espacio} no encontrado.", exit_code=1)
    docs_data = cmd.protegido(
        cloud_get,
        f"/espacios-trabajo/{id_espacio}/documentos/paginado",
        params={"limite": limite},
    )

    if output == "json":
        console.print(json.dumps({"espacio": espacio, "documentos": docs_data},
                                 indent=2, ensure_ascii=False, default=str))
        return

    console.print()
    info = Table(show_header=False, border_style="dim",
                 title=f"Espacio #{id_espacio}")
    info.add_column("Campo", style="bold")
    info.add_column("Valor")
    info.add_row("Nombre", espacio.get("nombre_espacio", "—"))
    info.add_row("Descripción", espacio.get("descripcion") or "—")
    info.add_row("Creado", str(espacio.get("fecha_creacion", "—"))[:19])
    console.print(info)
    console.print()

    docs = docs_data.get("items", docs_data) if isinstance(docs_data, dict) else docs_data
    if docs:
        t = Table(title=f"Documentos ({len(docs)})", border_style="dim")
        t.add_column("Código", style="dim")
        t.add_column("Nombre")
        t.add_column("Estado")
        t.add_column("Cola", justify="right")
        for d in docs:
            t.add_row(
                str(d.get("codigo_documento", "—")),
                d.get("nombre_documento", "—")[:45],
                d.get("codigo_estado_doc", "—"),
                d.get("estado_cola", "—"),
            )
        console.print(t)
    console.print()


# ── cloud cola ───────────────────────────────────────────────────────────────

@cloud.group("cola")
def cloud_cola():
    """Ver el estado de la cola de procesamiento."""
    pass


@cloud_cola.command("ver")
@click.option("--proceso", default=None, help="Filtrar por proceso (ej. VECTORIZAR)")
@click.option("--estado", default=None, help="Filtrar por estado (PENDIENTE, EJECUTANDO, etc.)")
@click.option("--limite", default=20, show_default=True)
@click.option("-o", "--output", type=click.Choice(["tabla", "json"]), default="tabla")
def cloud_cola_ver(proceso: str | None, estado: str | None, limite: int, output: str):
    """Ver el estado actual de la cola del pipeline."""
    from .cloud_commands import cloud_get
    from .oop import CliCommand

    params: dict = {"limite": limite}
    if proceso:
        params["proceso"] = proceso
    if estado:
        params["estado"] = estado

    cmd = CliCommand()
    data = cmd.protegido(cloud_get, "/cola-estados-docs/paginado", params=params)

    items = data.get("items", data) if isinstance(data, dict) else data

    if output == "json":
        console.print(json.dumps(items, indent=2, ensure_ascii=False, default=str))
        return

    console.print()
    t = Table(title="Cola de procesamiento", border_style="dim")
    t.add_column("ID", justify="right", style="dim")
    t.add_column("Proceso")
    t.add_column("Estado")
    t.add_column("Documento")
    t.add_column("Encolado")
    t.add_column("Error")

    _est_color = {
        "PENDIENTE": "yellow", "EJECUTANDO": "cyan",
        "TERMINADO": "green", "ERROR": "red",
    }
    for item in items:
        est = item.get("estado_cola", "—")
        t.add_row(
            str(item.get("id_cola", "—")),
            item.get("proceso") or item.get("codigo_habilidad", "—"),
            f"[{_est_color.get(est, 'white')}]{est}[/{_est_color.get(est, 'white')}]",
            str(item.get("codigo_documento", "—")),
            str(item.get("fecha_inicio", item.get("fecha_cola", "—")))[:16],
            (item.get("mensaje_error") or "")[:30],
        )
    console.print(t)

    total = data.get("total") if isinstance(data, dict) else None
    if total:
        console.print(f"  [dim]Total en cola: {total}[/dim]")
    console.print()


@cloud_cola.command("ejecuciones")
@click.option("--limite", default=10, show_default=True)
@click.option("-o", "--output", type=click.Choice(["tabla", "json"]), default="tabla")
def cloud_cola_ejecuciones(limite: int, output: str):
    """Ver historial de ejecuciones de habilidades."""
    from .cloud_commands import cloud_get
    from .oop import CliCommand

    cmd = CliCommand()
    data = cmd.protegido(cloud_get, "/cola-estados-docs/ejecuciones", params={"limite": limite})

    items = data.get("items", data) if isinstance(data, dict) else data

    if output == "json":
        console.print(json.dumps(items, indent=2, ensure_ascii=False, default=str))
        return

    console.print()
    t = Table(title="Historial de ejecuciones", border_style="dim")
    t.add_column("ID", justify="right", style="dim")
    t.add_column("Habilidad")
    t.add_column("Inicio")
    t.add_column("Fin")
    t.add_column("Docs", justify="right")
    t.add_column("OK", justify="right", style="green")
    t.add_column("Err", justify="right", style="red")
    t.add_column("Duración")

    for e in items:
        t.add_row(
            str(e.get("id_ejecucion") or e.get("id", "—")),
            e.get("codigo_habilidad", "—"),
            str(e.get("fecha_inicio", "—"))[:16],
            str(e.get("fecha_fin", "—"))[:16],
            str(e.get("total_docs", "—")),
            str(e.get("docs_ok", "—")),
            str(e.get("docs_error", "—")),
            e.get("duracion") or "—",
        )
    console.print(t)
    console.print()


# ── cloud habilidad ──────────────────────────────────────────────────────────

@cloud.group("habilidad")
def cloud_habilidad():
    """Gestionar y ejecutar habilidades LLM del catálogo global."""
    pass


@cloud_habilidad.command("listar")
@click.option("-o", "--output", type=click.Choice(["tabla", "json"]), default="tabla")
def cloud_habilidad_listar(output: str):
    """Listar todas las habilidades disponibles."""
    from .cloud_commands import cloud_get
    from .oop import CliCommand

    cmd = CliCommand()
    items = cmd.protegido(cloud_get, "/habilidades")

    if output == "json":
        console.print(json.dumps(items, indent=2, ensure_ascii=False, default=str))
        return

    console.print()
    t = Table(title="Habilidades disponibles", border_style="dim")
    t.add_column("Código", style="bold")
    t.add_column("Nombre")
    t.add_column("Tipo")
    t.add_column("Salida")
    t.add_column("Modelo")

    for h in items:
        t.add_row(
            h.get("codigo_habilidad", "—"),
            h.get("nombre_habilidad") or h.get("alias", "—"),
            h.get("aplica_a", "—"),
            h.get("salida_destino", "—"),
            h.get("id_modelo") or "[dim]del invocador[/dim]",
        )
    console.print(t)
    console.print()


@cloud_habilidad.command("ver")
@click.argument("codigo")
@click.option("-o", "--output", type=click.Choice(["tabla", "json"]), default="tabla")
def cloud_habilidad_ver(codigo: str, output: str):
    """Ver detalle de una habilidad."""
    from .cloud_commands import cloud_get
    from .oop import CliCommand

    cmd = CliCommand()
    h = cmd.protegido(cloud_get, f"/habilidades/{codigo}")

    if output == "json":
        console.print(json.dumps(h, indent=2, ensure_ascii=False, default=str))
        return

    console.print()
    t = Table(show_header=False, border_style="dim",
              title=f"Habilidad {codigo}")
    t.add_column("Campo", style="bold")
    t.add_column("Valor")
    t.add_row("Código", h.get("codigo_habilidad", "—"))
    t.add_row("Nombre", h.get("nombre_habilidad") or h.get("alias", "—"))
    t.add_row("Tipo", h.get("aplica_a", "—"))
    t.add_row("Modelo", h.get("id_modelo") or "[dim]del invocador[/dim]")
    t.add_row("Salida", h.get("salida_destino", "—"))
    t.add_row("Col. salida", h.get("salida_columna") or "—")
    console.print(t)

    if h.get("prompt_habilidad"):
        console.print()
        console.print("[bold]Prompt:[/bold]")
        console.print(f"  [dim]{h['prompt_habilidad'][:300]}[/dim]")
    if h.get("system_prompt"):
        console.print()
        console.print("[bold]System prompt:[/bold]")
        console.print(f"  [dim]{h['system_prompt'][:200]}[/dim]")
    console.print()


@cloud_habilidad.command("ejecutar")
@click.argument("codigo")
@click.option("--espacio", type=int, default=None, help="ID del Espacio de Trabajo")
@click.option("--documento", default=None, help="Código de documento único")
@click.option("--esperar", is_flag=True, help="Esperar a que termine y mostrar resultado")
@click.option("-o", "--output", type=click.Choice(["tabla", "json"]), default="tabla")
def cloud_habilidad_ejecutar(
    codigo: str, espacio: int | None, documento: str | None,
    esperar: bool, output: str
):
    """Ejecutar una habilidad sobre un Espacio de Trabajo o documento."""
    from .cloud_commands import cloud_post
    from .oop import CliCommand

    cmd = CliCommand()
    if not espacio and not documento:
        cmd.salir("Debes indicar --espacio <ID> o --documento <CODIGO>", exit_code=1)

    body: dict = {}
    if espacio:
        body["id_espacio"] = espacio
    if documento:
        body["codigo_documento"] = documento

    resultado = cmd.protegido(cloud_post, f"/habilidades/{codigo}/ejecutar", body=body)

    if output == "json":
        console.print(json.dumps(resultado, indent=2, ensure_ascii=False, default=str))
        return

    # Contrato uniforme (SobreEjecucion): codigo_proceso + detalle.n_items_cola.
    detalle = resultado.get("detalle") or {}
    proceso = resultado.get("codigo_proceso", "—")
    docs = detalle.get("n_items_cola", resultado.get("n_documentos", "—"))
    no_proc = detalle.get("n_no_procesables", 0)
    estado = resultado.get("estado", "PENDIENTE")

    console.print()
    console.print(f"[green]✓ Encolado[/green]" if resultado.get("aceptada", True)
                  else "[red]✗ No aceptada[/red]")
    console.print(f"  Proceso      : {proceso}")
    console.print(f"  Documentos   : {docs}")
    if no_proc:
        console.print(f"  No procesables: {no_proc}")
    console.print(f"  Estado       : {estado}")
    if resultado.get("mensaje"):
        console.print(f"  [dim]{resultado.get('mensaje')}[/dim]")
    console.print()
    console.print(f"  Sigue progreso: [dim]ragfly cloud cola ver[/dim]")
    console.print()


# ════════════════════════════════════════════════════════════════════════════
# Sub-comando: cloud catalogo (capabilities — contrato multi-interfaz)
# ════════════════════════════════════════════════════════════════════════════

@cloud.command("catalogo")
@click.option("--tipo", type=click.Choice(["TODO", "FUNCIONES", "HABILIDADES"]),
              default="TODO", show_default=True, help="Qué parte del catálogo listar")
@click.option("-o", "--output", type=click.Choice(["tabla", "json"]), default="tabla")
def cloud_catalogo(tipo: str, output: str):
    """Catálogo de capabilities: qué puede hacer el usuario (funciones + habilidades).

    Mismo contrato que consumen el chat y MCP (GET /catalogo). Filtrado por el
    rol, tipo de acceso, grupo y aplicación del usuario.
    """
    from .cloud_commands import cloud_get
    from .oop import CliCommand

    cmd = CliCommand()
    data = cmd.protegido(cloud_get, "/catalogo", params={"tipo": tipo})

    if output == "json":
        console.print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
        return

    funciones = data.get("funciones", [])
    habilidades = data.get("habilidades", [])

    if funciones:
        console.print()
        t = Table(title=f"Funciones disponibles ({len(funciones)})", border_style="dim")
        t.add_column("Código", style="bold")
        t.add_column("Nombre")
        t.add_column("Resumen")
        t.add_column("Permisos")
        for f in funciones:
            perms = "".join([
                "S" if f.get("perm_select") else "-",
                "I" if f.get("perm_insert") else "-",
                "U" if f.get("perm_update") else "-",
                "D" if f.get("perm_delete") else "-",
            ])
            t.add_row(
                f.get("codigo_funcion", "—"),
                f.get("nombre_funcion") or "—",
                (f.get("descripcion_llm") or f.get("descripcion") or "")[:80],
                perms,
            )
        console.print(t)

    if habilidades:
        console.print()
        t = Table(title=f"Habilidades disponibles ({len(habilidades)})", border_style="dim")
        t.add_column("Código", style="bold")
        t.add_column("Nombre")
        t.add_column("Resumen")
        for h in habilidades:
            t.add_row(
                h.get("codigo_habilidad", "—"),
                h.get("nombre_habilidad") or "—",
                (h.get("descripcion_llm") or h.get("descripcion") or "")[:80],
            )
        console.print(t)

    if not funciones and not habilidades:
        console.print("[dim]Sin capabilities disponibles para este contexto.[/dim]")
    console.print()


# ════════════════════════════════════════════════════════════════════════════
# Sub-grupo: cloud buscar (RAG one-shot)
# ════════════════════════════════════════════════════════════════════════════

@cloud.command("buscar")
@click.argument("consulta", nargs=-1, required=True)
@click.option("--limite", type=int, default=10, show_default=True,
              help="Top-K final tras rerank")
@click.option("--min-similitud", type=float, default=0.0, show_default=True,
              help="Umbral coseno mínimo")
@click.option("--entidad", default=None, help="Filtrar por código de entidad")
@click.option("-o", "--output", type=click.Choice(["tabla", "json"]), default="tabla")
def cloud_buscar(
    consulta: tuple[str, ...], limite: int, min_similitud: float,
    entidad: str | None, output: str,
):
    """Búsqueda semántica RAG sobre los documentos vectorizados del grupo."""
    from .cloud_commands import cloud_post
    from .oop import CliCommand

    q = " ".join(consulta).strip()
    if not q:
        err_console.print("[red]La consulta no puede estar vacía.[/red]")
        raise SystemExit(1)

    body: dict = {"q": q, "limit": limite, "min_similitud": min_similitud}
    if entidad:
        body["codigo_entidad"] = entidad

    cmd = CliCommand()
    data = cmd.protegido(cloud_post, "/documentos/buscar-semantico", body=body)

    if output == "json":
        console.print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
        return

    items = data.get("resultados") or data.get("items") or data if isinstance(data, list) else (
        data.get("resultados") or data.get("items") or []
    )
    if not items:
        console.print("[yellow]Sin resultados.[/yellow]")
        return

    tabla = Table(title=f"RAG: {q[:60]}", show_lines=False)
    tabla.add_column("#", style="dim", width=3)
    tabla.add_column("Documento", overflow="fold")
    tabla.add_column("Score", justify="right", width=8)
    tabla.add_column("Fragmento", overflow="fold")
    for i, h in enumerate(items, 1):
        score = h.get("score") or h.get("similitud") or h.get("rerank_score") or 0
        nombre = h.get("nombre_documento") or h.get("codigo_documento") or "—"
        frag = (h.get("texto") or h.get("chunk_texto") or "")[:200]
        tabla.add_row(str(i), str(nombre), f"{float(score):.3f}" if isinstance(score, (int, float)) else str(score), frag)
    console.print(tabla)


# ════════════════════════════════════════════════════════════════════════════
# Sub-grupo: cloud chat (RAG conversacional)
# ════════════════════════════════════════════════════════════════════════════

@cloud.group("chat")
def cloud_chat():
    """Conversar con tus documentos vía RAG."""
    pass


@cloud_chat.command("preguntar")
@click.argument("mensaje", nargs=-1, required=True)
@click.option("--funcion", default="CHAT-USUARIO", show_default=True,
              help="Código de función del chat")
@click.option("--conversacion", "id_conversacion", type=int, default=None,
              help="ID de conversación existente (omitir = crear nueva)")
@click.option("--titulo", default=None, help="Título inicial (al crear nueva)")
@click.option("-o", "--output", type=click.Choice(["texto", "json"]), default="texto")
def cloud_chat_preguntar(
    mensaje: tuple[str, ...], funcion: str, id_conversacion: int | None,
    titulo: str | None, output: str,
):
    """Hacer una pregunta al chat RAG. Crea conversación si no se indica una."""
    from .cloud_commands import cloud_post, _headers, CLOUD_URL, CloudError
    from .oop import CliCommand

    contenido = " ".join(mensaje).strip()
    if not contenido:
        err_console.print("[red]El mensaje no puede estar vacío.[/red]")
        raise SystemExit(1)

    cmd = CliCommand()

    if not id_conversacion:
        body_conv = {"codigo_funcion": funcion}
        if titulo:
            body_conv["titulo"] = titulo
        nueva = cmd.protegido(cloud_post, "/chat/conversaciones", body=body_conv)
        id_conversacion = int(nueva.get("id_conversacion") or 0)
        if not id_conversacion:
            err_console.print(f"[red]No se pudo crear conversación: {nueva}[/red]")
            raise SystemExit(2)

    url = f"{CLOUD_URL}/chat/conversaciones/{id_conversacion}/mensajes/stream"
    try:
        with httpx.stream(
            "POST", url, headers=_headers(), json={"contenido": contenido}, timeout=120.0,
        ) as r:
            if r.status_code >= 400:
                err_console.print(f"[red]HTTP {r.status_code}: {r.read()[:300].decode('utf-8', errors='replace')}[/red]")
                raise SystemExit(2)
            partes: list[str] = []
            meta: dict = {}
            for raw in r.iter_lines():
                if not raw or not raw.startswith("data:"):
                    continue
                payload = raw[5:].strip()
                if not payload:
                    continue
                try:
                    evt = json.loads(payload)
                except Exception:
                    continue
                if "text" in evt:
                    chunk = str(evt["text"])
                    partes.append(chunk)
                    if output == "texto":
                        console.print(chunk, end="", soft_wrap=True)
                elif "done" in evt:
                    meta = {k: v for k, v in evt.items() if k != "done"}
                elif "error" in evt:
                    err_console.print(f"\n[red]Error del servidor: {evt['error']}[/red]")
                    raise SystemExit(2)
    except httpx.RequestError as e:
        raise CloudError(f"No se pudo conectar al servidor: {e}", exit_code=2)

    if output == "json":
        console.print(json.dumps({
            "id_conversacion": id_conversacion,
            "respuesta": "".join(partes),
            **meta,
        }, indent=2, ensure_ascii=False, default=str))
    else:
        console.print()
        console.print(f"[dim]Conversación #{id_conversacion}[/dim]")


# ════════════════════════════════════════════════════════════════════════════
# Helpers internos
# ════════════════════════════════════════════════════════════════════════════

def _fmt_bytes(b: int | None) -> str:
    if b is None:
        return "—"
    for unit in ("B", "KB", "MB", "GB"):
        if b < 1024:
            return f"{b:.0f} {unit}"
        b //= 1024
    return f"{b} TB"


@app.command()
def version():
    """Muestra la versión del cliente y avisa si hay actualización disponible."""
    console.print(f"[bold blue]RAGfly[/bold blue] Cliente v{__version__}")
    try:
        from .version_check import chequear_actualizacion
        aviso = chequear_actualizacion()
        if aviso:
            console.print(f"[yellow]{aviso}[/yellow]")
    except Exception:
        pass  # silencioso: no romper version si no hay config/red


