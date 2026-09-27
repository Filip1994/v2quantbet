from datetime import UTC, datetime

from h2h.quantlab.card_lab.context import parse_fixture_contexts_from_fixture_response


NOW = datetime(2026, 9, 27, 21, 0, tzinfo=UTC)


def test_team_history_fixture_payload_yields_referee_context_without_extra_call() -> None:
    payload = {
        "errors": [],
        "response": [
            {
                "fixture": {
                    "id": 1001,
                    "date": "2026-09-20T18:00:00+00:00",
                    "referee": "Ref A",
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
                    "home": {"id": 10, "name": "Home"},
                    "away": {"id": 11, "name": "Away"},
                },
            },
            {
                "fixture": {
                    "id": 1002,
                    "date": "2026-09-21T18:00:00+00:00",
                    "referee": "Ref B",
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
                    "home": {"id": 12, "name": "Home 2"},
                    "away": {"id": 13, "name": "Away 2"},
                },
            },
        ],
    }

    rows = parse_fixture_contexts_from_fixture_response(payload, captured_at=NOW)

    assert len(rows) == 2
    assert [row.fixture_id for row in rows] == [
        "api-football:1001",
        "api-football:1002",
    ]
    assert [row.referee for row in rows] == ["Ref A", "Ref B"]
    assert all(row.available_at == NOW for row in rows)
    assert all(row.provider_status == "FT" for row in rows)


def _league_history_payload(count: int = 10) -> dict:
    response = []
    for index in range(count):
        response.append(
            {
                "fixture": {
                    "id": 2000 + index,
                    "date": f"2026-09-{index + 1:02d}T18:00:00+00:00",
                    "referee": "Ref A",
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
                    "home": {"id": 100 + index * 2, "name": f"Home {index}"},
                    "away": {"id": 101 + index * 2, "name": f"Away {index}"},
                },
            }
        )
    return {"errors": [], "response": response}


def test_targeted_referee_bootstrap_uses_one_scope_call_and_stops_at_target() -> None:
    from types import MethodType

    from h2h.quantlab.runtime import QuantLabRuntime, QuantLabRuntimeSettings

    class Repo:
        def __init__(self) -> None:
            self.sample_size = 1
            self.scope_captures = []
            self.contexts = []
            self.observations = []

        def referee_history_scope_due(self, league_id, season, **_kwargs):
            assert (league_id, season) == (39, 2026)
            return True

        def save_fixture_observations(self, observations):
            self.observations.extend(observations)
            return len(tuple(observations))

        def save_fixture_context(self, context):
            self.contexts.append(context)

        def save_referee_history_scope_capture(self, **kwargs):
            self.scope_captures.append(kwargs)
            return "scope"

        def referee_history(self, referee, *, decision_at):
            assert referee == "Ref A"
            assert decision_at == NOW
            return tuple(
                {
                    "referee": referee,
                    "kickoff_at": NOW,
                    "available_at": NOW,
                    "yellow_cards": 3,
                    "red_cards": 0,
                    "second_yellow_cards": None,
                    "fouls": 20,
                }
                for _ in range(self.sample_size)
            )

        def referee_statistics_backfill_candidates(self, referee, **_kwargs):
            assert referee == "Ref A"
            return tuple(
                {
                    "fixture_id": f"api-football:{3000 + index}",
                    "provider_fixture_id": 3000 + index,
                    "league_id": 39,
                    "season": 2026,
                    "home_team_id": 10 + index * 2,
                    "away_team_id": 11 + index * 2,
                    "home_team": f"Home {index}",
                    "away_team": f"Away {index}",
                    "competition_name": "Premier League",
                    "country": "England",
                    "competition_type": "League",
                    "kickoff_at": NOW,
                    "provider_status": "FT",
                }
                for index in range(12)
            )

    class Provider:
        def __init__(self) -> None:
            self.scope_calls = []

        def fetch_completed_league_fixtures(
            self, league_id, season, *, start_date, end_date
        ):
            self.scope_calls.append((league_id, season, start_date, end_date))
            return _league_history_payload()

    repo = Repo()
    provider = Provider()
    runtime = QuantLabRuntime(
        repo,
        provider,
        settings=QuantLabRuntimeSettings(
            card_referee_history_target=8,
            card_referee_statistics_per_cycle=64,
        ),
        clock=lambda: NOW,
    )
    runtime._card_referee_history_targets = MethodType(
        lambda self, _now: {(39, 2026): {"Ref A"}},
        runtime,
    )

    def fake_capture(self, _fixture, _now, *, allow_retry=False):
        assert allow_retry is True
        repo.sample_size += 1
        return True

    runtime._capture_historical_statistics = MethodType(fake_capture, runtime)

    scopes, stats, updated = runtime._bootstrap_card_referee_history(NOW)

    assert scopes == 1
    assert stats == 7
    assert updated == frozenset({"ref a"})
    assert len(provider.scope_calls) == 1
    assert len(repo.scope_captures) == 1
    assert repo.scope_captures[0]["response_fixture_count"] == 10
    assert repo.scope_captures[0]["referee_fixture_count"] == 10
    assert repo.sample_size == 8


def test_collect_upcoming_can_force_snapshot_after_referee_history_change() -> None:
    import inspect

    from h2h.quantlab.runtime import QuantLabRuntime

    source = inspect.getsource(QuantLabRuntime._collect_upcoming)

    assert "force_card_referees" in source
    assert "force_snapshot" in source
    assert "feature_snapshot_due" in source
