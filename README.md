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
export RAGFLY_TOKEN=slm_live_xxxxxxxxxx
```

## Command surface

```
ragfly
├── login / logout / version
└── cloud                    ← operations against api.ragfly.ai
    ├── me
    ├── grupo       listar | cambiar | limpiar
    ├── api-key     crear | listar | revocar
    ├── documento   listar | ver
    ├── espacio     listar | ver
    ├── cola        ver | ejecuciones
    ├── habilidad   listar | ver | ejecutar
    ├── catalogo
    ├── buscar
    └── chat        preguntar
```

Full reference: <https://api.ragfly.ai/docs> and `docs/integradores/CLI.md`.

> **Local operations** (`ragfly local scan/sync/daemon`) require the local file
> worker and ship with **RAGfly Desktop**, not with this package.

## Source

The command logic is extracted from the RAGfly Desktop client
(`cliente/ragfly/`). Canonical source of each module lives there; keep this
package's copies in sync when the cloud command surface changes.
