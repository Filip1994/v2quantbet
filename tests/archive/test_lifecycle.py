from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime

import pytest

from h2h.archive.lifecycle import ArchiveLifecycleConfig, ArchiveLifecycleService
from h2h.archive.repository import ColdArchiveCatalog


NOW = datetime(2026, 9, 29, 2, 0, tzinfo=UTC)


class FakeStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_bytes(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
        content_encoding: str | None = None,
    ) -> str:
        import hashlib

        del content_type, content_encoding
        self.objects[key] = data
        return hashlib.sha256(data).hexdigest()

    def get_bytes(self, key: str) -> bytes:
        return self.objects[key]


class FakeCatalog:
    def __init__(self) -> None:
        self.market_calls = 0
        self.registered: list[dict] = []
        self.deleted: list[tuple[str, ...]] = []
        self.hot_marks: list[dict] = []
        self.watermarks: list[dict] = []
        self.after_ids: list[str | None] = []
        self.expected_market_limit = 5000
        self.lock_acquired = True

    @contextmanager
    def exclusive_run(self):
        yield self.lock_acquired

    def register_verified_batch(self, **kwargs):
        self.registered.append(kwargs)
        return f"batch:{len(self.registered)}"

    def market_archive_candidates(self, *, cutoff, limit, after_id=None):
        assert cutoff.isoformat() == "2026-09-26T02:00:00+00:00"
        assert limit == self.expected_market_limit
        self.after_ids.append(after_id)
        self.market_calls += 1
        if self.market_calls > 1:
            return ()
        return (
            {
                "market_observation_id": "market:1",
                "fixture_id": "fixture:1",
                "captured_at": "2026-09-25T20:00:00+00:00",
                "raw_payload": {"odd": "1.90"},
            },
            {
                "market_observation_id": "market:2",
                "fixture_id": "fixture:2",
                "captured_at": "2026-09-25T21:00:00+00:00",
                "raw_payload": {"odd": "2.05"},
            },
        )

    def delete_archived_market_observations(self, ids):
        self.deleted.append(ids)
        # Simulate a race: market:2 became referenced by a decision after selection.
        return 1

    def mark_deleted_from_hot(self, archive_batch_id, **kwargs):
        self.hot_marks.append({"archive_batch_id": archive_batch_id, **kwargs})

    def settlement_export_rows(self, dataset, *, limit):
        assert limit == 2000
        if dataset != "production/settlements":
            return ()
        return (
            {
                "settlement_event_id": "settlement:1",
                "occurred_at": NOW,
                "pick_id": "pick:1",
                "outcome": "WIN",
                "realized_pnl_minor": 9500,
            },
        )

    def advance_watermark(self, dataset, *, recorded_at, record_id):
        self.watermarks.append(
            {"dataset": dataset, "recorded_at": recorded_at, "record_id": record_id}
        )

    def table_sizes(self, *, limit):
        assert limit == 12
        return ({"table_name": "quantlab_market_observations", "total_bytes": 123},)


def test_lifecycle_defaults(monkeypatch):
    for name in (
        "QUANTBET_ARCHIVE_MARKET_HOT_HOURS",
        "QUANTBET_ARCHIVE_MARKET_BATCH_SIZE",
        "QUANTBET_ARCHIVE_MARKET_MAX_BATCHES",
        "QUANTBET_ARCHIVE_SETTLEMENT_BATCH_SIZE",
    ):
        monkeypatch.delenv(name, raising=False)

    config = ArchiveLifecycleConfig.from_environment()

    assert config.market_hot_hours == 72
    assert config.market_batch_size == 5000
    assert config.market_max_batches == 20
    assert config.settlement_batch_size == 2000


def test_lifecycle_rejects_overaggressive_market_retention(monkeypatch):
    monkeypatch.setenv("QUANTBET_ARCHIVE_MARKET_HOT_HOURS", "12")
    with pytest.raises(ValueError, match="between 24 and 720"):
        ArchiveLifecycleConfig.from_environment()


def test_lifecycle_archives_then_deletes_only_still_unreferenced_rows():
    catalog = FakeCatalog()
    service = ArchiveLifecycleService(catalog, FakeStore())

    result = service.run(now=NOW)

    assert result["market"]["archived_rows"] == 2
    assert result["market"]["deleted_rows"] == 1
    assert catalog.deleted == [("market:1", "market:2")]
    assert catalog.hot_marks == [
        {
            "archive_batch_id": "batch:1",
            "deleted_rows": 1,
            "selected_rows": 2,
        }
    ]
    assert catalog.registered[0]["dataset"] == "quantlab/market-observations"
    assert catalog.registered[0]["metadata"]["hot_hours"] == 72

    production = result["settlements"]["production/settlements"]
    assert production["rows"] == 1
    assert production["archived"] is True
    assert catalog.watermarks == [
        {
            "dataset": "production/settlements",
            "recorded_at": NOW,
            "record_id": "settlement:1",
        }
    ]

    for dataset in (
        "quantlab/goallab-settlements",
        "quantlab/cornerlab-settlements",
        "quantlab/cardlab-settlements",
    ):
        assert result["settlements"][dataset] == {"rows": 0, "archived": False}


def test_lifecycle_advances_candidate_cursor_between_full_batches():
    catalog = FakeCatalog()
    catalog.expected_market_limit = 2
    service = ArchiveLifecycleService(
        catalog,
        FakeStore(),
        config=ArchiveLifecycleConfig(market_batch_size=2, market_max_batches=2),
    )

    service.run(now=NOW)

    assert catalog.after_ids == [None, "market:2"]


def test_lifecycle_skips_overlapping_cron_run_without_touching_data():
    catalog = FakeCatalog()
    catalog.lock_acquired = False
    service = ArchiveLifecycleService(catalog, FakeStore())

    assert service.run(now=NOW) == {
        "skipped": True,
        "reason": "archive lifecycle already running",
    }
    assert catalog.market_calls == 0
    assert catalog.registered == []


def test_database_run_lock_commits_before_work_and_releases_after_failure():
    class LockCursor:
        def __init__(self, connection):
            self.connection = connection

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def execute(self, sql, params):
            self.connection.events.append((sql, params))

        def fetchone(self):
            return next(self.connection.responses)

    class LockConnection:
        def __init__(self):
            self.events = []
            self.responses = iter(((True,), (True,)))

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.events.append("close")

        def cursor(self):
            return LockCursor(self)

        def commit(self):
            self.events.append("commit")

    connection = LockConnection()
    catalog = ColdArchiveCatalog(connect=lambda: connection)

    with pytest.raises(RuntimeError, match="work failed"), catalog.exclusive_run() as acquired:
        assert acquired is True
        assert connection.events[1] == "commit"
        raise RuntimeError("work failed")

    assert connection.events[2][0].startswith("SELECT pg_advisory_unlock")
    assert connection.events[3:] == ["commit", "close"]
