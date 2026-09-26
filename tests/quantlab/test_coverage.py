from __future__ import annotations

from datetime import UTC, datetime

from h2h.quantlab.coverage import parse_fixture_statistics_coverage
from h2h.quantlab.runtime import QuantLabRuntime


NOW = datetime(2026, 9, 26, 16, 45, tzinfo=UTC)


def _coverage_payload(value):
    return {
        "response": [
            {
                "league": {"id": 39, "name": "Premier League"},
                "seasons": [
                    {
                        "year": 2026,
                        "coverage": {
                            "fixtures": {
                                "events": True,
                                "lineups": True,
                                "statistics_fixtures": value,
                                "statistics_players": True,
                            }
                        },
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
    }


def _stats_payload():
    def team(team_id, corners):
        return {
            "team": {"id": team_id, "name": f"Team {team_id}"},
            "statistics": [
                {"type": "Corner Kicks", "value": corners},
                {"type": "Ball Possession", "value": "50%"},
                {"type": "Shots on Goal", "value": 4},
                {"type": "Total Shots", "value": 10},
            ],
        }

    return {"response": [team(10, 6), team(11, 4)]}


def test_fixture_statistics_coverage_parser_preserves_true_false_and_unknown() -> None:
    assert (
        parse_fixture_statistics_coverage(
            _coverage_payload(True),
            league_id=39,
            season=2026,
        )
        is True
    )
    assert (
        parse_fixture_statistics_coverage(
            _coverage_payload(False),
            league_id=39,
            season=2026,
        )
        is False
    )
    assert (
        parse_fixture_statistics_coverage(
            _coverage_payload(None),
            league_id=39,
            season=2026,
        )
        is None
    )
    assert (
        parse_fixture_statistics_coverage(
            _coverage_payload(True),
            league_id=40,
            season=2026,
        )
        is None
    )
    assert (
        parse_fixture_statistics_coverage(
            _coverage_payload(True),
            league_id=39,
            season=2025,
        )
        is None
    )


class _Repo:
    def __init__(self, cached_coverage):
        self.cached_coverage = cached_coverage
        self.coverage_captures = []
        self.statistics_captures = []
        self.statistics = []

    def statistics_capture_exists(self, _fixture_id):
        return False

    def latest_league_statistics_coverage(self, *_args, **_kwargs):
        return self.cached_coverage

    def save_league_statistics_coverage(self, **kwargs):
        self.coverage_captures.append(kwargs)
        return "coverage"

    def save_statistics_capture(self, **kwargs):
        self.statistics_captures.append(kwargs)
        return "stats-capture"

    def save_match_statistics(self, item):
        self.statistics.append(item)


class _Provider:
    def __init__(self, *, coverage_value=True):
        self.coverage_value = coverage_value
        self.coverage_calls = []
        self.statistics_calls = []

    def fetch_league_coverage(self, league_id, season):
        self.coverage_calls.append((league_id, season))
        return _coverage_payload(self.coverage_value)

    def fetch_statistics(self, fixture_id):
        self.statistics_calls.append(fixture_id)
        return _stats_payload()


def test_false_league_coverage_watermarks_fixture_without_stats_request() -> None:
    repo = _Repo(
        {
            "statistics_fixtures": False,
            "raw_payload": _coverage_payload(False),
        }
    )
    provider = _Provider()
    runtime = QuantLabRuntime(repo, provider, clock=lambda: NOW)

    attempted = runtime._capture_historical_statistics(_fixture(), NOW)

    assert attempted is False
    assert provider.coverage_calls == []
    assert provider.statistics_calls == []
    assert len(repo.statistics_captures) == 1
    capture = repo.statistics_captures[0]
    assert capture["status"] == "UNAVAILABLE"
    assert capture["response_team_count"] == 0
    assert capture["reason"] == "league-season-statistics-fixtures-false"


def test_coverage_cache_miss_fetches_metadata_then_supported_fixture_stats() -> None:
    repo = _Repo(None)
    provider = _Provider(coverage_value=True)
    runtime = QuantLabRuntime(repo, provider, clock=lambda: NOW)

    attempted = runtime._capture_historical_statistics(_fixture(), NOW)

    assert attempted is True
    assert provider.coverage_calls == [(39, 2026)]
    assert provider.statistics_calls == [42]
    assert len(repo.coverage_captures) == 1
    assert repo.coverage_captures[0]["statistics_fixtures"] is True
    assert len(repo.statistics) == 1
    assert repo.statistics[0].home_corner_kicks == 6
    assert repo.statistics[0].away_corner_kicks == 4


def test_unknown_coverage_does_not_fabricate_unavailable() -> None:
    repo = _Repo(None)
    provider = _Provider(coverage_value=None)
    runtime = QuantLabRuntime(repo, provider, clock=lambda: NOW)

    attempted = runtime._capture_historical_statistics(_fixture(), NOW)

    assert attempted is True
    assert provider.coverage_calls == [(39, 2026)]
    assert provider.statistics_calls == [42]
    assert repo.coverage_captures[0]["statistics_fixtures"] is None
    assert repo.statistics_captures[0]["status"] == "AVAILABLE"
