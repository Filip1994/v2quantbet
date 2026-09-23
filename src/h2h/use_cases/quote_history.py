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
        snapshots: list[QuoteSnapshot] = []
        fresh_observations = 0
        incoming_observations: set[tuple[str, datetime, str]] = set()
        for quote in quotes:
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
