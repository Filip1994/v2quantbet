from __future__ import annotations

from datetime import UTC, datetime

from h2h.quantlab.coverage import fixture_statistics_coverage
from h2h.quantlab.runtime import QuantLabRuntime


NOW = datetime(2026, 9, 26, 17, 0, tzinfo=UTC)


def _coverage_payload(flag):
    fixtures = {} if flag == "missing" else {"statistics_fixtures": flag}
    return {
        "response": [
            {
                "league": {"id": 39, "name": "Premier League"},
                "seasons": [
                    {
                        "year": 2026,
                        "coverage": {"fixtures": fixtures},
                    }
                ],
            }
        ]
    }


def _fixture():
    return {
        "fixture_id": "api-football:42",
        "provider_fixture_id": 42,
        "league_id": 39,
        "season": 2026,
        "home_team_id": 10,
        "away_team_id": 11,
        "home_team": "Home",
        "away_team": "Away",
        "competition_name": "Premier League",
        "country": "England",
        "competition_type": "League",
        "provider_status": "FT",
    }


def test_fixture_statistics_coverage_parses_true_false_and_unknown() -> None:
    supported, count = fixture_statistics_coverage(
        _coverage_payload(True),
        league_id=39,
        season=2026,
    )
    assert supported is True
    assert count == 1

    unsupported, _ = fixture_statistics_coverage(
        _coverage_payload(False),
        league_id=39,
        season=2026,
    )
    assert unsupported is False

    unknown, _ = fixture_statistics_coverage(
        _coverage_payload("missing"),
        league_id=39,
        season=2026,
    )
    assert unknown is None


class Repo:
    def __init__(self, cached):
        self.cached = cached
        self.saved = []
        self.capture_checks = []

    def latest_league_statistics_coverage(self, _league_id, _season, **_kwargs):
        return self.cached

    def save_league_statistics_coverage(self, **kwargs):
        self.saved.append(kwargs)

    def statistics_capture_exists(self, fixture_id):
        self.capture_checks.append(fixture_id)
        return False


class Provider:
    def __init__(self, coverage_payload=None):
        self.coverage_payload = coverage_payload
        self.coverage_calls = []
        self.statistics_calls = []

    def fetch_league_coverage(self, league_id, season):
        self.coverage_calls.append((league_id, season))
        if self.coverage_payload is None:
            raise AssertionError("coverage API must not be called")
        return self.coverage_payload

    def fetch_statistics(self, fixture_id):
        self.statistics_calls.append(fixture_id)
        raise AssertionError("statistics API must not be called")


def test_cached_unsupported_coverage_skips_fixture_statistics_request() -> None:
    repo = Repo(
        {
            "captured_at": NOW,
            "statistics_fixtures_supported": False,
            "response_item_count": 1,
            "raw_payload": {},
        }
    )
    provider = Provider()
    runtime = QuantLabRuntime(repo, provider, clock=lambda: NOW)

    assert runtime._capture_historical_statistics(_fixture(), NOW) is False
    assert provider.coverage_calls == []
    assert provider.statistics_calls == []


def test_missing_coverage_is_fetched_persisted_and_true_allows_statistics() -> None:
    repo = Repo(None)
    provider = Provider(_coverage_payload(True))
    runtime = QuantLabRuntime(repo, provider, clock=lambda: NOW)

    assert runtime._statistics_coverage_allows(_fixture(), NOW) is True
    assert provider.coverage_calls == [(39, 2026)]
    assert len(repo.saved) == 1
    assert repo.saved[0]["statistics_fixtures_supported"] is True


def test_unknown_coverage_is_persisted_but_does_not_fabricate_unsupported() -> None:
    repo = Repo(None)
    provider = Provider(_coverage_payload("missing"))
    runtime = QuantLabRuntime(repo, provider, clock=lambda: NOW)

    assert runtime._statistics_coverage_allows(_fixture(), NOW) is True
    assert len(repo.saved) == 1
    assert repo.saved[0]["statistics_fixtures_supported"] is None
