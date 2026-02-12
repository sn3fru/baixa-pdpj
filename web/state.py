"""
Devedor360 v2 - Estado da aplicacao web.
Gerencia runs do pipeline, eventos SSE, e estado global.

Design: eventos ficam numa lista (append-only). SSE usa index para saber
onde parou. Multiplas conexoes SSE podem coexistir. Reconectar funciona
perfeitamente porque a lista nunca perde eventos.
"""

import time
import threading
from datetime import datetime
from dataclasses import dataclass, field


@dataclass
class RunInfo:
    id: str
    steps: list
    started: str
    status: str = "running"       # running, completed, error
    finished: str = ""
    result: dict = field(default_factory=dict)
    events: list = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add_event(self, evt: str, data: dict = None):
        entry = {"event": evt, "data": data or {}, "ts": time.time()}
        with self._lock:
            self.events.append(entry)

    def get_events_since(self, index: int) -> tuple:
        """Retorna (novos_eventos, novo_index). Thread-safe."""
        with self._lock:
            if index >= len(self.events):
                return [], index
            new = self.events[index:]
            return new, len(self.events)

    @property
    def event_count(self) -> int:
        with self._lock:
            return len(self.events)

    @property
    def last_event(self) -> dict:
        with self._lock:
            return self.events[-1] if self.events else None


class AppState:
    """
    Singleton de estado da aplicacao.
    Thread-safe para acesso pelo pipeline (em thread) e FastAPI (async).
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.current_run: RunInfo = None
        self.last_completed_run: RunInfo = None  # Guarda ultimo run finalizado
        self.history: list = []
        self._run_counter = 0

    def start_run(self, steps: list) -> RunInfo:
        with self._lock:
            self._run_counter += 1
            run = RunInfo(
                id=f"run_{self._run_counter:04d}",
                steps=steps,
                started=datetime.now().isoformat(),
            )
            self.current_run = run
            return run

    def finish_run(self, result: dict = None, error: str = None):
        with self._lock:
            if self.current_run:
                self.current_run.finished = datetime.now().isoformat()
                self.current_run.status = "error" if error else "completed"
                self.current_run.result = result or {}
                if error:
                    self.current_run.result["error"] = error
                self.last_completed_run = self.current_run
                self.history.append({
                    "id": self.current_run.id,
                    "steps": self.current_run.steps,
                    "started": self.current_run.started,
                    "finished": self.current_run.finished,
                    "status": self.current_run.status,
                    "events_total": self.current_run.event_count,
                    "summary": {
                        k: v for k, v in (result or {}).items()
                        if k in ("processados", "processos", "detalhes", "elapsed",
                                 "total_processos", "total_entidades")
                    },
                })
                if len(self.history) > 50:
                    self.history = self.history[-50:]
                self.current_run = None

    def is_running(self) -> bool:
        with self._lock:
            return self.current_run is not None

    def get_current(self) -> dict:
        with self._lock:
            if not self.current_run:
                # Se tem um run recem-finalizado, informa
                if self.last_completed_run:
                    r = self.last_completed_run
                    return {
                        "running": False,
                        "last_run": {
                            "id": r.id,
                            "status": r.status,
                            "started": r.started,
                            "finished": r.finished,
                            "events_total": r.event_count,
                        }
                    }
                return {"running": False}
            r = self.current_run
            return {
                "running": True,
                "id": r.id,
                "steps": r.steps,
                "started": r.started,
                "events_total": r.event_count,
                "last_event": r.last_event,
            }

    def get_run_events(self, since: int = 0) -> tuple:
        """Retorna eventos do run atual ou ultimo finalizado.
        Returns: (events, new_index, is_running, run_id)"""
        with self._lock:
            run = self.current_run or self.last_completed_run
            if not run:
                return [], 0, False, None
            events, new_idx = run.get_events_since(since)
            is_running = self.current_run is not None
            return events, new_idx, is_running, run.id

    def get_history(self) -> list:
        with self._lock:
            return list(reversed(self.history))


# Singleton
app_state = AppState()
