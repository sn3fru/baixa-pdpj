"""
Devedor360 v2 - Cliente API PDPJ Unificado
Gerencia tokens, retries, backoff, HTTP 429, e paginacao cursor-based.
Aceita Config injetavel para uso com frontend.
"""

import os
import re
import json
import time
import random
import threading
import requests
from datetime import datetime


class PDPJClient:
    """
    Cliente para a API PDPJ.

    Uso CLI:
        from config import Config
        api = PDPJClient.from_config(Config.from_env())

    Uso frontend:
        api = PDPJClient(tokens=["..."], base_url="...")
    """

    def __init__(self, tokens: list, base_url: str,
                 tribunal: str = "TJPE", id_classe: str = "1116",
                 max_por_pagina: int = 100,
                 max_retries: int = 5, backoff_base: float = 1.0,
                 debug: bool = False):
        if not tokens:
            raise ValueError("Pelo menos 1 token PDPJ eh necessario.")
        self.tokens = list(tokens)
        self.base_url = base_url.rstrip("/")
        self.tribunal = tribunal
        self.id_classe = id_classe
        self.max_por_pagina = max_por_pagina
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.debug = debug

        self._token_idx = 0
        self._lock = threading.Lock()
        self._global_429_lock = threading.Event()
        self._global_429_lock.set()  # inicialmente desbloqueado
        self._stats = {"requests": 0, "retries": 0, "errors_429": 0,
                       "errors_other": 0, "pages_ok": 0, "details_ok": 0}

    @classmethod
    def from_config(cls, config) -> "PDPJClient":
        """Cria instancia a partir de Config."""
        return cls(
            tokens=config.tokens,
            base_url=config.base_url,
            tribunal=config.tribunal,
            id_classe=config.id_classe,
            max_por_pagina=config.max_por_pagina,
            debug=config.debug,
        )

    # ── Token rotation ──────────────────────────────────────────────────────

    def _next_token(self) -> str:
        with self._lock:
            t = self.tokens[self._token_idx % len(self.tokens)]
            self._token_idx += 1
            return t

    def _headers(self, token: str = None) -> dict:
        if token is None:
            token = self._next_token()
        return {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    # ── HTTP core ────────────────────────────────────────────────────────────

    def get(self, url: str, params: dict = None, token: str = None,
            timeout: int = 60) -> requests.Response:
        """GET com retries, backoff exponencial e gestao de 429."""
        last_exc = None
        for attempt in range(self.max_retries):
            # espera se 429 global ativo
            self._global_429_lock.wait(timeout=120)

            with self._lock:
                self._stats["requests"] += 1

            headers = self._headers(token)
            try:
                resp = requests.get(url, headers=headers, params=params, timeout=timeout)

                if resp.status_code == 429:
                    with self._lock:
                        self._stats["errors_429"] += 1
                    retry_after = int(resp.headers.get("Retry-After", 30))
                    wait = max(retry_after, 10 * (attempt + 1))
                    if self.debug:
                        print(f"[API] 429 - aguardando {wait}s")
                    self._global_429_lock.clear()
                    time.sleep(wait)
                    self._global_429_lock.set()
                    continue

                if resp.status_code in (500, 502, 503, 504):
                    with self._lock:
                        self._stats["retries"] += 1
                    wait = self.backoff_base * (2 ** attempt) + random.uniform(0, 1)
                    time.sleep(wait)
                    continue

                return resp

            except (requests.ConnectionError, requests.Timeout) as e:
                last_exc = e
                with self._lock:
                    self._stats["errors_other"] += 1
                    self._stats["retries"] += 1
                wait = self.backoff_base * (2 ** attempt) + random.uniform(0, 1)
                time.sleep(wait)
        raise requests.ConnectionError(f"Falha apos {self.max_retries} tentativas: {last_exc}")

    # ── Busca por documento (CPF/CNPJ) ──────────────────────────────────────

    def buscar_por_documento(self, documento: str,
                              max_paginas: int = 100,
                              max_processos: int = 1000,
                              id_classe: str = None,
                              save_dir: str = None,
                              callback=None) -> dict:
        """
        Busca paginada por documento.
        Retorna {'processos': [...items], 'total': int, 'paginas': int, 'gigante': bool}.
        """
        id_cl = id_classe or self.id_classe
        params = {"cpfCnpjParte": documento, "siglaTribunal": self.tribunal,
                  "tamanhoPagina": self.max_por_pagina}
        if id_cl:
            params["idClasse"] = id_cl

        all_items = []
        pagina = 1
        search_after = None
        total_api = None
        gigante = False

        while pagina <= max_paginas:
            if search_after:
                params["searchAfter"] = ",".join(str(x) for x in search_after)

            # Checa se ja temos a pagina em disco
            loaded = self._load_page(save_dir, pagina)
            if loaded is not None:
                data = loaded
            else:
                resp = self.get(self.base_url, params=params)
                if resp.status_code != 200:
                    break
                data = resp.json()
                if save_dir:
                    self._save_page(save_dir, pagina, data)

            # Total da API (pre-flight check)
            if total_api is None:
                total_api = data.get("totalRegistros", 0)
                if callback:
                    callback("total_api", total_api)
                # Verifica se eh caso gigante
                if total_api > 5000:
                    gigante = True

            content = data.get("content") or []
            if not content:
                break
            all_items.extend(content)

            with self._lock:
                self._stats["pages_ok"] += 1

            if len(all_items) >= max_processos:
                break

            search_after = self._extract_search_after(data)
            if not search_after:
                break
            pagina += 1
            if callback:
                callback("pagina", pagina)

        return {
            "processos": all_items,
            "total_api": total_api or len(all_items),
            "paginas": pagina,
            "gigante": gigante,
        }

    # ── Busca por nome ───────────────────────────────────────────────────────

    def buscar_por_nome(self, nome: str,
                         max_paginas: int = 100,
                         max_processos: int = 1000,
                         save_dir: str = None,
                         callback=None) -> dict:
        """
        Busca por nomeParte + outroNomeParte, merge e dedup.
        Retorna {'processos': [...], 'total': int, 'origens': {'nomeParte': int, 'outroNomeParte': int}}.
        """
        resultados = {}
        origens = {}

        for campo in ("nomeParte", "outroNomeParte"):
            params = {campo: nome, "siglaTribunal": self.tribunal,
                      "tamanhoPagina": self.max_por_pagina}
            items = []
            pagina = 1
            search_after = None
            sub_dir = os.path.join(save_dir, campo) if save_dir else None

            while pagina <= max_paginas:
                if search_after:
                    params["searchAfter"] = ",".join(str(x) for x in search_after)

                loaded = self._load_page(sub_dir, pagina)
                if loaded is not None:
                    data = loaded
                else:
                    resp = self.get(self.base_url, params=params)
                    if resp.status_code != 200:
                        break
                    data = resp.json()
                    if sub_dir:
                        self._save_page(sub_dir, pagina, data)

                content = data.get("content") or []
                if not content:
                    break
                items.extend(content)

                with self._lock:
                    self._stats["pages_ok"] += 1

                if len(items) >= max_processos:
                    break
                search_after = self._extract_search_after(data)
                if not search_after:
                    break
                pagina += 1

            origens[campo] = len(items)
            for it in items:
                np_val = it.get("numeroProcesso")
                if np_val and np_val not in resultados:
                    resultados[np_val] = it

        merged = list(resultados.values())
        return {
            "processos": merged,
            "total": len(merged),
            "origens": origens,
        }

    # ── Busca detalhe individual ─────────────────────────────────────────────

    def buscar_detalhe_processo(self, numero_processo: str,
                                 save_path: str = None) -> dict:
        """
        Baixa capa/detalhe de um processo individual.
        Retorna dict do processo ou {} se 404/erro.
        """
        # Tenta carregar do disco primeiro
        if save_path and os.path.isfile(save_path):
            try:
                with open(save_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass

        url = f"{self.base_url}/{numero_processo}"
        try:
            resp = self.get(url)
            if resp.status_code == 404:
                return {}
            if resp.status_code != 200:
                return {}
            data = resp.json()
            with self._lock:
                self._stats["details_ok"] += 1
            if save_path:
                os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
                with open(save_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            return data
        except Exception:
            return {}

    # ── Paginacao / Storage helpers ──────────────────────────────────────────

    def _extract_search_after(self, data: dict):
        """Extrai searchAfter (cursor) da resposta."""
        sa = data.get("searchAfter")
        if sa:
            return sa
        content = data.get("content") or []
        if content:
            last = content[-1]
            sort = last.get("sort")
            if sort:
                return sort
        return None

    def _load_page(self, save_dir: str, pagina: int):
        """Tenta carregar page_N.json do disco."""
        if not save_dir:
            return None
        p = os.path.join(save_dir, f"page_{pagina}.json")
        if not os.path.isfile(p):
            return None
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _save_page(self, save_dir: str, pagina: int, data: dict):
        """Salva page_N.json em disco."""
        if not save_dir:
            return
        os.makedirs(save_dir, exist_ok=True)
        p = os.path.join(save_dir, f"page_{pagina}.json")
        try:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    # ── Stats ────────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        with self._lock:
            return dict(self._stats)
