from __future__ import annotations

import os
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

pytest.importorskip("psycopg")

from h2h.odds.api_football_live import LiveMarketQuote
from h2h.persistence.postgres_live_closing_proxy import (
    PostgreSQLLiveClosingProxyRepository,
)
from tests.integration.test_postgres_task10_integration import _candidate, _cleanup, _migrate
from tests.integration.test_postgres_task11_integration import _fixture_cutoff, _registered


DATABASE_URL = os.environ.get("QUANTBET_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="QUANTBET_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)


def test_live_proxy_captures_pre_kickoff_quote_and_finalizes_proxy_clv() -> None:
    _migrate()
    candidate = _candidate()
    account = f"live-close-{uuid4()}"
    pick = _registered(candidate, account)
    repository = PostgreSQLLiveClosingProxyRepository(database_url=DATABASE_URL)
    cutoff = _fixture_cutoff(candidate)
    try:
        targets = repository.capture_targets(
            as_of=cutoff - timedelta(minutes=10),
            window_seconds=900,
        )
        target = next(item for item in targets if item.pick_id == pick.pick_id)
        quote = LiveMarketQuote(
            provider_fixture_id=target.provider_fixture_id,
            market=target.market,
            selection=target.selection,
            odd=1.90,
            observed_at=cutoff - timedelta(seconds=45),
            live_bet_id=25,
            live_bet_name="Match Goals",
        )

        observation_id = repository.persist_observation(
            target,
            quote,
            captured_at=cutoff - timedelta(seconds=30),
        )
        assert observation_id is not None

        finalized = repository.finalize_due(
            as_of=cutoff + timedelta(seconds=1),
            max_age_seconds=120,
        )
        item = next(value for value in finalized if value.pick_id == pick.pick_id)
        assert item.outcome == "CAPTURED"
        assert item.proxy_closing_odd == Decimal("1.9")
        assert item.proxy_clv_ppm == 52_632

        replay = repository.finalize_due(
            as_of=cutoff + timedelta(minutes=1),
            max_age_seconds=120,
        )
        assert all(value.pick_id != pick.pick_id for value in replay)
    finally:
        _cleanup(account, (candidate,))


def test_live_proxy_refuses_post_kickoff_observation() -> None:
    _migrate()
    candidate = _candidate()
    account = f"live-close-post-{uuid4()}"
    pick = _registered(candidate, account)
    repository = PostgreSQLLiveClosingProxyRepository(database_url=DATABASE_URL)
    cutoff = _fixture_cutoff(candidate)
    try:
        target = next(
            item
            for item in repository.capture_targets(
                as_of=cutoff - timedelta(minutes=5),
                window_seconds=900,
            )
            if item.pick_id == pick.pick_id
        )
        quote = LiveMarketQuote(
            provider_fixture_id=target.provider_fixture_id,
            market=target.market,
            selection=target.selection,
            odd=1.90,
            observed_at=cutoff + timedelta(seconds=1),
            live_bet_id=25,
            live_bet_name="Match Goals",
        )

        assert (
            repository.persist_observation(
                target,
                quote,
                captured_at=cutoff + timedelta(seconds=2),
            )
            is None
        )
    finally:
        _cleanup(account, (candidate,))
