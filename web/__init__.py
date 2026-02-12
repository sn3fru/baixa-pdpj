"""
Devedor360 v2 - Web Application (FastAPI)
"""
import os
import sys

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
