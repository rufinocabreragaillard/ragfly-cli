"""
Public-code translation at the CLI edge (English ↔ internal).

RAGfly catalog codes are OPAQUE internal identifiers that historically ended up in
Spanish (`VECTORIZADO`, `FACTURA`) — but they are *codes*, not prose: `VECTORIZADO`
could just as well be `0001`. Each catalog row has THREE orthogonal names:

  - **code**  (`codigo_*`): the opaque internal identifier. The wire/DB value.
  - **alias** (name): the human-readable label, translated by the UI's i18n.
  - **codigo_*_en**: a SECOND public code, in English (`VECTORIZED`, `INVOICE`),
    that points to the SAME row. This is the agentic-frontier face.

The CLI is an agentic frontier: a dev types and reads CODES, so it speaks the
English code (`--status VECTORIZED`, prints `Status: VECTORIZED`). The REST API
still speaks the internal code, so the CLI translates at its edge — internal on the
wire, English in the terminal. This is NOT translating the alias (that is prose /
i18n); it is swapping one code for its English twin.

The map comes from `GET /catalogo/public-codes` (the same helper the MCP server and
the SDKs use), so the CLI translates EXACTLY like every other surface. It only
changes with a catalog migration, so it is fetched once and cached for the process.
Fail-open: an unknown code passes through untouched.
"""

from __future__ import annotations

from typing import Optional

# Domains fetched for the CLI. Keys are the English aliases the endpoint exposes.
_DOMAINS_QUERY = (
    "status,queue_status,doc_type,skill,function,feature_category,"
    "process_type,applies_to,output_target"
)

_to_english: Optional[dict] = None
_to_internal: Optional[dict] = None


def _ensure_loaded() -> None:
    global _to_english, _to_internal
    if _to_english is not None:
        return
    try:
        from .cloud_commands import cloud_get
        data = cloud_get("/catalogo/public-codes", params={"domains": _DOMAINS_QUERY})
        mapa = (data or {}).get("domains", {}) if isinstance(data, dict) else {}
    except Exception:
        # If the map can't be fetched, degrade to identity (never break a command).
        mapa = {}
    _to_english = {dom: dict(t) for dom, t in mapa.items()}
    _to_internal = {
        dom: {en: internal for internal, en in t.items()} for dom, t in mapa.items()
    }


def to_english(domain: str, internal_code: Optional[str]) -> Optional[str]:
    """internal → English. Unknown codes pass through. None → None."""
    if not internal_code:
        return internal_code
    _ensure_loaded()
    return _to_english.get(domain, {}).get(internal_code, internal_code)


def to_internal(domain: str, public_code: Optional[str]) -> Optional[str]:
    """English → internal. Accepts an internal code too (bilingual during the
    transition). Unknown codes pass through. None → None."""
    if not public_code:
        return public_code
    _ensure_loaded()
    table = _to_internal.get(domain, {})
    if public_code in table:
        return table[public_code]
    # Already an internal code? (caller passed the internal one out of habit)
    if public_code in _to_english.get(domain, {}):
        return public_code
    return public_code
