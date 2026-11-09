"""Bounded, operator-triggered settlement of overdue Production CornerLab fixtures.

This path is not a collector cycle: it never discovers matches or generates picks.
It only refreshes terminal evidence for existing open Production corner picks.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from h2h.odds.budget import ApiBudgetExceededError
from h2h.quantlab.budget import QuantLabRequestBudget
from h2h.quantlab.card_lab.context import parse_fixture_statistics
from h2h.quantlab.corner_lab.settlement import settle_corner_shadow_bet
from h2h.quantlab.fixture_discovery import parse_fixture_discovery_response
from h2h.quantlab.provider import QuantLabApiFootballClient
from h2h.quantlab.repository import PostgreSQLQuantLabRepository


LOGGER = logging.getLogger("quantbet.operations.manual_corner_settlement")
MAX_FIXTURES_PER_CLICK = 5
MAX_MANUAL_PROVIDER_CALLS_PER_DAY = 30
RESULT_REFRESH_COOLDOWN = timedelta(minutes=15)
STATS_RETRY_COOLDOWN = timedelta(minutes=30)
TERMINAL_PLAYED = frozenset({"FT", "AET", "PEN"})
TERMINAL_VOID = frozenset({"CANC", "ABD", "AWD", "WO"})
# Must match the session-level lock held by h2h.quantlab.collector_entrypoint.
COLLECTOR_LOCK_NAME = "quantbet-quantlab-collector-v1"


class ManualSettlementBusy(RuntimeError):
    """Another settlement or full CornerLab collector cycle owns the lock."""


def _pending_production_corners(
    repository: PostgreSQLQuantLabRepository, *, now: datetime
) -> tuple[dict[str, Any], ...]:
    """Newest overdue Production fixtures, deduplicated by fixture, never Research-only."""
    sql = """
        SELECT * FROM (
            SELECT DISTINCT ON (q.fixture_id)
                q.fixture_id, f.provider_fixture_id, p.kickoff_at,
                latest.provider_status, latest.captured_at AS result_captured_at,
                latest.home_team_id, latest.away_team_id,
                stats.available_at AS statistics_at,
                capture.captured_at AS last_statistics_capture_at
            FROM production_funnel_picks p
            JOIN quantlab_shadow_bets q
              ON p.source_universe = 'CORNERLAB'
             AND q.shadow_bet_id = p.source_pick_id
             AND q.lab = 'CORNER'
            JOIN quantlab_fixtures f ON f.fixture_id = q.fixture_id
            JOIN LATERAL (
                SELECT o.provider_status, o.captured_at,
                       o.home_team_id, o.away_team_id
                FROM quantlab_fixture_observations o
                WHERE o.fixture_id = q.fixture_id
                ORDER BY o.captured_at DESC, o.fixture_observation_id DESC
                LIMIT 1
            ) latest ON TRUE
            LEFT JOIN LATERAL (
                SELECT s.available_at
                FROM quantlab_match_statistics_observations s
                WHERE s.fixture_id = q.fixture_id
                  AND s.home_corner_kicks IS NOT NULL
                  AND s.away_corner_kicks IS NOT NULL
                ORDER BY s.available_at DESC, s.statistics_observation_id DESC
                LIMIT 1
            ) stats ON TRUE
            LEFT JOIN LATERAL (
                SELECT s.captured_at
                FROM quantlab_statistics_captures s
                WHERE s.fixture_id = q.fixture_id
                ORDER BY s.captured_at DESC, s.statistics_capture_id DESC
                LIMIT 1
            ) capture ON TRUE
            WHERE p.kickoff_at <= %s - interval '2 hours'
              AND p.kickoff_at >= %s - interval '14 days'
              AND NOT EXISTS (
                SELECT 1 FROM production_funnel_voids pv WHERE pv.pick_id = p.pick_id
              )
              AND NOT EXISTS (
                SELECT 1 FROM quantlab_corner_settlement_events e
                WHERE e.shadow_bet_id = q.shadow_bet_id
              )
            ORDER BY q.fixture_id, p.kickoff_at DESC
        ) pending
        ORDER BY kickoff_at DESC, fixture_id
        LIMIT 100
    """
    with repository.connect() as connection, connection.cursor() as cursor:
        cursor.execute(sql, (now, now))
        columns = tuple(column.name for column in cursor.description)
        return tuple(dict(zip(columns, row)) for row in cursor.fetchall())


def _needs_statistics(row: dict[str, Any], *, terminal_at: datetime) -> bool:
    """Never trust in-play corner statistics as final settlement evidence."""
    statistics_at = row.get("statistics_at")
    return statistics_at is None or statistics_at < terminal_at


def run_manual_corner_settlement(
    *,
    database_url: str,
    api_key: str,
    daily_limit: int,
    reserve: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Settle at most five overdue Production fixtures using provider evidence.

    The existing full collector owns the same PostgreSQL advisory session lock.
    All provider requests use the shared daily quota plus a separate manual cap.
    """
    import psycopg

    if not database_url or not api_key:
        raise ValueError("manual corner settlement requires DATABASE_URL and API_FOOTBALL_KEY")
    current = (now or datetime.now(UTC)).astimezone(UTC)
    connection = psycopg.connect(database_url, autocommit=True)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_try_advisory_lock(hashtextextended(%s, 0))",
                (COLLECTOR_LOCK_NAME,),
            )
            acquired = bool(cursor.fetchone()[0])
        if not acquired:
            raise ManualSettlementBusy("CornerLab collector or another manual settlement is running")

        repository = PostgreSQLQuantLabRepository(database_url)
        budget = QuantLabRequestBudget(
            shared_daily_limit=daily_limit,
            production_reserve=reserve,
            database_url=database_url,
            request_category="manual_corner_settlement",
            category_daily_limit=MAX_MANUAL_PROVIDER_CALLS_PER_DAY,
        )
        provider = QuantLabApiFootballClient(api_key=api_key, budget=budget, timeout=6.0)
        candidates = _pending_production_corners(repository, now=current)
        selected: list[str] = []
        terminal_at_by_fixture: dict[str, datetime] = {}
        stats_refreshed = results_refreshed = 0
        deferred = 0
        budget_exhausted = False
        failed_fixtures: list[str] = []
        failure_codes: list[dict[str, str]] = []
        repeated_failure_key: tuple[str, str] | None = None
        repeated_failure_count = 0
        aborted_repeated_failure = False
        before_calls = budget.used

        for row in candidates:
            if len(selected) >= MAX_FIXTURES_PER_CLICK:
                break
            fixture_id = str(row["fixture_id"])
            status = str(row["provider_status"] or "")
            observed_at = row["result_captured_at"]
            needs_result = status not in TERMINAL_PLAYED | TERMINAL_VOID
            if needs_result and current - observed_at < RESULT_REFRESH_COOLDOWN:
                deferred += 1
                continue
            if status in TERMINAL_PLAYED and _needs_statistics(row, terminal_at=observed_at):
                last_capture = row.get("last_statistics_capture_at")
                if last_capture is not None and current - last_capture < STATS_RETRY_COOLDOWN:
                    deferred += 1
                    continue

            selected.append(fixture_id)
            provider_fixture_id = int(row["provider_fixture_id"])
            stage = "fixture_request" if needs_result else "statistics_request"
            try:
                if needs_result:
                    payload = provider.fetch_fixture(provider_fixture_id)
                    stage = "fixture_parse"
                    observed = parse_fixture_discovery_response(payload, captured_at=current)
                    matching = tuple(
                        item for item in observed
                        if str(item.fixture.fixture_id) == fixture_id
                    )
                    if not matching:
                        LOGGER.warning("Manual corner fixture identity mismatch fixture=%s", fixture_id)
                        failed_fixtures.append(fixture_id)
                        continue
                    stage = "fixture_persist"
                    repository.save_fixture_observations(matching)
                    results_refreshed += 1
                    status = str(matching[-1].fixture.status)
                    observed_at = current

                if status in TERMINAL_PLAYED:
                    terminal_at_by_fixture[fixture_id] = observed_at
                if status in TERMINAL_PLAYED and _needs_statistics(row, terminal_at=observed_at):
                    if not row["home_team_id"] or not row["away_team_id"]:
                        failed_fixtures.append(fixture_id)
                        continue
                    stage = "statistics_request"
                    payload = provider.fetch_statistics(provider_fixture_id)
                    stage = "statistics_parse"
                    response = payload.get("response") if isinstance(payload, dict) else None
                    try:
                        statistics = parse_fixture_statistics(
                            payload,
                            fixture_id=fixture_id,
                            provider_fixture_id=provider_fixture_id,
                            home_team_id=int(row["home_team_id"]),
                            away_team_id=int(row["away_team_id"]),
                            captured_at=current,
                        )
                    except ValueError as exc:
                        repository.save_statistics_capture(
                            fixture_id=fixture_id,
                            provider_fixture_id=provider_fixture_id,
                            captured_at=current,
                            status="UNAVAILABLE",
                            response_team_count=len(response) if isinstance(response, list) else 0,
                            reason=str(exc)[:200],
                            raw_payload=dict(payload),
                        )
                        deferred += 1
                        continue
                    stage = "statistics_persist"
                    repository.save_match_statistics(statistics)
                    has_corners = (
                        statistics.home_corner_kicks is not None
                        and statistics.away_corner_kicks is not None
                    )
                    repository.save_statistics_capture(
                        fixture_id=fixture_id,
                        provider_fixture_id=provider_fixture_id,
                        captured_at=current,
                        status="AVAILABLE" if has_corners else "UNAVAILABLE",
                        response_team_count=len(response) if isinstance(response, list) else 0,
                        reason=None if has_corners else "missing-final-corner-counts",
                        raw_payload=dict(payload),
                    )
                    stats_refreshed += int(has_corners)
                    deferred += int(not has_corners)
                elif status not in TERMINAL_PLAYED | TERMINAL_VOID:
                    deferred += 1
            except ApiBudgetExceededError:
                budget_exhausted = True
                break
            except Exception as exc:  # noqa: BLE001 - boundary diagnostics
                error_class = type(exc).__name__
                # Never put provider credentials or connection URLs into Railway logs.
                redacted_message = (
                    str(exc)
                    .replace(api_key, "[provider credential]")
                    .replace(database_url, "[database URL]")
                    .replace("\\n", " ")
                    .replace("\\r", " ")
                )[:220]
                LOGGER.error(
                    "Manual corner settlement refresh failed fixture=%s stage=%s error=%s: %s",
                    fixture_id, stage, error_class, redacted_message,
                )
                failed_fixtures.append(fixture_id)
                failure_codes.append({
                    "fixture_id": fixture_id,
                    "stage": stage,
                    "error_class": error_class,
                })
                failure_key = (stage, error_class)
                if failure_key == repeated_failure_key:
                    repeated_failure_count += 1
                else:
                    repeated_failure_key = failure_key
                    repeated_failure_count = 1
                if repeated_failure_count >= 2 and stage.endswith("_request"):
                    # Likely shared integration/configuration fault. Do not spend
                    # the remaining manual API budget on the same failure.
                    aborted_repeated_failure = True
                    LOGGER.error(
                        "Manual corner settlement halted after repeated provider errors stage=%s class=%s",
                        stage, error_class,
                    )
                    break

        settled = 0
        if selected:
            selected_ids = set(selected)
            for candidate in repository.corner_shadow_settlement_candidates(
                limit=5000, production_only=True
            ):
                fixture_id = str(candidate["fixture_id"])
                if fixture_id not in selected_ids:
                    continue
                if candidate["result_classification"] == "PLAYED_SETTLEABLE":
                    stats_at = candidate["statistics_available_at"]
                    terminal_at = terminal_at_by_fixture.get(fixture_id)
                    if terminal_at is None or stats_at is None or stats_at < terminal_at:
                        # Never settle from an earlier, potentially live corner count.
                        continue
                settlement = settle_corner_shadow_bet(candidate, settled_at=current)
                if settlement is not None:
                    settled += int(bool(repository.save_corner_settlement_event(settlement)))
        result = {
            "fixtures_checked": len(selected),
            "results_refreshed": results_refreshed,
            "statistics_refreshed": stats_refreshed,
            "settled_picks": settled,
            "deferred": deferred,
            "api_calls": budget.used - before_calls,
            "budget_exhausted": budget_exhausted,
            "failed_fixtures": failed_fixtures[:5],
            "failure_codes": failure_codes[:5],
            "aborted_repeated_failure": aborted_repeated_failure,
        }
        LOGGER.info("Manual Production corner settlement completed: %s", result)
        return result
    finally:
        # Closing the PostgreSQL session releases the advisory lock even on failure.
        connection.close()
