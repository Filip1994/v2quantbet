"""One-shot Railway entrypoint for QuantLab collection and scoring."""

from __future__ import annotations

import logging
import os
from typing import Any

from h2h.quantlab.entrypoint import main as quantlab_main


LOGGER = logging.getLogger("quantbet.quantlab.collector")
COLLECTOR_LOCK_NAME = "quantbet-quantlab-collector-v1"


def _try_collector_lock() -> Any | None:
    """Own one PostgreSQL advisory lock for the lifetime of a one-shot cycle.

    The Railway cron may fire again while a heavy catch-up cycle is still running.
    Session-scoped advisory locking makes the duplicate invocation exit immediately
    instead of duplicating provider requests and database work. A killed process
    automatically releases the lock when PostgreSQL closes the session.
    """
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        return None

    import psycopg

    connection = psycopg.connect(database_url, autocommit=True)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_try_advisory_lock(hashtextextended(%s, 0))",
            (COLLECTOR_LOCK_NAME,),
        )
        acquired = bool(cursor.fetchone()[0])
    if not acquired:
        connection.close()
        return False
    return connection


def _release_collector_lock(connection: Any) -> None:
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_unlock(hashtextextended(%s, 0))",
                (COLLECTOR_LOCK_NAME,),
            )
    finally:
        connection.close()


def main() -> None:
    os.environ.setdefault("QUANTBET_QUANTLAB_COLLECTOR_ONLY", "true")
    os.environ.setdefault("QUANTBET_QUANTLAB_ONE_SHOT", "true")

    lock = _try_collector_lock()
    if lock is False:
        LOGGER.info("QuantLab collector cycle skipped because prior cycle still owns lock")
        return

    try:
        quantlab_main()
    finally:
        if lock is not None:
            _release_collector_lock(lock)


if __name__ == "__main__":
    main()
