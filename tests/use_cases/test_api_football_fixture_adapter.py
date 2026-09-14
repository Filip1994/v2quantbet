from datetime import UTC

import pytest

from h2h.use_cases.api_football_fixture_adapter import ApiFootballFixtureAdapter


def payload() -> dict:
    return {
        "fixture": {
            "id": 123,
            "date": "2026-09-15T18:00:00+00:00",
            "status": {"short": "NS"},
        },
        "teams": {
            "home": {"id": 10, "name": "Home FC"},
            "away": {"id": 20, "name": "Away FC"},
        },
        "league": {
            "id": 39,
            "name": "Premier League",
            "country": "England",
            "type": "League",
            "season": 2026,
        },
    }


def test_adapts_api_football_fixture_to_canonical_model() -> None:
    fixture = ApiFootballFixtureAdapter().adapt(payload())

    assert fixture.fixture_id == "api-football:123"
    assert fixture.provider_fixture_id == "123"
    assert fixture.home_team == "Home FC"
    assert fixture.away_team == "Away FC"
    assert fixture.competition_id == 39
    assert fixture.competition_type == "League"
    assert fixture.kickoff_at.tzinfo == UTC
    assert fixture.status == "NS"


@pytest.mark.parametrize("path", [("fixture",), ("teams",), ("league",)])
def test_rejects_missing_required_sections(path: tuple[str, ...]) -> None:
    value = payload()
    del value[path[0]]
    with pytest.raises((TypeError, ValueError)):
        ApiFootballFixtureAdapter().adapt(value)


@pytest.mark.parametrize("field", ["id"])
def test_rejects_invalid_fixture_id(field: str) -> None:
    value = payload()
    value["fixture"][field] = 0
    with pytest.raises(ValueError, match="positive integer"):
        ApiFootballFixtureAdapter().adapt(value)


@pytest.mark.parametrize("section", ["home", "away"])
def test_rejects_invalid_team_id(section: str) -> None:
    value = payload()
    value["teams"][section]["id"] = True
    with pytest.raises(ValueError, match="positive integer"):
        ApiFootballFixtureAdapter().adapt(value)


def test_rejects_invalid_status_shape() -> None:
    value = payload()
    value["fixture"]["status"] = "NS"
    with pytest.raises(TypeError, match="fixture.status"):
        ApiFootballFixtureAdapter().adapt(value)


def test_rejects_invalid_status_code() -> None:
    value = payload()
    value["fixture"]["status"] = {"short": ""}
    with pytest.raises(ValueError, match="status.short"):
        ApiFootballFixtureAdapter().adapt(value)


@pytest.mark.parametrize("date", ["not-a-date", "2026-09-15T18:00:00"])
def test_rejects_invalid_or_naive_kickoff(date: str) -> None:
    value = payload()
    value["fixture"]["date"] = date
    with pytest.raises(ValueError, match="fixture.date"):
        ApiFootballFixtureAdapter().adapt(value)


def test_rejects_invalid_competition_type() -> None:
    value = payload()
    value["league"]["type"] = 123
    with pytest.raises(ValueError, match="league.type"):
        ApiFootballFixtureAdapter().adapt(value)


def test_rejects_invalid_season() -> None:
    value = payload()
    value["league"]["season"] = 0
    with pytest.raises(ValueError, match="league.season"):
        ApiFootballFixtureAdapter().adapt(value)


def test_defaults_missing_status_to_scheduled() -> None:
    value = payload()
    del value["fixture"]["status"]
    assert ApiFootballFixtureAdapter().adapt(value).status == "scheduled"


def test_rejects_missing_kickoff() -> None:
    value = payload()
    del value["fixture"]["date"]
    with pytest.raises(ValueError):
        ApiFootballFixtureAdapter().adapt(value)
