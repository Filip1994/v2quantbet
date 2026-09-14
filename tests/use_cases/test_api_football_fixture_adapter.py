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
    with pytest.raises(ValueError):
        ApiFootballFixtureAdapter().adapt(value)


def test_rejects_missing_kickoff() -> None:
    value = payload()
    del value["fixture"]["date"]
    with pytest.raises(ValueError):
        ApiFootballFixtureAdapter().adapt(value)
