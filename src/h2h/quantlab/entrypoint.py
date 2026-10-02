"""Standalone Railway entrypoint for the QuantLab collector and dashboard."""

from __future__ import annotations

import logging
import os
from threading import Event

from h2h.archive.object_store import S3ObjectStore
from h2h.archive.repository import ColdArchiveCatalog
from h2h.archive.service import ColdArchiveWriter
from h2h.logging_config import configure_logging
from h2h.persistence.migrations import MIGRATION_RUNNER_VERSION
from h2h.persistence.postgres_model_lifecycle import (
    PostgreSQLActiveDixonColesModelRepository,
    PostgreSQLDixonColesModelVersionRepository,
)
from h2h.quantlab.budget import QuantLabRequestBudget
from h2h.quantlab.card_lab.audit import log_cardlab_v5_audit
from h2h.quantlab.card_lab.referee_web import StatBunkerRefereeSource
from h2h.quantlab.card_lab.shadow_engine import CardLabShadowPickEngine
from h2h.quantlab.corner_lab.audit import log_cornerlab_v2_audit
from h2h.quantlab.corner_lab.readiness_audit import (
    log_cornerlab_v2_readiness,
    log_cornerlab_v2_training_readiness,
)
from h2h.quantlab.corner_lab.research_audit import log_cornerlab_historical_holdout
from h2h.quantlab.corner_lab.shadow_engine import CornerLabShadowPickEngine
from h2h.quantlab.dashboard import QuantLabDashboardHTTPService, QuantLabDashboardService
from h2h.quantlab.goal_lab.audit import ensure_latest_goal_model_validation
from h2h.quantlab.goal_lab.composite_engine import GoalLabCompositeEngine
from h2h.quantlab.goal_lab.picks import PICK_POLICY_VERSION
from h2h.quantlab.goal_lab.readiness import assert_goallab_v1_contract
from h2h.quantlab.goal_lab.shadow_engine import GoalLabShadowPickEngine
from h2h.quantlab.goal_lab.structural_shadow_engine import (
    GoalLabStructuralShadowEngine,
    StructuralGoalPolicy,
)
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


def _boolean(name: str, default: str = "false") -> bool:
    value = os.getenv(name, default).strip().casefold()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


def _market_archive_writer(database_url: str) -> ColdArchiveWriter | None:
    required = ("BUCKET", "ACCESS_KEY_ID", "SECRET_ACCESS_KEY", "ENDPOINT")
    present = {name: bool(os.getenv(name, "").strip()) for name in required}
    if not any(present.values()):
        LOGGER.info("QuantLab raw odds archive disabled; bucket variables are absent")
        return None
    if not all(present.values()):
        LOGGER.warning(
            "QuantLab raw odds archive disabled; bucket variable references are incomplete"
        )
        return None
    try:
        return ColdArchiveWriter(
            ColdArchiveCatalog(database_url),
            S3ObjectStore.from_environment(),
        )
    except Exception:
        LOGGER.exception(
            "QuantLab raw odds archive setup failed; PostgreSQL raw fallback remains active"
        )
        return None


def _log_latest_goal_picks(repository: PostgreSQLQuantLabRepository, *, limit: int = 20) -> None:
    """Emit the dedicated canonical GoalLab pick sector."""
    for row in repository.list_goal_picks(limit=limit):
        LOGGER.info(
            "GoalLab canonical pick fixture=%s match=%s vs %s league=%s "
            "kickoff=%s bookmaker=%s market=%s selection=%s odds=%s "
            "model_p=%s market_p=%s edge=%s ev=%s lambda_home=%s lambda_away=%s "
            "outcome=%s pnl_minor=%s model_version=%s",
            row.get("fixture_id"),
            row.get("home_team"),
            row.get("away_team"),
            row.get("competition_name"),
            row.get("kickoff_at"),
            row.get("bookmaker_name"),
            row.get("market_key"),
            row.get("selection"),
            row.get("odds"),
            row.get("model_probability"),
            row.get("market_probability"),
            row.get("edge"),
            row.get("expected_value"),
            row.get("expected_home_goals"),
            row.get("expected_away_goals"),
            row.get("outcome") or "PENDING",
            row.get("pnl_minor"),
            row.get("model_version"),
        )


def main() -> None:
    configure_logging(os.getenv("LOG_LEVEL", "INFO"))
    stop = Event()
    install_shutdown_handlers(stop.set)

    database_url = _database_url()
    repository = PostgreSQLQuantLabRepository(database_url)
    if not repository.check_database():
        raise RuntimeError("QuantLab schema is unavailable")

    LOGGER.info("QuantLab migration runner=%s", MIGRATION_RUNNER_VERSION)

    goal_contract = assert_goallab_v1_contract()
    LOGGER.info(
        "GoalLab active lock verified lock=%s model_prefix=%s feature=%s "
        "evaluation_policy=%s pick_policy=%s settlement=%s validation=%s",
        goal_contract["lock_version"],
        goal_contract["model_prefix"],
        goal_contract["feature_version"],
        goal_contract["evaluation_policy_version"],
        goal_contract["pick_policy_version"],
        goal_contract["settlement_rule_version"],
        goal_contract["validation_method_version"],
    )

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
    goal_control_engine = GoalLabShadowPickEngine(repository, model_loader)
    goal_pick_authority = _boolean("QUANTBET_QUANTLAB_GOAL_PICK_AUTHORITY", "false")
    approved_goal_model_version = (
        os.getenv("QUANTBET_QUANTLAB_GOAL_APPROVED_MODEL_VERSION", "").strip() or None
    )
    goal_structural_engine = GoalLabStructuralShadowEngine(
        repository,
        policy=StructuralGoalPolicy(
            pick_authority=goal_pick_authority,
            approved_model_version=approved_goal_model_version,
        ),
    )
    LOGGER.info(
        "GoalLab DC+ pick authority=%s approved_model=%s policy=%s",
        goal_pick_authority,
        approved_goal_model_version,
        PICK_POLICY_VERSION,
    )
    goal_engine = GoalLabCompositeEngine(goal_control_engine, goal_structural_engine)
    corner_engine = CornerLabShadowPickEngine(repository)
    card_engine = CardLabShadowPickEngine(repository)

    market_archive_writer = _market_archive_writer(database_url)
    LOGGER.info(
        "QuantLab raw odds archive enabled=%s",
        market_archive_writer is not None,
    )
    referee_web_source = (
        StatBunkerRefereeSource(
            timeout=float(os.getenv("QUANTBET_QUANTLAB_REFEREE_WEB_TIMEOUT_SECONDS", "10"))
        )
        if _boolean("QUANTBET_QUANTLAB_REFEREE_WEB_ENABLED", "true")
        else None
    )
    runtime = QuantLabRuntime(
        repository,
        provider,
        goal_engine=goal_engine,
        corner_engine=corner_engine,
        card_engine=card_engine,
        market_archive_writer=market_archive_writer,
        referee_web_source=referee_web_source,
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
            goal_injury_refresh_seconds=_positive_integer(
                "QUANTBET_QUANTLAB_GOAL_INJURY_REFRESH_SECONDS", "14400"
            ),
            goal_lineup_refresh_seconds=_positive_integer(
                "QUANTBET_QUANTLAB_GOAL_LINEUP_REFRESH_SECONDS", "900"
            ),
            goal_lineup_window_minutes=_positive_integer(
                "QUANTBET_QUANTLAB_GOAL_LINEUP_WINDOW_MINUTES", "120"
            ),
            goal_coach_refresh_seconds=_positive_integer(
                "QUANTBET_QUANTLAB_GOAL_COACH_REFRESH_SECONDS", "86400"
            ),
            history_backfill_per_cycle=_integer(
                "QUANTBET_QUANTLAB_HISTORY_BACKFILL_PER_CYCLE", "25"
            ),
            goal_team_history_last=_positive_integer(
                "QUANTBET_QUANTLAB_GOAL_TEAM_HISTORY_LAST", "15"
            ),
            goal_team_history_teams_per_cycle=_positive_integer(
                "QUANTBET_QUANTLAB_GOAL_TEAM_HISTORY_TEAMS_PER_CYCLE", "120"
            ),
            goal_team_statistics_per_cycle=_positive_integer(
                "QUANTBET_QUANTLAB_GOAL_TEAM_STATS_PER_CYCLE", "360"
            ),
            goal_player_history_per_cycle=_positive_integer(
                "QUANTBET_QUANTLAB_GOAL_PLAYER_HISTORY_PER_CYCLE", "60"
            ),
            goal_team_history_refresh_seconds=_positive_integer(
                "QUANTBET_QUANTLAB_GOAL_TEAM_HISTORY_REFRESH_SECONDS", "21600"
            ),
            corner_team_history_last=_positive_integer(
                "QUANTBET_QUANTLAB_CORNER_TEAM_HISTORY_LAST", "12"
            ),
            corner_team_history_teams_per_cycle=_positive_integer(
                "QUANTBET_QUANTLAB_CORNER_TEAM_HISTORY_TEAMS_PER_CYCLE", "120"
            ),
            corner_team_statistics_per_cycle=_positive_integer(
                "QUANTBET_QUANTLAB_CORNER_TEAM_STATS_PER_CYCLE", "360"
            ),
            corner_team_history_refresh_seconds=_positive_integer(
                "QUANTBET_QUANTLAB_CORNER_TEAM_HISTORY_REFRESH_SECONDS", "21600"
            ),
            card_referee_history_target=_positive_integer(
                "QUANTBET_QUANTLAB_CARD_REFEREE_HISTORY_TARGET", "8"
            ),
            card_referee_history_lookback_days=_positive_integer(
                "QUANTBET_QUANTLAB_CARD_REFEREE_HISTORY_LOOKBACK_DAYS", "1100"
            ),
            card_referee_prior_seasons=int(
                os.environ.get("QUANTBET_QUANTLAB_CARD_REFEREE_PRIOR_SEASONS", "3")
            ),
            card_referee_history_days_per_cycle=_positive_integer(
                "QUANTBET_QUANTLAB_CARD_REFEREE_DAYS_PER_CYCLE", "12"
            ),
            card_referee_history_scopes_per_cycle=_positive_integer(
                "QUANTBET_QUANTLAB_CARD_REFEREE_SCOPES_PER_CYCLE", "24"
            ),
            card_referee_statistics_per_cycle=_positive_integer(
                "QUANTBET_QUANTLAB_CARD_REFEREE_STATS_PER_CYCLE", "128"
            ),
            card_referee_history_refresh_seconds=_positive_integer(
                "QUANTBET_QUANTLAB_CARD_REFEREE_HISTORY_REFRESH_SECONDS", "604800"
            ),
            card_referee_statistics_retry_seconds=_positive_integer(
                "QUANTBET_QUANTLAB_CARD_REFEREE_STATS_RETRY_SECONDS", "86400"
            ),
            card_referee_web_refresh_seconds=_positive_integer(
                "QUANTBET_QUANTLAB_CARD_REFEREE_WEB_REFRESH_SECONDS", "21600"
            ),
            card_referee_web_seasons=_positive_integer(
                "QUANTBET_QUANTLAB_CARD_REFEREE_WEB_SEASONS", "3"
            ),
            league_coverage_refresh_seconds=_positive_integer(
                "QUANTBET_QUANTLAB_LEAGUE_COVERAGE_REFRESH_SECONDS", "21600"
            ),
        ),
    )

    collector_only = _boolean("QUANTBET_QUANTLAB_COLLECTOR_ONLY", "false")
    one_shot = _boolean("QUANTBET_QUANTLAB_ONE_SHOT", "false")
    server = None
    if not collector_only:
        dashboard = QuantLabDashboardService(
            repository,
            api_daily_limit=api_daily_limit,
            currency=os.getenv("QUANTBET_CURRENCY", "RSD").strip().upper() or "RSD",
        )
        server = QuantLabDashboardHTTPService(
            dashboard, host="0.0.0.0", port=_positive_integer("PORT", "8080")
        )
    cycle_seconds = _positive_integer("QUANTBET_QUANTLAB_CYCLE_SECONDS", "300")
    inline_goal_validation = _boolean(
        "QUANTBET_QUANTLAB_INLINE_GOAL_VALIDATION", "false"
    )
    inline_research_audits = _boolean(
        "QUANTBET_QUANTLAB_INLINE_RESEARCH_AUDITS", "false"
    )
    model_ready_audit_emitted = not inline_research_audits
    try:
        if server is not None:
            server.start()
            LOGGER.info("QuantLab dashboard listening; startup audits continue asynchronously from healthcheck perspective")
        else:
            LOGGER.info("QuantLab collector-only runtime started")
        if inline_research_audits:
            try:
                log_cardlab_v5_audit(repository, LOGGER)
            except Exception:
                LOGGER.exception("QuantLab CardLab V5 startup audit failed")

            try:
                log_cornerlab_v2_audit(repository, LOGGER)
                log_cornerlab_v2_readiness(repository, LOGGER)
                log_cornerlab_historical_holdout(repository, LOGGER)
            except Exception:
                LOGGER.exception("QuantLab CornerLab V2 startup audit failed")
            else:
                model_ready_audit_emitted = True

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
        if inline_goal_validation:
            try:
                ensure_latest_goal_model_validation(repository, LOGGER)
            except Exception as exc:
                sqlstate = getattr(exc, "sqlstate", None)
                error_text = str(exc)
                LOGGER.exception(
                    "GoalLab DC+ startup validation failed error_class=%s sqlstate=%s error=%s",
                    type(exc).__name__,
                    sqlstate,
                    error_text,
                )
        while not stop.is_set():
            try:
                cycle_result = runtime.run_once()
                if inline_research_audits and (
                    cycle_result.get("card_decisions") or cycle_result.get("card_picks")
                ):
                    try:
                        log_cardlab_v5_audit(repository, LOGGER)
                    except Exception:
                        LOGGER.exception("QuantLab CardLab V5 cycle audit failed")
                goal_readiness = goal_structural_engine.readiness()
                LOGGER.info(
                    "GoalLab DC+ readiness reason=%s training_sample=%s minimum=%s "
                    "history_matches=%s active_features=%s model_version=%s "
                    "api_used_today=%s api_daily_limit=%s",
                    goal_readiness.get("reason"),
                    goal_readiness.get("training_sample_size"),
                    goal_readiness.get("minimum_training_examples", 300),
                    goal_readiness.get("history_match_count"),
                    goal_readiness.get("active_feature_count"),
                    goal_readiness.get("model_version"),
                    repository.api_usage_today(),
                    api_daily_limit,
                )
                if inline_goal_validation:
                    try:
                        ensure_latest_goal_model_validation(repository, LOGGER)
                    except Exception as exc:
                        sqlstate = getattr(exc, "sqlstate", None)
                        error_text = str(exc)
                        LOGGER.exception(
                            "GoalLab DC+ validation failed error_class=%s sqlstate=%s error=%s",
                            type(exc).__name__,
                            sqlstate,
                            error_text,
                        )
                if inline_research_audits:
                    readiness = log_cornerlab_v2_training_readiness(repository, LOGGER)
                    if (
                        bool(readiness["model_fit_eligible"])
                        and not model_ready_audit_emitted
                    ):
                        try:
                            log_cornerlab_v2_audit(repository, LOGGER)
                            log_cornerlab_v2_readiness(repository, LOGGER)
                        except Exception:
                            LOGGER.exception(
                                "QuantLab CornerLab V2 model-ready transition audit failed"
                            )
                        else:
                            model_ready_audit_emitted = True
            except Exception as exc:
                error_text = str(exc)
                LOGGER.exception(
                    "QuantLab cycle failed error_class=%s error=%s",
                    type(exc).__name__,
                    error_text,
                )
            if one_shot:
                LOGGER.info("QuantLab one-shot collector cycle complete; exiting")
                break
            stop.wait(cycle_seconds)
    finally:
        if server is not None:
            server.close()


if __name__ == "__main__":
    main()
