"""Offline fitting for CornerLab only; no provider API calls."""
import logging
import os
from datetime import UTC, datetime

from h2h.cornerlab_entrypoint import configure_corner_only
from h2h.logging_config import configure_logging
from h2h.quantlab.corner_lab.model import CornerPressureModelService
from h2h.quantlab.repository import PostgreSQLQuantLabRepository


def main() -> None:
    configure_corner_only()
    configure_logging(os.getenv('LOG_LEVEL', 'INFO'))
    logger = logging.getLogger('quantbet.cornerlab.modeler')
    url = os.getenv('QUANTBET_QUANTLAB_DATABASE_URL') or os.getenv('DATABASE_URL')
    repository = PostgreSQLQuantLabRepository(url)
    if not repository.check_database():
        raise RuntimeError('CornerLab schema is unavailable')
    logger.info('CornerLab modeler: corner=True goal=False h2h=False card=False; API requests=0')
    readiness = CornerPressureModelService(repository).readiness(decision_at=datetime.now(UTC))
    logger.info('CornerLab modeler readiness=%s', readiness)
    # Rolling evidence and calibration now run in Research. The former offline
    # holdout/readiness audits remain available as manual tools in preserved code.


if __name__ == '__main__':
    main()
