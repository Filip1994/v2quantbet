"""Application service for immutable historical quote ingestion."""

from collections.abc import Callable, Iterable
from datetime import datetime
from hashlib import sha256

from h2h.domain.odds import CanonicalQuote
from h2h.domain.quote_history import QuoteSeries, QuoteSnapshot
from h2h.persistence.quote_history import QuoteHistoryRepository


class QuoteHistoryIngestionService:
    """Convert canonical observations into stable series and immutable snapshots."""

    def __init__(
        self,
        repository: QuoteHistoryRepository,
        *,
        capture_clock: Callable[[], datetime],
    ) -> None:
        self._repository = repository
        self._capture_clock = capture_clock
        self._series_created_at: dict[str, datetime] = {}

    @staticmethod
    def _series_id(quote: CanonicalQuote) -> str:
        value = "|".join(
            (
                str(quote.fixture_id),
                str(quote.bookmaker_id),
                quote.market.value,
                quote.selection.value,
            )
        )
        return "series-" + sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _snapshot_id(series_id: str, quote: CanonicalQuote, captured_at: datetime) -> str:
        value = (
            f"{series_id}|{quote.observed_at.isoformat()}|{captured_at.isoformat()}|{quote.source}"
        )
        return "snapshot-" + sha256(value.encode("utf-8")).hexdigest()

    def _existing_series(self, quote: CanonicalQuote) -> QuoteSeries | None:
        for series in self._repository.series_for_fixture(str(quote.fixture_id)):
            if (
                series.bookmaker_id == quote.bookmaker_id
                and series.market == quote.market
                and series.selection == quote.selection
            ):
                return series
        return None

    def ingest(
        self, quotes: Iterable[CanonicalQuote], *, captured_at: datetime | None = None
    ) -> int:
        """Persist one collection cycle and return newly observed quote count."""
        captured_at = self._capture_clock() if captured_at is None else captured_at
        incoming = tuple(quotes)
        if not incoming:
            return 0

        state_loader = getattr(self._repository, "fixture_ingestion_state", None)
        batch_ensure = getattr(self._repository, "ensure_series_batch", None)
        if callable(state_loader) and callable(batch_ensure):
            return self._ingest_batched(
                incoming,
                captured_at=captured_at,
                state_loader=state_loader,
                batch_ensure=batch_ensure,
            )

        snapshots: list[QuoteSnapshot] = []
        fresh_observations = 0
        incoming_observations: set[tuple[str, datetime, str]] = set()
        for quote in incoming:
            series_id = self._series_id(quote)
            existing = self._existing_series(quote)
            observation_key = (series_id, quote.observed_at, quote.source)
            already_persisted = existing is not None and any(
                snapshot.observed_at == quote.observed_at and snapshot.source == quote.source
                for snapshot in self._repository.snapshots_for_series(existing.series_id)
            )
            if not already_persisted and observation_key not in incoming_observations:
                fresh_observations += 1
            incoming_observations.add(observation_key)
            created_at = (
                existing.created_at
                if existing is not None
                else self._series_created_at.setdefault(series_id, captured_at)
            )
            self._repository.ensure_series(
                QuoteSeries(
                    series_id=series_id,
                    fixture_id=str(quote.fixture_id),
                    bookmaker_id=quote.bookmaker_id,
                    market=quote.market,
                    selection=quote.selection,
                    created_at=created_at,
                )
            )
            snapshots.append(
                QuoteSnapshot(
                    snapshot_id=self._snapshot_id(series_id, quote, captured_at),
                    series_id=series_id,
                    odd=quote.odd,
                    observed_at=quote.observed_at,
                    captured_at=captured_at,
                    source=quote.source,
                )
            )
        self._repository.append_snapshots(snapshots)
        return fresh_observations

    def _ingest_batched(
        self,
        quotes: tuple[CanonicalQuote, ...],
        *,
        captured_at: datetime,
        state_loader: Callable[
            [str],
            tuple[
                tuple[QuoteSeries, ...],
                frozenset[tuple[str, datetime, str]],
            ],
        ],
        batch_ensure: Callable[[Iterable[QuoteSeries]], None],
    ) -> int:
        """Use fixture-level preload plus batch persistence when repository supports it."""
        existing_by_identity: dict[
            tuple[str, int, object, object], QuoteSeries
        ] = {}
        persisted_observations: set[tuple[str, datetime, str]] = set()
        for fixture_id in dict.fromkeys(str(quote.fixture_id) for quote in quotes):
            series, observations = state_loader(fixture_id)
            persisted_observations.update(observations)
            for item in series:
                existing_by_identity[
                    (
                        item.fixture_id,
                        item.bookmaker_id,
                        item.market,
                        item.selection,
                    )
                ] = item

        series_to_ensure: dict[str, QuoteSeries] = {}
        snapshots: list[QuoteSnapshot] = []
        incoming_observations: set[tuple[str, datetime, str]] = set()
        fresh_observations = 0
        for quote in quotes:
            series_id = self._series_id(quote)
            existing = existing_by_identity.get(
                (
                    str(quote.fixture_id),
                    quote.bookmaker_id,
                    quote.market,
                    quote.selection,
                )
            )
            observation_key = (series_id, quote.observed_at, quote.source)
            if (
                observation_key not in persisted_observations
                and observation_key not in incoming_observations
            ):
                fresh_observations += 1
            incoming_observations.add(observation_key)
            created_at = (
                existing.created_at
                if existing is not None
                else self._series_created_at.setdefault(series_id, captured_at)
            )
            series_to_ensure.setdefault(
                series_id,
                QuoteSeries(
                    series_id=series_id,
                    fixture_id=str(quote.fixture_id),
                    bookmaker_id=quote.bookmaker_id,
                    market=quote.market,
                    selection=quote.selection,
                    created_at=created_at,
                ),
            )
            snapshots.append(
                QuoteSnapshot(
                    snapshot_id=self._snapshot_id(series_id, quote, captured_at),
                    series_id=series_id,
                    odd=quote.odd,
                    observed_at=quote.observed_at,
                    captured_at=captured_at,
                    source=quote.source,
                )
            )

        batch_ensure(series_to_ensure.values())
        self._repository.append_snapshots(snapshots)
        return fresh_observations
