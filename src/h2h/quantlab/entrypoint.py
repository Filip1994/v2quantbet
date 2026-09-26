"""Standalone Railway entrypoint for the QuantLab collector and dashboard."""

from __future__ import annotations

import logging
import os
from threading import Event

from h2h.logging_config import configure_logging
from h2h.persistence.postgres_model_lifecycle import (
    PostgreSQLActiveDixonColesModelRepository,
    PostgreSQLDixonColesModelVersionRepository,
)
from h2h.quantlab.budget import QuantLabRequestBudget
from h2h.quantlab.card_lab.shadow_engine import CardLabShadowPickEngine
from h2h.quantlab.corner_lab.audit import log_cornerlab_v2_audit
from h2h.quantlab.corner_lab.readiness_audit import log_cornerlab_v2_readiness
from h2h.quantlab.corner_lab.shadow_engine import CornerLabShadowPickEngine
from h2h.quantlab.dashboard import QuantLabDashboardHTTPService, QuantLabDashboardService
from h2h.quantlab.goal_lab.shadow_engine import GoalLabShadowPickEngine
from h2h.quantlab.provider import QuantLabApiFootballClient
from h2h.quantlab.repository import PostgreSQLQuantLabRepository
from h2h.quantlab.runtime import QuantLabRuntime, QuantLabRuntimeSettings
from h2h.use_cases.model_lifecycle import LoadActiveDixonColesModel
from h2h.workers.runtime import install_shutdown_handlers


LOGGER = logging.getLogger("quantbet.quantlab")


def _database_url() -> str:
    value = (
        os.getenv("QUANTBET_QUANTLAB_DATABASE_URL", "").strip()
        or os.getenv("DATABASE_URL", "").strip()
    )
    if not value:
        raise ValueError("Missing QUANTBET_QUANTLAB_DATABASE_URL or DATABASE_URL")
    return value


def _integer(name: str, default: str) -> int:
    try:
        value = int(os.getenv(name, default).strip())
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


def _positive_integer(name: str, default: str) -> int:
    value = _integer(name, default)
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _log_latest_goal_picks(repository: PostgreSQLQuantLabRepository, *, limit: int = 20) -> None:
    """Emit a bounded read-only snapshot for operational inspection."""
    for row in repository.list_bets("GOAL", limit=limit):
        LOGGER.info(
            "QuantLab GoalLab shadow pick fixture=%s match=%s vs %s league=%s "
            "kickoff=%s bookmaker=%s market=%s selection=%s line=%s odds=%s "
            "model_p=%s market_p=%s edge=%s ev=%s",
            row.get("fixture_id"),
            row.get("home_team"),
            row.get("away_team"),
            row.get("competition_name"),
            row.get("kickoff_at"),
            row.get("bookmaker_name"),
            row.get("market_key"),
            row.get("selection"),
            row.get("line"),
            row.get("odds"),
            row.get("model_probability"),
            row.get("market_probability"),
            row.get("edge"),
            row.get("expected_value"),
        )


def main() -> None:
    configure_logging(os.getenv("LOG_LEVEL", "INFO"))
    stop = Event()
    install_shutdown_handlers(stop.set)

    database_url = _database_url()
    repository = PostgreSQLQuantLabRepository(database_url)
    if not repository.check_database():
        raise RuntimeError("QuantLab schema is unavailable")

    try:
        log_cornerlab_v2_audit(repository, LOGGER)
        log_cornerlab_v2_readiness(repository, LOGGER)
    except Exception:
        LOGGER.exception("QuantLab CornerLab V2 startup audit failed")

    api_daily_limit = _positive_integer("QUANTBET_API_DAILY_LIMIT", "75000")
    api_key = os.getenv("API_FOOTBALL_KEY", "").strip()
    if not api_key:
        raise ValueError("API_FOOTBALL_KEY is required for QuantLab collection")

    budget = QuantLabRequestBudget(
        shared_daily_limit=api_daily_limit,
        production_reserve=_integer("QUANTBET_API_RESERVE", "0"),
        database_url=database_url,
    )
    provider = QuantLabApiFootballClient(
        api_key=api_key,
        budget=budget,
        timeout=float(os.getenv("QUANTBET_QUANTLAB_API_TIMEOUT_SECONDS", "10")),
    )
    model_loader = LoadActiveDixonColesModel(
        PostgreSQLDixonColesModelVersionRepository(database_url),
        PostgreSQLActiveDixonColesModelRepository(database_url),
    )
    goal_engine = GoalLabShadowPickEngine(repository, model_loader)
    corner_engine = CornerLabShadowPickEngine(repository)
    card_engine = CardLabShadowPickEngine(repository)

    runtime = QuantLabRuntime(
        repository,
        provider,
        goal_engine=goal_engine,
        corner_engine=corner_engine,
        card_engine=card_engine,
        settings=QuantLabRuntimeSettings(
            lookahead_hours=_positive_integer("QUANTBET_QUANTLAB_LOOKAHEAD_HOURS", "36"),
            discovery_lookback_days=_integer(
                "QUANTBET_QUANTLAB_DISCOVERY_LOOKBACK_DAYS", "1"
            ),
            fixture_limit=_positive_integer("QUANTBET_QUANTLAB_FIXTURE_LIMIT", "1000"),
            fixture_discovery_refresh_seconds=_positive_integer(
                "QUANTBET_QUANTLAB_FIXTURE_DISCOVERY_REFRESH_SECONDS", "21600"
            ),
            market_refresh_seconds=_positive_integer(
                "QUANTBET_QUANTLAB_MARKET_REFRESH_SECONDS", "3600"
            ),
            context_refresh_seconds=_positive_integer(
                "QUANTBET_QUANTLAB_CONTEXT_REFRESH_SECONDS", "21600"
            ),
            standings_refresh_seconds=_positive_integer(
                "QUANTBET_QUANTLAB_STANDINGS_REFRESH_SECONDS", "21600"
            ),
            feature_refresh_seconds=_positive_integer(
                "QUANTBET_QUANTLAB_FEATURE_REFRESH_SECONDS", "1800"
            ),
            history_backfill_per_cycle=_integer(
                "QUANTBET_QUANTLAB_HISTORY_BACKFILL_PER_CYCLE", "25"
            ),
            corner_team_history_last=_positive_integer(
                "QUANTBET_QUANTLAB_CORNER_TEAM_HISTORY_LAST", "12"
            ),
            corner_team_history_teams_per_cycle=_positive_integer(
                "QUANTBET_QUANTLAB_CORNER_TEAM_HISTORY_TEAMS_PER_CYCLE", "40"
            ),
            corner_team_statistics_per_cycle=_positive_integer(
                "QUANTBET_QUANTLAB_CORNER_TEAM_STATS_PER_CYCLE", "120"
            ),
            corner_team_history_refresh_seconds=_positive_integer(
                "QUANTBET_QUANTLAB_CORNER_TEAM_HISTORY_REFRESH_SECONDS", "21600"
            ),
        ),
    )

    dashboard = QuantLabDashboardService(
        repository,
        api_daily_limit=api_daily_limit,
        currency=os.getenv("QUANTBET_CURRENCY", "RSD").strip().upper() or "RSD",
    )
    server = QuantLabDashboardHTTPService(
        dashboard, host="0.0.0.0", port=_positive_integer("PORT", "8080")
    )
    cycle_seconds = _positive_integer("QUANTBET_QUANTLAB_CYCLE_SECONDS", "300")
    _log_latest_goal_picks(repository)
    for lab, label in (("CORNER", "CornerLab"), ("CARD", "CardLab")):
        for row in repository.list_bets(lab, limit=20):
            LOGGER.info(
                "QuantLab %s shadow pick fixture=%s match=%s vs %s league=%s "
                "kickoff=%s bookmaker=%s market=%s selection=%s line=%s odds=%s "
                "model_p=%s market_p=%s edge=%s ev=%s",
                label,
                row.get("fixture_id"),
                row.get("home_team"),
                row.get("away_team"),
                row.get("competition_name"),
                row.get("kickoff_at"),
                row.get("bookmaker_name"),
                row.get("market_key"),
                row.get("selection"),
                row.get("line"),
                row.get("odds"),
                row.get("model_probability"),
                row.get("market_probability"),
                row.get("edge"),
                row.get("expected_value"),
            )

    try:
        server.start()
        while not stop.is_set():
            try:
                runtime.run_once()
            except Exception as exc:
                error_text = str(exc)
                LOGGER.exception(
                    "QuantLab cycle failed error_class=%s error=%s",
                    type(exc).__name__,
                    error_text,
                )
            stop.wait(cycle_seconds)
    finally:
        server.close()


if __name__ == "__main__":
    main()
