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


def main() -> None:
    configure_logging(os.getenv("LOG_LEVEL", "INFO"))
    database_url = _database_url()
    repository = PostgreSQLQuantLabRepository(database_url)
    if not repository.check_database():
        raise RuntimeError("QuantLab schema is unavailable")

    LOGGER.info("QuantLab modeler migration runner=%s", MIGRATION_RUNNER_VERSION)
    contract = assert_goallab_v1_contract()
    LOGGER.info(
        "QuantLab modeler GoalLab contract lock=%s model_prefix=%s feature=%s",
        contract["lock_version"],
        contract["model_prefix"],
        contract["feature_version"],
    )

    now = datetime.now(UTC)
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

    corner_readiness = CornerPressureModelService(repository).readiness(decision_at=now)
    LOGGER.info("QuantLab modeler CornerLab readiness=%s", corner_readiness)

    log_cornerlab_v2_audit(repository, LOGGER)
    log_cornerlab_v2_readiness(repository, LOGGER)
    log_cornerlab_historical_holdout(repository, LOGGER)
    log_cardlab_v5_audit(repository, LOGGER)


if __name__ == "__main__":
    main()
