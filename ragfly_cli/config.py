"""
Configuración del cliente RAGfly.

Lee de ~/.ragfly/config.env o variables de entorno.
Patrón idéntico al backend (pydantic-settings + lru_cache).
"""

import os
from pathlib import Path
from functools import lru_cache
from pydantic_settings import BaseSettings


def _get_home() -> Path:
    """Retorna el directorio home de RAGfly (evaluado en runtime)."""
    return Path(os.environ.get("RAGFLY_HOME", Path.home() / ".ragfly"))


# Directorio base de datos del cliente (evaluado al importar, útil como default)
RAGFLY_HOME = _get_home()


class ClienteConfig(BaseSettings):
    """Configuración del cliente local."""

    # --- Conexión al Cloud ---
    cloud_url: str = ""
    email: str = ""
    password: str = ""  # TODO: encriptar con keyring en futuras versiones

    # --- Tokens OAuth ---
    # Si están presentes, `sync.py` los usa en vez de email/password para autenticar.
    # NOTA: el flujo OAuth Authorization Code → localhost redirect que los poblaba
    # vivía en `api_local.py` (servidor :27182), retirado 2026-06-19 (legado D.1).
    # El SSO del Desktop GUI va por otro camino (auth_bridge → keyring del SO). El
    # CLI puro autentica por email/password salvo que estos tokens se seteen aparte.
    access_token: str = ""
    refresh_token: str = ""

    # --- Contexto multi-tenant ---
    codigo_grupo: str = ""
    codigo_entidad: str = ""

    # --- Rutas locales ---
    directorio_documentos: str = ""
    db_path: str = str(RAGFLY_HOME / "data.db")

    # NOTA: el cliente NO configura su modelo LLM ni de embeddings ni sus API
    # keys. El modelo de cada paso lo gobierna la habilidad/transición
    # sincronizada del cloud (registro_llm vía sync_catalogo) y las keys vienen
    # de cat_llm_keys sincronizado. Cualquier "elección de modelo" debe vivir en
    # el catálogo, nunca como literal en el cliente.

    # --- Sync ---
    sync_batch_size: int = 500
    sync_max_reintentos: int = 5
    sync_comprimir: bool = True

    # --- Flags de pipeline ---
    # Los flags `analizar_habilitado` / `chunkear_habilitado` fueron eliminados
    # del cloud en mig 325 (limpieza de parámetros + parametrización por plan).
    # El cliente asume True para todos los pasos; el control administrativo se
    # hace en `rel_transiciones_estado.activo` del cloud.
    # La vectorización ocurre SIEMPRE en el cloud con su modelo sincronizado
    # (VECTORIZAR_CHUNKS → registro_llm); no hay embeddings local.

    # --- General ---
    debug: bool = False

    model_config = {
        "env_prefix": "RAGFLY_",
        "extra": "ignore",
    }

    @classmethod
    def settings_customise_sources(cls, settings_cls, **kwargs):
        """Carga el env_file de forma dinámica (runtime) para que
        RAGFLY_HOME sea respetado incluso si cambia después del import."""
        from pydantic_settings import DotEnvSettingsSource
        init_settings = kwargs.get("init_settings")
        env_settings = kwargs.get("env_settings")
        return (
            init_settings,
            env_settings,
            DotEnvSettingsSource(settings_cls, env_file=str(_get_home() / "config.env")),
        )


@lru_cache
def get_config() -> ClienteConfig:
    """Retorna la configuración cacheada del cliente."""
    return ClienteConfig()


def config_existe() -> bool:
    """Verifica si ya se ejecutó el setup (evaluado en runtime)."""
    return (_get_home() / "config.env").exists()


def crear_directorio_home():
    """Crea ~/.ragfly/ si no existe (evaluado en runtime)."""
    _get_home().mkdir(parents=True, exist_ok=True)
