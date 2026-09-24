"""Durable API-Football live market-close proxy observations and finalization."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from collections.abc import Callable
from typing import Any

from h2h.domain.odds import Market, Selection
from h2h.domain.settlement import realized_clv_ppm
from h2h.odds.api_football_live import LiveMarketQuote


ConnectionFactory = Callable[[], Any]
PROXY_SOURCE = "api-football-live"
PROXY_CLV_METHOD_VERSION = "CLV_MARKET_PROXY_ODDS_RATIO_PPM_V1"


def _utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


def _fact_id(prefix: str, value: str) -> str:
    return f"{prefix}:" + sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class LiveCloseTarget:
    pick_id: str
    fixture_id: str
    provider_fixture_id: int
    market: Market
    selection: Selection
    cutoff_at: datetime


@dataclass(frozen=True, slots=True)
class LiveCloseFinalization:
    pick_id: str
    cutoff_at: datetime
    outcome: str
    proxy_closing_odd: Decimal | None
    proxy_clv_ppm: int | None


class PostgreSQLLiveClosingProxyRepository:
    def __init__(
        self, database_url: str | None = None, *, connect: ConnectionFactory | None = None
    ) -> None:
        self._database_url = database_url or os.environ.get("DATABASE_URL")
        if not self._database_url and connect is None:
            raise ValueError("DATABASE_URL is required")
        self._connect_factory = connect

    def connect(self) -> Any:
        if self._connect_factory is not None:
            return self._connect_factory()
        import psycopg

        return psycopg.connect(self._database_url)

    def capture_targets(
        self, *, as_of: datetime, window_seconds: int, limit: int = 25
    ) -> tuple[LiveCloseTarget, ...]:
        now = _utc(as_of, "as_of")
        if window_seconds <= 0 or limit <= 0:
            raise ValueError("window_seconds and limit must be positive")
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT r.pick_id, r.fixture_id, f.provider_fixture_id::bigint, "
                "r.market, r.selection, latest.kickoff_at "
                "FROM registered_picks r "
                "JOIN fixtures f ON f.fixture_id = r.fixture_id AND f.provider = 'api-football' "
                "JOIN LATERAL (SELECT kickoff_at FROM fixture_observations fo "
                "WHERE fo.fixture_id = r.fixture_id "
                "ORDER BY observed_at DESC, fixture_observation_id DESC LIMIT 1) latest ON TRUE "
                "LEFT JOIN pick_live_close_finalizations final ON final.pick_id = r.pick_id "
                "WHERE final.pick_id IS NULL AND latest.kickoff_at > %s "
                "AND latest.kickoff_at <= %s "
                "ORDER BY latest.kickoff_at, r.pick_id LIMIT %s",
                (now, now + timedelta(seconds=window_seconds), limit),
            )
            return tuple(
                LiveCloseTarget(
                    str(row[0]),
                    str(row[1]),
                    int(row[2]),
                    Market(row[3]),
                    Selection(row[4]),
                    row[5],
                )
                for row in cursor.fetchall()
            )

    def persist_observation(
        self,
        target: LiveCloseTarget,
        quote: LiveMarketQuote,
        *,
        captured_at: datetime,
    ) -> str | None:
        captured = _utc(captured_at, "captured_at")
        observed = _utc(quote.observed_at, "quote.observed_at")
        if (
            quote.provider_fixture_id != target.provider_fixture_id
            or quote.market is not target.market
            or quote.selection is not target.selection
            or quote.source != PROXY_SOURCE
        ):
            raise ValueError("live quote does not match target identity")
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT kickoff_at FROM fixture_observations WHERE fixture_id = %s "
                "ORDER BY observed_at DESC, fixture_observation_id DESC LIMIT 1",
                (target.fixture_id,),
            )
            row = cursor.fetchone()
            if row is None or row[0] != target.cutoff_at:
                return None
            cutoff = row[0]
            if captured >= cutoff or observed >= cutoff:
                return None
            observation_id = _fact_id(
                "pick-live-close-observation-v1",
                f"{target.pick_id}:{quote.live_bet_id}:{observed.isoformat()}:{quote.odd}",
            )
            cursor.execute(
                "INSERT INTO pick_live_close_observations "
                "(observation_id, pick_id, fixture_id, market, selection, source, "
                "live_bet_id, live_bet_name, odd, provider_observed_at, captured_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT DO NOTHING",
                (
                    observation_id,
                    target.pick_id,
                    target.fixture_id,
                    target.market.value,
                    target.selection.value,
                    PROXY_SOURCE,
                    quote.live_bet_id,
                    quote.live_bet_name,
                    Decimal(str(quote.odd)),
                    observed,
                    captured,
                ),
            )
            return observation_id

    def finalize_due(
        self, *, as_of: datetime, max_age_seconds: int, limit: int = 100
    ) -> tuple[LiveCloseFinalization, ...]:
        now = _utc(as_of, "as_of")
        if max_age_seconds <= 0 or limit <= 0:
            raise ValueError("max_age_seconds and limit must be positive")
        finalized: list[LiveCloseFinalization] = []
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT r.pick_id, r.entry_snapshot_id, latest.kickoff_at "
                "FROM registered_picks r "
                "JOIN LATERAL (SELECT kickoff_at FROM fixture_observations fo "
                "WHERE fo.fixture_id = r.fixture_id "
                "ORDER BY observed_at DESC, fixture_observation_id DESC LIMIT 1) latest ON TRUE "
                "LEFT JOIN pick_live_close_finalizations final ON final.pick_id = r.pick_id "
                "WHERE final.pick_id IS NULL AND latest.kickoff_at <= %s "
                "ORDER BY latest.kickoff_at, r.pick_id LIMIT %s FOR UPDATE OF r SKIP LOCKED",
                (now, limit),
            )
            due = cursor.fetchall()
            for pick_id, entry_snapshot_id, cutoff in due:
                cursor.execute(
                    "SELECT observation_id, odd, provider_observed_at FROM "
                    "pick_live_close_observations WHERE pick_id = %s "
                    "AND provider_observed_at < %s AND captured_at < %s "
                    "ORDER BY provider_observed_at DESC, captured_at DESC, observation_id DESC "
                    "LIMIT 1",
                    (pick_id, cutoff, cutoff),
                )
                candidate = cursor.fetchone()
                if (
                    candidate is not None
                    and cutoff - candidate[2] <= timedelta(seconds=max_age_seconds)
                ):
                    cursor.execute(
                        "SELECT odd FROM quote_snapshots WHERE snapshot_id = %s",
                        (entry_snapshot_id,),
                    )
                    entry_row = cursor.fetchone()
                    if entry_row is None:
                        raise RuntimeError("registered pick Entry snapshot disappeared")
                    proxy_odd = Decimal(candidate[1])
                    proxy_clv = realized_clv_ppm(Decimal(entry_row[0]), proxy_odd)
                    outcome = "CAPTURED"
                    observation_id = candidate[0]
                else:
                    proxy_odd = None
                    proxy_clv = None
                    outcome = "NO_VALID_QUOTE"
                    observation_id = None
                finalization_id = _fact_id("pick-live-close-finalization-v1", str(pick_id))
                cursor.execute(
                    "INSERT INTO pick_live_close_finalizations "
                    "(finalization_id, pick_id, cutoff_at, finalized_at, outcome, "
                    "observation_id, entry_snapshot_id, proxy_closing_odd_decimal, "
                    "proxy_clv_ppm, source, method_version, max_age_seconds) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (pick_id) DO NOTHING",
                    (
                        finalization_id,
                        pick_id,
                        cutoff,
                        now,
                        outcome,
                        observation_id,
                        entry_snapshot_id,
                        proxy_odd,
                        proxy_clv,
                        PROXY_SOURCE,
                        PROXY_CLV_METHOD_VERSION,
                        max_age_seconds,
                    ),
                )
                finalized.append(
                    LiveCloseFinalization(
                        str(pick_id), cutoff, outcome, proxy_odd, proxy_clv
                    )
                )
        return tuple(finalized)
