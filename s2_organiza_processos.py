"""
Devedor360 v2 - Step 2: Organizacao de Processos
Substitui s2-1, s2-2, sx-recife e s2_compile_results.
Le saidas do Step 1, extrai campos, deduplica, corrige SELIC, exporta Excel.
Modular para uso com frontend.
"""

import os
import json
import glob
import traceback
from datetime import datetime

import pandas as pd

from config import Config
from cache_manager import CacheManager
from utils import (
    normalizar_documento, obter_raiz_cnpj, identificar_tipo_documento,
    extrair_campos_processo, extrair_campos_pagina,
    formatar_data_iso, deletar_pastas_vazias,
)


# ============================================================================
# Colunas de exportacao
# ============================================================================

EXPORT_COLUMNS = [
    "ID Individuo", "Nome Cliente", "Origens",
    "Numero CNJ", "Valor Acao", "Valor Corrigido",
    "Data Ajuizamento", "Data Primeiro Ajuizamento", "Data Ultimo Movimento",
    "Classe", "Classe Hierarquia", "Assunto", "Assunto Hierarquia",
    "Partes", "Orgao Julgador", "Instancia", "Tribunal",
    "CNPJ Completo", "CNPJ Raiz", "CNPJ Filial",
    "Flag Extinto", "Flag Reu",
]


# ============================================================================
# Classe principal
# ============================================================================

class OrganizadorProcessos:
    """
    Orchestrator do Step 2.

    CLI:
        df = OrganizadorProcessos(Config.from_env()).executar()

    Frontend:
        org = OrganizadorProcessos(cfg, progress_callback=cb)
        df = org.executar()
    """

    def __init__(self, config: Config = None, progress_callback=None):
        self.cfg = config or Config.from_env()
        self.cb = progress_callback
        self.cache = CacheManager(self.cfg.cache_dir, self.cfg.debug)
        self._stats = {"individuos": 0, "processos_raw": 0,
                        "processos_dedup": 0, "erros": 0}

    # ------------------------------------------------------------------
    #  Execucao principal
    # ------------------------------------------------------------------

    def executar(self) -> pd.DataFrame:
        """
        Pipeline completo:
          1. Le todas as pastas de individuos
          2. Extrai campos (detalhes ou pages)
          3. Deduplica
          4. Junta com dados de cliente
          5. Salva Excel
        Retorna DataFrame consolidado.
        """
        cfg = self.cfg
        output_dir = cfg.output_dir

        # 1. Listar individuos
        ind_dirs = self._listar_individuos(output_dir)
        self._emit("s2_inicio", {"total": len(ind_dirs)})

        # Limpa pastas vazias primeiro
        deletar_pastas_vazias(output_dir)

        # 2. Extrai registros de cada individuo
        all_records = []
        for i, ind_dir in enumerate(ind_dirs):
            try:
                recs = self._processar_individuo(ind_dir)
                all_records.extend(recs)
            except Exception as e:
                self._stats["erros"] += 1
                if cfg.debug:
                    print(f"[S2-ERRO] {ind_dir}: {e}\n{traceback.format_exc()}")
            self._stats["individuos"] += 1
            self._emit("s2_progresso", {"i": i + 1, "total": len(ind_dirs),
                                         "records": len(all_records)})

        if not all_records:
            print("[S2] Nenhum registro encontrado.")
            return pd.DataFrame(columns=EXPORT_COLUMNS)

        df = pd.DataFrame(all_records)
        self._stats["processos_raw"] = len(df)

        # 3. Deduplicacao
        df = self._deduplicar(df)
        self._stats["processos_dedup"] = len(df)

        # 4. Join com dados de cliente (nome da planilha original)
        df = self._join_clientes(df)

        # 5. Ajusta colunas
        for col in EXPORT_COLUMNS:
            if col not in df.columns:
                df[col] = ""
        df = df[EXPORT_COLUMNS]

        # 6. Salva Excel
        out_name = f"saida_processos_consolidados_{datetime.now():%Y%m%d_%H%M}.xlsx"
        out_path = os.path.join(output_dir, out_name)
        df.to_excel(out_path, index=False, engine="openpyxl")
        print(f"[S2] Salvo: {out_path}  ({len(df):,} processos)")

        # Salva caches (SELIC, etc.)
        self.cache.save_all()

        self._emit("s2_fim", {"arquivo": out_path, "total": len(df),
                               "stats": self._stats})
        return df

    # ------------------------------------------------------------------
    #  Funcao parcial: so consolida paginas (sem detalhes)
    # ------------------------------------------------------------------

    def consolidar_paginas(self) -> pd.DataFrame:
        """
        Consolida apenas dados de page_*.json (como o antigo sx-recife).
        Util quando DOWNLOAD_DETALHES=False.
        Retorna DataFrame.
        """
        cfg = self.cfg
        ind_dirs = self._listar_individuos(cfg.output_dir)
        records = []
        for ind_dir in ind_dirs:
            meta = self._ler_metadata(ind_dir)
            id_ind = meta.get("id", os.path.basename(ind_dir))
            nome = meta.get("nome", "")
            doc = meta.get("documento", "")
            pages = self._coletar_pages(ind_dir)
            for page_data in pages:
                for item in (page_data.get("content") or []):
                    rec = extrair_campos_pagina(item, doc)
                    rec["ID Individuo"] = id_ind
                    rec["Nome Cliente"] = nome
                    records.append(rec)
        df = pd.DataFrame(records)
        if not df.empty and "Numero CNJ" in df.columns:
            df.drop_duplicates(subset=["Numero CNJ"], keep="first", inplace=True)
        out_name = f"processos_paginados_consolidados_{datetime.now():%Y%m%d_%H%M}.xlsx"
        out_path = os.path.join(cfg.output_dir, out_name)
        df.to_excel(out_path, index=False, engine="openpyxl")
        print(f"[S2-PAGES] Salvo: {out_path}  ({len(df):,} processos)")
        return df

    # ------------------------------------------------------------------
    #  Processar 1 individuo
    # ------------------------------------------------------------------

    def _processar_individuo(self, ind_dir: str) -> list:
        meta = self._ler_metadata(ind_dir)
        id_ind = meta.get("id", os.path.basename(ind_dir))
        nome = meta.get("nome", "")
        doc = meta.get("documento", "")
        tipo = meta.get("tipo_documento", "")
        raiz = obter_raiz_cnpj(doc) if tipo == "CNPJ" else (doc if tipo == "CPF" else "")

        # Le processos_unicos.json para origens
        pu = self._ler_proc_unicos(ind_dir)

        # Tenta usar detalhes primeiro, fallback para pages
        det_dir = os.path.join(ind_dir, "detalhes")
        records = []

        if os.path.isdir(det_dir):
            for fpath in glob.glob(os.path.join(det_dir, "*.json")):
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    recs = extrair_campos_processo(
                        data, doc_pasta=doc, raiz_pasta=raiz,
                        cache_manager=self.cache)
                    np_val = data.get("numeroProcesso", "")
                    origens_str = ", ".join(pu.get(np_val, {}).get("origens", []))
                    for r in recs:
                        r["ID Individuo"] = id_ind
                        r["Nome Cliente"] = nome
                        r["Origens"] = origens_str
                    records.extend(recs)
                except Exception:
                    self._stats["erros"] += 1

        # Se nao temos detalhes, extrai das paginas
        if not records:
            pages = self._coletar_pages(ind_dir)
            for page_data in pages:
                for item in (page_data.get("content") or []):
                    rec = extrair_campos_pagina(item, doc)
                    np_val = item.get("numeroProcesso", "")
                    origens_str = ", ".join(pu.get(np_val, {}).get("origens", []))
                    rec["ID Individuo"] = id_ind
                    rec["Nome Cliente"] = nome
                    rec["Origens"] = origens_str
                    rec["CNPJ Raiz"] = raiz
                    records.append(rec)

        return records

    # ------------------------------------------------------------------
    #  Deduplicacao (3 etapas, como original)
    # ------------------------------------------------------------------

    def _deduplicar(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or "Numero CNJ" not in df.columns:
            return df

        antes = len(df)

        # Etapa 1: remove duplicatas exatas
        df = df.drop_duplicates(subset=["Numero CNJ"], keep="first")

        # Etapa 2: para linhas ainda duplicadas em Numero CNJ, mantém a com mais info
        if df["Numero CNJ"].duplicated().any():
            df["_info_count"] = df.apply(
                lambda r: sum(1 for v in r if v is not None and str(v).strip()), axis=1)
            df = df.sort_values("_info_count", ascending=False)
            df = df.drop_duplicates(subset=["Numero CNJ"], keep="first")
            df = df.drop(columns=["_info_count"], errors="ignore")

        # Etapa 3: dedup por [Numero CNJ, CNPJ Raiz] se raiz existe
        if "CNPJ Raiz" in df.columns:
            df = df.drop_duplicates(subset=["Numero CNJ", "CNPJ Raiz"], keep="first")

        # Consolida origens de duplicatas antes da dedup
        # (se mesmo processo aparece com origens diferentes, mergeia)
        if "Origens" in df.columns:
            # Agrupa origens unicas por Numero CNJ
            origens_map = {}
            for _, row in df.iterrows():
                cnj = row.get("Numero CNJ", "")
                ori = str(row.get("Origens", ""))
                if cnj not in origens_map:
                    origens_map[cnj] = set()
                for o in ori.split(","):
                    o = o.strip()
                    if o:
                        origens_map[cnj].add(o)
            df["Origens"] = df["Numero CNJ"].map(
                lambda x: ", ".join(sorted(origens_map.get(x, set()))))

        depois = len(df)
        if self.cfg.debug:
            print(f"[S2-DEDUP] {antes:,} -> {depois:,} ({antes - depois:,} removidos)")

        return df.reset_index(drop=True)

    # ------------------------------------------------------------------
    #  Join com dados de cliente
    # ------------------------------------------------------------------

    def _join_clientes(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Se a planilha de entrada possui mapeamento doc->nome,
        preenche Nome Cliente onde estiver vazio.
        """
        cfg = self.cfg
        path = cfg.input_file
        if not os.path.isfile(path):
            alt = os.path.join(os.path.dirname(os.path.abspath(__file__)), path)
            if os.path.isfile(alt):
                path = alt
            else:
                return df

        try:
            if path.lower().endswith(".xls"):
                df_in = pd.read_excel(path, dtype=str, engine="xlrd")
            else:
                df_in = pd.read_excel(path, dtype=str)
        except Exception:
            return df

        # Cria mapeamento doc -> nome
        doc_col = None
        nome_col = None
        for c in df_in.columns:
            cl = c.lower().strip()
            if "documento" in cl or "nr_doc" in cl or "cpf" in cl or "cnpj" in cl:
                doc_col = c
            if "nome" in cl:
                nome_col = c
        if not doc_col or not nome_col:
            return df

        nome_map = {}
        for _, row in df_in.iterrows():
            d = normalizar_documento(str(row.get(doc_col, "")))
            n = str(row.get(nome_col, "")).strip()
            if d and n:
                nome_map[d] = n
                # Mapeia pela raiz tambem
                if len(d) == 14:
                    nome_map[d[:8]] = n

        # Preenche Nome Cliente onde vazio
        if "Nome Cliente" in df.columns:
            mask = df["Nome Cliente"].fillna("").str.strip() == ""
            if "CNPJ Completo" in df.columns:
                df.loc[mask, "Nome Cliente"] = df.loc[mask, "CNPJ Completo"].map(
                    lambda x: nome_map.get(normalizar_documento(str(x)), ""))
            mask2 = df["Nome Cliente"].fillna("").str.strip() == ""
            if "CNPJ Raiz" in df.columns:
                df.loc[mask2, "Nome Cliente"] = df.loc[mask2, "CNPJ Raiz"].map(
                    lambda x: nome_map.get(str(x).strip(), ""))
        return df

    # ------------------------------------------------------------------
    #  Helpers
    # ------------------------------------------------------------------

    def _listar_individuos(self, output_dir: str) -> list:
        """Retorna lista de pastas de individuos (que possuem metadata.json)."""
        if not os.path.isdir(output_dir):
            return []
        dirs = []
        for name in sorted(os.listdir(output_dir)):
            d = os.path.join(output_dir, name)
            if os.path.isdir(d) and os.path.isfile(os.path.join(d, "metadata.json")):
                dirs.append(d)
        # Fallback: pastas sem metadata (formato v1 ou manual)
        if not dirs:
            for name in sorted(os.listdir(output_dir)):
                d = os.path.join(output_dir, name)
                if os.path.isdir(d):
                    dirs.append(d)
        return dirs

    @staticmethod
    def _ler_metadata(ind_dir: str) -> dict:
        p = os.path.join(ind_dir, "metadata.json")
        if os.path.isfile(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"id": os.path.basename(ind_dir)}

    @staticmethod
    def _ler_proc_unicos(ind_dir: str) -> dict:
        p = os.path.join(ind_dir, "processos_unicos.json")
        if os.path.isfile(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    @staticmethod
    def _coletar_pages(ind_dir: str) -> list:
        """Coleta todos page_*.json recursivamente dentro de ind_dir."""
        pages = []
        for root, _, files in os.walk(ind_dir):
            for fn in sorted(files):
                if fn.startswith("page_") and fn.endswith(".json"):
                    try:
                        with open(os.path.join(root, fn), "r", encoding="utf-8") as f:
                            pages.append(json.load(f))
                    except Exception:
                        pass
        return pages

    def _emit(self, evt, data):
        if self.cb:
            try:
                self.cb(evt, data)
            except Exception:
                pass


# ============================================================================
# API de conveniencia
# ============================================================================

def executar_organizacao(config: Config = None, progress_callback=None) -> pd.DataFrame:
    """Executa Step 2 completo. Retorna DataFrame."""
    return OrganizadorProcessos(config, progress_callback).executar()


def consolidar_paginas(config: Config = None) -> pd.DataFrame:
    """Consolida apenas pages (sem detalhes). Retorna DataFrame."""
    return OrganizadorProcessos(config).consolidar_paginas()


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    cfg = Config.from_env()
    print(f"[S2] Processando saidas em: {cfg.output_dir}")

    if cfg.download_detalhes:
        df = executar_organizacao(cfg)
    else:
        print("[S2] DOWNLOAD_DETALHES=False -> consolidando apenas paginas")
        df = consolidar_paginas(cfg)

    print(f"\n=== S2 FINALIZADO ===")
    print(f"  Total processos: {len(df):,}")
    if not df.empty:
        print(f"  Colunas: {list(df.columns)}")
