"""
Devedor360 v2 - Funcoes Utilitarias Consolidadas
Todas as funcoes puras compartilhadas entre os modulos.
Inclui SELIC, validacao de documentos, classificacao de processos, etc.
"""

import os
import re
import time
import requests
from datetime import datetime, timedelta

# =============================================================================
# VALIDACAO E NORMALIZACAO DE DOCUMENTOS
# =============================================================================

def normalizar_documento(documento_str: str) -> str:
    """Limpa e normaliza documento para CPF (11) ou CNPJ (14) digitos."""
    doc_digits = re.sub(r"\D", "", documento_str or "")
    if not doc_digits:
        return ""
    if len(doc_digits) <= 11:
        return doc_digits.zfill(11)
    if len(doc_digits) > 14:
        doc_digits = doc_digits[-14:]
    return doc_digits.zfill(14)


def validar_cpf(cpf: str) -> bool:
    cpf = re.sub(r"\D", "", cpf)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    def _d(s, p):
        soma = sum(int(s[i]) * ((p + 1) - i) for i in range(p))
        r = soma % 11
        return "0" if r < 2 else str(11 - r)
    return cpf[-2:] == _d(cpf, 9) + _d(cpf, 10)


def validar_cnpj(cnpj: str) -> bool:
    cnpj = re.sub(r"\D", "", cnpj)
    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        return False
    def _d(s, p):
        pesos = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        if p == 12:
            pesos = pesos[1:]
        r = sum(int(s[i]) * pesos[i] for i in range(p)) % 11
        return "0" if r < 2 else str(11 - r)
    return cnpj[-2:] == _d(cnpj, 12) + _d(cnpj, 13)


def gerar_cnpj_completo(root: str, branch: str) -> str:
    """Gera CNPJ completo (14 dig) a partir de raiz (8) + filial (4)."""
    base = root + branch
    p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    r = sum(int(base[i]) * p1[i] for i in range(12)) % 11
    d1 = 0 if r < 2 else 11 - r
    base2 = base + str(d1)
    p2 = [6] + p1
    r = sum(int(base2[i]) * p2[i] for i in range(13)) % 11
    d2 = 0 if r < 2 else 11 - r
    return base + str(d1) + str(d2)


def obter_raiz_cnpj(doc: str) -> str:
    """Retorna raiz (8 dig) se CNPJ, senao ''."""
    return doc[:8] if len(doc) == 14 else ""


def identificar_tipo_documento(doc_raw: str) -> str:
    """Retorna 'CPF', 'CNPJ' ou '' (invalido)."""
    d = normalizar_documento(doc_raw)
    if len(d) == 14 and validar_cnpj(d):
        return "CNPJ"
    if len(d) == 11 and validar_cpf(d):
        return "CPF"
    return ""


# =============================================================================
# FORMATACAO DE DATAS
# =============================================================================

def parse_iso_date(iso_str: str):
    """Parse robusto de data ISO -> datetime ou None."""
    if not iso_str:
        return None
    try:
        return datetime.fromisoformat(iso_str)
    except (ValueError, TypeError):
        pass
    m = re.match(r"^(.*T\d+:\d+:\d+)\.(\d+)$", str(iso_str))
    if m:
        try:
            return datetime.fromisoformat(f"{m.group(1)}.{m.group(2).ljust(6, '0')}")
        except (ValueError, TypeError):
            pass
    try:
        return datetime.strptime(str(iso_str).split('.')[0], "%Y-%m-%dT%H:%M:%S")
    except (ValueError, TypeError):
        return None


def formatar_data_iso(iso_str: str) -> str:
    """ISO -> DD/MM/YYYY."""
    dt = parse_iso_date(iso_str)
    return dt.strftime("%d/%m/%Y") if dt else (iso_str or "")


def parse_date(date_str: str):
    """Parse que tenta ISO e DD/MM/YYYY."""
    if not date_str:
        raise ValueError("Data vazia")
    dt = parse_iso_date(date_str)
    if dt:
        return dt
    return datetime.strptime(date_str, "%d/%m/%Y")


def obter_ano_processo(numero_cnj: str) -> int:
    """Extrai ano do CNJ (2o segmento apos '.')."""
    parts = str(numero_cnj).split(".")
    if len(parts) < 2:
        raise ValueError(f"CNJ invalido: {numero_cnj}")
    return int(parts[1])


def calcular_data_ajuizamento(data_distribuicao: str, data_primeiro_doc: str,
                               numero_cnj: str) -> str:
    """Determina data de ajuizamento com logica inteligente."""
    try:
        dt_d = parse_date(data_distribuicao) if data_distribuicao else None
    except Exception:
        dt_d = None
    try:
        dt_p = parse_date(data_primeiro_doc) if data_primeiro_doc else None
    except Exception:
        dt_p = None
    try:
        ano = obter_ano_processo(numero_cnj)
    except Exception:
        return formatar_data_iso(data_distribuicao) or ""
    if dt_d and dt_d.year == ano:
        return dt_d.strftime("%d/%m/%Y")
    if dt_p and dt_p.year == ano:
        return dt_p.strftime("%d/%m/%Y")
    return datetime(ano, 7, 1).strftime("%d/%m/%Y")


# =============================================================================
# SELIC (correcao monetaria)
# =============================================================================

def somar_selic_periodo(data_inicial: str, data_final: str, cache_manager=None) -> float:
    """
    Consulta API do BCB para taxa SELIC acumulada no periodo.
    Usa cache_manager.get_selic / set_selic se fornecido.
    """
    try:
        dt_ini = datetime.strptime(data_inicial, "%d/%m/%Y")
        dt_fim = datetime.strptime(data_final, "%d/%m/%Y")
    except Exception:
        return 0.0

    data_ini_key = dt_ini.replace(day=1).strftime("%d/%m/%Y")
    key = f"{data_ini_key}_{data_final}"

    if cache_manager:
        cached = cache_manager.get_selic(key)
        if cached is not None:
            return cached

    url = (f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.4390/dados"
           f"?formato=json&dataInicial={data_ini_key}&dataFinal={data_final}")
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        dados = resp.json()
        soma = sum(float(item["valor"].replace(",", ".")) for item in dados)
        if cache_manager:
            cache_manager.set_selic(key, soma)
        return soma
    except Exception:
        if cache_manager:
            cache_manager.set_selic(key, 0.0)
        return 0.0


def corrigir_valor_com_selic(valor_acao, data_ajuiz: str, cache_manager=None) -> float:
    """Aplica correcao monetaria pela SELIC."""
    if not valor_acao or not data_ajuiz:
        return valor_acao or 0.0
    try:
        valor_acao = float(valor_acao)
    except (ValueError, TypeError):
        return 0.0
    try:
        dt_ajuiz = datetime.strptime(data_ajuiz, "%d/%m/%Y")
    except Exception:
        return valor_acao
    hoje = datetime.today()
    dt_fim = hoje.replace(day=1) - timedelta(days=1)
    if dt_ajuiz >= dt_fim:
        return valor_acao
    data_ini = dt_ajuiz.replace(day=1).strftime("%d/%m/%Y")
    data_fim = dt_fim.strftime("%d/%m/%Y")
    selic = somar_selic_periodo(data_ini, data_fim, cache_manager)
    return valor_acao * (1.0 + selic / 100.0)


# =============================================================================
# MANIPULACAO DE PARTES
# =============================================================================

_POLO_ATIVO_KW = {"AUTOR", "APELANTE", "EXEQUENTE", "REQUERENTE", "ATIVO"}
_POLO_PASSIVO_KW = {"REU", "RÉU", "APELADO", "EXECUTADO", "REQUERIDO", "PASSIVO"}


def montar_partes_string(partes: list) -> str:
    """'ATIVO X PASSIVO e OUTROS(n)'"""
    if not partes:
        return ""
    ativos, passivos = [], []
    for p in partes:
        tipo = p.get("tipoParte", "").upper()
        polo = p.get("polo", "").upper()
        nome = p.get("nome", "").strip()
        if tipo in _POLO_ATIVO_KW or polo == "ATIVO":
            ativos.append(nome)
        elif tipo in _POLO_PASSIVO_KW or polo == "PASSIVO":
            passivos.append(nome)
    atv = ativos[0] if ativos else ""
    pas = passivos[0] if passivos else ""
    res = f"{atv} X {pas}".strip()
    extras = max(0, len(ativos) - 1) + max(0, len(passivos) - 1)
    if extras > 0:
        res += f" e OUTROS ({extras})"
    return res


# =============================================================================
# CLASSIFICACAO DE PROCESSOS
# =============================================================================

def is_execucao_fiscal(item: dict) -> bool:
    for t in (item.get("tramitacoes") or []):
        for c in (t.get("classe") or []):
            if c.get("codigo") == 1116:
                return True
    return False


def is_polo_ativo(item: dict, doc_normalizado: str) -> bool:
    for t in (item.get("tramitacoes") or []):
        for p in (t.get("partes") or []):
            if p.get("polo", "").upper() != "ATIVO":
                continue
            for dp in (p.get("documentosPrincipais") or []):
                if re.sub(r"\D", "", dp.get("numero", "")) == doc_normalizado:
                    return True
    return False


def is_polo_passivo_nao_exec_fiscal(tram: dict, doc_normalizado: str) -> int:
    for c in (tram.get("classe") or []):
        if c.get("codigo") == 1116:
            return 0
    for p in (tram.get("partes") or []):
        if p.get("polo", "").upper() == "PASSIVO":
            for dp in (p.get("documentosPrincipais") or []):
                if re.sub(r"\D", "", dp.get("numero", "")) == doc_normalizado:
                    return 1
    return 0


def is_justica_trabalho(numero_cnj: str) -> bool:
    try:
        parts = re.split(r"[-.]", str(numero_cnj).strip())
        return len(parts) >= 6 and parts[4] == "5"
    except Exception:
        return False


# --- termos de extincao (lista completa) ---
EXTINCAO_TERMS = [t.lower() for t in [
    "OBRIGACAO SATISFEITA",
    "EXTINTA A EXECUCAO/CUMPRIMENTO DA SENTENCA PELA SATISFACAO DA OBRIGACAO",
    "PEDIDO DE EXTINCAO (ART. 26, DA LEI 6.830/80)",
    "PEDIDO DE EXTINCAO (ART. 794, I, DO CPC)",
    "EXTINTO O PROCESSO PELO CANCELAMENTO DA DIVIDA ATIVA",
    "EXTINTA A EXECUCAO OU O CUMPRIMENTO DA SENTENCA PELO PAGAMENTO",
    "BAIXA DEFINITIVA",
    "EXTINTO O PROCESSO POR DESISTENCIA",
    "JUNTADA DE PETICAO DE PEDIDO DE EXTINCAO DE EXECUCAO FISCAL POR DESISTENCIA COM RENUNCIA DE PRAZO",
    "JUNTADA DE PETICAO DE PEDIDO DE EXTINCAO DE EXECUCAO FISCAL PELO PAGAMENTO COM RENUNCIA PRAZO",
    "EXTINTO O PROCESSO POR AUSENCIA DAS CONDICOES DA ACAO",
    "JUNTADA DE PETICAO DE PEDIDO DE EXTINCAO DE EXECUCAO FISCAL POR PAGAMENTO/CANCELAMENTO COM RENUNCIA DE PRAZO",
    "EXTINTO O PROCESSO POR ABANDONO DA CAUSA",
    "EXTINTO O PROCESSO POR SER A ACAO INTRANSMISSIVEL",
    "EXTINTO OS AUTOS EM RAZAO DE PERDA DE OBJETO",
    "EXTINTO O PROCESSO POR PEREMPTION, LITISPENDENCIA OU COISA JULGADA",
    "EXTINTO O PROCESSO POR AUSENCIA DE CITACAO DE SUCESSORES DO REU FALECIDO",
    "EXTINTO O PROCESSO POR INEXISTENCIA DE BENS PENHORAVEIS",
    "EXTINTO O PROCESSO POR DEVEDOR NAO ENCONTRADO",
    "EXTINTO O PROCESSO POR FALECIMENTO DO AUTOR SEM HABILITACAO DE SUCESSORES",
    "JUNTADA DE PETICAO DE PEDIDO DE EXTINCAO DE EXECUCAO FISCAL POR PRESCRICAO COM RENUNCIA DE PRAZO",
    "EXTINCAO DO PROCESSO PELO CANCELAMENTO DA DIVIDA ATIVA",
    "JUNTADA DE PETICAO DE EXTINCAO DE EXECUCAO FISCAL POR PRESCRICAO SEM RENUNCIA DE PRAZO",
    "JUNTADA DE PEDICAO DE PEDIDO DE EXTINCAO DE EXECUCAO FISCAL PELO PAGAMENTO SEM RENUNCIA PRAZO",
    "EXTINTA A EXECUCAO OU O CUMPRIMENTO DA SENTENCA",
]]


def extrair_flag_extinto(detalhe: dict) -> int:
    """1 se extinto, 0 se ativo."""
    for t in (detalhe.get("tramitacoes") or []):
        for mov in (t.get("movimentos") or []):
            desc = mov.get("descricao", "").lower()
            if any(term in desc for term in EXTINCAO_TERMS):
                return 1
        ult = t.get("ultimoMovimento")
        if isinstance(ult, dict):
            desc = ult.get("descricao", "").lower()
            if any(term in desc for term in EXTINCAO_TERMS):
                return 1
    return 0


# =============================================================================
# PRIORIZACAO
# =============================================================================

def _unique(seq):
    seen = set()
    return [x for x in seq if not (x in seen or seen.add(x))]


def priorizar_processos(lista_conteudo: list, doc_normalizado: str = None) -> tuple:
    """Retorna (exec_fiscal, polo_ativo, outros). Se doc=None, polo_ativo fica vazio."""
    ef, pa, ou = [], [], []
    for item in lista_conteudo:
        np_val = item.get("numeroProcesso")
        if not np_val:
            continue
        if is_execucao_fiscal(item):
            ef.append(np_val)
        elif doc_normalizado and is_polo_ativo(item, doc_normalizado):
            pa.append(np_val)
        else:
            ou.append(np_val)
    return _unique(ef), _unique(pa), _unique(ou)


# =============================================================================
# EXTRACAO DE DOCUMENTOS DOS PROCESSOS
# =============================================================================

def extrair_documentos_dos_processos(processos: list) -> dict:
    """{doc_normalizado: [processos]}"""
    resultado = {}
    for item in processos:
        docs_encontrados = set()
        for tram in (item.get("tramitacoes") or []):
            for parte in (tram.get("partes") or []):
                for dp in (parte.get("documentosPrincipais") or []):
                    if not isinstance(dp, dict):
                        continue
                    num = dp.get("numero", "")
                    if not num:
                        continue
                    dn = normalizar_documento(num)
                    if len(dn) == 11 and validar_cpf(dn):
                        docs_encontrados.add(dn)
                    elif len(dn) == 14 and validar_cnpj(dn):
                        docs_encontrados.add(dn)
        for dn in docs_encontrados:
            resultado.setdefault(dn, []).append(item)
    return resultado


# =============================================================================
# EXTRACAO DE CAMPOS DETALHADOS DE UM PROCESSO
# =============================================================================

def extrair_campos_processo(item: dict, doc_pasta: str = "",
                             raiz_pasta: str = "NA", filial_pasta: str = "NA",
                             cache_manager=None) -> list:
    """
    Extrai registros estruturados de um JSON de detalhe de processo.
    Retorna lista de dicts (um por tramitacao).
    Inclui: valor corrigido (SELIC), flag extinto, flag reu.
    """
    resultados = []
    numero_proc = (item.get("numeroProcesso") or "").strip()
    if not numero_proc:
        return resultados

    # data primeiro ajuizamento
    data_header = item.get("dataHoraPrimeiroAjuizamento", "")
    dt_header = parse_iso_date(data_header)
    dt_doc = None
    documentos = item.get("documentos") or []
    if isinstance(documentos, list) and documentos:
        datas = []
        for d in documentos:
            dd = d.get("dataHoraJuntada", "")
            dt = parse_iso_date(dd)
            if dt:
                datas.append(dt)
        if datas:
            dt_doc = min(datas)
    if dt_header and dt_doc:
        dt_primeiro = min(dt_header, dt_doc)
    else:
        dt_primeiro = dt_header or dt_doc
    data_primeiro_ajuizamento = dt_primeiro.strftime("%d/%m/%Y") if dt_primeiro else ""

    flag_extinto = extrair_flag_extinto(item)
    doc_normalizado_pasta = re.sub(r"\D", "", doc_pasta or "")

    tramitacoes = item.get("tramitacoes") or []
    for tram in tramitacoes:
        if not isinstance(tram, dict):
            continue
        data_dist = tram.get("dataHoraUltimaDistribuicao", "")
        data_prim_tram = tram.get("dataHoraPrimeiroAjuizamento", "")
        try:
            data_ajuiz = calcular_data_ajuizamento(data_dist, data_prim_tram, numero_proc)
        except Exception:
            data_ajuiz = formatar_data_iso(data_header)

        data_ult_mov = formatar_data_iso(item.get("dataHoraUltimoMovimento", ""))
        valor_acao = tram.get("valorAcao")
        try:
            valor_acao = float(valor_acao) if valor_acao is not None else None
        except (ValueError, TypeError):
            valor_acao = None
        valor_corrigido = corrigir_valor_com_selic(valor_acao, data_ajuiz, cache_manager) if valor_acao else None

        cls = tram.get("classe") or []
        classe_str = classe_hier = ""
        if cls and isinstance(cls[0], dict):
            c0 = cls[0]
            classe_str = f"{c0.get('descricao', '').strip()} ({c0.get('codigo', '')})"
            classe_hier = c0.get("hierarquia", "")

        asst = tram.get("assunto") or []
        assunto_str = assunto_hier = ""
        if asst and isinstance(asst[0], dict):
            a0 = asst[0]
            assunto_str = f"{a0.get('descricao', '').strip()} ({a0.get('codigo', '')})"
            assunto_hier = a0.get("hierarquia", "")

        partes_str = montar_partes_string(tram.get("partes") or [])
        sigla = (item.get("siglaTribunal") or "").strip()
        org = tram.get("orgaoJulgador") or {}
        orgao_str = f"{sigla} - {org.get('nome', '')}"
        instancia = tram.get("instancia", "")
        trib_dict = tram.get("tribunal")
        tribunal = trib_dict.get("nome", "") if isinstance(trib_dict, dict) else ""

        flag_reu = is_polo_passivo_nao_exec_fiscal(tram, doc_normalizado_pasta)

        resultados.append({
            "Numero CNJ": numero_proc,
            "Valor Acao": valor_acao,
            "Valor Corrigido": valor_corrigido,
            "Data Ajuizamento": data_ajuiz,
            "Data Primeiro Ajuizamento": data_primeiro_ajuizamento,
            "Data Ultimo Movimento": data_ult_mov,
            "Classe": classe_str,
            "Classe Hierarquia": classe_hier,
            "Assunto": assunto_str,
            "Assunto Hierarquia": assunto_hier,
            "Partes": partes_str,
            "Orgao Julgador": orgao_str,
            "Instancia": instancia,
            "Tribunal": tribunal,
            "CNPJ Completo": doc_pasta,
            "CNPJ Raiz": raiz_pasta,
            "CNPJ Filial": filial_pasta,
            "Flag Extinto": flag_extinto,
            "Flag Reu": flag_reu,
        })

    # registro base se sem tramitacoes
    if not resultados and numero_proc:
        resultados.append({
            "Numero CNJ": numero_proc,
            "Valor Acao": None, "Valor Corrigido": None,
            "Data Ajuizamento": formatar_data_iso(data_header),
            "Data Primeiro Ajuizamento": data_primeiro_ajuizamento,
            "Data Ultimo Movimento": formatar_data_iso(item.get("dataHoraUltimoMovimento", "")),
            "Classe": "", "Classe Hierarquia": "", "Assunto": "", "Assunto Hierarquia": "",
            "Partes": "", "Orgao Julgador": (item.get("siglaTribunal") or ""),
            "Instancia": "", "Tribunal": "",
            "CNPJ Completo": doc_pasta, "CNPJ Raiz": raiz_pasta, "CNPJ Filial": filial_pasta,
            "Flag Extinto": flag_extinto, "Flag Reu": 0,
        })
    return resultados


def extrair_campos_pagina(item: dict, doc_pasta: str = "") -> dict:
    """Extrai campos basicos de um item de content de page_*.json (sem detalhes)."""
    data = {
        "Numero CNJ": item.get("numeroProcesso"),
        "ID Processo": item.get("id"),
        "Tribunal": item.get("siglaTribunal"),
        "Data Atualizacao": item.get("dataHoraAtualizacao"),
        "Data Ultimo Movimento Global": item.get("dataHoraUltimoMovimento"),
        "CNPJ Completo": doc_pasta,
    }
    trams = item.get("tramitacoes") or []
    if trams:
        t = trams[0]
        data["Data Ajuizamento"] = t.get("dataHoraAjuizamento") or t.get("dataAjuizamento")
        data["Valor Acao"] = t.get("valorAcao")
        cls = t.get("classe") or []
        data["Classe"] = " | ".join(c.get("descricao", "") for c in cls) if isinstance(cls, list) else ""
        asst = t.get("assunto") or []
        data["Assunto"] = " | ".join(a.get("descricao", "") for a in asst) if isinstance(asst, list) else ""
        org = t.get("orgaoJulgador") or {}
        data["Orgao Julgador"] = org.get("nome", "")
        data["Partes"] = montar_partes_string(t.get("partes") or [])
        # flag extinto simples (via ultimoMovimento)
        ult = t.get("ultimoMovimento")
        data["Flag Extinto"] = 0
        if isinstance(ult, dict):
            desc = ult.get("descricao", "").lower()
            if any(term in desc for term in EXTINCAO_TERMS):
                data["Flag Extinto"] = 1
    return data


# =============================================================================
# UTILIDADES DE ARQUIVO
# =============================================================================

def deletar_pastas_vazias(root_dir: str) -> int:
    count = 0
    if not os.path.isdir(root_dir):
        return 0
    abs_root = os.path.abspath(root_dir)
    changed = True
    while changed:
        changed = False
        for dirpath, _, _ in os.walk(root_dir, topdown=False):
            if os.path.abspath(dirpath) == abs_root:
                continue
            try:
                if not os.listdir(dirpath):
                    os.rmdir(dirpath)
                    count += 1
                    changed = True
            except OSError:
                pass
    return count


def pasta_so_tem_paginas(pasta: str) -> bool:
    if not os.path.exists(pasta):
        return True
    try:
        for f in os.listdir(pasta):
            if f.endswith(".json") and not f.startswith("page_"):
                return False
        return True
    except OSError:
        return True
