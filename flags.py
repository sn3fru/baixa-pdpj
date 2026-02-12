"""
Devedor360 v2 - Sistema de Flags Extensivel
Cada flag e uma funcao Python pura registrada via decorator.
Para adicionar nova flag: criar funcao + @register_flag(...).
Usado pelo pipeline (S2/S3) e pelo frontend automaticamente.
"""

import re

# ============================================================================
# Registry
# ============================================================================

FLAG_REGISTRY: dict = {}


def register_flag(key: str, label: str, description: str = "", color: str = "blue"):
    """
    Decorator para registrar uma flag.
    key: identificador interno (ex: "pgfn")
    label: nome exibido no frontend (ex: "PGFN")
    description: tooltip explicativo
    color: cor do badge no frontend (tailwind: blue, red, green, yellow, purple, etc.)
    """
    def decorator(fn):
        FLAG_REGISTRY[key] = {
            "fn": fn,
            "key": key,
            "label": label,
            "description": description,
            "color": color,
        }
        return fn
    return decorator


def avaliar_flags(processo: dict, doc_normalizado: str = "") -> dict:
    """
    Avalia todas as flags registradas para um processo.
    Retorna {"flag_anulatoria": 0/1, "flag_pgfn": 0/1, ...}
    """
    result = {}
    for key, entry in FLAG_REGISTRY.items():
        try:
            result[f"Flag {entry['label']}"] = 1 if entry["fn"](processo, doc_normalizado) else 0
        except Exception:
            result[f"Flag {entry['label']}"] = 0
    return result


def listar_flags() -> list:
    """Retorna lista de flags para o frontend."""
    return [
        {"key": k, "label": v["label"], "description": v["description"], "color": v["color"]}
        for k, v in FLAG_REGISTRY.items()
    ]


# ============================================================================
# Helpers internos
# ============================================================================

def _get_partes(processo: dict) -> list:
    """Extrai todas as partes de todas as tramitacoes."""
    partes = []
    for tram in (processo.get("tramitacoes") or []):
        for p in (tram.get("partes") or []):
            partes.append(p)
    return partes


def _get_nomes_polo(processo: dict, polo: str) -> list:
    """Retorna nomes de um polo especifico (ATIVO/PASSIVO)."""
    nomes = []
    for p in _get_partes(processo):
        if p.get("polo", "").upper() == polo.upper():
            nomes.append(p.get("nome", "").upper().strip())
    return nomes


def _doc_no_polo(processo: dict, doc: str, polo: str) -> bool:
    """Verifica se documento esta em determinado polo."""
    for p in _get_partes(processo):
        if p.get("polo", "").upper() != polo.upper():
            continue
        for dp in (p.get("documentosPrincipais") or []):
            if re.sub(r"\D", "", dp.get("numero", "")) == doc:
                return True
    return False


def _is_classe(processo: dict, codigo: int) -> bool:
    """Verifica se processo tem determinada classe."""
    for tram in (processo.get("tramitacoes") or []):
        for c in (tram.get("classe") or []):
            if c.get("codigo") == codigo:
                return True
    return False


# ============================================================================
# Flags registradas
# ============================================================================

TERMOS_ESTADO = {
    "ESTADO", "MUNICIPIO", "PREFEITURA", "GOVERNO", "SECRETARIA",
    "FAZENDA PUBLICA", "PROCURADORIA", "DISTRITO FEDERAL",
}

TERMOS_FAZENDA_NACIONAL = {
    "FAZENDA NACIONAL", "UNIAO FEDERAL", "UNIAO", "PGFN",
    "PROCURADORIA-GERAL DA FAZENDA NACIONAL",
    "PROCURADORIA GERAL DA FAZENDA NACIONAL",
}

TERMOS_BANCOS = {
    "ITAU", "ITAÚ", "SANTANDER", "BRADESCO", "CAIXA ECONOMICA",
    "CAIXA ECONÔMICA", "BANCO DO BRASIL", "BANCO INTER",
    "NUBANK", "NU PAGAMENTOS", "SAFRA", "BTG", "VOTORANTIM",
    "BANRISUL", "SICOOB", "SICREDI", "BANCO PAN",
}


@register_flag("anulatoria", "Anulatoria",
               "Devedor no polo ativo atacando o estado (acao anulatoria)",
               color="orange")
def flag_anulatoria(processo: dict, doc: str = "") -> bool:
    if not doc:
        return False
    if not _doc_no_polo(processo, doc, "ATIVO"):
        return False
    nomes_passivo = _get_nomes_polo(processo, "PASSIVO")
    return any(
        any(termo in nome for termo in TERMOS_ESTADO)
        for nome in nomes_passivo
    )


@register_flag("pgfn", "PGFN",
               "Fazenda Nacional / Uniao Federal no polo ativo contra o devedor",
               color="red")
def flag_pgfn(processo: dict, doc: str = "") -> bool:
    nomes_ativo = _get_nomes_polo(processo, "ATIVO")
    return any(
        any(termo in nome for termo in TERMOS_FAZENDA_NACIONAL)
        for nome in nomes_ativo
    )


@register_flag("bancos", "Bancos",
               "Grande banco no polo ativo contra o devedor",
               color="purple")
def flag_bancos(processo: dict, doc: str = "") -> bool:
    nomes_ativo = _get_nomes_polo(processo, "ATIVO")
    return any(
        any(termo in nome for termo in TERMOS_BANCOS)
        for nome in nomes_ativo
    )


@register_flag("exec_fiscal", "Exec. Fiscal",
               "Execucao fiscal (classe 1116)",
               color="yellow")
def flag_exec_fiscal(processo: dict, doc: str = "") -> bool:
    return _is_classe(processo, 1116)


@register_flag("trabalhista", "Trabalhista",
               "Processo na Justica do Trabalho (segmento 5 do CNJ)",
               color="green")
def flag_trabalhista(processo: dict, doc: str = "") -> bool:
    cnj = processo.get("numeroProcesso", "")
    parts = re.split(r"[-.]", str(cnj).strip())
    return len(parts) >= 6 and parts[4] == "5"
