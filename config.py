"""
Devedor360 v2 - Modulo de Configuracao
Carrega variaveis do .env e define constantes centralizadas.
Inclui classe Config injetavel para uso com frontend (Flask/FastAPI/Streamlit).
"""

import os
import sys

# ---------------------------------------------------------------------------
# Carrega .env
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    _env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(_env_path):
        with open(_env_path, "r", encoding="utf-8") as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _, _v = _line.partition("=")
                    os.environ.setdefault(_k.strip(), _v.strip())


def _bool(val) -> bool:
    if isinstance(val, bool):
        return val
    return str(val).lower() in ("true", "1", "yes", "sim")


def _int(val, default: int = 0) -> int:
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


# ---------------------------------------------------------------------------
# Deteccao de ambiente
# ---------------------------------------------------------------------------
try:
    from IPython.display import clear_output  # noqa: F401
    RUNNING_IN_JUPYTER = True
except ImportError:
    RUNNING_IN_JUPYTER = False


# ---------------------------------------------------------------------------
# Constantes de nivel de modulo (defaults lidos do .env)
# ---------------------------------------------------------------------------
TOKENS = [t.strip() for t in os.getenv("PDPJ_TOKENS", "").split(",") if t.strip()]
BASE_URL = os.getenv("PDPJ_BASE_URL",
                      "https://api-processo-integracao.data-lake.pdpj.jus.br/processo-api/api/v1/processos")
TRIBUNAL = os.getenv("PDPJ_TRIBUNAL", "TJPE")
ID_CLASSE = os.getenv("PDPJ_ID_CLASSE", "1116")

INPUT_FILE = os.getenv("INPUT_FILE", "Recife_nomes_partes_estoque.xlsx")
INPUT_FILE_SECUNDARIO = os.getenv("INPUT_FILE_SECUNDARIO", "entrada-Copy1.xls")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "outputs")

MAX_POR_PAGINA = _int(os.getenv("MAX_POR_PAGINA", "100"), 100)
MAX_PAGINAS_POR_CASO = _int(os.getenv("MAX_PAGINAS_POR_CASO", "100"), 100)
MAX_PROCESSOS_TOTAIS_POR_CASO = _int(os.getenv("MAX_PROCESSOS_TOTAIS_POR_CASO", "1000"), 1000)
MAX_PROCESSOS_ALERTA_API = _int(os.getenv("MAX_PROCESSOS_ALERTA_API", "5000"), 5000)
MAX_PROCESSOS_PER_DOC = _int(os.getenv("MAX_PROCESSOS_PER_DOC", "1"), 1)
MAX_PROCESSOS_PER_CNPJ_ROOT = _int(os.getenv("MAX_PROCESSOS_PER_CNPJ_ROOT", "2"), 2)
MAX_FILIAIS = _int(os.getenv("MAX_FILIAIS", "1"), 1)

DOWNLOAD_DETALHES = _bool(os.getenv("DOWNLOAD_DETALHES", "false"))
ENABLE_BUSCA_DOCUMENTO = _bool(os.getenv("ENABLE_BUSCA_DOCUMENTO", "true"))
ENABLE_BUSCA_NOME = _bool(os.getenv("ENABLE_BUSCA_NOME", "true"))
ENABLE_BUSCA_FILIAL = _bool(os.getenv("ENABLE_BUSCA_FILIAL", "true"))
WORKERS_PER_TOKEN = _int(os.getenv("WORKERS_PER_TOKEN", "1"), 1)
DEBUG = _bool(os.getenv("DEBUG", "false"))

DASHBOARD_ENABLED = _bool(os.getenv("DASHBOARD_ENABLED", "true"))
DASHBOARD_UPDATE_INTERVAL = _int(os.getenv("DASHBOARD_UPDATE_INTERVAL", "10"), 10)

FILTRO_MUNICIPIO = os.getenv("FILTRO_MUNICIPIO", "DISTRITO FEDERAL X")
BLACKLIST = set(os.getenv("BLACKLIST", "9999").split(","))

CACHE_DIR = os.getenv("CACHE_DIR", ".")
SELIC_CACHE_FILE = os.getenv("SELIC_CACHE_FILE", "selic_cache.json")

PROCESSOS_404_FILE = "processos_404.json"
FILIAIS_INEXISTENTES_FILE = "filiais_inexistentes.json"
CASOS_GIGANTES_FILE = "casos_gigantes.json"
CACHE_PROCESSOS_FILE = "cache_processos_completos.json"
LOG_DETALHADO_FILE = "log_detalhado_execucao.json"
LOG_ERROS_FILE = "log_erros_detalhado.json"

NUM_WORKERS = max(1, min(len(TOKENS) * WORKERS_PER_TOKEN, 8)) if TOKENS else 1


# ============================================================================
# Classe Config  -  injetavel via frontend
# ============================================================================
class Config:
    """
    Objeto de configuracao injetavel.

    Uso CLI (le .env):
        cfg = Config.from_env()

    Uso frontend (parametros vindo do formulario):
        cfg = Config.from_dict(request_json)
        cfg = Config(tokens=["..."], download_detalhes=True, ...)
    """

    def __init__(self, **kw):
        # Auth
        self.tokens: list = kw.get("tokens", TOKENS)
        self.base_url: str = kw.get("base_url", BASE_URL)
        self.tribunal: str = kw.get("tribunal", TRIBUNAL)
        self.id_classe: str = kw.get("id_classe", ID_CLASSE)

        # I/O
        self.input_file: str = kw.get("input_file", INPUT_FILE)
        self.input_file_secundario: str = kw.get("input_file_secundario", INPUT_FILE_SECUNDARIO)
        self.output_dir: str = kw.get("output_dir", OUTPUT_DIR)

        # Limites
        self.max_por_pagina: int = _int(kw.get("max_por_pagina", MAX_POR_PAGINA), MAX_POR_PAGINA)
        self.max_paginas_por_caso: int = _int(kw.get("max_paginas_por_caso", MAX_PAGINAS_POR_CASO), MAX_PAGINAS_POR_CASO)
        self.max_processos_totais: int = _int(kw.get("max_processos_totais", MAX_PROCESSOS_TOTAIS_POR_CASO), MAX_PROCESSOS_TOTAIS_POR_CASO)
        self.max_processos_alerta: int = _int(kw.get("max_processos_alerta", MAX_PROCESSOS_ALERTA_API), MAX_PROCESSOS_ALERTA_API)
        self.max_processos_per_doc: int = _int(kw.get("max_processos_per_doc", MAX_PROCESSOS_PER_DOC), MAX_PROCESSOS_PER_DOC)
        self.max_processos_per_root: int = _int(kw.get("max_processos_per_root", MAX_PROCESSOS_PER_CNPJ_ROOT), MAX_PROCESSOS_PER_CNPJ_ROOT)
        self.max_filiais: int = _int(kw.get("max_filiais", MAX_FILIAIS), MAX_FILIAIS)

        # Flags
        self.download_detalhes: bool = _bool(kw.get("download_detalhes", DOWNLOAD_DETALHES))
        self.enable_busca_documento: bool = _bool(kw.get("enable_busca_documento", ENABLE_BUSCA_DOCUMENTO))
        self.enable_busca_nome: bool = _bool(kw.get("enable_busca_nome", ENABLE_BUSCA_NOME))
        self.enable_busca_filial: bool = _bool(kw.get("enable_busca_filial", ENABLE_BUSCA_FILIAL))
        self.workers_per_token: int = _int(kw.get("workers_per_token", WORKERS_PER_TOKEN), WORKERS_PER_TOKEN)
        self.debug: bool = _bool(kw.get("debug", DEBUG))

        # Dashboard
        self.dashboard_enabled: bool = _bool(kw.get("dashboard_enabled", DASHBOARD_ENABLED))
        self.dashboard_interval: int = _int(kw.get("dashboard_interval", DASHBOARD_UPDATE_INTERVAL), DASHBOARD_UPDATE_INTERVAL)

        # Filtros
        self.filtro_municipio: str = kw.get("filtro_municipio", FILTRO_MUNICIPIO)
        self.blacklist: set = set(kw.get("blacklist", BLACKLIST))

        # Cache
        self.cache_dir: str = kw.get("cache_dir", CACHE_DIR)

        # Derivados
        self.num_workers: int = max(1, min(len(self.tokens) * self.workers_per_token, 8)) if self.tokens else 1

    # -- serialização ----------------------------------------------------------

    def to_dict(self) -> dict:
        """Serializa para dict (JSON-safe). Util para API / frontend."""
        d = {}
        for k, v in self.__dict__.items():
            if k.startswith("_"):
                continue
            if isinstance(v, set):
                d[k] = list(v)
            else:
                d[k] = v
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Config":
        """Cria Config a partir de dict (vindo de request JSON, por exemplo)."""
        return cls(**d)

    @classmethod
    def from_env(cls) -> "Config":
        """Cria Config relendo o .env (garante valores frescos apos edicao pelo frontend)."""
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        env_vals = {}
        if os.path.isfile(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, _, v = line.partition("=")
                        env_vals[k.strip()] = v.strip()

        def _g(key, default=""):
            return env_vals.get(key, os.getenv(key, default))

        return cls(
            tokens=[t.strip() for t in _g("PDPJ_TOKENS", "").split(",") if t.strip()],
            base_url=_g("PDPJ_BASE_URL",
                        "https://api-processo-integracao.data-lake.pdpj.jus.br/processo-api/api/v1/processos"),
            tribunal=_g("PDPJ_TRIBUNAL", "TJPE"),
            id_classe=_g("PDPJ_ID_CLASSE", "1116"),
            input_file=_g("INPUT_FILE", "Recife_nomes_partes_estoque.xlsx"),
            input_file_secundario=_g("INPUT_FILE_SECUNDARIO", "entrada-Copy1.xls"),
            output_dir=_g("OUTPUT_DIR", "outputs"),
            max_por_pagina=_int(_g("MAX_POR_PAGINA", "100"), 100),
            max_paginas_por_caso=_int(_g("MAX_PAGINAS_POR_CASO", "100"), 100),
            max_processos_totais=_int(_g("MAX_PROCESSOS_TOTAIS_POR_CASO", "1000"), 1000),
            max_processos_alerta=_int(_g("MAX_PROCESSOS_ALERTA_API", "5000"), 5000),
            max_processos_per_doc=_int(_g("MAX_PROCESSOS_PER_DOC", "1"), 1),
            max_processos_per_root=_int(_g("MAX_PROCESSOS_PER_CNPJ_ROOT", "2"), 2),
            max_filiais=_int(_g("MAX_FILIAIS", "1"), 1),
            download_detalhes=_bool(_g("DOWNLOAD_DETALHES", "false")),
            enable_busca_documento=_bool(_g("ENABLE_BUSCA_DOCUMENTO", "true")),
            enable_busca_nome=_bool(_g("ENABLE_BUSCA_NOME", "true")),
            enable_busca_filial=_bool(_g("ENABLE_BUSCA_FILIAL", "true")),
            workers_per_token=_int(_g("WORKERS_PER_TOKEN", "1"), 1),
            debug=_bool(_g("DEBUG", "false")),
            dashboard_enabled=_bool(_g("DASHBOARD_ENABLED", "true")),
            dashboard_interval=_int(_g("DASHBOARD_UPDATE_INTERVAL", "10"), 10),
            filtro_municipio=_g("FILTRO_MUNICIPIO", "DISTRITO FEDERAL X"),
            blacklist=set(_g("BLACKLIST", "9999").split(",")),
            cache_dir=_g("CACHE_DIR", "."),
        )

    # -- validação -------------------------------------------------------------

    def validar(self) -> list:
        """Retorna lista de erros (vazia = OK)."""
        erros = []
        if not self.tokens:
            erros.append("Nenhum token PDPJ configurado.")
        elif not all(isinstance(t, str) and len(t) > 50 for t in self.tokens):
            erros.append("Um ou mais tokens PDPJ parecem invalidos.")
        if not self.base_url:
            erros.append("base_url nao definida.")
        if not self.input_file:
            erros.append("input_file nao definido.")
        return erros

    def imprimir(self):
        """Imprime resumo da configuracao (sem expor tokens completos)."""
        tok = f"{len(self.tokens)} token(s)" if self.tokens else "NENHUM"
        print("=" * 60)
        print("DEVEDOR360 v2 - CONFIGURACAO")
        print("=" * 60)
        print(f"  Tokens          : {tok}")
        print(f"  API URL         : {self.base_url[:60]}...")
        print(f"  Tribunal        : {self.tribunal}  |  Classe: {self.id_classe}")
        print(f"  Input           : {self.input_file}")
        print(f"  Output          : {self.output_dir}")
        print(f"  Workers         : {self.num_workers}")
        print(f"  Download det.   : {self.download_detalhes}")
        print(f"  Busca documento : {self.enable_busca_documento}")
        print(f"  Busca nome      : {self.enable_busca_nome}")
        print(f"  Busca filial    : {self.enable_busca_filial}")
        print(f"  Max filiais     : {self.max_filiais}")
        print(f"  Max proc/doc    : {self.max_processos_per_doc}")
        print(f"  Max proc/raiz   : {self.max_processos_per_root}")
        print(f"  Alerta gigantes : >{self.max_processos_alerta:,}")
        print(f"  Dashboard       : {self.dashboard_enabled}")
        print(f"  Debug           : {self.debug}")
        print("=" * 60)
