"""Small JSON log formatter with no secret-bearing context."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime


_EXTRA_FIELDS = (
    "worker",
    "provider_endpoint",
    "provider_fixture_date",
    "provider_requests",
    "provider_response_items",
    "fixtures_persisted",
    "eligible_fixtures",
    "phase_i_excluded",
    "waiting_for_window",
    "waiting_for_refresh",
    "due_fixtures",
    "model_unavailable",
    "odds_unavailable",
    "processed_fixtures",
    "failed_fixtures",
    "quotes_fetched",
    "fresh_quotes",
    "predictions",
    "evaluations",
    "decisions",
    "registered_picks",
    "rejected_picks",
    "model_unavailable_scopes",
    "model_unavailable_by_scope",
    "pending_work",
    "budget_exhausted",
    "max_items",
    "cycle_started_at",
    "cycle_finished_at",
    "duration_seconds",
    "next_due_at",
    "fixture_id",
    "pick_id",
    "model_version_id",
    "evaluation_id",
    "settlement_id",
    "result_observation_id",
    "error_class",
    "shutdown_grace_seconds",
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in _EXTRA_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception_class"] = record.exc_info[0].__name__
        return json.dumps(payload, sort_keys=True, ensure_ascii=True, default=str)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
