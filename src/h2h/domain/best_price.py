"""Deterministic best-price selection across the approved bookmaker universe."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from .bookmaker_policy import API_FOOTBALL_BOOKMAKERS
from .odds import Market, Selection


class ExecutableEvaluation(Protocol):
    evaluation_id: str
    fixture_id: str
    bookmaker_id: int
    market: Market
    selected_selection: Selection
    selected_odd: float


@dataclass(frozen=True, slots=True)
class ComparablePriceSet:
    """Ranked quotes that share exact executable selection semantics."""

    fixture_id: str
    market: Market
    selection: Selection
    candidates: tuple[ExecutableEvaluation, ...]

    @property
    def winner(self) -> ExecutableEvaluation:
        return self.candidates[0]


def rank_best_prices(
    evaluations: Iterable[ExecutableEvaluation],
) -> tuple[ComparablePriceSet, ...]:
    """Group comparable approved quotes and rank odds high-to-low.

    Provider bookmaker id is the stable tie-breaker, so replaying the same facts
    always chooses the same winner. Unsupported bookmakers fail closed.
    """

    groups: dict[tuple[str, Market, Selection], list[ExecutableEvaluation]] = {}
    for evaluation in evaluations:
        if evaluation.bookmaker_id not in API_FOOTBALL_BOOKMAKERS:
            continue
        key = (evaluation.fixture_id, evaluation.market, evaluation.selected_selection)
        groups.setdefault(key, []).append(evaluation)

    ranked: list[ComparablePriceSet] = []
    for (fixture_id, market, selection), candidates in sorted(
        groups.items(), key=lambda item: tuple(str(value) for value in item[0])
    ):
        ordered = tuple(
            sorted(
                candidates,
                key=lambda candidate: (
                    -float(candidate.selected_odd),
                    candidate.bookmaker_id,
                    candidate.evaluation_id,
                ),
            )
        )
        ranked.append(ComparablePriceSet(fixture_id, market, selection, ordered))
    return tuple(ranked)
