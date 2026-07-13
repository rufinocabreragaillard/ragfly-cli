"""
Main RAGfly CLI — `ragfly-cli` package (the `ragfly` binary).

Commands:
  ragfly version       — Client version
  ragfly login         — Authenticate against the cloud
  ragfly logout        — Log out
  ragfly cloud me      — Show active context
  ragfly cloud group     list/switch/clear
  ragfly cloud api-key   create/list/revoke
  ragfly cloud document  list/show
  ragfly cloud space     list/show
  ragfly cloud queue     show/runs
  ragfly cloud skill     list/show/run
  ragfly cloud catalog
  ragfly cloud search
  ragfly cloud chat      ask

Legacy Spanish command/flag names are kept as compatibility aliases so existing
scripts keep working.

Local filesystem operations (`ragfly local scan/sync/daemon`) do NOT live in
this package: they ship with RAGfly Desktop.

Global flags: `-o {table,json,csv,id}` (per command) and `-v/--verbose`
(method+URL+status of each request, to stderr). `-v` goes before the
subcommand: `ragfly -v cloud document list`.
"""

import json
import sys

import click
import httpx
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from . import __version__, _runtime
from ._http import default_headers

console = Console()
err_console = Console(stderr=True)


# ── Raw stdout output (pipe-safe) ────────────────────────────────────────────
# Rich (`console.print`) interprets `[...]` as markup and soft-wraps to the
# terminal width: both break JSON/CSV when piped to `jq` or another tool.
# For machine-readable data we write straight to stdout with click.echo.

def _emit_json(obj) -> None:
    """Print raw JSON to stdout, bypassing Rich. Safe for `| jq`."""
    click.echo(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def _emit_ids(items, *keys: str) -> None:
    """Print one id per line (the first `key` present in each item). For
    `-o id` in pipes. Accepts a bare dict (single resource) or a list."""
    if isinstance(items, dict):
        items = [items]
    for it in items or []:
        if not isinstance(it, dict):
            click.echo(str(it))
            continue
        for k in keys:
            val = it.get(k)
            if val not in (None, ""):
                click.echo(str(val))
                break


# ════════════════════════════════════════════════════════════════════════════
# Root group
# ════════════════════════════════════════════════════════════════════════════

@click.group()
@click.option("-v", "--verbose", is_flag=True,
              help="Show method+URL+status of each request (to stderr).")
def app(verbose: bool):
    """RAGfly — `ragfly-cli` package (the `ragfly` binary)."""
    if verbose:
        _runtime.set_verbose(True)


# ════════════════════════════════════════════════════════════════════════════
# Global commands: login / logout
# ════════════════════════════════════════════════════════════════════════════

@app.command()
@click.option("--email", "-e", default=None, help="Email (for non-interactive use)")
@click.option("--password-stdin", is_flag=True, help="Read the password from stdin")
def login(email: str | None, password_stdin: bool):
    """Authenticate against the cloud and store the session."""
    from .cloud_commands import login as _login, CloudError

    console.print()
    if not email:
        email = click.prompt("  Email")

    if password_stdin:
        password = sys.stdin.readline().rstrip("\n")
    else:
        password = click.prompt("  Password", hide_input=True)

    console.print()
    console.print("[dim]  Connecting...[/dim]", end="")

    try:
        data = _login(email, password)
    except CloudError as e:
        console.print()
        err_console.print(f"[red]✗ {e}[/red]")
        raise SystemExit(e.exit_code)

    console.print()
    console.print(f"[green]✓ Logged in as[/green] {email}")

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
    console.print(f"  Active group:  {grupo}")
    console.print(f"  Active entity: {entidad}")
    console.print(f"  Session stored in [dim]OS keyring[/dim]")
    console.print()


@app.command()
def logout():
    """Log out (removes the JWT from the keyring)."""
    from .cloud_commands import borrar_credenciales, ya_esta_logueado

    if ya_esta_logueado():
        borrar_credenciales()
        console.print("[green]✓ Logged out.[/green]")
    else:
        console.print("[yellow]No active session.[/yellow]")


# ════════════════════════════════════════════════════════════════════════════
# Sub-group: cloud
# ════════════════════════════════════════════════════════════════════════════

@app.group()
def cloud():
    """Operations against the RAGfly cloud (requires ragfly login)."""
    pass


@cloud.command("me")
@click.option("-o", "--output", type=click.Choice(["table", "tabla", "json"]), default="table")
def cloud_me(output: str):
    """Show the active context of the authenticated user."""
    from .cloud_commands import cloud_get
    from .oop import CliCommand

    cmd = CliCommand()
    data = cmd.protegido(cloud_get, "/auth/me")

    if output == "json":
        click.echo(json.dumps(data, indent=2, ensure_ascii=False))
        return

    console.print()
    # /auth/me returns fields at the root level: codigo_usuario, nombre, grupo_activo, etc.
    tabla = Table(show_header=False, border_style="dim")
    tabla.add_column("Field", style="bold")
    tabla.add_column("Value")
    tabla.add_row("User", data.get("codigo_usuario") or data.get("email", "—"))
    tabla.add_row("Name", data.get("nombre") or data.get("nombre_completo", "—"))
    tabla.add_row("Primary role", data.get("rol_principal", "—"))
    tabla.add_row("Active group", str(data.get("grupo_activo") or data.get("nombre_grupo", "—")))
    tabla.add_row("Active entity", str(data.get("entidad_activa") or data.get("nombre_entidad", "—")))
    console.print(tabla)
    console.print()


# ── cloud group ──────────────────────────────────────────────────────────────

@cloud.group("group")
def cloud_grupo():
    """Manage the client's active group (parity with the web header dropdown)."""
    pass


@cloud_grupo.command("list")
@click.option("-o", "--output", type=click.Choice(["table", "tabla", "json"]), default="table")
def cloud_grupo_listar(output: str):
    """List groups available to the authenticated user."""
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
        click.echo(json.dumps({"activo": activo, "grupos": grupos}, indent=2, ensure_ascii=False))
        return

    console.print()
    if not grupos:
        console.print("[yellow]No groups assigned.[/yellow]")
        return

    t = Table(title="Available groups", border_style="dim")
    t.add_column("", width=2)
    t.add_column("Code", style="bold")
    t.add_column("Name")
    t.add_column("Alias", style="dim")
    for g in grupos:
        marca = "[green]●[/green]" if g["codigo_grupo"] == activo else " "
        t.add_row(marca, g["codigo_grupo"], g.get("nombre_grupo") or "—", g.get("alias_grupo") or "—")
    console.print(t)
    if activo:
        console.print(f"  [dim]Local active group: {activo}[/dim]")
    else:
        console.print("  [dim]No local active group — using the user's default.[/dim]")
    console.print()


@cloud_grupo.command("switch")
@click.argument("codigo_grupo")
def cloud_grupo_cambiar(codigo_grupo: str):
    """Switch the client's active group. Validates with the backend before persisting."""
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
    console.print(f"[green]✓ Active group switched to:[/green] [bold]{codigo_grupo}[/bold] ({nombre})")
    entidad = contexto.get("entidad_activa")
    if entidad:
        console.print(f"  Active entity: {entidad}")


@cloud_grupo.command("clear")
def cloud_grupo_limpiar():
    """Clear the local active group — reverts to the user's default group."""
    from .grupo_activo import clear_grupo_activo, get_grupo_activo_local

    actual = get_grupo_activo_local()
    if not actual:
        console.print("[yellow]No local active group configured.[/yellow]")
        return
    clear_grupo_activo()
    console.print(f"[green]✓ Local active group '{actual}' cleared.[/green]")
    console.print("  The client will use the user's default group on the next request.")


# compat aliases (Spanish)
cloud_grupo.add_command(cloud_grupo_listar, name="listar")
cloud_grupo.add_command(cloud_grupo_cambiar, name="cambiar")
cloud_grupo.add_command(cloud_grupo_limpiar, name="limpiar")


# ── cloud api-key ─────────────────────────────────────────────────────────────

@cloud.group("api-key")
def cloud_api_key():
    """Manage long-lived API Keys (CI / automation, no expiration)."""
    pass


@cloud_api_key.command("create")
@click.option("--name", "--nombre", "nombre", required=True, help="Descriptive name for the key (e.g. pipeline-ci)")
@click.option("--role", "--rol", "rol", default=None, help="Requested role (e.g. DOC-ADMIN, DOCS-USUARIO-FINAL). Default: owner's primary role")
@click.option("--area", default=None, help="Scope the key to an area subtree (default: inherits the user's)")
@click.option("--target-user", "--usuario-destino", "usuario_destino", default=None, help="(admin) create the key for another user in the group")
@click.option("-o", "--output", type=click.Choice(["text", "texto", "json"]), default="text")
def cloud_api_key_crear(nombre: str, rol: str | None, area: str | None, usuario_destino: str | None, output: str):
    """Create an API Key. The secret is shown ONLY once."""
    from .cloud_commands import cloud_post
    from .oop import CliCommand

    body: dict = {"nombre": nombre}
    if rol:
        body["rol_solicitado"] = rol
    if area:
        body["codigo_area"] = area
    if usuario_destino:
        body["codigo_usuario_destino"] = usuario_destino

    cmd = CliCommand()
    data = cmd.protegido(cloud_post, "/auth/api-key", body)

    if output == "json":
        click.echo(json.dumps(data, indent=2, ensure_ascii=False, default=str))
        return

    console.print()
    console.print(f"[green]✓ API Key created:[/green] [bold]{data.get('nombre')}[/bold]")
    console.print(Panel(
        f"[bold yellow]{data.get('api_key')}[/bold yellow]",
        title="Save it NOW — it won't be shown again",
        border_style="yellow",
    ))
    console.print(f"  Prefix: [dim]{data.get('prefijo')}[/dim]   Role: {data.get('codigo_rol') or '—'}   Group: {data.get('codigo_grupo')}")
    console.print(f"  Usage: [dim]export RAGFLY_API_KEY={data.get('api_key')}[/dim]")
    console.print()


@cloud_api_key.command("list")
@click.option("-o", "--output", type=click.Choice(["table", "tabla", "json"]), default="table")
def cloud_api_key_listar(output: str):
    """List the user's API Keys (without the secret, prefix only)."""
    from .cloud_commands import cloud_get
    from .oop import CliCommand

    cmd = CliCommand()
    data = cmd.protegido(cloud_get, "/auth/api-key")
    items = data if isinstance(data, list) else data.get("items", [])

    if output == "json":
        click.echo(json.dumps(items, indent=2, ensure_ascii=False, default=str))
        return

    console.print()
    if not items:
        console.print("[yellow]You have no API Keys.[/yellow] Create one with `ragfly cloud api-key create --name ...`.")
        return

    t = Table(title="API Keys", border_style="dim")
    t.add_column("Prefix", style="bold")
    t.add_column("Name")
    t.add_column("Role", style="dim")
    t.add_column("Area", style="dim")
    t.add_column("Created")
    t.add_column("Last used")
    t.add_column("Status")
    for k in items:
        revocada = k.get("revocada_en")
        estado = "[red]revoked[/red]" if revocada else "[green]active[/green]"
        t.add_row(
            k.get("prefijo") or "—",
            k.get("nombre") or "—",
            k.get("codigo_rol") or "—",
            k.get("codigo_area") or "—",
            (k.get("creada_en") or "—")[:10],
            (k.get("ultimo_uso") or "—")[:10],
            estado,
        )
    console.print(t)
    console.print()


@cloud_api_key.command("revoke")
@click.argument("prefijo")
def cloud_api_key_revocar(prefijo: str):
    """Revoke an API Key by its prefix (stops authenticating immediately)."""
    from .cloud_commands import cloud_delete
    from .oop import CliCommand

    cmd = CliCommand()
    cmd.protegido(cloud_delete, f"/auth/api-key/{prefijo}")
    console.print(f"[green]✓ API Key revoked:[/green] [bold]{prefijo}[/bold]")


# compat aliases (Spanish)
cloud_api_key.add_command(cloud_api_key_crear, name="crear")
cloud_api_key.add_command(cloud_api_key_listar, name="listar")
cloud_api_key.add_command(cloud_api_key_revocar, name="revocar")


# ── cloud document ───────────────────────────────────────────────────────────

@cloud.group("document")
def cloud_documento():
    """Manage documents in the cloud."""
    pass


@cloud_documento.command("list")
@click.option("--status", "--estado", "estado", default=None, help="Filter by status (e.g. VECTORIZADO)")
@click.option("--limit", "--limite", "limite", default=20, show_default=True)
@click.option("--page", "--pagina", "pagina", default=1, show_default=True)
@click.option("-o", "--output", type=click.Choice(["table", "tabla", "json", "csv", "id"]), default="table")
def cloud_documento_listar(estado: str | None, limite: int, pagina: int, output: str):
    """List documents of the active group."""
    from .cloud_commands import cloud_get
    from .oop import CliCommand
    from . import codes

    # The backend (GET /documentos/paginado) expects limit/page/codigo_estado_doc.
    # The dev types the English public code (VECTORIZED); translate it to the
    # internal code on the wire, and the returned codes back to English below.
    params: dict = {"limit": limite, "page": pagina}
    if estado:
        params["codigo_estado_doc"] = codes.to_internal("status", estado)

    cmd = CliCommand()
    data = cmd.protegido(cloud_get, "/documentos/paginado", params=params)

    items = data.get("items", data) if isinstance(data, dict) else data
    for d in items or []:
        if isinstance(d, dict):
            if d.get("codigo_estado_doc"):
                d["codigo_estado_doc"] = codes.to_english("status", d["codigo_estado_doc"])
            if d.get("codigo_tipo_documento"):
                d["codigo_tipo_documento"] = codes.to_english("doc_type", d["codigo_tipo_documento"])

    if output == "json":
        _emit_json(items)
        return

    if output == "id":
        _emit_ids(items, "codigo_documento")
        return

    if output == "csv":
        click.echo("code,name,status,location")
        for d in items:
            click.echo(
                f"{d.get('codigo_documento','')},{d.get('nombre_documento','')}"
                f",{d.get('codigo_estado_doc','')},{d.get('nombre_ubicacion','')}"
            )
        return

    console.print()
    t = Table(title=f"Documents (page {pagina})", border_style="dim")
    t.add_column("Code", style="dim", no_wrap=True)
    t.add_column("Name")
    t.add_column("Status")
    t.add_column("Location")
    t.add_column("Size", justify="right")

    for d in items:
        estado_val = d.get("codigo_estado_doc", "—")
        color = {"VECTORIZADO": "green", "VECTORIZED": "green",
                 "ESCANEADO": "cyan", "SCANNED": "cyan",
                 "CARGADO": "yellow", "LOADED": "yellow",
                 "REVISAR": "red", "REVIEW": "red",
                 "CHUNKEADO": "blue", "CHUNKED": "blue"}.get(estado_val, "white")
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
        console.print(f"  [dim]Total: {total} | Page {pagina}[/dim]")
    console.print()


@cloud_documento.command("show")
@click.argument("codigo")
@click.option("-o", "--output", type=click.Choice(["table", "tabla", "json"]), default="table")
def cloud_documento_ver(codigo: str, output: str):
    """Show details of a document."""
    from .cloud_commands import cloud_get
    from .oop import CliCommand
    from . import codes

    cmd = CliCommand()
    data = cmd.protegido(cloud_get, f"/documentos/{codigo}")

    if output == "json":
        click.echo(json.dumps(data, indent=2, ensure_ascii=False, default=str))
        return

    console.print()
    t = Table(show_header=False, border_style="dim", title=f"Document {codigo}")
    t.add_column("Field", style="bold")
    t.add_column("Value")
    t.add_row("Code", str(data.get("codigo_documento", "—")))
    t.add_row("Name", data.get("nombre_documento", "—"))
    t.add_row("Status", codes.to_english("status", data.get("codigo_estado_doc")) or "—")
    t.add_row("Location", data.get("nombre_ubicacion") or data.get("codigo_ubicacion", "—"))
    t.add_row("Size", _fmt_bytes(data.get("tamano_bytes")))
    t.add_row("Pages", str(data.get("total_paginas", "—")))
    t.add_row("Chunks", str(data.get("total_chunks", "—")))
    t.add_row("Created", str(data.get("fecha_creacion", "—"))[:19])
    t.add_row("Processed", str(data.get("fecha_actualizacion", "—"))[:19])
    if data.get("resumen_documento"):
        t.add_row("Summary", data["resumen_documento"][:120])
    console.print(t)
    console.print()


@cloud_documento.command("edges")
@click.argument("codigo")
@click.option("--limit", "--limite", "limite", default=50, show_default=True, help="Maximum documents at 2 hops.")
@click.option("-o", "--output", type=click.Choice(["table", "tabla", "json"]), default="table")
def cloud_documento_arcos(codigo: str, limite: int, output: str):
    """Corpus graph edges of a document: neighbors and docs at 2 hops."""
    from .cloud_commands import cloud_get
    from .oop import CliCommand

    cmd = CliCommand()
    data = cmd.protegido(
        cloud_get, f"/documentos/{codigo}/arcos", params={"limite_vecinos": limite}
    )

    if output == "json":
        click.echo(json.dumps(data, indent=2, ensure_ascii=False, default=str))
        return

    doc = data.get("documento", {}) or {}
    console.print()
    console.print(
        f"[bold]{doc.get('nombre_documento', codigo)}[/bold] "
        f"· type {doc.get('nombre_tipo_documento') or doc.get('codigo_tipo_documento') or '—'} "
        f"· {doc.get('formato_archivo') or '—'}"
    )
    caracs = data.get("caracteristicas") or []
    if caracs:
        console.print(f"\n[dim]Features ({len(caracs)}):[/dim]")
        for c in caracs[:20]:
            console.print(f"  {c.get('codigo_cat_docs')}/{c.get('codigo_tipo_docs')}: {c.get('valor')}")
    vecinos = data.get("vecinos_2_saltos") or []
    console.print(f"\n[dim]Documents at 2 hops ({len(vecinos)}):[/dim]")
    t = Table(border_style="dim")
    t.add_column("Document", style="bold")
    t.add_column("Name")
    t.add_column("Connected by")
    for v in vecinos[:50]:
        t.add_row(
            str(v.get("codigo_documento")),
            (v.get("nombre_documento") or "")[:40],
            f"{v.get('codigo_cat_docs')}={v.get('valor')}",
        )
    console.print(t)
    console.print()


# compat aliases (Spanish)
cloud_documento.add_command(cloud_documento_listar, name="listar")
cloud_documento.add_command(cloud_documento_ver, name="ver")
cloud_documento.add_command(cloud_documento_arcos, name="arcos")


# ── cloud space ──────────────────────────────────────────────────────────────

@cloud.group("space")
def cloud_espacio():
    """Manage Workspaces in the cloud."""
    pass


@cloud_espacio.command("list")
@click.option("--limit", "--limite", "limite", default=20, show_default=True)
@click.option("-o", "--output", type=click.Choice(["table", "tabla", "json", "id"]), default="table")
def cloud_espacio_listar(limite: int, output: str):
    """List Workspaces of the active group."""
    from .cloud_commands import cloud_get
    from .oop import CliCommand

    cmd = CliCommand()
    data = cmd.protegido(cloud_get, "/espacios-trabajo/paginado", params={"limit": limite})

    items = data.get("items", data) if isinstance(data, dict) else data

    if output == "json":
        _emit_json(items)
        return

    if output == "id":
        _emit_ids(items, "id_espacio")
        return

    console.print()
    t = Table(title="Workspaces", border_style="dim")
    t.add_column("ID", justify="right", style="dim")
    t.add_column("Name")
    t.add_column("Description")
    t.add_column("Docs", justify="right")
    t.add_column("Created")

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


@cloud_espacio.command("show")
@click.argument("id_espacio", type=int)
@click.option("--limit", "--limite", "limite", default=20, show_default=True)
@click.option("-o", "--output", type=click.Choice(["table", "tabla", "json"]), default="table")
def cloud_espacio_ver(id_espacio: int, limite: int, output: str):
    """Show details of a Workspace with its documents."""
    from .cloud_commands import cloud_get
    from .oop import CliCommand

    cmd = CliCommand()
    # There's no bare GET /{id} — we search the paginated list and filter
    espacios_data = cmd.protegido(cloud_get, "/espacios-trabajo/paginado", params={"limit": 200})
    items_esp = espacios_data.get("items", espacios_data) if isinstance(espacios_data, dict) else espacios_data
    espacio = next((e for e in items_esp if e.get("id_espacio") == id_espacio), None)
    if not espacio:
        cmd.salir(f"Workspace #{id_espacio} not found.", exit_code=1)
    docs_data = cmd.protegido(
        cloud_get,
        f"/espacios-trabajo/{id_espacio}/documentos/paginado",
        params={"limit": limite},
    )

    if output == "json":
        _emit_json({"espacio": espacio, "documentos": docs_data})
        return

    console.print()
    info = Table(show_header=False, border_style="dim",
                 title=f"Workspace #{id_espacio}")
    info.add_column("Field", style="bold")
    info.add_column("Value")
    info.add_row("Name", espacio.get("nombre_espacio", "—"))
    info.add_row("Description", espacio.get("descripcion") or "—")
    info.add_row("Created", str(espacio.get("fecha_creacion", "—"))[:19])
    console.print(info)
    console.print()

    docs = docs_data.get("items", docs_data) if isinstance(docs_data, dict) else docs_data
    if docs:
        t = Table(title=f"Documents ({len(docs)})", border_style="dim")
        t.add_column("Code", style="dim")
        t.add_column("Name")
        t.add_column("Status")
        t.add_column("Queue", justify="right")
        from . import codes
        for d in docs:
            t.add_row(
                str(d.get("codigo_documento", "—")),
                d.get("nombre_documento", "—")[:45],
                codes.to_english("status", d.get("codigo_estado_doc")) or "—",
                codes.to_english("queue_status", d.get("estado_cola")) or "—",
            )
        console.print(t)
    console.print()


# compat aliases (Spanish)
cloud_espacio.add_command(cloud_espacio_listar, name="listar")
cloud_espacio.add_command(cloud_espacio_ver, name="ver")


# ── cloud queue ──────────────────────────────────────────────────────────────

@cloud.group("queue")
def cloud_cola():
    """View the processing queue status."""
    pass


@cloud_cola.command("show")
@click.option("--process", "--proceso", "proceso", default=None, help="Filter by process (e.g. VECTORIZAR)")
@click.option("--status", "--estado", "estado", default=None, help="Filter by status (PENDIENTE, EJECUTANDO, etc.)")
@click.option("--limit", "--limite", "limite", default=20, show_default=True)
@click.option("-o", "--output", type=click.Choice(["table", "tabla", "json"]), default="table")
def cloud_cola_ver(proceso: str | None, estado: str | None, limite: int, output: str):
    """View the current state of the pipeline queue."""
    from .cloud_commands import cloud_get
    from .oop import CliCommand
    from . import codes

    # Backend GET /cola-estados-docs/paginado → page/limit/estado_cola/q.
    # Queue state is the canonical process state; translate English↔internal at the edge.
    params: dict = {"limit": limite}
    if estado:
        params["estado_cola"] = codes.to_internal("queue_status", estado)
    if proceso:
        # The paginated list doesn't filter by process; we use it as free search (q).
        params["q"] = codes.to_internal("process_type", proceso)

    cmd = CliCommand()
    data = cmd.protegido(cloud_get, "/cola-estados-docs/paginado", params=params)

    items = data.get("items", data) if isinstance(data, dict) else data
    for it in items or []:
        if isinstance(it, dict) and it.get("estado_cola"):
            it["estado_cola"] = codes.to_english("queue_status", it["estado_cola"])

    if output == "json":
        click.echo(json.dumps(items, indent=2, ensure_ascii=False, default=str))
        return

    console.print()
    t = Table(title="Processing queue", border_style="dim")
    t.add_column("ID", justify="right", style="dim")
    t.add_column("Process")
    t.add_column("Status")
    t.add_column("Document")
    t.add_column("Queued")
    t.add_column("Error")

    _est_color = {
        "PENDIENTE": "yellow", "PENDING": "yellow",
        "EJECUTANDO": "cyan", "RUNNING": "cyan",
        "TERMINADO": "green", "DONE": "green",
        "ERROR": "red",
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
        console.print(f"  [dim]Total in queue: {total}[/dim]")
    console.print()


@cloud_cola.command("runs")
@click.option("--limit", "--limite", "limite", default=10, show_default=True)
@click.option("-o", "--output", type=click.Choice(["table", "tabla", "json"]), default="table")
def cloud_cola_ejecuciones(limite: int, output: str):
    """View the history of skill runs."""
    from .cloud_commands import cloud_get
    from .oop import CliCommand

    cmd = CliCommand()
    data = cmd.protegido(cloud_get, "/cola-estados-docs/ejecuciones", params={"limit": limite})

    items = data.get("items", data) if isinstance(data, dict) else data

    if output == "json":
        click.echo(json.dumps(items, indent=2, ensure_ascii=False, default=str))
        return

    console.print()
    t = Table(title="Run history", border_style="dim")
    t.add_column("ID", justify="right", style="dim")
    t.add_column("Skill")
    t.add_column("Start")
    t.add_column("End")
    t.add_column("Docs", justify="right")
    t.add_column("OK", justify="right", style="green")
    t.add_column("Err", justify="right", style="red")
    t.add_column("Duration")

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


# compat aliases (Spanish)
cloud_cola.add_command(cloud_cola_ver, name="ver")
cloud_cola.add_command(cloud_cola_ejecuciones, name="ejecuciones")


# ── cloud skill ──────────────────────────────────────────────────────────────

@cloud.group("skill")
def cloud_habilidad():
    """Manage and run LLM skills from the global catalog."""
    pass


@cloud_habilidad.command("list")
@click.option("-o", "--output", type=click.Choice(["table", "tabla", "json", "id"]), default="table")
def cloud_habilidad_listar(output: str):
    """List all available skills."""
    from .cloud_commands import cloud_get
    from .oop import CliCommand

    from . import codes

    cmd = CliCommand()
    items = cmd.protegido(cloud_get, "/habilidades")

    # Expose skill code + applies-to + output-target in English on this surface,
    # for every output format (json/id/table).
    for h in items or []:
        if not isinstance(h, dict):
            continue
        if h.get("codigo_habilidad"):
            h["codigo_habilidad"] = codes.to_english("skill", h["codigo_habilidad"])
        if h.get("aplica_a"):
            h["aplica_a"] = codes.to_english("applies_to", h["aplica_a"])
        if h.get("salida_destino"):
            h["salida_destino"] = codes.to_english("output_target", h["salida_destino"])

    if output == "json":
        _emit_json(items)
        return

    if output == "id":
        _emit_ids(items, "codigo_habilidad")
        return

    console.print()
    t = Table(title="Available skills", border_style="dim")
    t.add_column("Code", style="bold")
    t.add_column("Name")
    t.add_column("Type")
    t.add_column("Output")
    t.add_column("Model")

    for h in items:
        t.add_row(
            h.get("codigo_habilidad", "—"),
            h.get("nombre_habilidad") or h.get("alias", "—"),
            h.get("aplica_a", "—"),
            h.get("salida_destino", "—"),
            h.get("id_modelo") or "[dim]from caller[/dim]",
        )
    console.print(t)
    console.print()


@cloud_habilidad.command("show")
@click.argument("codigo")
@click.option("-o", "--output", type=click.Choice(["table", "tabla", "json"]), default="table")
def cloud_habilidad_ver(codigo: str, output: str):
    """Show details of a skill."""
    from .cloud_commands import cloud_get
    from .oop import CliCommand
    from . import codes

    # The dev passes the English skill code; the REST route expects the internal one.
    cmd = CliCommand()
    h = cmd.protegido(cloud_get, f"/habilidades/{codes.to_internal('skill', codigo)}")

    if output == "json":
        click.echo(json.dumps(h, indent=2, ensure_ascii=False, default=str))
        return

    console.print()
    t = Table(show_header=False, border_style="dim",
              title=f"Skill {codigo}")
    t.add_column("Field", style="bold")
    t.add_column("Value")
    t.add_row("Code", codes.to_english("skill", h.get("codigo_habilidad")) or "—")
    t.add_row("Name", h.get("nombre_habilidad") or h.get("alias", "—"))
    t.add_row("Type", codes.to_english("applies_to", h.get("aplica_a")) or "—")
    t.add_row("Model", h.get("id_modelo") or "[dim]from caller[/dim]")
    t.add_row("Output", codes.to_english("output_target", h.get("salida_destino")) or "—")
    t.add_row("Output col.", h.get("salida_columna") or "—")
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


@cloud_habilidad.command("run")
@click.argument("codigo")
@click.option("--space", "--espacio", "espacio", type=int, default=None, help="Workspace ID")
@click.option("--document", "--documento", "documento", default=None, help="Single document code")
@click.option("--wait", "--esperar", "esperar", is_flag=True, help="Wait for completion and show the result")
@click.option("-o", "--output", type=click.Choice(["table", "tabla", "json"]), default="table")
def cloud_habilidad_ejecutar(
    codigo: str, espacio: int | None, documento: str | None,
    esperar: bool, output: str
):
    """Run a skill on a Workspace or document."""
    from .cloud_commands import cloud_post
    from .oop import CliCommand
    from . import codes

    cmd = CliCommand()
    if not espacio and not documento:
        cmd.salir("You must provide --space <ID> or --document <CODE>", exit_code=1)

    body: dict = {}
    if espacio:
        body["id_espacio"] = espacio
    if documento:
        body["codigo_documento"] = documento

    # The dev passes the English skill code; the REST route expects the internal one.
    codigo_int = codes.to_internal("skill", codigo)
    resultado = cmd.protegido(cloud_post, f"/habilidades/{codigo_int}/ejecutar", body=body)

    if output == "json":
        click.echo(json.dumps(resultado, indent=2, ensure_ascii=False, default=str))
        return

    # Uniform contract (SobreEjecucion): codigo_proceso + detalle.n_items_cola.
    detalle = resultado.get("detalle") or {}
    proceso = resultado.get("codigo_proceso", "—")
    docs = detalle.get("n_items_cola", resultado.get("n_documentos", "—"))
    no_proc = detalle.get("n_no_procesables", 0)
    estado = resultado.get("estado", "PENDIENTE")

    console.print()
    console.print(f"[green]✓ Queued[/green]" if resultado.get("aceptada", True)
                  else "[red]✗ Not accepted[/red]")
    console.print(f"  Process       : {proceso}")
    console.print(f"  Documents     : {docs}")
    if no_proc:
        console.print(f"  Not processable: {no_proc}")
    console.print(f"  Status        : {estado}")
    if resultado.get("mensaje"):
        console.print(f"  [dim]{resultado.get('mensaje')}[/dim]")
    console.print()
    console.print(f"  Track progress: [dim]ragfly cloud queue show[/dim]")
    console.print()


# compat aliases (Spanish)
cloud_habilidad.add_command(cloud_habilidad_listar, name="listar")
cloud_habilidad.add_command(cloud_habilidad_ver, name="ver")
cloud_habilidad.add_command(cloud_habilidad_ejecutar, name="ejecutar")


# ════════════════════════════════════════════════════════════════════════════
# Sub-command: cloud catalog (capabilities — multi-interface contract)
# ════════════════════════════════════════════════════════════════════════════

@cloud.command("catalog")
@click.option("--tipo", type=click.Choice(["TODO", "FUNCIONES", "HABILIDADES"]),
              default="TODO", show_default=True, help="Which part of the catalog to list")
@click.option("-o", "--output", type=click.Choice(["table", "tabla", "json"]), default="table")
def cloud_catalogo(tipo: str, output: str):
    """Capabilities catalog: what the user can do (functions + skills).

    Same contract consumed by chat and MCP (GET /catalogo). Filtered by the
    user's role, access type, group and application.
    """
    from .cloud_commands import cloud_get
    from .oop import CliCommand
    from . import codes

    cmd = CliCommand()
    data = cmd.protegido(cloud_get, "/catalogo", params={"tipo": tipo})

    funciones = data.get("funciones", [])
    habilidades = data.get("habilidades", [])
    # Expose function/skill codes in English on this agentic surface.
    for f in funciones:
        if isinstance(f, dict) and f.get("codigo_funcion"):
            f["codigo_funcion"] = codes.to_english("function", f["codigo_funcion"])
    for h in habilidades:
        if isinstance(h, dict) and h.get("codigo_habilidad"):
            h["codigo_habilidad"] = codes.to_english("skill", h["codigo_habilidad"])

    if output == "json":
        click.echo(json.dumps(data, indent=2, ensure_ascii=False, default=str))
        return

    if funciones:
        console.print()
        t = Table(title=f"Available functions ({len(funciones)})", border_style="dim")
        t.add_column("Code", style="bold")
        t.add_column("Name")
        t.add_column("Summary")
        t.add_column("Permissions")
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
        t = Table(title=f"Available skills ({len(habilidades)})", border_style="dim")
        t.add_column("Code", style="bold")
        t.add_column("Name")
        t.add_column("Summary")
        for h in habilidades:
            t.add_row(
                h.get("codigo_habilidad", "—"),
                h.get("nombre_habilidad") or "—",
                (h.get("descripcion_llm") or h.get("descripcion") or "")[:80],
            )
        console.print(t)

    if not funciones and not habilidades:
        console.print("[dim]No capabilities available for this context.[/dim]")
    console.print()


# compat alias (Spanish)
cloud.add_command(cloud_catalogo, name="catalogo")


# ════════════════════════════════════════════════════════════════════════════
# Sub-group: cloud search (RAG one-shot)
# ════════════════════════════════════════════════════════════════════════════

@cloud.command("search")
@click.argument("consulta", nargs=-1, required=True)
@click.option("--limit", "--limite", "limite", type=int, default=10, show_default=True,
              help="Final top-K after rerank")
@click.option("--min-similarity", "--min-similitud", "min_similitud", type=float, default=0.0, show_default=True,
              help="Minimum cosine threshold")
@click.option("--entity", "--entidad", "entidad", default=None, help="Filter by entity code")
@click.option("-o", "--output", type=click.Choice(["table", "tabla", "json"]), default="table")
def cloud_buscar(
    consulta: tuple[str, ...], limite: int, min_similitud: float,
    entidad: str | None, output: str,
):
    """Semantic RAG search over the group's vectorized documents."""
    from .cloud_commands import cloud_post
    from .oop import CliCommand

    q = " ".join(consulta).strip()
    if not q:
        err_console.print("[red]The query cannot be empty.[/red]")
        raise SystemExit(1)

    body: dict = {"q": q, "limit": limite, "min_similitud": min_similitud}
    if entidad:
        body["codigo_entidad"] = entidad

    cmd = CliCommand()
    data = cmd.protegido(cloud_post, "/documentos/buscar-semantico", body=body)

    if output == "json":
        click.echo(json.dumps(data, indent=2, ensure_ascii=False, default=str))
        return

    items = data.get("resultados") or data.get("items") or data if isinstance(data, list) else (
        data.get("resultados") or data.get("items") or []
    )
    if not items:
        console.print("[yellow]No results.[/yellow]")
        return

    tabla = Table(title=f"RAG: {q[:60]}", show_lines=False)
    tabla.add_column("#", style="dim", width=3)
    tabla.add_column("Document", overflow="fold")
    tabla.add_column("Score", justify="right", width=8)
    tabla.add_column("Fragment", overflow="fold")
    for i, h in enumerate(items, 1):
        score = h.get("score") or h.get("similitud") or h.get("rerank_score") or 0
        nombre = h.get("nombre_documento") or h.get("codigo_documento") or "—"
        frag = (h.get("texto") or h.get("chunk_texto") or "")[:200]
        tabla.add_row(str(i), str(nombre), f"{float(score):.3f}" if isinstance(score, (int, float)) else str(score), frag)
    console.print(tabla)


# compat alias (Spanish)
cloud.add_command(cloud_buscar, name="buscar")


# ════════════════════════════════════════════════════════════════════════════
# Sub-group: cloud chat (conversational RAG)
# ════════════════════════════════════════════════════════════════════════════

@cloud.group("chat")
def cloud_chat():
    """Chat with your documents via RAG."""
    pass


@cloud_chat.command("ask")
@click.argument("mensaje", nargs=-1, required=True)
@click.option("--function", "--funcion", "funcion", default="CHAT-USER", show_default=True,
              help="Chat function code (English public code)")
@click.option("--conversation", "--conversacion", "id_conversacion", type=int, default=None,
              help="Existing conversation ID (omit = create new)")
@click.option("--title", "--titulo", "titulo", default=None, help="Initial title (when creating a new one)")
@click.option("-o", "--output", type=click.Choice(["text", "texto", "json"]), default="text")
def cloud_chat_preguntar(
    mensaje: tuple[str, ...], funcion: str, id_conversacion: int | None,
    titulo: str | None, output: str,
):
    """Ask a question to the RAG chat. Creates a conversation if none is given."""
    from .cloud_commands import cloud_post, _headers, CLOUD_URL, CloudError
    from .oop import CliCommand
    from . import codes

    contenido = " ".join(mensaje).strip()
    if not contenido:
        err_console.print("[red]The message cannot be empty.[/red]")
        raise SystemExit(1)

    cmd = CliCommand()

    if not id_conversacion:
        # The dev passes the English function code; the API expects the internal one.
        body_conv = {"codigo_funcion": codes.to_internal("function", funcion)}
        if titulo:
            body_conv["titulo"] = titulo
        nueva = cmd.protegido(cloud_post, "/chat/conversaciones", body=body_conv)
        id_conversacion = int(nueva.get("id_conversacion") or 0)
        if not id_conversacion:
            err_console.print(f"[red]Could not create conversation: {nueva}[/red]")
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
            recibio_done = False
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
                    if output == "text":
                        console.print(chunk, end="", soft_wrap=True)
                elif "done" in evt:
                    meta = {k: v for k, v in evt.items() if k != "done"}
                    recibio_done = True
                elif "error" in evt:
                    err_console.print(f"\n[red]Server error: {evt['error']}[/red]")
                    raise SystemExit(2)
    except httpx.RequestError as e:
        # Connection drop/timeout: clean error to stderr + non-zero exit, not a
        # raw traceback (this block is outside CliCommand.protegido).
        err_console.print(f"\n[red]Could not connect to the server: {e}[/red]")
        raise SystemExit(2)

    # The stream closed without the final `done` event: truncated response. Exit
    # with an error instead of printing the partial response as if complete.
    if not recibio_done:
        err_console.print(
            "\n[red]The stream was cut off before finishing (no 'done' event); "
            "incomplete response.[/red]"
        )
        raise SystemExit(2)

    if output == "json":
        click.echo(json.dumps({
            "id_conversacion": id_conversacion,
            "respuesta": "".join(partes),
            **meta,
        }, indent=2, ensure_ascii=False, default=str))
    else:
        console.print()
        console.print(f"[dim]Conversation #{id_conversacion}[/dim]")


# compat alias (Spanish)
cloud_chat.add_command(cloud_chat_preguntar, name="preguntar")


# compat aliases for cloud sub-groups (Spanish)
cloud.add_command(cloud_grupo, name="grupo")
cloud.add_command(cloud_documento, name="documento")
cloud.add_command(cloud_espacio, name="espacio")
cloud.add_command(cloud_cola, name="cola")
cloud.add_command(cloud_habilidad, name="habilidad")


# ════════════════════════════════════════════════════════════════════════════
# Internal helpers
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
    """Show the client version and warn if an update is available."""
    console.print(f"[bold blue]RAGfly[/bold blue] Client v{__version__}")
    try:
        from .version_check import chequear_actualizacion
        aviso = chequear_actualizacion()
        if aviso:
            console.print(f"[yellow]{aviso}[/yellow]")
    except Exception:
        pass  # silent: don't break version if there's no config/network
