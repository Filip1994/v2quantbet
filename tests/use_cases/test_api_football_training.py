from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest

from h2h.application import build_trusted_api_football_historical_results
from h2h.config import ApplicationSettings
from h2h.domain.fixture import Fixture
from h2h.domain.fixture_identity import api_football_fixture_identity
from h2h.odds.api_football_client import ApiFootballClient
from h2h.odds.http import UrllibJsonTransport
from h2h.quant.dixon_coles import DixonColesModel
from h2h.use_cases.api_football_training import (
    FT_SCORE_SEMANTIC,
    ApiFootballHistoricalResults,
    ApiFootballTrainingDataset,
    ApiFootballTrainingScope,
    fit_api_football_dixon_coles,
    normalize_api_football_historical_response,
    _trusted_api_football_historical_results,
)
from h2h.use_cases.fixture_prediction import DixonColesFixturePredictor


START = datetime(2025, 1, 1, tzinfo=UTC)
END = datetime(2025, 2, 1, tzinfo=UTC)


def scope(**changes: object) -> ApiFootballTrainingScope:
    values = {"league_id": 39, "season": 2024, "start_at": START, "end_at": END}
    values.update(changes)
    return ApiFootballTrainingScope(**values)  # type: ignore[arg-type]


def item(
    fixture_id: int = 101,
    *,
    date: str = "2025-01-10T15:00:00+00:00",
    home_id: int = 1,
    away_id: int = 2,
    home_goals: int = 2,
    away_goals: int = 1,
) -> dict[str, object]:
    return {
        "fixture": {"id": fixture_id, "date": date, "status": {"short": "FT"}},
        "league": {"id": 39, "season": 2024},
        "teams": {"home": {"id": home_id}, "away": {"id": away_id}},
        "goals": {"home": home_goals, "away": away_goals},
        "score": {
            "halftime": {"home": 1, "away": 0},
            "fulltime": {"home": home_goals, "away": away_goals},
            "extratime": {"home": None, "away": None},
            "penalty": {"home": None, "away": None},
        },
    }


def envelope(items: list[object] | None = None, **changes: object) -> dict[str, object]:
    response = [] if items is None else items
    payload: dict[str, object] = {
        "errors": [],
        "results": len(response),
        "paging": {"current": 1, "total": 1},
        "response": response,
    }
    payload.update(changes)
    return payload


def normalize(
    payload: object,
    requested_scope: ApiFootballTrainingScope | None = None,
):
    return normalize_api_football_historical_response(
        payload,  # type: ignore[arg-type]
        scope=requested_scope or scope(),
    )


def trusted_acquire(
    payload: object,
    requested_scope: ApiFootballTrainingScope | None = None,
):
    settings = ApplicationSettings(database_path="unused.sqlite3", api_football_key="secret")
    with patch.object(UrllibJsonTransport, "get_json", return_value=payload):
        service = build_trusted_api_football_historical_results(settings)
        return service.acquire(requested_scope or scope())


def test_completed_historical_acquisition_is_reused_after_service_restart() -> None:
    transport = Mock()
    transport.get_json.return_value = envelope([item()])
    client = ApiFootballClient(transport=transport, api_key="secret")
    cache: dict[tuple[object, ...], object] = {}

    def key(values):
        return (
            values["league_id"],
            values["season"],
            values["start_at"],
            values["end_at"],
        )

    def load(**values):
        return cache.get(key(values))

    def save(**values):
        cache[key(values)] = values["payload"]

    first = _trusted_api_football_historical_results(
        client,
        load_cached_payload=load,
        save_cached_payload=save,
        clock=lambda: END,
    )
    assert len(first.acquire(scope())) == 1

    restarted = _trusted_api_football_historical_results(
        client,
        load_cached_payload=load,
        save_cached_payload=save,
        clock=lambda: END,
    )
    assert len(restarted.acquire(scope())) == 1
    assert transport.get_json.call_count == 1


def test_valid_ft_fixture_preserves_identity_order_score_and_utc() -> None:
    records = normalize(envelope([item(date="2025-01-10T16:00:00+01:00")]))

    assert len(records) == 1
    record = records[0]
    assert record.fixture_identity == api_football_fixture_identity(101)
    assert record.provider_fixture_id == 101
    assert (record.home_id, record.away_id) == (1, 2)
    assert (record.home_goals, record.away_goals) == (2, 1)
    assert record.date == datetime(2025, 1, 10, 15, tzinfo=UTC)
    assert record.status == "FT"
    assert record.score_semantic == FT_SCORE_SEMANTIC


def test_zero_goals_are_valid() -> None:
    record = normalize(envelope([item(home_goals=0, away_goals=0)]))[0]
    assert (record.home_goals, record.away_goals) == (0, 0)


@pytest.mark.parametrize("value", [0, -1, True, 1.0, "1"])
@pytest.mark.parametrize("path", [("fixture", "id"), ("teams", "home", "id"), ("teams", "away", "id")])
def test_fixture_and_team_ids_must_be_positive_non_boolean_integers(
    path: tuple[str, ...], value: object
) -> None:
    payload = item()
    target = payload
    for key in path[:-1]:
        target = target[key]  # type: ignore[index,assignment]
    target[path[-1]] = value  # type: ignore[index]
    with pytest.raises(ValueError, match="positive integer"):
        normalize(envelope([payload]))


def test_missing_team_id_is_rejected() -> None:
    payload = item()
    del payload["teams"]["home"]["id"]  # type: ignore[index]
    with pytest.raises(ValueError, match="teams.home.id"):
        normalize(envelope([payload]))


def test_same_team_is_rejected() -> None:
    with pytest.raises(ValueError, match="distinct"):
        normalize(envelope([item(home_id=4, away_id=4)]))


@pytest.mark.parametrize("value", [None, -1, True, "2", 2.0, 1.5])
@pytest.mark.parametrize("side", ["home", "away"])
def test_goals_require_explicit_nonnegative_integers(side: str, value: object) -> None:
    payload = item()
    payload["goals"][side] = value  # type: ignore[index]
    payload["score"]["fulltime"][side] = value  # type: ignore[index]
    with pytest.raises(ValueError, match="non-negative integer"):
        normalize(envelope([payload]))


@pytest.mark.parametrize("date", [None, "", "not-a-date", "2025-01-10T15:00:00"])
def test_kickoff_must_be_valid_and_timezone_aware(date: object) -> None:
    payload = item()
    payload["fixture"]["date"] = date  # type: ignore[index]
    with pytest.raises((TypeError, ValueError), match="fixture.date"):
        normalize(envelope([payload]))


@pytest.mark.parametrize("status", ["AET", "PEN", "NS", "2H", "CANC", "AWD", None])
def test_only_exact_ft_status_is_accepted(status: object) -> None:
    payload = item()
    payload["fixture"]["status"]["short"] = status  # type: ignore[index]
    with pytest.raises(ValueError, match="exactly FT"):
        normalize(envelope([payload]))


def test_contradictory_fulltime_score_is_rejected() -> None:
    payload = item()
    payload["score"]["fulltime"]["home"] = 3  # type: ignore[index]
    with pytest.raises(ValueError, match="must agree"):
        normalize(envelope([payload]))


@pytest.mark.parametrize("period", ["extratime", "penalty"])
def test_extra_time_and_shootout_scores_cannot_enter_training(period: str) -> None:
    payload = item()
    payload["score"][period] = {"home": 1, "away": 0}  # type: ignore[index]
    with pytest.raises(ValueError, match=period):
        normalize(envelope([payload]))


@pytest.mark.parametrize("period", ["extratime", "penalty"])
def test_missing_extra_time_or_shootout_evidence_is_rejected(period: str) -> None:
    payload = item()
    del payload["score"][period]  # type: ignore[index]
    with pytest.raises((TypeError, ValueError), match=period):
        normalize(envelope([payload]))


@pytest.mark.parametrize("period", ["extratime", "penalty"])
def test_incomplete_extra_time_or_shootout_evidence_is_rejected(period: str) -> None:
    payload = item()
    del payload["score"][period]["away"]  # type: ignore[index]
    with pytest.raises(ValueError, match=period):
        normalize(envelope([payload]))


@pytest.mark.parametrize("field,value", [("id", 40), ("season", 2023)])
def test_returned_league_and_season_must_match_scope(field: str, value: int) -> None:
    payload = item()
    payload["league"][field] = value  # type: ignore[index]
    with pytest.raises(ValueError, match="requested scope"):
        normalize(envelope([payload]))


@pytest.mark.parametrize("field,value", [("id", True), ("id", 39.0), ("season", "2024")])
def test_returned_league_and_season_require_positive_non_boolean_integers(
    field: str, value: object
) -> None:
    payload = item()
    payload["league"][field] = value  # type: ignore[index]
    with pytest.raises(ValueError, match="positive integer"):
        normalize(envelope([payload]))


def test_scope_is_utc_normalized_and_half_open() -> None:
    offset = timezone(timedelta(hours=2))
    requested = scope(
        start_at=datetime(2025, 1, 1, 2, tzinfo=offset),
        end_at=datetime(2025, 1, 2, 2, tzinfo=offset),
    )
    records = normalize(
        envelope(
            [
                item(1, date="2025-01-01T00:00:00+00:00"),
                item(2, date="2025-01-01T23:59:59+00:00"),
                item(3, date="2025-01-02T00:00:00+00:00"),
                item(4, date="2024-12-31T23:59:59+00:00"),
            ]
        ),
        requested,
    )
    assert requested.start_at == datetime(2025, 1, 1, tzinfo=UTC)
    assert requested.end_at == datetime(2025, 1, 2, tzinfo=UTC)
    assert [record.provider_fixture_id for record in records] == [1, 2]


@pytest.mark.parametrize(
    "changes",
    [
        {"league_id": True},
        {"season": 2024.0},
        {"start_at": START.replace(tzinfo=None)},
        {"end_at": END.replace(tzinfo=None)},
        {"end_at": START},
    ],
)
def test_invalid_scope_is_rejected(changes: dict[str, object]) -> None:
    with pytest.raises((TypeError, ValueError)):
        scope(**changes)


def test_identical_duplicate_collapses_and_order_is_deterministic() -> None:
    late = item(200, date="2025-01-20T15:00:00+00:00")
    early_high_id = item(102, date="2025-01-10T15:00:00+00:00")
    early_low_id = item(101, date="2025-01-10T15:00:00+00:00")
    records = normalize(envelope([late, early_high_id, deepcopy(early_low_id), early_low_id]))
    assert [record.provider_fixture_id for record in records] == [101, 102, 200]


def test_conflicting_duplicate_aborts_acquisition() -> None:
    first = item()
    conflict = item(home_goals=3)
    with pytest.raises(ValueError, match="conflicting duplicate"):
        normalize(envelope([first, conflict]))


def test_conflicting_duplicate_aborts_even_when_one_version_is_outside_window() -> None:
    outside = item(date="2024-12-31T23:59:59+00:00")
    inside = item(date="2025-01-10T15:00:00+00:00")
    with pytest.raises(ValueError, match="conflicting duplicate"):
        normalize(envelope([outside, inside]))


def test_successful_empty_response_is_an_empty_proven_dataset() -> None:
    dataset = trusted_acquire(envelope())
    assert len(dataset) == 0
    assert dataset.records == ()
    assert dataset.team_id_namespace == "api-football"


@pytest.mark.parametrize(
    "payload,error",
    [
        ({}, ValueError),
        (envelope(errors=["bad request"]), RuntimeError),
        (envelope(response={}), TypeError),
        (envelope([item()], results=0), ValueError),
        (envelope([item()], paging={"current": 1, "total": 2}), ValueError),
        (envelope([item()], paging={"current": 2, "total": 2}), ValueError),
        (envelope([item()], paging={"current": True, "total": 1}), ValueError),
    ],
)
def test_error_malformed_and_incomplete_envelopes_never_return_a_dataset(
    payload: object, error: type[Exception]
) -> None:
    with pytest.raises(error):
        normalize(payload)


def test_transport_failure_is_not_confused_with_empty_success() -> None:
    settings = ApplicationSettings(database_path="unused.sqlite3", api_football_key="secret")
    with patch.object(UrllibJsonTransport, "get_json", side_effect=OSError("network down")):
        service = build_trusted_api_football_historical_results(settings)
        with pytest.raises(OSError, match="network down"):
            service.acquire(scope())


def test_injected_general_client_cannot_mint_trusted_training_provenance() -> None:
    transport = Mock()
    transport.get_json.return_value = envelope([item()])
    injected_client = ApiFootballClient(
        transport,
        "caller-key",
    )
    replacement_transport = Mock()
    replacement_transport.get_json.return_value = envelope([item()])
    injected_client.transport = replacement_transport
    injected_client.base_url = "https://caller-controlled.example"

    with pytest.raises(TypeError, match="build_trusted_api_football_historical_results"):
        ApiFootballHistoricalResults(injected_client)

    records = normalize(replacement_transport.get_json.return_value)
    with pytest.raises(TypeError, match="trusted API-Football acquisition"):
        fit_api_football_dixon_coles(
            records,  # type: ignore[arg-type]
            reference_time=END,
            xi=0.001,
            min_matches=1,
        )


def test_trusted_factory_fixes_endpoint_and_hides_mutable_client_configuration() -> None:
    settings = ApplicationSettings(database_path="unused.sqlite3", api_football_key="secret")
    with patch.object(
        UrllibJsonTransport,
        "get_json",
        return_value=envelope(),
    ) as get_json:
        service = build_trusted_api_football_historical_results(settings)
        dataset = service.acquire(scope())

    assert dataset.records == ()
    get_json.assert_called_once_with(
        "https://v3.football.api-sports.io/fixtures?"
        "league=39&season=2024&from=2025-01-01&to=2025-02-01&status=FT&timezone=UTC",
        headers={"x-apisports-key": "secret"},
        timeout=10.0,
    )
    for public_name in ("client", "transport", "base_url"):
        with pytest.raises(AttributeError):
            getattr(service, public_name)
        with pytest.raises((AttributeError, FrozenInstanceError, TypeError)):
            setattr(service, public_name, object())
    with pytest.raises(FrozenInstanceError):
        service._fetch_completed_fixtures = Mock()  # type: ignore[misc]


@pytest.mark.parametrize(
    "parameter",
    ["transport", "base_url", "adapter", "normalizer", "loader", "token"],
)
def test_trusted_factory_has_no_provenance_critical_injection_parameters(
    parameter: str,
) -> None:
    settings = ApplicationSettings(database_path="unused.sqlite3", api_football_key="secret")
    with pytest.raises(TypeError, match="unexpected keyword"):
        build_trusted_api_football_historical_results(  # type: ignore[call-arg]
            settings,
            **{parameter: object()},
        )


def test_subclass_cannot_reuse_trusted_acquire_method_to_mint_provenance() -> None:
    class CallerSubclass(ApiFootballHistoricalResults):
        def __init__(self) -> None:
            pass

    with pytest.raises(TypeError, match="trusted production construction"):
        CallerSubclass().acquire(scope())


def test_dataset_cannot_be_caller_constructed_or_relabelled() -> None:
    with pytest.raises(TypeError, match="trusted acquisition"):
        ApiFootballTrainingDataset(())
    dataset = trusted_acquire(envelope())
    with pytest.raises((AttributeError, TypeError)):
        dataset.team_id_namespace = "other"  # type: ignore[misc]


def test_fitting_bridge_derives_namespace_and_forwards_configuration() -> None:
    dataset = trusted_acquire(envelope([item()]))
    expected = Mock(spec=DixonColesModel)
    reference = datetime(2025, 3, 1, tzinfo=UTC)
    with patch.object(DixonColesModel, "fit", return_value=expected) as fit:
        result = fit_api_football_dixon_coles(
            dataset,
            reference_time=reference,
            xi=0.001,
            ridge=0.02,
            min_matches=1,
        )
    assert result is expected
    fit.assert_called_once_with(
        list(dataset.records),
        team_id_namespace="api-football",
        reference_time=reference,
        xi=0.001,
        ridge=0.02,
        min_matches=1,
        should_abort=None,
    )
    with pytest.raises(TypeError, match="unexpected keyword"):
        fit_api_football_dixon_coles(
            dataset,
            reference_time=reference,
            xi=0.001,
            team_id_namespace="caller-choice",  # type: ignore[call-arg]
        )


def test_real_fitted_model_is_compatible_with_api_football_fixture_predictor() -> None:
    fixtures = []
    teams = (1, 2, 3, 4)
    for index in range(24):
        home = teams[index % 4]
        away = teams[(index + 1 + (index // 4)) % 4]
        if home == away:
            away = teams[(teams.index(away) + 1) % 4]
        fixtures.append(
            item(
                1000 + index,
                date=f"2025-01-{index + 1:02d}T15:00:00+00:00",
                home_id=home,
                away_id=away,
                home_goals=index % 3,
                away_goals=(index + 1) % 2,
            )
        )
    dataset = trusted_acquire(envelope(fixtures))
    model = fit_api_football_dixon_coles(
        dataset,
        reference_time=END,
        xi=0.001,
        min_matches=20,
    )
    fixture = Fixture(
        fixture_id="api-football:9999",
        home_team="Home",
        away_team="Away",
        competition_id=39,
        competition_name="League",
        country="England",
        kickoff_at=datetime(2025, 3, 1, tzinfo=UTC),
        provider="api-football",
        provider_fixture_id="9999",
        provider_home_team_id=1,
        provider_away_team_id=2,
    )
    prediction = DixonColesFixturePredictor(model).predict(fixture)
    assert model.team_id_namespace == "api-football"
    assert prediction.target.home_team_id == 1
    assert prediction.target.away_team_id == 2
