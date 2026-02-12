"""API de configuracao."""

import os
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

router = APIRouter(tags=["config"])

# Mapa: campo Python -> chave .env
FIELD_MAP = {
    "tokens": "PDPJ_TOKENS",
    "base_url": "PDPJ_BASE_URL",
    "tribunal": "PDPJ_TRIBUNAL",
    "id_classe": "PDPJ_ID_CLASSE",
    "input_file": "INPUT_FILE",
    "output_dir": "OUTPUT_DIR",
    "max_por_pagina": "MAX_POR_PAGINA",
    "max_paginas_por_caso": "MAX_PAGINAS_POR_CASO",
    "max_processos_totais": "MAX_PROCESSOS_TOTAIS_POR_CASO",
    "max_processos_per_doc": "MAX_PROCESSOS_PER_DOC",
    "max_processos_per_root": "MAX_PROCESSOS_PER_CNPJ_ROOT",
    "max_filiais": "MAX_FILIAIS",
    "download_detalhes": "DOWNLOAD_DETALHES",
    "enable_busca_documento": "ENABLE_BUSCA_DOCUMENTO",
    "enable_busca_nome": "ENABLE_BUSCA_NOME",
    "enable_busca_filial": "ENABLE_BUSCA_FILIAL",
    "workers_per_token": "WORKERS_PER_TOKEN",
    "debug": "DEBUG",
    "dashboard_enabled": "DASHBOARD_ENABLED",
    "filtro_municipio": "FILTRO_MUNICIPIO",
}


class ConfigUpdate(BaseModel):
    tokens: Optional[list] = None
    base_url: Optional[str] = None
    tribunal: Optional[str] = None
    id_classe: Optional[str] = None
    input_file: Optional[str] = None
    output_dir: Optional[str] = None
    max_por_pagina: Optional[int] = None
    max_paginas_por_caso: Optional[int] = None
    max_processos_totais: Optional[int] = None
    max_processos_per_doc: Optional[int] = None
    max_processos_per_root: Optional[int] = None
    max_filiais: Optional[int] = None
    download_detalhes: Optional[bool] = None
    enable_busca_documento: Optional[bool] = None
    enable_busca_nome: Optional[bool] = None
    enable_busca_filial: Optional[bool] = None
    workers_per_token: Optional[int] = None
    debug: Optional[bool] = None
    dashboard_enabled: Optional[bool] = None
    filtro_municipio: Optional[str] = None


def _env_path():
    return os.path.abspath(os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        ".env"))


@router.get("/config")
async def get_config():
    """Retorna configuracao atual relendo do .env (valores frescos)."""
    from config import Config
    cfg = Config.from_env()
    d = cfg.to_dict()

    # Tokens: mascara para exibicao, mas preserva contagem
    raw_tokens = d.get("tokens", [])
    d["tokens_count"] = len(raw_tokens)
    d["tokens_masked"] = []
    for t in raw_tokens:
        if len(t) > 30:
            d["tokens_masked"].append(t[:12] + "..." + t[-8:])
        elif len(t) > 10:
            d["tokens_masked"].append(t[:6] + "..." + t[-4:])
        else:
            d["tokens_masked"].append("***")
    # Remove tokens reais do response
    d.pop("tokens", None)
    return d


@router.post("/config")
async def update_config(update: ConfigUpdate):
    """Atualiza .env com novos valores."""
    env_file = _env_path()

    # Le .env existente
    lines = []
    if os.path.isfile(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

    # Prepara updates
    updates = {}
    data = update.dict(exclude_none=True)
    for py_key, env_key in FIELD_MAP.items():
        if py_key not in data:
            continue
        val = data[py_key]
        if isinstance(val, bool):
            val = "true" if val else "false"
        elif isinstance(val, list):
            val = ",".join(str(v) for v in val)
        updates[env_key] = str(val)

    if not updates:
        return {"status": "ok", "updated": []}

    # Atualiza linhas existentes
    written_keys = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}\n")
                written_keys.add(key)
                continue
        new_lines.append(line)

    # Adiciona keys novas que nao existiam
    for key, val in updates.items():
        if key not in written_keys:
            new_lines.append(f"{key}={val}\n")

    with open(env_file, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    return {"status": "ok", "updated": list(updates.keys())}


@router.get("/config/validate")
async def validate_config():
    """Valida configuracao atual."""
    from config import Config
    cfg = Config.from_env()
    erros = cfg.validar()
    return {"valid": len(erros) == 0, "errors": erros}
