from datetime import UTC, datetime

import pytest

from h2h.domain.odds import CanonicalQuote, Market, Selection
from h2h.domain.pick_registration import PickRegistration, PickStatus
from h2h.domain.value_pick import evaluate_value


def make_registration() -> PickRegistration:
    quote = CanonicalQuote(
        fixture_id="fixture-1",
        bookmaker_id=10,
        bookmaker_name="Bookmaker",
        market=Market.OU_25,
        selection=Selection.OVER,
        odd=1.90,
        observed_at=datetime(2026, 9, 14, tzinfo=UTC),
        source="test",
    )
    return PickRegistration(
        pick_id="pick-1",
        value_pick=evaluate_value(quote, 0.70),
        registered_at=datetime(2026, 9, 14, 12, tzinfo=UTC),
    )


def test_registration_preserves_identity_and_defaults_to_registered() -> None:
    registration = make_registration()

    assert registration.pick_id == "pick-1"
    assert registration.fixture_id == "fixture-1"
    assert registration.status is PickStatus.REGISTERED


def test_registration_is_immutable() -> None:
    with pytest.raises(AttributeError):
        make_registration().status = PickStatus.VOIDED  # type: ignore[misc]


@pytest.mark.parametrize("pick_id", ["", "   "])
def test_registration_rejects_empty_pick_id(pick_id: str) -> None:
    registration = make_registration()
    with pytest.raises(ValueError):
        PickRegistration(pick_id, registration.value_pick, registration.registered_at)


def test_registration_requires_datetime_and_known_status() -> None:
    registration = make_registration()
    with pytest.raises(TypeError):
        PickRegistration("pick-1", registration.value_pick, "not-a-date")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        PickRegistration("pick-1", registration.value_pick, registration.registered_at, "registered")  # type: ignore[arg-type]
