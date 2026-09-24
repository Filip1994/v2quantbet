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
    "provider_fixture_id",
    "provider_bookmaker_id",
    "provider_bet_id",
    "provider_update_oldest",
    "provider_update_latest",
    "claimed_pick_count",
    "refreshed_fixture_count",
    "persisted_snapshot_count",
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
    "fresh_market_count",
    "stale_market_count",
    "hard_stale_market_count",
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
    "live_corroborations",
    "live_proxy_rejections",
    "item_retry_deferred",
    "max_items",
    "selection_seconds",
    "model_gate_seconds",
    "preliminary_fetch_seconds",
    "quote_processing_seconds",
    "prediction_seconds",
    "evaluation_seconds",
    "registration_seconds",
    "final_fetch_seconds",
    "failure_flush_seconds",
    "cycle_started_at",
    "cycle_finished_at",
    "duration_seconds",
    "next_due_at",
    "fixture_id",
    "market",
    "selection",
    "preliminary_odds",
    "preliminary_edge",
    "preliminary_ev",
    "final_odds",
    "final_edge",
    "final_ev",
    "minimum_playable_odds",
    "quote_age_seconds",
    "stale_quote",
    "warning_codes",
    "rejection_reasons",
    "final_decision",
    "open_exposure_minor",
    "fixed_stake_minor",
    "max_open_exposure_minor",
    "available_bankroll_minor",
    "risk_reserved_pick_count",
    "risk_reserved_played_count",
    "risk_reserved_skipped_count",
    "risk_reserved_played_minor",
    "risk_reserved_skipped_minor",
    "risk_reserved_monitoring_count",
    "risk_reserved_closed_for_odds_count",
    "risk_reserved_without_monitoring_count",
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
