from datetime import UTC, date, datetime

from h2h.quantlab.card_lab.context import parse_fixture_contexts_from_fixture_response
from h2h.quantlab.card_lab.features import referee_rates
from h2h.quantlab.card_lab.referee import referee_key


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


def test_verified_card_events_fill_missing_red_statistics() -> None:
    from h2h.quantlab.runtime import QuantLabRuntime

    class Repo:
        def __init__(self) -> None:
            self.saved = None

        def save_card_event_observation(self, observation):
            self.saved = observation
            return True

    class Provider:
        def fetch_events(self, _fixture_id):
            return {
                "errors": [],
                "response": [
                    {
                        "type": "Card",
                        "detail": "Yellow Card",
                        "time": {"elapsed": 79, "extra": None},
                        "player": {"id": 39165},
                        "team": {"id": 10},
                    }
                ],
            }

    repo = Repo()
    runtime = QuantLabRuntime(repo, Provider(), clock=lambda: NOW)
    fixture = {
        "fixture_id": "api-football:1494763",
        "provider_fixture_id": 1494763,
        "home_yellow_cards": 0,
        "away_yellow_cards": 1,
    }
    assert runtime._capture_referee_card_events(fixture, NOW)
    assert repo.saved.total_cards_1xbet == 1
    assert runtime._card_history_sample_size(({"card_total": 1, "red_cards": None},)) == 1

    repo.saved = None
    fixture["away_yellow_cards"] = 2
    assert not runtime._capture_referee_card_events(fixture, NOW)
    assert repo.saved is None

    card, _foul, count, _ = referee_rates(
        ({
            "referee": "Ref A",
            "kickoff_at": NOW.replace(day=26),
            "available_at": NOW,
            "card_total": 1,
            "yellow_cards": 1,
            "red_cards": None,
            "fouls": 10,
        },),
        referee="Ref A",
        decision_at=NOW,
    )
    assert count == 1
    assert card.value == 1
    assert card.components["event_samples"] == 1


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

        def unscanned_referee_history_days(self, **_kwargs):
            return ()

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

        def referee_card_event_backfill_candidates(self, *_args, **_kwargs):
            return ()

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



def test_scope_context_unlocks_existing_referee_statistics_for_same_cycle_refresh() -> None:
    from types import MethodType

    from h2h.quantlab.runtime import QuantLabRuntime, QuantLabRuntimeSettings

    class Repo:
        def __init__(self) -> None:
            self.scope_loaded = False

        def referee_history_scope_due(self, *_args, **_kwargs):
            return True

        def unscanned_referee_history_days(self, **_kwargs):
            return ()

        def save_fixture_observations(self, observations):
            return len(tuple(observations))

        def save_fixture_context(self, _context):
            self.scope_loaded = True

        def save_referee_history_scope_capture(self, **_kwargs):
            return "scope"

        def referee_history(self, referee, *, decision_at):
            assert referee == "Ref A"
            assert decision_at == NOW
            count = 6 if self.scope_loaded else 1
            return tuple(
                {
                    "referee": referee,
                    "kickoff_at": NOW.replace(hour=18),
                    "available_at": NOW.replace(hour=20),
                    "yellow_cards": 3,
                    "red_cards": 0,
                    "second_yellow_cards": None,
                    "fouls": 20,
                }
                for _ in range(count)
            )

        def referee_statistics_backfill_candidates(self, *_args, **_kwargs):
            raise AssertionError("existing stats should avoid new statistics fetches")

    class Provider:
        def fetch_completed_league_fixtures(self, *_args, **_kwargs):
            return _league_history_payload()

    repo = Repo()
    runtime = QuantLabRuntime(
        repo,
        Provider(),
        settings=QuantLabRuntimeSettings(card_referee_history_target=5),
        clock=lambda: NOW,
    )
    runtime._card_referee_history_targets = MethodType(
        lambda self, _now: {(39, 2026): {"Ref A"}},
        runtime,
    )

    scopes, stats, updated = runtime._bootstrap_card_referee_history(NOW)

    assert scopes == 1
    assert stats == 0
    assert updated == frozenset({"ref a"})

def test_collect_upcoming_can_force_snapshot_after_referee_history_change() -> None:
    import inspect

    from h2h.quantlab.runtime import QuantLabRuntime

    source = inspect.getsource(QuantLabRuntime._collect_upcoming)

    assert "force_card_referees" in source
    assert "force_snapshot" in source
    assert "feature_snapshot_due" in source


def test_prior_season_country_suffix_matches_current_referee() -> None:
    history = ({
        "referee": "Espen Eskas, Norway",
        "kickoff_at": datetime(2024, 10, 10, 18, tzinfo=UTC),
        "available_at": datetime(2026, 9, 1, tzinfo=UTC),
        "yellow_cards": 4,
        "red_cards": 1,
        "second_yellow_cards": None,
        "fouls": 24,
    },)
    cards, _fouls, card_n, _foul_n = referee_rates(
        history, referee="Espen Eskas", decision_at=NOW
    )
    assert referee_key(" Espen  Eskas, Norway ") == referee_key("Espen Eskas")
    assert card_n == 1
    assert cards.value == 5


def test_referee_bootstrap_does_not_persist_blocked_national_team_history() -> None:
    from types import MethodType

    from h2h.quantlab.runtime import QuantLabRuntime, QuantLabRuntimeSettings

    class Repo:
        def __init__(self) -> None:
            self.captures = []
            self.contexts = []

        def referee_history(self, *_args, **_kwargs):
            return ()

        def referee_history_scope_due(self, *_args, **_kwargs):
            return True

        def unscanned_referee_history_days(self, **_kwargs):
            return ()

        def save_fixture_observations(self, observations):
            return len(tuple(observations))

        def save_fixture_context(self, context):
            self.contexts.append(context)

        def save_referee_history_scope_capture(self, **kwargs):
            self.captures.append(kwargs)

        def referee_statistics_backfill_candidates(self, *_args, **_kwargs):
            return ()

        def referee_card_event_backfill_candidates(self, *_args, **_kwargs):
            return ()

    class Provider:
        def __init__(self) -> None:
            self.calls = []

        def fetch_completed_league_fixtures(self, league_id, season, *, start_date, end_date):
            self.calls.append((league_id, season, start_date, end_date))
            if season != 2024:
                return {"errors": [], "response": []}
            return {
                "errors": [],
                "response": [{
                    "fixture": {
                        "id": 12345,
                        "date": "2024-10-10T18:00:00+00:00",
                        "referee": "Espen Eskas, Norway",
                        "status": {"short": "FT"},
                    },
                    "league": {
                        "id": 5, "name": "UEFA Nations League", "country": "World",
                        "type": "Cup", "season": 2024,
                    },
                    "teams": {
                        "home": {"id": 10, "name": "Home"},
                        "away": {"id": 11, "name": "Away"},
                    },
                }],
            }

    repo, provider = Repo(), Provider()
    runtime = QuantLabRuntime(
        repo,
        provider,
        settings=QuantLabRuntimeSettings(
            card_referee_history_lookback_days=1100,
            card_referee_prior_seasons=2,
        ),
        clock=lambda: NOW,
    )
    runtime._card_referee_history_targets = MethodType(
        lambda self, _now: {(5, 2026): {"Espen Eskas"}}, runtime
    )

    scopes, stats, _updated = runtime._bootstrap_card_referee_history(NOW)

    assert scopes == 3
    assert stats == 0
    assert [call[1] for call in provider.calls] == [2026, 2025, 2024]
    assert provider.calls[-1][2].year <= 2024
    assert repo.contexts == []


def test_cross_competition_day_scan_persists_only_finished_referee_fixtures() -> None:
    from h2h.quantlab.runtime import QuantLabRuntime

    scan_day = date(2026, 9, 20)

    class Repo:
        def __init__(self) -> None:
            self.observations = []
            self.contexts = []
            self.scans = []

        def unscanned_referee_history_days(self, **kwargs):
            assert kwargs["limit"] == 12
            return (scan_day,)

        def save_fixture_observations(self, observations):
            self.observations.extend(observations)

        def save_fixture_context(self, context):
            self.contexts.append(context)

        def save_referee_day_scan(self, **kwargs):
            self.scans.append(kwargs)

    def fixture(fixture_id, referee, status):
        return {
            "fixture": {
                "id": fixture_id, "date": "2026-09-20T18:00:00+00:00",
                "referee": referee, "status": {"short": status},
            },
            "league": {
                "id": 140, "name": "La Liga", "country": "Spain",
                "type": "League", "season": 2026,
            },
            "teams": {
                "home": {"id": 10, "name": "Home"},
                "away": {"id": 11, "name": "Away"},
            },
        }

    class Provider:
        def __init__(self) -> None:
            self.pages = []

        def fetch_fixtures_for_date(self, fixture_date, *, page=1):
            assert fixture_date == scan_day
            self.pages.append(page)
            return {
                "errors": [], "paging": {"current": page, "total": 2},
                "response": (
                    [fixture(1, "Alejandro Hernandez", "FT"), fixture(2, None, "FT")]
                    if page == 1 else
                    [fixture(3, "Espen Eskas, Norway", "AET"), fixture(4, "Other", "NS")]
                ),
            }

    repo, provider = Repo(), Provider()
    runtime = QuantLabRuntime(repo, provider, clock=lambda: NOW)

    assert runtime._scan_card_referee_days(NOW) == 1
    assert provider.pages == [1, 2]
    assert {item.fixture.fixture_id for item in repo.observations} == {
        "api-football:1", "api-football:3",
    }
    assert {item.referee for item in repo.contexts} == {
        "Alejandro Hernandez", "Espen Eskas, Norway",
    }
    assert repo.scans[0]["response_fixture_count"] == 4
    assert repo.scans[0]["referee_fixture_count"] == 2
    assert repo.scans[0]["page_count"] == 2


def test_referee_bootstrap_skips_candidate_sql_after_api_attempt_cap() -> None:
    """Unused referee candidates must not be queried after cycle budget is exhausted."""
    from types import MethodType

    from h2h.quantlab.runtime import QuantLabRuntime, QuantLabRuntimeSettings

    class Repo:
        def __init__(self) -> None:
            self.event_candidate_queries: list[str] = []
            self.stats_candidate_queries: list[str] = []

        def referee_history(self, *_args, **_kwargs):
            return ()

        def unscanned_referee_history_days(self, **_kwargs):
            return ()

        def referee_history_scope_due(self, *_args, **_kwargs):
            return False

        def referee_card_event_backfill_candidates(self, referee, **_kwargs):
            self.event_candidate_queries.append(referee)
            return ({"fixture_id": "api-football:1"},)

        def referee_statistics_backfill_candidates(self, referee, **_kwargs):
            self.stats_candidate_queries.append(referee)
            return ({"fixture_id": "api-football:1"},)

    repo = Repo()
    runtime = QuantLabRuntime(
        repo,
        object(),
        settings=QuantLabRuntimeSettings(
            card_referee_prior_seasons=0,
            card_referee_history_target=8,
            card_referee_statistics_per_cycle=1,
        ),
        clock=lambda: NOW,
    )
    runtime._card_referee_history_targets = MethodType(
        lambda self, _now: {(39, 2026): {"Ref B", "Ref A"}}, runtime
    )
    captured_events: list[str] = []
    captured_stats: list[str] = []

    def capture_events(self, fixture, now):
        captured_events.append(str(fixture["fixture_id"]))
        return False

    def capture_stats(self, fixture, now, *, allow_retry=False):
        assert allow_retry
        captured_stats.append(str(fixture["fixture_id"]))
        return True

    runtime._capture_referee_card_events = MethodType(capture_events, runtime)
    runtime._capture_historical_statistics = MethodType(capture_stats, runtime)
    scopes, stats, updated = runtime._bootstrap_card_referee_history(NOW)

    assert scopes == 0
    assert stats == 1
    assert updated == frozenset()
    assert repo.event_candidate_queries == ["Ref A"]
    assert repo.stats_candidate_queries == ["Ref A"]
    assert captured_events == ["api-football:1"]
    assert captured_stats == ["api-football:1"]


def test_referee_history_scopes_stats_and_events_to_matching_fixtures() -> None:
    """Per-referee lookups must not materialize latest stats for every fixture."""
    from types import SimpleNamespace

    from h2h.quantlab.repository import PostgreSQLQuantLabRepository

    class Cursor:
        def __init__(self) -> None:
            self.query = ""
            self.params = ()

        @property
        def description(self):
            return (SimpleNamespace(name="referee"),)

        def execute(self, query, params):
            self.query = query
            self.params = params

        def fetchall(self):
            return [("Ref A",)]

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class Connection:
        def __init__(self, cursor):
            self._cursor = cursor

        def cursor(self):
            return self._cursor

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    cursor = Cursor()
    repository = PostgreSQLQuantLabRepository(
        connect=lambda: Connection(cursor)
    )
    rows = repository.referee_history(
        "Ref A, England", decision_at=NOW, limit=8
    )

    assert rows == ({"referee": "Ref A"},)
    assert cursor.params == (
        "Ref A, England", NOW, NOW, NOW, NOW, 8
    )
    sql = " ".join(cursor.query.split())
    for table in (
        "quantlab_match_statistics_observations",
        "quantlab_card_event_observations",
    ):
        assert (
            f"FROM {table} "
            "WHERE fixture_id IN (SELECT fixture_id FROM context) "
            "AND available_at <= %s"
        ) in sql
    assert "FROM context JOIN stats USING (fixture_id)" in sql
    assert "LEFT JOIN events USING (fixture_id)" in sql
    assert "ORDER BY context.kickoff_at DESC LIMIT %s" in sql
