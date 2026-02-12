"""API de execucao do pipeline + SSE."""

import json
import asyncio
import threading
import traceback
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from web.state import app_state

router = APIRouter(tags=["pipeline"])


@router.post("/executar")
async def executar_pipeline(body: dict = None):
    """Inicia pipeline em background. Retorna ID do run."""
    if app_state.is_running():
        return {"error": "Pipeline ja esta em execucao.", "status": "already_running",
                "run": app_state.get_current()}

    body = body or {}
    steps = body.get("steps", ["s1", "s2", "s3"])
    config_overrides = body.get("config", {})

    run = app_state.start_run(steps)

    def _run_in_thread():
        try:
            from config import Config
            from pipeline import Pipeline

            cfg = Config.from_env()
            # Aplica overrides do request
            for k, v in config_overrides.items():
                if hasattr(cfg, k):
                    setattr(cfg, k, v)

            def callback(evt, data=None, extra=None):
                payload = {}
                if isinstance(data, dict):
                    payload = data
                elif isinstance(data, str):
                    payload = {"message": data}
                if extra and isinstance(extra, dict):
                    payload.update(extra)
                run.add_event(evt, payload)

            p = Pipeline(cfg, progress_callback=callback)
            result = p.executar(steps=steps)
            run.add_event("pipeline_done", {"result": _safe_serialize(result)})
            app_state.finish_run(result)
        except Exception as e:
            run.add_event("pipeline_error", {"error": str(e), "tb": traceback.format_exc()})
            app_state.finish_run(error=str(e))

    t = threading.Thread(target=_run_in_thread, daemon=True)
    t.start()

    return {"status": "started", "run_id": run.id, "steps": steps}


@router.get("/status")
async def get_status():
    """Retorna status atual do pipeline."""
    return app_state.get_current()


@router.get("/status/stream")
async def stream_status(since: int = Query(0, ge=0)):
    """SSE endpoint - stream de eventos do pipeline em tempo real.

    O parametro 'since' indica o index do ultimo evento recebido.
    Permite reconexao sem perder eventos: cliente envia o ultimo index
    que recebeu e recebe apenas os novos a partir dali.
    """
    async def generate():
        idx = since

        while True:
            events, new_idx, is_running, run_id = app_state.get_run_events(idx)

            # Envia eventos novos
            for evt in events:
                payload = _safe_serialize(evt)
                payload["_idx"] = idx
                yield f"data: {json.dumps(payload)}\n\n"
                idx += 1
            idx = new_idx

            # Se nao esta rodando e ja enviou tudo, finaliza stream
            if not is_running:
                # Envia um ultimo batch caso tenha eventos finais
                events, new_idx, _, _ = app_state.get_run_events(idx)
                for evt in events:
                    payload = _safe_serialize(evt)
                    payload["_idx"] = idx
                    yield f"data: {json.dumps(payload)}\n\n"
                    idx += 1
                yield f"data: {json.dumps({'event': 'stream_end', '_idx': idx})}\n\n"
                return

            # Aguarda antes de checar novos eventos (polling leve)
            await asyncio.sleep(0.5)

            # Heartbeat periodico para manter conexao
            yield f": heartbeat\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream",
                              headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/history")
async def get_history():
    """Retorna historico de execucoes."""
    return app_state.get_history()


def _safe_serialize(obj):
    """Converte objetos nao-serializaveis para JSON."""
    if isinstance(obj, dict):
        return {k: _safe_serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_safe_serialize(i) for i in obj]
    if isinstance(obj, set):
        return sorted(obj)
    if isinstance(obj, float):
        if obj != obj:  # NaN
            return None
        return obj
    return obj
