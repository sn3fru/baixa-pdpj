"""
Devedor360 v2 - Step 1: Coleta Unificada
Substitui s1-BaixaDadosPessoa, s1-BaixaDadosProcesso e s1-nomes-recife.
Para cada individuo faz busca por documento, filiais, nome e numero de processo.
Modular o suficiente para ser chamado por frontend (Flask/FastAPI/Streamlit).
"""

import os
import re
import json
import time
import queue
import threading
import traceback
from datetime import datetime

import pandas as pd

from config import Config
from api_client import PDPJClient
from cache_manager import CacheManager
from utils import (
    normalizar_documento, validar_cpf, validar_cnpj,
    gerar_cnpj_completo, obter_raiz_cnpj, identificar_tipo_documento,
    priorizar_processos, extrair_documentos_dos_processos,
)


# ============================================================================
# Stats  (thread-safe, servido para dashboard e frontend)
# ============================================================================

class GlobalStats:
    def __init__(self):
        self._lock = threading.Lock()
        self.total_individuos = 0
        self.processados = 0
        self.em_andamento = ""
        self.processos_encontrados = 0
        self.detalhes_baixados = 0
        self.detalhes_404 = 0
        self.detalhes_cache = 0
        self.erros = 0
        self.inicio = time.time()

    def inc(self, **kw):
        with self._lock:
            for k, v in kw.items():
                setattr(self, k, getattr(self, k, 0) + v)

    def put(self, **kw):
        with self._lock:
            for k, v in kw.items():
                setattr(self, k, v)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "total": self.total_individuos,
                "processados": self.processados,
                "em_andamento": self.em_andamento,
                "processos": self.processos_encontrados,
                "detalhes": self.detalhes_baixados,
                "det_404": self.detalhes_404,
                "det_cache": self.detalhes_cache,
                "erros": self.erros,
                "elapsed": time.time() - self.inicio,
            }


# ============================================================================
# ColetaUnificada  –  orquestrador principal
# ============================================================================

class ColetaUnificada:
    """
    Orquestra o Step 1 completo.

    CLI:
        resultado = ColetaUnificada(Config.from_env()).executar()

    Frontend:
        coleta = ColetaUnificada(cfg, progress_callback=my_cb)
        resultado = coleta.executar()

    Parcial (apenas lista de processos):
        resultado = coleta.executar_por_processos(["0001234-56..."])
    """

    def __init__(self, config: Config = None, progress_callback=None):
        self.cfg = config or Config.from_env()
        self.cb = progress_callback
        self.api = PDPJClient.from_config(self.cfg)
        self.cache = CacheManager(self.cfg.cache_dir, self.cfg.debug)
        self.stats = GlobalStats()
        self._queue: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._workers: list = []

    # ------------------------------------------------------------------
    #  Execucao principal
    # ------------------------------------------------------------------

    def executar(self) -> dict:
        """Roda pipeline completo: le Excel → busca → salva."""
        cfg = self.cfg
        errs = cfg.validar()
        if errs:
            raise ValueError("; ".join(errs))

        os.makedirs(cfg.output_dir, exist_ok=True)

        df = self._ler_entrada()
        self.stats.put(total_individuos=len(df))
        self._emit("coleta_inicio", {"total": len(df)})

        if cfg.debug:
            cfg.imprimir()

        if cfg.download_detalhes:
            self._start_workers()

        dash = None
        if cfg.dashboard_enabled and not self.cb:
            dash = threading.Thread(target=self._dash_loop, daemon=True)
            dash.start()

        for idx, row in df.iterrows():
            try:
                self._processar_individuo(idx, row)
            except Exception as exc:
                self.stats.inc(erros=1)
                self.cache.log_erro(
                    "", str(row.get("nr_documento", "")),
                    "erro_individuo", traceback.format_exc())
                if cfg.debug:
                    print(f"[ERRO] idx={idx}: {exc}")
            self.stats.inc(processados=1)

        if cfg.download_detalhes:
            self._queue.join()
            self._stop.set()
            for w in self._workers:
                w.join(timeout=10)

        self.cache.save_all()

        res = self.stats.snapshot()
        res["api"] = self.api.get_stats()
        res["cache"] = self.cache.get_stats()
        self._emit("coleta_fim", res)

        if cfg.dashboard_enabled and not self.cb:
            self._print_dash(final=True)

        return res

    # ------------------------------------------------------------------
    #  Execucao por lista de processos (antigo s1-BaixaDadosProcesso)
    # ------------------------------------------------------------------

    def executar_por_processos(self, numeros: list,
                                output_subdir: str = "por_numero") -> dict:
        """
        Baixa detalhes de uma lista explícita de numeros de processo.
        Retorna {numero: detalhe_dict}.
        """
        cfg = self.cfg
        save_dir = os.path.join(cfg.output_dir, output_subdir)
        os.makedirs(save_dir, exist_ok=True)
        resultados = {}
        for proc in numeros:
            proc = proc.strip()
            if not proc:
                continue
            if self.cache.is_processo_404(proc):
                self.stats.inc(detalhes_404=1)
                continue
            fname = f"{proc.replace('/', '_')}.json"
            spath = os.path.join(save_dir, fname)
            data = self.api.buscar_detalhe_processo(proc, save_path=spath)
            if data:
                resultados[proc] = data
                self.stats.inc(detalhes_baixados=1)
                self.cache.add_processo(proc, "ok")
            else:
                self.cache.add_processo_404(proc)
                self.stats.inc(detalhes_404=1)
        self.cache.save_all()
        return resultados

    # ------------------------------------------------------------------
    #  Processar 1 individuo
    # ------------------------------------------------------------------

    def _processar_individuo(self, idx, row):
        cfg = self.cfg

        # ---- identificacao ----
        id_ind = str(row.get("posicao", row.get("id", idx))).strip().zfill(6)
        nome = str(row.get("nome_estoque", row.get("nome", ""))).strip()
        doc_raw = str(row.get("nr_documento", row.get("documento", ""))).strip()
        doc = normalizar_documento(doc_raw)
        tipo = identificar_tipo_documento(doc_raw)
        raiz = obter_raiz_cnpj(doc) if tipo == "CNPJ" else ""

        self.stats.put(em_andamento=f"{id_ind} {nome[:25]}")
        self._emit("ind_start", {"id": id_ind, "nome": nome, "idx": idx})

        ind_dir = os.path.join(cfg.output_dir, id_ind)
        os.makedirs(ind_dir, exist_ok=True)

        if raiz in cfg.blacklist or doc in cfg.blacklist:
            self._save_meta(ind_dir, id_ind, nome, doc, tipo, {"status": "blacklist"})
            return

        pool: dict = {}           # {numero: {"item": ..., "origens": set()}}
        buscas: dict = {}

        # ---- (A) busca por documento ----
        if cfg.enable_busca_documento and doc and tipo:
            buscas["por_documento"] = self._busca_doc(doc, ind_dir, pool)

        # ---- (B) busca filiais CNPJ ----
        if cfg.enable_busca_filial and tipo == "CNPJ" and raiz:
            buscas["por_filial"] = self._busca_filiais(raiz, ind_dir, pool)

        # ---- (C) busca por nome ----
        if cfg.enable_busca_nome and nome:
            buscas["por_nome"] = self._busca_nome(nome, ind_dir, pool)

        # ---- priorizacao ----
        items = [v["item"] for v in pool.values()]
        ef, pa, ou = priorizar_processos(items, doc)
        selecionados = self._aplicar_limites(ef, pa, ou)
        self.stats.inc(processos_encontrados=len(selecionados))

        # ---- salva processos_unicos.json ----
        unicos = {}
        for np_val in selecionados:
            entry = pool.get(np_val, {})
            unicos[np_val] = {
                "origens": sorted(entry.get("origens", set())),
                "prioridade": ("exec_fiscal" if np_val in ef
                               else "polo_ativo" if np_val in pa
                               else "outros"),
                "detalhe_baixado": False,
            }

        pu_path = os.path.join(ind_dir, "processos_unicos.json")
        self._write_json(pu_path, unicos)

        # ---- enfileira detalhes ----
        if cfg.download_detalhes:
            det_dir = os.path.join(ind_dir, "detalhes")
            os.makedirs(det_dir, exist_ok=True)
            for np_val in selecionados:
                if self.cache.is_processo_404(np_val):
                    self.stats.inc(detalhes_404=1)
                    continue
                fname = f"{np_val.replace('/', '_')}.json"
                spath = os.path.join(det_dir, fname)
                if os.path.isfile(spath):
                    self.stats.inc(detalhes_cache=1)
                    self.cache.add_processo(np_val, "ok")
                    unicos[np_val]["detalhe_baixado"] = True
                    continue
                self._queue.put((np_val, spath, doc))
            self._write_json(pu_path, unicos)

        # ---- metadata ----
        self._save_meta(ind_dir, id_ind, nome, doc, tipo, buscas,
                         total=len(selecionados),
                         ef=len(ef), pa=len(pa), ou=len(ou))

        self._emit("ind_done", {"id": id_ind, "procs": len(selecionados), "idx": idx})

    # ------------------------------------------------------------------
    #  Buscas especificas
    # ------------------------------------------------------------------

    def _busca_doc(self, documento, ind_dir, pool) -> dict:
        """Busca por documento (CPF ou CNPJ)."""
        save_dir = os.path.join(ind_dir, "por_documento", "pages")
        try:
            res = self.api.buscar_por_documento(
                documento,
                max_paginas=self.cfg.max_paginas_por_caso,
                max_processos=self.cfg.max_processos_totais,
                save_dir=save_dir)
            for it in res.get("processos", []):
                np_val = it.get("numeroProcesso")
                if np_val:
                    pool.setdefault(np_val, {"item": it, "origens": set()})
                    pool[np_val]["origens"].add("por_documento")
            if res.get("gigante"):
                self.cache.add_caso_gigante(documento, res.get("total_api", 0))
            return {"total_api": res.get("total_api", 0),
                    "processos": len(res.get("processos", [])),
                    "gigante": res.get("gigante", False)}
        except Exception as e:
            self.cache.log_erro("", documento, "busca_doc", str(e))
            return {"erro": str(e)}

    def _busca_filiais(self, raiz, ind_dir, pool) -> dict:
        """Itera filiais de um CNPJ (0002 em diante; 0001 = matriz coberta por busca_doc)."""
        info = {}
        for n in range(2, self.cfg.max_filiais + 2):  # 0002 ate max_filiais+1
            branch = str(n).zfill(4)
            try:
                cnpj_fil = gerar_cnpj_completo(raiz, branch)
            except Exception:
                continue
            if self.cache.is_filial_inexistente(cnpj_fil):
                continue
            sub = os.path.join(ind_dir, "por_filial", cnpj_fil, "pages")
            try:
                res = self.api.buscar_por_documento(
                    cnpj_fil,
                    max_paginas=self.cfg.max_paginas_por_caso,
                    max_processos=self.cfg.max_processos_totais,
                    save_dir=sub)
                qtd = len(res.get("processos", []))
                info[cnpj_fil] = {"processos": qtd}
                if qtd == 0:
                    self.cache.add_filial_inexistente(cnpj_fil)
                for it in res.get("processos", []):
                    np_val = it.get("numeroProcesso")
                    if np_val:
                        pool.setdefault(np_val, {"item": it, "origens": set()})
                        pool[np_val]["origens"].add(f"por_filial:{cnpj_fil}")
            except Exception as e:
                info[cnpj_fil] = {"erro": str(e)}
        return info

    def _busca_nome(self, nome, ind_dir, pool) -> dict:
        """Busca por nomeParte + outroNomeParte, merge e dedup."""
        save_dir = os.path.join(ind_dir, "por_nome")
        try:
            res = self.api.buscar_por_nome(
                nome,
                max_paginas=self.cfg.max_paginas_por_caso,
                max_processos=self.cfg.max_processos_totais,
                save_dir=save_dir)
            # extrai documentos dos processos achados por nome
            docs_enc = extrair_documentos_dos_processos(res.get("processos", []))
            for it in res.get("processos", []):
                np_val = it.get("numeroProcesso")
                if np_val:
                    pool.setdefault(np_val, {"item": it, "origens": set()})
                    pool[np_val]["origens"].add("por_nome")
            return {
                "total": res.get("total", 0),
                "origens_api": res.get("origens", {}),
                "documentos_encontrados": list(docs_enc.keys()),
            }
        except Exception as e:
            self.cache.log_erro("", nome, "busca_nome", str(e))
            return {"erro": str(e)}

    # ------------------------------------------------------------------
    #  Limites
    # ------------------------------------------------------------------

    def _aplicar_limites(self, ef, pa, ou) -> list:
        lim_cat = self.cfg.max_processos_per_doc
        lim_root = self.cfg.max_processos_per_root

        if lim_cat > 0:
            ef = ef[:lim_cat]
            pa = pa[:lim_cat]
            ou = ou[:lim_cat]

        merged = ef + pa + ou

        if lim_root > 0:
            merged = merged[:lim_root]

        return merged

    # ------------------------------------------------------------------
    #  Workers para download de detalhes
    # ------------------------------------------------------------------

    def _start_workers(self):
        for i in range(self.cfg.num_workers):
            t = threading.Thread(target=self._worker, daemon=True, name=f"w{i}")
            t.start()
            self._workers.append(t)

    def _worker(self):
        while not self._stop.is_set():
            try:
                item = self._queue.get(timeout=2)
            except queue.Empty:
                continue
            np_val, spath, doc = item
            try:
                data = self.api.buscar_detalhe_processo(np_val, save_path=spath)
                if data:
                    self.cache.add_processo(np_val, "ok")
                    self.stats.inc(detalhes_baixados=1)
                    self._emit("det_ok", {"proc": np_val})
                else:
                    self.cache.add_processo_404(np_val)
                    self.stats.inc(detalhes_404=1)
            except Exception as e:
                self.stats.inc(erros=1)
                self.cache.log_erro(np_val, doc, "detalhe", str(e))
            finally:
                self._queue.task_done()

    # ------------------------------------------------------------------
    #  Dashboard
    # ------------------------------------------------------------------

    def _dash_loop(self):
        try:
            from IPython.display import clear_output  # noqa: F401
            jup = True
        except ImportError:
            jup = False
        while not self._stop.is_set():
            time.sleep(self.cfg.dashboard_interval)
            self._print_dash(jupyter=jup)

    def _print_dash(self, jupyter=False, final=False):
        s = self.stats.snapshot()
        api = self.api.get_stats()
        h, rem = divmod(int(s["elapsed"]), 3600)
        m, sec = divmod(rem, 60)
        if jupyter:
            try:
                from IPython.display import clear_output
                clear_output(wait=True)
            except Exception:
                pass
        else:
            try:
                os.system("cls" if os.name == "nt" else "clear")
            except Exception:
                pass
        tag = "FINALIZADO" if final else "EM EXECUCAO"
        print(f"""
+==============================================================+
|  DEVEDOR360 v2 - COLETA UNIFICADA  [{tag:^13}]       |
+--------------------------------------------------------------+
|  Tempo       : {h:02d}:{m:02d}:{sec:02d}                                     |
|  Individuos  : {s['processados']:>6} / {s['total']:<6}                        |
|  Atual       : {s['em_andamento'][:42]:<42} |
+--------------------------------------------------------------+
|  Processos encontrados : {s['processos']:>8,}                         |
|  Detalhes baixados     : {s['detalhes']:>8,}                         |
|  Detalhes 404          : {s['det_404']:>8,}                         |
|  Detalhes cache        : {s['det_cache']:>8,}                         |
|  Erros                 : {s['erros']:>8,}                         |
+--------------------------------------------------------------+
|  API reqs: {api['requests']:>6}  429: {api['errors_429']:>4}  retries: {api['retries']:>4}           |
|  Fila    : {self._queue.qsize():>6}                                        |
+==============================================================+""")

    # ------------------------------------------------------------------
    #  Helpers
    # ------------------------------------------------------------------

    def _ler_entrada(self) -> pd.DataFrame:
        path = self.cfg.input_file
        if not os.path.isfile(path):
            alt = os.path.join(os.path.dirname(os.path.abspath(__file__)), path)
            if os.path.isfile(alt):
                path = alt
        if path.lower().endswith(".xls"):
            return pd.read_excel(path, dtype=str, engine="xlrd")
        return pd.read_excel(path, dtype=str)

    def _save_meta(self, ind_dir, id_ind, nome, doc, tipo, buscas,
                    total=0, ef=0, pa=0, ou=0):
        def _ser(o):
            if isinstance(o, set):
                return sorted(o)
            if isinstance(o, dict):
                return {k: _ser(v) for k, v in o.items()}
            if isinstance(o, list):
                return [_ser(i) for i in o]
            return o
        meta = _ser({
            "id": id_ind, "nome": nome, "documento": doc,
            "tipo_documento": tipo,
            "buscas": buscas if isinstance(buscas, dict) else {"info": buscas},
            "total_processos_unicos": total,
            "priorizacao": {"exec_fiscal": ef, "polo_ativo": pa, "outros": ou},
            "timestamp": datetime.now().isoformat(),
        })
        self._write_json(os.path.join(ind_dir, "metadata.json"), meta)

    @staticmethod
    def _write_json(path, data):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _emit(self, evt, data):
        if self.cb:
            try:
                self.cb(evt, data)
            except Exception:
                pass


# ============================================================================
# API de conveniencia  (chamavel por frontend ou CLI)
# ============================================================================

def executar_coleta(config: Config = None, progress_callback=None) -> dict:
    """Executa coleta completa. Retorna dict de estatisticas."""
    return ColetaUnificada(config, progress_callback).executar()


def executar_coleta_processos(processos: list, config: Config = None) -> dict:
    """Baixa detalhes de processos especificos."""
    return ColetaUnificada(config).executar_por_processos(processos)


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    cfg = Config.from_env()
    cfg.imprimir()
    res = executar_coleta(cfg)
    print("\n=== COLETA FINALIZADA ===")
    for k in ("processados", "processos", "detalhes", "det_404", "erros"):
        print(f"  {k:<20}: {res.get(k, 0):>8,}")
    print(f"  {'tempo (s)':<20}: {res.get('elapsed', 0):>8.0f}")
