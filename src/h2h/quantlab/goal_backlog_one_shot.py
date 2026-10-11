"""Run one guarded GoalLab backlog catch-up using existing immutable settlement rules.

This is an operational one-shot, not a new scoring engine, and intentionally
does not touch CornerLab, CardLab, H2H, Production or active GoalLab picks.
"""
from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta

import psycopg

from h2h.logging_config import configure_logging
from h2h.odds.budget import ApiBudgetExceededError
from h2h.quantlab.budget import QuantLabRequestBudget
from h2h.quantlab.fixture_discovery import parse_fixture_discovery_response
from h2h.quantlab.goal_lab.picks import (
    GOAL_RESULT_FINALITY_DELAY_SECONDS,
    settle_goal_pick,
    stable_goal_result_evidence,
)
from h2h.quantlab.provider import QuantLabApiFootballClient
from h2h.quantlab.repository import PostgreSQLQuantLabRepository

LOGGER = logging.getLogger("quantbet.goallab.backlog.oneshot")
LOCK_NAME = "quantbet-goallab-backlog-oneshot-v1"
MIN_AGE = timedelta(hours=48)
MAX_CALLS = 75


def stats(repository: PostgreSQLQuantLabRepository) -> dict[str, int]:
    with repository.connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT (SELECT count(*) FROM quantlab_goal_pick_settlements), "
            "(SELECT count(*) FROM quantlab_goal_picks p "
            "WHERE p.kickoff_at < now() - interval '48 hours' "
            "AND NOT EXISTS (SELECT 1 FROM quantlab_goal_pick_settlements s "
            "WHERE s.goal_pick_id = p.goal_pick_id)), "
            "(SELECT count(*) FROM quantlab_goal_picks p "
            "WHERE p.kickoff_at < date '2026-10-04' "
            "AND NOT EXISTS (SELECT 1 FROM quantlab_goal_pick_settlements s "
            "WHERE s.goal_pick_id = p.goal_pick_id))"
        )
        total, overdue, original = cursor.fetchone()
        return {
            "settled": int(total),
            "overdue_48h": int(overdue),
            "old_before_oct4": int(original),
        }


def settle_confirmed(repository: PostgreSQLQuantLabRepository, now: datetime) -> int:
    count = 0
    for row in repository.goal_pick_settlement_candidates(limit=1000):
        if row["kickoff_at"] > now - MIN_AGE:
            continue
        try:
            evidence = stable_goal_result_evidence(
                row, finality_delay_seconds=GOAL_RESULT_FINALITY_DELAY_SECONDS,
            )
            if evidence is None:
                continue
            settled = settle_goal_pick({**row, **evidence}, settled_at=now)
            if settled and repository.save_goal_pick_settlement(settled):
                count += 1
                LOGGER.info("GOALLAB_ONESHOT_SETTLED fixture=%s outcome=%s",
                            settled.fixture_id, settled.outcome)
        except Exception:
            LOGGER.exception("GOALLAB_ONESHOT_SETTLE_FAILED fixture=%s", row["fixture_id"])
    return count


def pending_historical_targets(repository: PostgreSQLQuantLabRepository, now: datetime):
    """Only pre-existing unsettled picks older than 48h; prioritize known FT."""
    with repository.connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT DISTINCT ON (p.fixture_id) "
            "p.fixture_id, f.provider_fixture_id, o.provider_status, o.captured_at "
            "FROM quantlab_goal_picks p "
            "JOIN quantlab_fixtures f ON f.fixture_id = p.fixture_id "
            "JOIN LATERAL (SELECT provider_status, captured_at "
            "FROM quantlab_fixture_observations x "
            "WHERE x.fixture_id = p.fixture_id "
            "ORDER BY captured_at DESC, fixture_observation_id DESC LIMIT 1) o ON true "
            "WHERE p.kickoff_at < %s "
            "AND o.captured_at < %s "
            "AND NOT EXISTS (SELECT 1 FROM quantlab_goal_pick_settlements s "
            "WHERE s.goal_pick_id = p.goal_pick_id) "
            "ORDER BY p.fixture_id, p.kickoff_at",
            (now - MIN_AGE, now - timedelta(
                seconds=GOAL_RESULT_FINALITY_DELAY_SECONDS,
            )),
        )
        values = [dict(zip([c.name for c in cursor.description], x, strict=True))
                  for x in cursor.fetchall()]
    return sorted(values, key=lambda x: (
        0 if x["provider_status"] == "FT" else 1,
        x["captured_at"], x["fixture_id"],
    ))[:MAX_CALLS]


def main() -> None:
    configure_logging("INFO")
    url = os.environ["DATABASE_URL"]
    key = os.environ["API_FOOTBALL_KEY"].strip()
    daily_limit = int(os.environ["QUANTBET_API_DAILY_LIMIT"])
    reserve = int(os.environ["QUANTBET_API_RESERVE"])
    connection = psycopg.connect(url, autocommit=True)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(hashtextextended(%s,0))",
                           (LOCK_NAME,))
            locked = bool(cursor.fetchone()[0])
        if not locked:
            LOGGER.warning("GOALLAB_ONESHOT_ALREADY_RUNNING")
            return
        try:
            repo = PostgreSQLQuantLabRepository(url)
            if not repo.check_database():
                raise RuntimeError("QuantLab schema unavailable")
            budget = QuantLabRequestBudget(
                shared_daily_limit=daily_limit,
                production_reserve=reserve,
                database_url=url,
            )
            provider = QuantLabApiFootballClient(api_key=key, budget=budget)
            start = datetime.now(UTC)
            before = stats(repo)
            LOGGER.info("GOALLAB_ONESHOT_START before=%s api_remaining=%s",
                        before, budget.remaining)
            early = settle_confirmed(repo, start)
            targets = pending_historical_targets(repo, datetime.now(UTC))
            LOGGER.info("GOALLAB_ONESHOT_TARGETS count=%d early_settled=%d",
                        len(targets), early)
            captured = no_match = failed = called = 0
            for target in targets:
                fixture_id = target["fixture_id"]
                now = datetime.now(UTC)
                if budget.remaining <= 1:
                    LOGGER.warning("GOALLAB_ONESHOT_RESERVE_REACHED")
                    break
                called += 1
                try:
                    payload = provider.fetch_fixture(int(target["provider_fixture_id"]))
                    parsed = parse_fixture_discovery_response(
                        payload, captured_at=now, include_blocked=True,
                    )
                    matching = tuple(o for o in parsed
                                     if o.fixture.fixture_id == fixture_id)
                    if not matching:
                        no_match += 1
                        repo.record_goal_pick_result_poll_attempt(
                            fixture_id=fixture_id, attempted_at=now, outcome="NO_MATCH",
                        )
                        continue
                    captured += int(bool(repo.save_fixture_observations(matching)))
                    repo.record_goal_pick_result_poll_attempt(
                        fixture_id=fixture_id, attempted_at=now, outcome="CAPTURED",
                    )
                except ApiBudgetExceededError:
                    LOGGER.warning("GOALLAB_ONESHOT_API_BUDGET_EXHAUSTED")
                    break
                except Exception as exc:
                    failed += 1
                    LOGGER.exception("GOALLAB_ONESHOT_POLL_FAILED fixture=%s error_class=%s error=%s", fixture_id, type(exc).__name__, str(exc))
                    repo.record_goal_pick_result_poll_attempt(
                        fixture_id=fixture_id, attempted_at=now, outcome="ERROR",
                    )
            late = settle_confirmed(repo, datetime.now(UTC))
            LOGGER.info(
                "GOALLAB_ONESHOT_COMPLETE before=%s after=%s early_settled=%d "
                "late_settled=%d called=%d captured=%d no_match=%d failed=%d "
                "api_remaining=%d", before, stats(repo), early, late, called,
                captured, no_match, failed, budget.remaining,
            )
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(hashtextextended(%s,0))",
                               (LOCK_NAME,))
    finally:
        connection.close()


if __name__ == "__main__":
    main()
