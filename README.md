# RAGfly CLI

Operate RAGfly from the terminal and CI — `login` + the full `cloud` API surface
against `api.ragfly.ai`. Lightweight: depends only on `click`, `rich`, `httpx`
and `keyring`. **No desktop / PySide6 / OCR dependencies.**

```bash
pip install ragfly-cli
ragfly version
ragfly login
ragfly cloud me
```

> This package ships the **`ragfly` binary** for scripting and automation.
> It is distinct from `pip install ragfly` (the **Python SDK**, import `import ragfly`)
> and from **RAGfly Desktop** (the DMG/exe that bundles the local file worker for
> `ragfly local scan/sync/daemon`).

## Authentication

```bash
# Interactive (JWT, stored in the OS keyring)
ragfly login

# Non-interactive / CI (API key, no expiry)
export RAGFLY_API_KEY=slm_live_xxxxxxxxxx
```

## `RAGFLY_ROOT` (optional) — open original files on disk

Searching, asking and citing need zero extra config. Only if a script or agent
on this machine must open the **original file** on disk, set `RAGFLY_ROOT` once:
it is the **parent folder** of the folder you selected when uploading your
documents via the web app. RAGfly never reads it nor stores your absolute
path — documents uploaded via browser carry a *relative* `ruta_archivo`, and
the real path is `$RAGFLY_ROOT + ruta_archivo`.

```bash
# Example: you uploaded /Users/ana/Dropbox/MisDocumentos → the PARENT is the root
echo 'export RAGFLY_ROOT="/Users/ana/Dropbox"' >> ~/.zshrc
# "/MisDocumentos/letras/cancion.txt" → /Users/ana/Dropbox/MisDocumentos/letras/cancion.txt
```

Not needed for documents loaded via RAGfly Desktop (their paths are already
absolute). Step-by-step walkthrough:
<https://ragfly.ai/build/mcp#setting-up-ragfly_root--once-per-machine-in-3-steps>

## Command surface

```
ragfly
├── login / logout / version
└── cloud                    ← operations against api.ragfly.ai
    ├── me
    ├── group       list | switch | clear
    ├── api-key     create | list | revoke
    ├── document    list | show | edges
    ├── space       list | show
    ├── queue       show | runs
    ├── skill       list | show | run
    ├── catalog
    ├── search
    └── chat        ask
```

Codes are English on the wire: filter and read catalog codes in English
(`--status VECTORIZED`, `codigo_estado_doc: VECTORIZED`, skill code `SUMMARIZE_DOCUMENT`).
The CLI translates them to RAGfly's internal codes at its edge, using the same
public-code map as the MCP server (`GET /catalogo/public-codes`). The former
Spanish command/flag names (`documento listar`, `--estado`) still work as
compatibility aliases.

```bash
ragfly cloud document list --status VECTORIZED --limit 20
ragfly cloud skill run SUMMARIZE_DOCUMENT --space 12
ragfly cloud search "Q1 revenue"
```

Full reference: <https://api.ragfly.ai/docs> and `docs/integradores/CLI.md`.

> **Local operations** (`ragfly local scan/sync/daemon`) require the local file
> worker and ship with **RAGfly Desktop**, not with this package.

## Source

The command logic is extracted from the RAGfly Desktop client
(`cliente/ragfly/`). Canonical source of each module lives there; keep this
package's copies in sync when the cloud command surface changes.
