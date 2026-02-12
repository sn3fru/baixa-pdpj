"""Rotas de paginas HTML."""

from fastapi import APIRouter, Request
from web import templates
from web.state import app_state
from flags import listar_flags

router = APIRouter(tags=["pages"])


@router.get("/")
async def page_dashboard(request: Request):
    return templates.TemplateResponse("pages/dashboard.html", {
        "request": request, "page": "dashboard",
        "state": app_state.get_current(),
        "history": app_state.get_history()[:10],
    })


@router.get("/upload")
async def page_upload(request: Request):
    return templates.TemplateResponse("pages/upload.html", {
        "request": request, "page": "upload",
    })


@router.get("/pipeline")
async def page_pipeline(request: Request):
    return templates.TemplateResponse("pages/pipeline.html", {
        "request": request, "page": "pipeline",
        "state": app_state.get_current(),
    })


@router.get("/config")
async def page_config(request: Request):
    return templates.TemplateResponse("pages/config.html", {
        "request": request, "page": "config",
        "flags": listar_flags(),
    })


@router.get("/individuos")
async def page_individuos(request: Request):
    return templates.TemplateResponse("pages/individuos.html", {
        "request": request, "page": "individuos",
    })


@router.get("/processos")
async def page_processos(request: Request):
    return templates.TemplateResponse("pages/processos.html", {
        "request": request, "page": "processos",
    })


@router.get("/devedores")
async def page_devedores(request: Request):
    return templates.TemplateResponse("pages/devedores.html", {
        "request": request, "page": "devedores",
    })


@router.get("/homonimos")
async def page_homonimos(request: Request):
    return templates.TemplateResponse("pages/homonimos.html", {
        "request": request, "page": "homonimos",
    })


@router.get("/arquivos")
async def page_arquivos(request: Request):
    return templates.TemplateResponse("pages/arquivos.html", {
        "request": request, "page": "arquivos",
    })


@router.get("/ajuda")
async def page_ajuda(request: Request):
    return templates.TemplateResponse("pages/ajuda.html", {
        "request": request, "page": "ajuda",
        "flags": listar_flags(),
    })
