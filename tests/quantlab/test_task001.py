import inspect
from datetime import UTC, datetime, timedelta

import pytest

from h2h.odds.budget import ApiBudgetExceededError
from h2h.quantlab.budget import DEFAULT_PROVIDER_DAILY_LIMIT, QuantLabRequestBudget
from h2h.quantlab.card_lab.features import (
    MATCH_IMPORTANCE_VERSION,
    TABLE_PRESSURE_VERSION,
    FeatureDatum,
    FeatureLeakageError,
    match_importance,
    referee_rates,
    table_pressure,
)
from h2h.quantlab.card_lab.rivalry import RIVALRY_REGISTRY_VERSION, rivalry_indicator
from h2h.quantlab.dashboard import QuantLabDashboardService
from h2h.quantlab.fixture_discovery import parse_fixture_discovery_response
from h2h.quantlab.market_collector import QuantLabMarketCollector, parse_market_response
from h2h.quantlab.provider import QuantLabApiFootballClient
from h2h.quantlab.repository import PostgreSQLQuantLabRepository
from h2h.quantlab.runtime import QuantLabRuntime, QuantLabRuntimeSettings
from h2h.quantlab.scope import card_corner_scope, goal_scope


NOW = datetime(2026, 9, 26, 2, 0, tzinfo=UTC)


def _odds_payload():
    return {
        "response": [
            {
                "fixture": {"id": 42},
                "update": "2026-09-26T01:55:00+00:00",
                "bookmakers": [
                    {
                        "id": 8,
                        "name": "Bet365",
                        "bets": [
                            {
                                "id": 5,
                                "name": "Goals Over/Under",
                                "values": [
                                    {"value": "Over 2.5", "odd": "1.91"},
                                    {"value": "Under 2.5", "odd": "1.95"},
                                ],
                            },
                            {
                                "id": 999,
                                "name": "Exotic Provider Market",
                                "values": [
                                    {
                                        "value": "Some Raw Selection",
                                        "odd": "3.40",
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "id": 11,
                        "name": "1xBet",
                        "bets": [
                            {
                                "id": 120,
                                "name": "Total Cards",
                                "values": [{"value": "Over 4.5", "odd": 2.05}],
                            }
                        ],
                    },
                    {
                        "id": 6,
                        "name": "Ignored Book",
                        "bets": [
                            {
                                "id": 5,
                                "name": "Goals Over/Under",
                                "values": [{"value": "Over 2.5", "odd": 1.8}],
                            }
                        ],
                    },
                ],
            }
        ]
    }


def _fixture_payload(
    fixture_id,
    league_id,
    competition_name,
    country,
    *,
    competition_type="League",
    kickoff="2026-09-26T02:30:00+00:00",
):
    return {
        "fixture": {
            "id": fixture_id,
            "date": kickoff,
            "status": {"short": "NS"},
        },
        "league": {
            "id": league_id,
            "name": competition_name,
            "country": country,
            "type": competition_type,
            "season": 2026,
        },
        "teams": {
            "home": {"id": fixture_id * 2, "name": f"Home {fixture_id}"},
            "away": {"id": fixture_id * 2 + 1, "name": f"Away {fixture_id}"},
        },
    }


def test_all_market_parser_keeps_unknown_raw_market_and_only_target_books() -> None:
    rows = parse_market_response(
        _odds_payload(),
        fixture_id="api-football:42",
        provider_fixture_id=42,
        captured_at=NOW,
    )

    assert {row.bookmaker_id for row in rows} == {8, 11}
    exotic = next(row for row in rows if row.provider_bet_id == 999)
    assert exotic.lab_owner == "UNCLASSIFIED"
    assert exotic.raw_selection == "Some Raw Selection"
    assert exotic.raw_payload["bet"]["name"] == "Exotic Provider Market"

    over = next(
        row
        for row in rows
        if row.provider_bet_id == 5 and row.raw_selection == "Over 2.5"
    )
    assert float(over.parsed_line) == 2.5
    cards = next(row for row in rows if row.provider_bet_id == 120)
    assert cards.lab_owner == "CARD"


def test_collector_reuses_one_fixture_response_for_both_books_and_all_markets() -> None:
    class Provider:
        def __init__(self):
            self.calls = []

        def fetch_odds(self, fixture_id):
            self.calls.append(fixture_id)
            return _odds_payload()

    class Repo:
        def __init__(self):
            self.saved = ()
            self.capture = None

        def save_market_observations(self, rows):
            self.saved = tuple(rows)

        def save_market_capture(self, **kwargs):
            self.capture = kwargs

    provider = Provider()
    repo = Repo()
    rows = QuantLabMarketCollector(repo, provider).collect_fixture(
        fixture_id="api-football:42",
        provider_fixture_id=42,
        captured_at=NOW,
    )

    assert provider.calls == [42]
    assert repo.saved == rows
    assert {row.bookmaker_id for row in rows} == {8, 11}
    assert repo.capture["raw_observation_count"] == len(rows)
    assert repo.capture["stored_observation_count"] == len(rows)


def test_collector_filters_card_corner_rows_and_watermarks_empty_or_filtered_capture() -> None:
    class Provider:
        def fetch_odds(self, fixture_id):
            assert fixture_id == 42
            return _odds_payload()

    class Repo:
        def __init__(self):
            self.saved = ()
            self.capture = None

        def save_market_observations(self, rows):
            self.saved = tuple(rows)

        def save_market_capture(self, **kwargs):
            self.capture = kwargs

    repo = Repo()
    rows = QuantLabMarketCollector(repo, Provider()).collect_fixture(
        fixture_id="api-football:42",
        provider_fixture_id=42,
        captured_at=NOW,
        allowed_labs={"GOAL"},
    )

    assert rows
    assert {row.lab_owner for row in rows} == {"GOAL"}
    assert {row.lab_owner for row in repo.saved} == {"GOAL"}
    assert repo.capture["raw_observation_count"] == 4
    assert repo.capture["stored_observation_count"] == 2
    assert set(repo.capture["allowed_labs"]) == {"GOAL"}


def test_collector_write_path_has_no_production_table_mutations() -> None:
    collector_source = inspect.getsource(QuantLabMarketCollector)
    persistence_source = inspect.getsource(
        PostgreSQLQuantLabRepository.save_market_observations
    )
    combined = collector_source + persistence_source

    assert "quantlab_market_observations" in combined
    for forbidden in (
        "quote_series",
        "value_evaluations",
        "pick_decisions",
        "registered_picks",
        "bankroll",
    ):
        assert forbidden not in combined


class _BudgetCursor:
    def __init__(self, connection):
        self.connection = connection
        self._one = None
        self._all = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return None

    def execute(self, sql, params=None):
        self.connection.sql.append(sql)
        if "SELECT category, request_count" in sql:
            self._all = list(self.connection.usage.items())
        if "SELECT COALESCE(request_count, 0)" in sql:
            self._one = (self.connection.usage.get("quantlab_context", 0),)

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._all


class _BudgetConnection:
    def __init__(self, usage=None):
        self.usage = dict(usage or {})
        self.sql = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return None

    def cursor(self):
        return _BudgetCursor(self)


def test_quantlab_budget_and_client_use_quantlab_context_category() -> None:
    connection = _BudgetConnection()
    budget = QuantLabRequestBudget(
        shared_daily_limit=75_000,
        connect=lambda: connection,
        clock=lambda: NOW,
    )

    budget.acquire()

    rendered = "\n".join(connection.sql)
    assert "VALUES (%s, 'quantlab_context', 1, %s)" in rendered
    client_source = inspect.getsource(QuantLabApiFootballClient._get)
    assert 'provider_request_category("quantlab_context")' in client_source


def test_quantlab_budget_uses_shared_75k_provider_envelope_without_local_cap() -> None:
    budget = QuantLabRequestBudget(
        connect=lambda: _BudgetConnection(),
        clock=lambda: NOW,
    )
    assert budget.daily_limit == DEFAULT_PROVIDER_DAILY_LIMIT == 75_000
    assert budget.shared_daily_limit == 75_000
    assert budget.production_reserve == 0


def test_quantlab_budget_stops_only_at_shared_provider_capacity() -> None:
    connection = _BudgetConnection({"discovery": 74_999})
    budget = QuantLabRequestBudget(
        connect=lambda: connection,
        clock=lambda: NOW,
        shared_daily_limit=75_000,
        production_reserve=0,
    )

    budget.acquire()
    connection.usage["discovery"] = 75_000
    with pytest.raises(ApiBudgetExceededError, match="shared football API budget"):
        budget.acquire()


def test_scope_blocks_waste_before_fixture_specific_calls() -> None:
    for country, competition in (
        ("England", "Premier League"),
        ("Scotland", "Premiership"),
        ("England", "Championship"),
        ("Poland", "Ekstraklasa"),
        ("World", "UEFA Champions League"),
        ("Sweden", "Division 2 - Norrland"),
        ("Japan", "J1 League"),
    ):
        decision = card_corner_scope(country=country, competition_name=competition)
        assert decision.allowed
        assert decision.reason == "market_driven_candidate"

    assert goal_scope(country="Poland", competition_name="III Liga").allowed
    assert not goal_scope(
        country="England",
        competition_name="Premier League U20",
    ).allowed
    assert not goal_scope(
        country="Egypt",
        competition_name="Premier League",
    ).allowed
    assert not goal_scope(
        country="Japan",
        competition_name="J1 League",
    ).allowed


def test_referee_rates_exclude_target_and_future_rows() -> None:
    history = (
        {
            "referee": "Ref A",
            "kickoff_at": NOW - timedelta(days=7),
            "available_at": NOW - timedelta(days=6),
            "yellow_cards": 4,
            "red_cards": 0,
            "second_yellow_cards": None,
            "fouls": 23,
        },
        {
            "referee": "Ref A",
            "kickoff_at": NOW,
            "available_at": NOW,
            "yellow_cards": 8,
            "red_cards": 1,
            "second_yellow_cards": 1,
            "fouls": 40,
        },
        {
            "referee": "Ref A",
            "kickoff_at": NOW - timedelta(days=10),
            "available_at": NOW + timedelta(seconds=1),
            "yellow_cards": 9,
            "red_cards": 1,
            "second_yellow_cards": None,
            "fouls": 50,
        },
    )

    cards, fouls, card_n, foul_n = referee_rates(
        history,
        referee="Ref A",
        decision_at=NOW,
    )

    assert cards.value == 4
    assert fouls.value == 23
    assert card_n == 1
    assert foul_n == 1
    assert cards.quality == "SMALL_SAMPLE"


def _standings_payload(team_points=70):
    rows = []
    points = [80, 75, 72, 70, 65, 60, 55, 50, 45, 40]
    points[3] = team_points
    for rank, value in enumerate(points, start=1):
        rows.append(
            {
                "rank": rank,
                "points": value,
                "team": {"id": 100 + rank},
                "all": {"played": 25},
            }
        )
    return {"response": [{"league": {"standings": [rows]}}]}


def test_table_pressure_uses_distance_to_threshold_and_rejects_future_snapshot() -> None:
    payload = _standings_payload(team_points=70)
    pressure = table_pressure(
        payload,
        team_id=104,
        competition_name="Premier League",
        available_at=NOW - timedelta(minutes=2),
        decision_at=NOW,
    )

    assert pressure.version == TABLE_PRESSURE_VERSION
    assert pressure.value == 1.0
    assert pressure.components["continental"]["points_gap"] == 0

    with pytest.raises(FeatureLeakageError):
        table_pressure(
            payload,
            team_id=104,
            competition_name="Premier League",
            available_at=NOW + timedelta(seconds=1),
            decision_at=NOW,
        )


def test_rivalry_registry_is_deterministic_and_unknown_is_not_false() -> None:
    first = rivalry_indicator("Arsenal", "Tottenham")
    second = rivalry_indicator("Tottenham", "Arsenal")
    unknown = rivalry_indicator("Example FC", "Another FC")

    assert first == second
    assert first.value == 1
    assert first.version == RIVALRY_REGISTRY_VERSION
    assert unknown.value is None
    assert unknown.quality == "UNKNOWN_COVERAGE"


def test_match_importance_is_deterministic_and_versioned() -> None:
    home = FeatureDatum(
        0.8,
        "test",
        NOW - timedelta(minutes=5),
        "P",
        "OBSERVED",
        {},
    )
    away = FeatureDatum(
        0.5,
        "test",
        NOW - timedelta(minutes=5),
        "P",
        "OBSERVED",
        {},
    )
    derby = FeatureDatum(
        1,
        "test",
        NOW - timedelta(minutes=5),
        "R",
        "OBSERVED",
        {},
    )

    arguments = {
        "home_pressure": home,
        "away_pressure": away,
        "derby": derby,
        "stage": 0.75,
        "competition_name": "Premier League",
        "decision_at": NOW,
    }
    a = match_importance(**arguments)
    b = match_importance(**arguments)

    assert a == b
    assert a.version == MATCH_IMPORTANCE_VERSION
    assert a.value is not None
    assert 0 <= float(a.value) <= 1


class _DashboardRepo:
    def list_bets(self, lab):
        return ()

    def api_usage_today(self):
        return 12

    def list_card_features(self):
        return (
            {
                "fixture_id": "api-football:42",
                "home_team": "Arsenal",
                "away_team": "Tottenham",
                "competition_name": "Premier League",
                "kickoff_at": NOW + timedelta(hours=3),
                "referee": "Ref A",
                "referee_card_rate": 4.25,
                "referee_sample_size": 8,
                "referee_foul_rate": 22.5,
                "referee_foul_sample_size": 8,
                "derby_rivalry_indicator": 1,
                "home_table_pressure": 0.8,
                "away_table_pressure": 0.7,
                "match_importance": 0.81,
                "available_at": NOW,
                "feature_version": "CARDLAB_FEATURES_V1",
                "feature_payload": {
                    "referee_card_rate": {
                        "source": "quantlab_completed_fixture_statistics",
                        "version": "CARD_COUNT_RULE_V1",
                        "available_at": NOW.isoformat(),
                    },
                    "match_importance": {
                        "source": "derived:cardlab_context",
                        "version": "MATCH_IMPORTANCE_V1",
                        "available_at": NOW.isoformat(),
                    },
                },
            },
        )


def test_cardlab_dashboard_displays_feature_values_and_provenance() -> None:
    html = QuantLabDashboardService(_DashboardRepo()).render_html("lab=card")

    assert "CardLab v1 context snapshots" in html
    assert "Ref A" in html
    assert "4.25" in html
    assert "n=8" in html
    assert "MATCH_IMPORTANCE_V1" in html
    assert "quantlab_completed_fixture_statistics" in html
    assert "CARDLAB_FEATURES_V1" in html


def test_global_discovery_is_independent_from_production_scope() -> None:
    payload = {
        "response": [
            _fixture_payload(1, 1001, "III Liga", "Poland"),
            _fixture_payload(2, 98, "J1 League", "Japan"),
            _fixture_payload(3, 1002, "Premier League U20", "England"),
        ]
    }

    rows = parse_fixture_discovery_response(payload, captured_at=NOW)

    assert [row.fixture.fixture_id for row in rows] == [
        "api-football:1",
        "api-football:2",
        "api-football:3",
    ]
    assert rows[0].fixture.competition_name == "III Liga"
    assert rows[1].fixture.country == "Japan"


def test_runtime_scans_global_discovery_for_market_driven_card_corner_research() -> None:
    class Provider:
        def __init__(self):
            self.date_calls = []
            self.odds_calls = []

        def fetch_fixtures_for_date(self, fixture_date):
            self.date_calls.append(fixture_date)
            return {
                "response": [
                    _fixture_payload(1, 1001, "III Liga", "Poland"),
                    _fixture_payload(2, 98, "J1 League", "Japan"),
                    _fixture_payload(3, 1002, "Premier League U20", "England"),
                ]
            }

        def fetch_odds(self, fixture_id):
            self.odds_calls.append(fixture_id)
            return {
                "response": [
                    {
                        "fixture": {"id": fixture_id},
                        "bookmakers": [],
                    }
                ]
            }

    class Repo:
        def __init__(self):
            self.observations = ()
            self.saved_markets = ()

        def fixture_discovery_due(self, *_args, **_kwargs):
            return True

        def save_fixture_discovery(self, *, observations, **_kwargs):
            self.observations = tuple(observations)
            return len(self.observations)

        def completed_for_context_backfill(self, **_kwargs):
            return ()

        def upcoming_fixtures(self, **_kwargs):
            rows = []
            for item in self.observations:
                fixture = item.fixture
                rows.append(
                    {
                        "fixture_id": fixture.fixture_id,
                        "provider_fixture_id": int(fixture.provider_fixture_id),
                        "league_id": fixture.competition_id,
                        "season": fixture.season,
                        "home_team_id": fixture.provider_home_team_id,
                        "away_team_id": fixture.provider_away_team_id,
                        "home_team": fixture.home_team,
                        "away_team": fixture.away_team,
                        "competition_name": fixture.competition_name,
                        "country": fixture.country,
                        "competition_type": fixture.competition_type,
                        "kickoff_at": fixture.kickoff_at,
                        "provider_status": fixture.status,
                    }
                )
            return tuple(rows)

        def market_capture_due(self, *_args, **_kwargs):
            return True

        def save_market_observations(self, observations):
            self.saved_markets = tuple(observations)

        def save_market_capture(self, **_kwargs):
            return None

        def market_labs_for_fixture(self, _fixture_id):
            return frozenset()

    provider = Provider()
    repo = Repo()
    runtime = QuantLabRuntime(
        repo,
        provider,
        settings=QuantLabRuntimeSettings(
            lookahead_hours=1,
            discovery_lookback_days=0,
            history_backfill_per_cycle=0,
        ),
        clock=lambda: NOW,
    )

    result = runtime.run_once()

    assert result["fixtures_discovered"] == 3
    assert result["market_fixtures"] == 3
    assert provider.date_calls == [NOW.date()]
    assert provider.odds_calls == [1, 2, 3]
    assert {item.fixture.competition_name for item in repo.observations} == {
        "III Liga",
        "J1 League",
        "Premier League U20",
    }


def test_fixture_discovery_repository_writes_only_quantlab_tables() -> None:
    source = inspect.getsource(PostgreSQLQuantLabRepository.save_fixture_discovery)

    assert "INSERT INTO quantlab_fixtures" in source
    assert "INSERT INTO quantlab_fixture_observations" in source
    assert "INSERT INTO quantlab_fixture_discovery_shards" in source
    assert "INSERT INTO fixtures " not in source


def test_market_capture_watermark_is_persistent_even_without_market_rows() -> None:
    due_source = inspect.getsource(PostgreSQLQuantLabRepository.market_capture_due)
    save_source = inspect.getsource(PostgreSQLQuantLabRepository.save_market_capture)

    assert "quantlab_market_captures" in due_source
    assert "quantlab_market_observations" in due_source
    assert "INSERT INTO quantlab_market_captures" in save_source


def test_runtime_defaults_use_expanded_research_budget() -> None:
    settings = QuantLabRuntimeSettings()
    assert settings.market_refresh_seconds == 3600
    assert settings.standings_refresh_seconds == 21600
    assert settings.history_backfill_per_cycle == 25


def test_goal_scope_rejects_broader_youth_aliases_and_far_east_aliases() -> None:
    assert not goal_scope(
        country="England",
        competition_name="Premier League U12",
    ).allowed
    assert not goal_scope(
        country="Korea Republic",
        competition_name="K League 1",
    ).allowed


def test_history_backfill_skips_malformed_fixture_and_continues() -> None:
    malformed = {
        "fixture_id": "api-football:bad-history",
        "provider_fixture_id": 9001,
        "home_team_id": None,
        "away_team_id": 22,
    }
    valid = {
        "fixture_id": "api-football:good-history",
        "provider_fixture_id": 9002,
        "home_team_id": 31,
        "away_team_id": 32,
    }

    class Repo:
        def completed_for_context_backfill(self, **_kwargs):
            return (malformed, valid)

        def latest_context_before(self, fixture_id, **_kwargs):
            if fixture_id == "api-football:good-history":
                return {"referee": None}
            return None

        def statistics_exists(self, fixture_id):
            return fixture_id == "api-football:good-history"

    class Provider:
        def fetch_fixture(self, _fixture_id):
            raise AssertionError("malformed fixture must fail before provider access")

        def fetch_statistics(self, _fixture_id):
            raise AssertionError("existing statistics must not be refetched")

    runtime = QuantLabRuntime(
        Repo(),
        Provider(),
        settings=QuantLabRuntimeSettings(history_backfill_per_cycle=1),
        clock=lambda: NOW,
    )

    assert runtime._backfill_history(NOW) == 1


def test_upcoming_collection_isolates_bad_fixture_and_scans_next_fixture() -> None:
    bad = {
        "fixture_id": "api-football:bad-upcoming",
        "provider_fixture_id": 7001,
        "league_id": 1,
        "season": 2026,
        "home_team_id": 10,
        "away_team_id": 11,
        "home_team": "Bad Home",
        "away_team": "Bad Away",
        "competition_name": "Example League",
        "country": "Example",
        "competition_type": "League",
        "kickoff_at": NOW + timedelta(hours=2),
        "provider_status": "NS",
    }
    good = {
        **bad,
        "fixture_id": "api-football:good-upcoming",
        "provider_fixture_id": 7002,
        "home_team_id": 12,
        "away_team_id": 13,
        "home_team": "Good Home",
        "away_team": "Good Away",
    }

    class Repo:
        def __init__(self):
            self.captures = []

        def upcoming_fixtures(self, **_kwargs):
            return (bad, good)

        def market_capture_due(self, *_args, **_kwargs):
            return True

        def save_market_observations(self, _rows):
            return 0

        def save_market_capture(self, **kwargs):
            self.captures.append(kwargs)

        def market_labs_for_fixture(self, _fixture_id):
            return frozenset()

    class Provider:
        def __init__(self):
            self.calls = []

        def fetch_odds(self, fixture_id):
            self.calls.append(fixture_id)
            if fixture_id == 7001:
                raise ValueError("malformed provider odds payload")
            return {"response": [{"fixture": {"id": fixture_id}, "bookmakers": []}]}

    provider = Provider()
    repo = Repo()
    runtime = QuantLabRuntime(
        repo,
        provider,
        settings=QuantLabRuntimeSettings(fixture_limit=2),
        clock=lambda: NOW,
    )

    market_fixtures, card_snapshots = runtime._collect_upcoming(NOW)

    assert market_fixtures == 1
    assert card_snapshots == 0
    assert provider.calls == [7001, 7002]
    assert len(repo.captures) == 1
    assert repo.captures[0]["fixture_id"] == "api-football:good-upcoming"
