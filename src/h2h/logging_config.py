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
    "model_training_deferred",
    "fresh_market_count",
    "stale_market_count",
    "hard_stale_market_count",
    "live_corroborations",
    "live_proxy_rejections",
    "item_retry_deferred",
    "stale_retries_requested",
    "stale_retries_scheduled",
    "stale_retries_cleared",
    "stale_retries_suppressed_by_budget",
    "stale_retries_stopped",
    "odds_fetches",
    "compared_quotes",
    "preliminary_refreshes",
    "final_refreshes",
    "fallback_attempts",
    "no_valid_quote_count",
    "bookmaker_wins",
    "model_scope",
    "eligible_model_scopes",
    "claimed_model_scopes",
    "activated_model_scopes",
    "insufficient_data_scopes",
    "training_failed_scopes",
    "training_provider_requests",
    "accepted_matches",
    "fitted_matches",
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
