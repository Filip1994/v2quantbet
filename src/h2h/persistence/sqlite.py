"""SQLite-backed persistence for canonical quote observations."""

from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
import sqlite3

from h2h.domain.odds import CanonicalQuote, Market, Selection
from h2h.odds.quote_deduplication import QuoteConflictError


class SQLiteQuoteRepository:
    """Persist canonical quotes in SQLite with atomic conflict handling."""

    def __init__(self, database: str | Path) -> None:
        self._connection = sqlite3.connect(str(database))
        self._connection.row_factory = sqlite3.Row
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS quotes (
                fixture_id TEXT NOT NULL,
                bookmaker_id INTEGER NOT NULL,
                bookmaker_name TEXT NOT NULL,
                market TEXT NOT NULL,
                selection TEXT NOT NULL,
                odd REAL NOT NULL,
                observed_at TEXT NOT NULL,
                source TEXT NOT NULL,
                PRIMARY KEY (fixture_id, bookmaker_id, market, selection)
            )
            """
        )
        self._connection.commit()

    def save(self, quotes: Iterable[CanonicalQuote]) -> None:
        """Persist quotes idempotently, rejecting conflicting identities atomically."""
        with self._connection:
            for quote in quotes:
                row = self._connection.execute(
                    """
                    SELECT * FROM quotes
                    WHERE fixture_id = ? AND bookmaker_id = ?
                      AND market = ? AND selection = ?
                    """,
                    self._identity_params(quote),
                ).fetchone()
                if row is not None:
                    if self._row_to_quote(row) != quote:
                        raise QuoteConflictError(
                            f"conflicting observations for quote identity {quote.identity!r}"
                        )
                    continue
                self._connection.execute(
                    """
                    INSERT INTO quotes (
                        fixture_id, bookmaker_id, bookmaker_name, market,
                        selection, odd, observed_at, source
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        quote.fixture_id,
                        quote.bookmaker_id,
                        quote.bookmaker_name,
                        quote.market.value,
                        quote.selection.value,
                        quote.odd,
                        quote.observed_at.isoformat(),
                        quote.source,
                    ),
                )

    def all(self) -> tuple[CanonicalQuote, ...]:
        """Return all stored quotes in insertion order."""
        rows = self._connection.execute("SELECT * FROM quotes ORDER BY rowid").fetchall()
        return tuple(self._row_to_quote(row) for row in rows)

    def for_fixture(self, fixture_id: str) -> tuple[CanonicalQuote, ...]:
        """Return stored quotes for one fixture in insertion order."""
        rows = self._connection.execute(
            "SELECT * FROM quotes WHERE fixture_id = ? ORDER BY rowid", (fixture_id,)
        ).fetchall()
        return tuple(self._row_to_quote(row) for row in rows)

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._connection.close()

    @staticmethod
    def _identity_params(quote: CanonicalQuote) -> tuple[str, int, str, str]:
        return (
            quote.fixture_id,
            quote.bookmaker_id,
            quote.market.value,
            quote.selection.value,
        )

    @staticmethod
    def _row_to_quote(row: sqlite3.Row) -> CanonicalQuote:
        return CanonicalQuote(
            fixture_id=row["fixture_id"],
            bookmaker_id=row["bookmaker_id"],
            bookmaker_name=row["bookmaker_name"],
            market=Market(row["market"]),
            selection=Selection(row["selection"]),
            odd=row["odd"],
            observed_at=datetime.fromisoformat(row["observed_at"]),
            source=row["source"],
        )
