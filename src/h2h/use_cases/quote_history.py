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
        value = "|".join(
            (series_id, quote.observed_at.isoformat(), captured_at.isoformat(), quote.source)
        )
        return "snapshot-" + sha256(value.encode("utf-8")).hexdigest()

    def ingest(self, quotes: Iterable[CanonicalQuote]) -> int:
        """Persist one collection cycle and return the number of observations."""
        captured_at = self._capture_clock()
        snapshots: list[QuoteSnapshot] = []
        for quote in quotes:
            series_id = self._series_id(quote)
            self._repository.ensure_series(
                QuoteSeries(
                    series_id=series_id,
                    fixture_id=str(quote.fixture_id),
                    bookmaker_id=quote.bookmaker_id,
                    market=quote.market,
                    selection=quote.selection,
                    created_at=captured_at,
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
        return len(snapshots)
