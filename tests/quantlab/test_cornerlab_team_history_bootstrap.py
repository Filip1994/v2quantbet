from __future__ import annotations

from datetime import UTC, datetime, timedelta

from h2h.quantlab.runtime import QuantLabRuntime, QuantLabRuntimeSettings


NOW = datetime(2026, 9, 26, 16, 30, tzinfo=UTC)


def _upcoming_fixture() -> dict[str, object]:
    return {
        "fixture_id": "api-football:9001",
        "provider_fixture_id": 9001,
        "league_id": 39,
        "season": 2026,
        "home_team_id": 10,
        "away_team_id": 11,
        "home_team": "Home",
        "away_team": "Away",
        "competition_name": "Premier League",
        "country": "England",
        "competition_type": "League",
        "kickoff_at": NOW + timedelta(hours=3),
        "provider_status": "NS",
    }


def _historical_fixture(fixture_id: int, home_id: int, away_id: int) -> dict[str, object]:
    return {
        "fixture_id": f"api-football:{fixture_id}",
        "provider_fixture_id": fixture_id,
        "league_id": 39,
        "season": 2026,
        "home_team_id": home_id,
        "away_team_id": away_id,
        "home_team": f"Team {home_id}",
        "away_team": f"Team {away_id}",
        "competition_name": "Premier League",
        "country": "England",
        "competition_type": "League",
        "kickoff_at": NOW - timedelta(days=fixture_id % 20 + 1),
        "provider_status": "FT",
    }


def _team_fixture_payload(team_id: int) -> dict[str, object]:
    response = []
    for offset in range(3):
        fixture_id = team_id * 100 + offset + 1
        opponent = team_id + 100 + offset
        response.append(
            {
                "fixture": {
                    "id": fixture_id,
                    "date": (NOW - timedelta(days=offset + 1)).isoformat(),
                    "status": {"short": "FT"},
                },
                "league": {
                    "id": 39,
                    "name": "Premier League",
                    "country": "England",
                    "type": "League",
                    "season": 2026,
                },
                "teams": {
                    "home": {"id": team_id, "name": f"Team {team_id}"},
                    "away": {"id": opponent, "name": f"Team {opponent}"},
                },
            }
        )
    return {"response": response}


def _statistics_payload(home_id: int, away_id: int) -> dict[str, object]:
    def team(team_id: int, corners: int) -> dict[str, object]:
        return {
            "team": {"id": team_id, "name": f"Team {team_id}"},
            "statistics": [
                {"type": "Corner Kicks", "value": corners},
                {"type": "Ball Possession", "value": "50%"},
                {"type": "Shots on Goal", "value": 4},
                {"type": "Shots off Goal", "value": 5},
                {"type": "Total Shots", "value": 11},
                {"type": "Blocked Shots", "value": 2},
                {"type": "Shots insidebox", "value": 7},
                {"type": "Shots outsidebox", "value": 4},
                {"type": "Offsides", "value": 1},
                {"type": "Goalkeeper Saves", "value": 3},
                {"type": "Total passes", "value": 400},
                {"type": "Passes accurate", "value": 330},
                {"type": "Passes %", "value": "82%"},
                {"type": "Fouls", "value": 12},
                {"type": "Yellow Cards", "value": 2},
                {"type": "Red Cards", "value": 0},
            ],
        }

    return {"response": [team(home_id, 6), team(away_id, 4)]}


class Repo:
    def __init__(
        self,
        *,
        has_corner_market: bool = True,
        opponents: dict[int, tuple[int, ...]] | None = None,
    ) -> None:
        self.has_corner_market = has_corner_market
        self.opponents = opponents or {}
        self.team_captures: list[dict[str, object]] = []
        self.fixture_observations = []
        self.statistics_captures: dict[str, dict[str, object]] = {}
        self.statistics = []
        self.historical = (
            _historical_fixture(1001, 10, 101),
            _historical_fixture(1002, 10, 102),
            _historical_fixture(1003, 10, 103),
            _historical_fixture(1101, 11, 111),
            _historical_fixture(1102, 11, 112),
            _historical_fixture(1103, 11, 113),
        )

    def upcoming_fixtures(self, **_kwargs):
        return (_upcoming_fixture(),)

    def market_labs_for_fixture(self, _fixture_id):
        return {"CORNER"} if self.has_corner_market else set()

    def team_history_due(self, _team_id, **_kwargs):
        return True

    def save_fixture_observations(self, observations):
        self.fixture_observations.extend(observations)
        return len(tuple(observations))

    def save_team_history_capture(self, **kwargs):
        self.team_captures.append(kwargs)
        return "capture"

    def recent_team_opponent_ids(self, team_id, **_kwargs):
        return self.opponents.get(team_id, ())

    def completed_for_team_statistics(self, _team_ids, **_kwargs):
        return self.historical

    def statistics_capture_exists(self, fixture_id):
        return fixture_id in self.statistics_captures

    def save_statistics_capture(self, **kwargs):
        self.statistics_captures[str(kwargs["fixture_id"])] = kwargs

    def save_match_statistics(self, item):
        self.statistics.append(item)


class Provider:
    def __init__(self, repo: Repo) -> None:
        self.repo = repo
        self.team_calls: list[tuple[int, int]] = []
        self.stats_calls: list[int] = []

    def fetch_team_recent_fixtures(self, team_id, *, last):
        self.team_calls.append((team_id, last))
        return _team_fixture_payload(team_id)

    def fetch_statistics(self, fixture_id):
        self.stats_calls.append(fixture_id)
        fixture = next(
            item for item in self.repo.historical
            if int(item["provider_fixture_id"]) == fixture_id
        )
        return _statistics_payload(
            int(fixture["home_team_id"]),
            int(fixture["away_team_id"]),
        )


def test_corner_team_history_bootstrap_targets_only_corner_market_teams() -> None:
    repo = Repo()
    provider = Provider(repo)
    runtime = QuantLabRuntime(
        repo,
        provider,
        settings=QuantLabRuntimeSettings(
            corner_team_history_last=12,
            corner_team_history_teams_per_cycle=40,
            corner_team_statistics_per_cycle=4,
        ),
        clock=lambda: NOW,
    )

    discoveries, stats = runtime._bootstrap_corner_team_history(NOW)

    assert discoveries == 2
    assert provider.team_calls == [(10, 12), (11, 12)]
    assert len(repo.team_captures) == 2
    assert len(repo.fixture_observations) == 6
    assert stats == 4
    assert len(provider.stats_calls) == 4
    assert len(repo.statistics_captures) == 4
    assert len(repo.statistics) == 4


def test_corner_team_history_bootstrap_expands_one_hop_opponents() -> None:
    repo = Repo(
        opponents={
            10: (101, 102),
            11: (111,),
            101: (999,),
        }
    )
    provider = Provider(repo)
    runtime = QuantLabRuntime(
        repo,
        provider,
        settings=QuantLabRuntimeSettings(
            corner_team_history_last=12,
            corner_team_history_teams_per_cycle=5,
            corner_team_statistics_per_cycle=1,
        ),
        clock=lambda: NOW,
    )

    discoveries, stats = runtime._bootstrap_corner_team_history(NOW)

    assert discoveries == 5
    assert provider.team_calls == [
        (10, 12),
        (101, 12),
        (102, 12),
        (11, 12),
        (111, 12),
    ]
    assert all(team_id != 999 for team_id, _last in provider.team_calls)
    assert stats == 1


def test_corner_team_history_bootstrap_makes_zero_calls_without_corner_market() -> None:
    repo = Repo(has_corner_market=False)
    provider = Provider(repo)
    runtime = QuantLabRuntime(repo, provider, clock=lambda: NOW)

    assert runtime._bootstrap_corner_team_history(NOW) == (0, 0)
    assert provider.team_calls == []
    assert provider.stats_calls == []


def test_corner_team_history_defaults_are_bounded() -> None:
    settings = QuantLabRuntimeSettings()

    assert settings.corner_team_history_last == 12
    assert settings.corner_team_history_teams_per_cycle == 120
    assert settings.corner_team_statistics_per_cycle == 360
    assert settings.corner_team_history_refresh_seconds == 21600
