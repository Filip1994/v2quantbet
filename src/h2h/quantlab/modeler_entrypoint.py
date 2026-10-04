"""Offline QuantLab model fitting, validation, and research-audit entrypoint."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime

from h2h.logging_config import configure_logging
from h2h.persistence.migrations import MIGRATION_RUNNER_VERSION
from h2h.quantlab.card_lab.audit import log_cardlab_v5_audit
from h2h.quantlab.corner_lab.audit import log_cornerlab_v2_audit
from h2h.quantlab.corner_lab.model import CornerPressureModelService
from h2h.quantlab.corner_lab.readiness_audit import log_cornerlab_v2_readiness
from h2h.quantlab.corner_lab.research_audit import log_cornerlab_historical_holdout
from h2h.quantlab.goal_lab.audit import ensure_latest_goal_model_validation
from h2h.quantlab.goal_lab.model import GoalStructuralModelService
from h2h.quantlab.goal_lab.readiness import assert_goallab_v1_contract
from h2h.quantlab.repository import PostgreSQLQuantLabRepository


LOGGER = logging.getLogger("quantbet.quantlab.modeler")


def _database_url() -> str:
    value = (
        os.getenv("QUANTBET_QUANTLAB_DATABASE_URL", "").strip()
        or os.getenv("DATABASE_URL", "").strip()
    )
    if not value:
        raise ValueError("Missing QUANTBET_QUANTLAB_DATABASE_URL or DATABASE_URL")
    return value


def _boolean(name: str, default: str = "false") -> bool:
    value = os.getenv(name, default).strip().casefold()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


def main() -> None:
    configure_logging(os.getenv("LOG_LEVEL", "INFO"))
    database_url = _database_url()
    repository = PostgreSQLQuantLabRepository(database_url)
    if not repository.check_database():
        raise RuntimeError("QuantLab schema is unavailable")

    LOGGER.info("QuantLab modeler migration runner=%s", MIGRATION_RUNNER_VERSION)
    goal_enabled = _boolean("QUANTBET_QUANTLAB_GOAL_ENABLED", "true")
    corner_enabled = _boolean("QUANTBET_QUANTLAB_CORNER_ENABLED", "true")
    card_enabled = _boolean("QUANTBET_QUANTLAB_CARD_ENABLED", "true")
    h2h_enabled = _boolean("QUANTBET_QUANTLAB_H2H_ENABLED", "true")
    LOGGER.info(
        "QuantLab modeler lab switches goal=%s corner=%s card=%s h2h=%s",
        goal_enabled,
        corner_enabled,
        card_enabled,
        h2h_enabled,
    )

    now = datetime.now(UTC)
    if goal_enabled:
        contract = assert_goallab_v1_contract()
        LOGGER.info(
            "QuantLab modeler GoalLab contract lock=%s model_prefix=%s feature=%s",
            contract["lock_version"],
            contract["model_prefix"],
            contract["feature_version"],
        )
        goal_readiness = GoalStructuralModelService(repository).readiness(decision_at=now)
        LOGGER.info("QuantLab modeler GoalLab readiness=%s", goal_readiness)
        validation = ensure_latest_goal_model_validation(
            repository,
            LOGGER,
            evaluated_at=now,
        )
        LOGGER.info(
            "QuantLab modeler GoalLab validation status=%s model=%s",
            validation.get("status"),
            validation.get("model_version"),
        )

    if corner_enabled:
        corner_readiness = CornerPressureModelService(repository).readiness(decision_at=now)
        LOGGER.info("QuantLab modeler CornerLab readiness=%s", corner_readiness)
        log_cornerlab_v2_audit(repository, LOGGER)
        log_cornerlab_v2_readiness(repository, LOGGER)
        log_cornerlab_historical_holdout(repository, LOGGER)

    if card_enabled:
        log_cardlab_v5_audit(repository, LOGGER)


if __name__ == "__main__":
    main()
