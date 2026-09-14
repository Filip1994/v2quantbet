from datetime import UTC, datetime

import pytest

from h2h.domain.fixture import Fixture


def make_fixture() -> Fixture:
    return Fixture(
        fixture_id="fixture-1",
        home_team="Home FC",
        away_team="Away FC",
        competition_id=1,
        competition_name="Example League",
        country="Exampleland",
        kickoff_at=datetime(2026, 9, 15, 18, 0, tzinfo=UTC),
        season=2026,
        provider="api-football",
        provider_fixture_id="123",
    )


def test_fixture_is_immutable_and_preserves_canonical_fields() -> None:
    fixture = make_fixture()

    assert fixture.fixture_id == "fixture-1"
    assert fixture.home_team == "Home FC"
    assert fixture.provider_fixture_id == "123"
    with pytest.raises(AttributeError):
        fixture.home_team = "Changed FC"  # type: ignore[misc]


@pytest.mark.parametrize(
    "field, value",
    [
        ("fixture_id", ""),
        ("home_team", ""),
        ("away_team", ""),
        ("competition_name", ""),
        ("country", ""),
        ("provider", ""),
    ],
)
def test_fixture_rejects_empty_required_text(field: str, value: str) -> None:
    values = make_fixture().__dict__ if hasattr(make_fixture(), "__dict__") else None
    del values
    kwargs = {
        "fixture_id": "fixture-1",
        "home_team": "Home FC",
        "away_team": "Away FC",
        "competition_id": 1,
        "competition_name": "Example League",
        "country": "Exampleland",
        "kickoff_at": datetime(2026, 9, 15, 18, 0, tzinfo=UTC),
        "provider": "api-football",
    }
    kwargs[field] = value
    with pytest.raises(ValueError):
        Fixture(**kwargs)


def test_fixture_rejects_non_positive_competition_id() -> None:
    with pytest.raises(ValueError):
        Fixture(
            fixture_id="fixture-1",
            home_team="Home FC",
            away_team="Away FC",
            competition_id=0,
            competition_name="Example League",
            country="Exampleland",
            kickoff_at=datetime(2026, 9, 15, 18, 0, tzinfo=UTC),
        )
