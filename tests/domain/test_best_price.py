from types import SimpleNamespace

from h2h.domain.best_price import rank_best_prices
from h2h.domain.odds import Market, Selection


def candidate(
    evaluation_id,
    bookmaker_id,
    odd,
    *,
    market=Market.BTTS,
    selection=Selection.YES,
    edge=0.1,
    expected_value=0.15,
):
    return SimpleNamespace(
        evaluation_id=evaluation_id,
        fixture_id="api-football:1",
        bookmaker_id=bookmaker_id,
        market=market,
        selected_selection=selection,
        selected_odd=odd,
        edge=edge,
        expected_value=expected_value,
    )


def test_highest_approved_price_wins_and_all_quotes_are_retained() -> None:
    ranked = rank_best_prices(
        (
            candidate("bet365", 8, 2.05),
            candidate("1xbet", 11, 2.10),
            candidate("superbet", 34, 2.08),
        )
    )

    assert ranked[0].winner.evaluation_id == "1xbet"
    assert [item.evaluation_id for item in ranked[0].candidates] == ["1xbet", "superbet", "bet365"]


def test_superbet_can_win_and_ties_use_stable_provider_id() -> None:
    ranked = rank_best_prices(
        (
            candidate("superbet", 34, 2.20),
            candidate("1xbet", 11, 2.10),
            candidate("bet365", 8, 2.10),
        )
    )
    assert ranked[0].winner.evaluation_id == "superbet"

    tied = rank_best_prices((candidate("1xbet", 11, 2.10), candidate("bet365", 8, 2.10)))
    assert tied[0].winner.evaluation_id == "bet365"


def test_unsupported_and_different_semantics_are_never_compared() -> None:
    ranked = rank_best_prices(
        (
            candidate("unsupported", 999, 9.0),
            candidate("yes", 8, 2.0),
            candidate("no", 11, 2.1, selection=Selection.NO),
            candidate("over", 34, 2.2, market=Market.OU_25, selection=Selection.OVER),
        )
    )
    assert len(ranked) == 3
    assert {group.winner.evaluation_id for group in ranked} == {"yes", "no", "over"}


def test_selection_sets_are_ordered_by_expected_value_for_single_fixture_pick() -> None:
    ranked = rank_best_prices(
        (
            candidate(
                "btts",
                8,
                2.30,
                market=Market.BTTS,
                selection=Selection.NO,
                edge=0.08,
                expected_value=0.11,
            ),
            candidate(
                "under",
                8,
                2.10,
                market=Market.OU_25,
                selection=Selection.UNDER,
                edge=0.12,
                expected_value=0.18,
            ),
        )
    )

    assert [group.winner.evaluation_id for group in ranked] == ["under", "btts"]
