"""Minimal operational liveness and readiness HTTP service."""

from __future__ import annotations

import json
from dataclasses import asdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock, Thread
from typing import Any

from h2h.production import ProductionApplication


@dataclass
class RuntimeHealthState:
    schema_current: bool = False
    leadership: str = "starting"
    scheduler_alive: bool = False
    accepting_work: bool = False
    missing_model_scopes: tuple[str, ...] = ()
    last_scheduler_tick: datetime | None = None
    _lock: Lock = field(default_factory=Lock, repr=False)

    def update(self, **values: Any) -> None:
        with self._lock:
            for name, value in values.items():
                setattr(self, name, value)


class HealthService:
    def __init__(
        self,
        application: ProductionApplication,
        state: RuntimeHealthState,
        *,
        host: str,
        port: int,
    ) -> None:
        self._application = application
        self._state = state
        service = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if self.path == "/livez":
                    service._respond(self, 200, service.liveness())
                elif self.path == "/readyz":
                    body = service.readiness()
                    service._respond(self, 200 if body["ready"] else 503, body)
                else:
                    service._respond(self, 404, {"error": "not_found"})

            def log_message(self, _format: str, *_args: object) -> None:
                return

        self._server = ThreadingHTTPServer((host, port), Handler)
        self._thread = Thread(target=self._server.serve_forever, name="health-http", daemon=True)

    @staticmethod
    def _respond(handler: BaseHTTPRequestHandler, status: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(body, sort_keys=True, default=str).encode("utf-8")
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(encoded)))
        handler.end_headers()
        handler.wfile.write(encoded)

    def start(self) -> None:
        self._thread.start()

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    def liveness(self) -> dict[str, Any]:
        return {
            "live": self._thread.is_alive(),
            "scheduler_alive": self._state.scheduler_alive,
            "leadership": self._state.leadership,
        }

    def readiness(self) -> dict[str, Any]:
        app = self._application
        generated_at = datetime.now(UTC)
        try:
            database = app.runtime.check_database()
            workers = []
            stale_workers: list[str] = []
            for status in app.runtime.worker_statuses():
                item = asdict(status)
                stale = bool(
                    status.next_due_at is not None
                    and generated_at > status.next_due_at + timedelta(seconds=120)
                )
                item["stale"] = stale
                workers.append(item)
                if stale:
                    stale_workers.append(status.worker_name)
            counts = app.runtime.operational_counts()
            policy = app.settings.application.registration_policy
            assert policy is not None
            performance = app.results.performance.summary(policy.bankroll_account_id)
            bankroll = {
                "available_minor": performance.available_bankroll_minor,
                "open_exposure_minor": performance.open_exposure_minor,
                "currency": performance.currency,
            }
        except Exception as exc:  # noqa: BLE001 - readiness must degrade, never crash HTTP
            database = False
            workers = []
            stale_workers = []
            counts = {}
            bankroll = None
            database_error = type(exc).__name__
        else:
            database_error = None
        budget = app.budget
        ready = bool(
            database
            and self._state.schema_current
            and self._state.leadership == "active"
            and self._state.scheduler_alive
            and self._state.accepting_work
            and not self._state.missing_model_scopes
            and not stale_workers
        )
        return {
            "ready": ready,
            "database": {"reachable": database, "error_class": database_error},
            "schema_current": self._state.schema_current,
            "leadership": self._state.leadership,
            "workers": workers,
            "stale_workers": stale_workers,
            "provider_budget": {
                "day": budget.day.isoformat(),
                "used": budget.used,
                "effective_limit": budget.effective_limit,
                "remaining": budget.remaining,
                "exhausted": budget.exhausted,
                "last_error_class": app.provider_state.last_error_class,
                "last_error_message": app.provider_state.last_error_message,
                "last_error_at": app.provider_state.last_error_at,
            },
            "missing_active_model_scopes": self._state.missing_model_scopes,
            "counts": counts,
            "bankroll": bankroll,
            "generated_at": generated_at,
        }
