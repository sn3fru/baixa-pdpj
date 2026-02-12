"""
Devedor360 v2 - Gerenciamento Unificado de Caches
Thread-safe. Aceita Config injetavel.
"""

import os
import json
import threading
from datetime import datetime


# Nomes de arquivo default (override via construtor)
_DEFAULTS = dict(
    processos_404="processos_404.json",
    filiais_inex="filiais_inexistentes.json",
    casos_gigantes="casos_gigantes.json",
    cache_procs="cache_processos_completos.json",
    selic="selic_cache.json",
    log_det="log_detalhado_execucao.json",
    log_erros="log_erros_detalhado.json",
)


class CacheManager:
    """
    Gerenciamento unificado de caches (thread-safe).

    Uso CLI:
        cache = CacheManager()

    Uso frontend (pasta custom):
        cache = CacheManager(cache_dir="/tmp/run123")
    """

    def __init__(self, cache_dir: str = ".", debug: bool = False, **file_overrides):
        self.cache_dir = cache_dir
        self.debug = debug
        self._lock = threading.Lock()

        # Nomes dos arquivos (permitem override)
        self._files = {k: file_overrides.get(k, v) for k, v in _DEFAULTS.items()}

        # Dados em memoria
        self.processos_404: set = set()
        self.filiais_inexistentes: set = set()
        self.casos_gigantes: dict = {}
        self.cache_processos: dict = {}
        self.selic_cache: dict = {}

        self._hits = {"p404": 0, "filial": 0, "proc": 0, "selic": 0}
        self._load_all()

    # ── I/O helpers ──────────────────────────────────────────────────────────

    def _path(self, key: str) -> str:
        return os.path.join(self.cache_dir, self._files[key])

    def _load_set(self, key: str) -> set:
        p = self._path(key)
        if os.path.isfile(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    d = json.load(f)
                return set(d) if isinstance(d, list) else set()
            except Exception:
                pass
        return set()

    def _load_dict(self, key: str) -> dict:
        p = self._path(key)
        if os.path.isfile(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    d = json.load(f)
                return d if isinstance(d, dict) else {}
            except Exception:
                pass
        return {}

    def _save(self, key: str, data):
        p = self._path(key)
        try:
            os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
            payload = list(data) if isinstance(data, set) else data
            with open(p, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
        except Exception as e:
            if self.debug:
                print(f"[CACHE-ERR] {key}: {e}")

    def _load_all(self):
        self.processos_404 = self._load_set("processos_404")
        self.filiais_inexistentes = self._load_set("filiais_inex")
        self.casos_gigantes = self._load_dict("casos_gigantes")
        self.cache_processos = self._load_dict("cache_procs")
        self.selic_cache = self._load_dict("selic")
        if self.debug:
            print(f"[CACHE] p404={len(self.processos_404)}  filiais={len(self.filiais_inexistentes)}  "
                  f"gigantes={len(self.casos_gigantes)}  procs={len(self.cache_processos)}  "
                  f"selic={len(self.selic_cache)}")

    # ── Processos 404 ────────────────────────────────────────────────────────

    def is_processo_404(self, proc: str) -> bool:
        with self._lock:
            hit = proc in self.processos_404
            if hit:
                self._hits["p404"] += 1
            return hit

    def add_processo_404(self, proc: str):
        with self._lock:
            self.processos_404.add(proc)

    # ── Filiais inexistentes ─────────────────────────────────────────────────

    def is_filial_inexistente(self, cnpj: str) -> bool:
        with self._lock:
            return cnpj in self.filiais_inexistentes

    def add_filial_inexistente(self, cnpj: str):
        with self._lock:
            self.filiais_inexistentes.add(cnpj)

    # ── Casos gigantes ───────────────────────────────────────────────────────

    def is_caso_gigante(self, doc: str) -> bool:
        with self._lock:
            return doc in self.casos_gigantes

    def add_caso_gigante(self, doc: str, total: int):
        with self._lock:
            self.casos_gigantes[doc] = total

    # ── Cache processos ──────────────────────────────────────────────────────

    def is_processo_processado(self, proc: str) -> bool:
        with self._lock:
            return proc in self.cache_processos

    def get_status_processo(self, proc: str) -> str:
        with self._lock:
            return self.cache_processos.get(proc, "")

    def add_processo(self, proc: str, status: str):
        with self._lock:
            self.cache_processos[proc] = status

    def separar_processados(self, lista: list) -> tuple:
        with self._lock:
            ja = [p for p in lista if p in self.cache_processos]
            falta = [p for p in lista if p not in self.cache_processos]
            return ja, falta

    # ── SELIC ────────────────────────────────────────────────────────────────

    def get_selic(self, key: str):
        with self._lock:
            v = self.selic_cache.get(key)
            if v is not None:
                self._hits["selic"] += 1
            return v

    def set_selic(self, key: str, valor: float):
        with self._lock:
            self.selic_cache[key] = valor

    # ── Logs ─────────────────────────────────────────────────────────────────

    def log_erro(self, processo: str, documento: str, tipo: str, detalhes: str):
        try:
            p = self._path("log_erros")
            logs = []
            if os.path.isfile(p):
                with open(p, "r", encoding="utf-8") as f:
                    logs = json.load(f)
            logs.append({"ts": datetime.now().isoformat(), "proc": processo,
                         "doc": documento, "tipo": tipo, "det": detalhes})
            if len(logs) > 2000:
                logs = logs[-2000:]
            with open(p, "w", encoding="utf-8") as f:
                json.dump(logs, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def log_detalhado(self, documento: str, info: dict):
        try:
            p = self._path("log_det")
            existing = {}
            if os.path.isfile(p):
                with open(p, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            info["timestamp"] = datetime.now().isoformat()
            existing[documento] = info
            with open(p, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    # ── Persistencia ─────────────────────────────────────────────────────────

    def save_all(self):
        self._save("processos_404", self.processos_404)
        self._save("filiais_inex", self.filiais_inexistentes)
        self._save("casos_gigantes", self.casos_gigantes)
        self._save("cache_procs", self.cache_processos)
        self._save("selic", self.selic_cache)
        if self.debug:
            print("[CACHE] Todos os caches salvos.")

    def get_stats(self) -> dict:
        with self._lock:
            return {
                "processos_404": len(self.processos_404),
                "filiais_inexistentes": len(self.filiais_inexistentes),
                "casos_gigantes": len(self.casos_gigantes),
                "cache_processos": len(self.cache_processos),
                "selic_cache": len(self.selic_cache),
                "hits": dict(self._hits),
            }
