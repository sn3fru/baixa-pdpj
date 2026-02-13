"""
Devedor360 v2 - Web Application (FastAPI)
"""
import os
import sys
import glob
import threading

# Garante que o diretorio pai esta no path (para imports do pipeline)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

_WEB_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="Devedor360", version="2.0")

# Static files
_static_dir = os.path.join(_WEB_DIR, "static")
os.makedirs(_static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=_static_dir), name="static")

# Templates
templates = Jinja2Templates(directory=os.path.join(_WEB_DIR, "templates"))

# Include routers
from web.routes.pages import router as pages_router          # noqa: E402
from web.routes.api_config import router as config_router     # noqa: E402
from web.routes.api_pipeline import router as pipeline_router # noqa: E402
from web.routes.api_data import router as data_router         # noqa: E402

app.include_router(pages_router)
app.include_router(config_router, prefix="/api")
app.include_router(pipeline_router, prefix="/api")
app.include_router(data_router, prefix="/api")


# ============================================================================
# Cache warming: pre-load Excel files in background on startup
# ============================================================================

def _warm_cache():
    """Pre-carrega os Excel pesados no _DFCache para que o primeiro request
    de cada pagina seja instantaneo em vez de esperar 3-5s de pd.read_excel."""
    try:
        from config import Config
        from web.routes.api_data import _df_cache

        cfg = Config.from_env()
        output_dir = cfg.output_dir
        if not os.path.isdir(output_dir):
            return

        # Pre-carrega S2 (processos consolidados)
        for f in sorted(glob.glob(os.path.join(output_dir, "saida_processos_consolidados_*.xlsx")), reverse=True):
            try:
                _df_cache.get(f)
                print(f"[CACHE] Pre-loaded: {os.path.basename(f)}")
            except Exception:
                pass
            break  # So o mais recente

        # Pre-carrega S3 (visao devedor)
        for f in sorted(glob.glob(os.path.join(output_dir, "visao_devedor_*.xlsx")), reverse=True):
            try:
                _df_cache.get(f)
                print(f"[CACHE] Pre-loaded: {os.path.basename(f)}")
            except Exception:
                pass
            break

    except Exception as e:
        print(f"[CACHE] Warm-up error: {e}")


@app.on_event("startup")
async def startup_cache_warm():
    """Inicia pre-carregamento de dados em background thread.
    Nao bloqueia o startup do servidor."""
    t = threading.Thread(target=_warm_cache, daemon=True)
    t.start()
