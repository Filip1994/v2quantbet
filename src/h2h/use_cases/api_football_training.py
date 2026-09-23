"""Trusted API-Football completed-match acquisition and Dixon-Coles fitting."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

from h2h.domain.fixture_identity import (
    API_FOOTBALL_PROVIDER,
    ResolvedFixtureIdentity,
    api_football_fixture_identity,
    api_football_provider_fixture_id,
)
from h2h.odds.api_football_client import ApiFootballClient
from h2h.quant.dixon_coles import DixonColesModel


FT_STATUS: Final = "FT"
FT_SCORE_SEMANTIC: Final = (
    "goals=score.fulltime;extratime.home/away=null;penalty.home/away=null"
)
_DATASET_PROVENANCE = object()
_ACQUISITION_AUTHORITY = object()


@dataclass(frozen=True, slots=True)
class ApiFootballTrainingScope:
    """One explicit API-Football league, season and half-open UTC window."""

    league_id: int
    season: int
    start_at: datetime
    end_at: datetime

    def __post_init__(self) -> None:
        _positive_int(self.league_id, "league_id")
        _positive_int(self.season, "season")
        start = _aware_datetime(self.start_at, "start_at")
        end = _aware_datetime(self.end_at, "end_at")
        if start >= end:
            raise ValueError("start_at must be before end_at")
        object.__setattr__(self, "start_at", start)
        object.__setattr__(self, "end_at", end)


@dataclass(frozen=True, slots=True)
class ApiFootballCompletedMatch:
    """One strictly normalized ordinary-full-time API-Football result."""

    fixture_identity: ResolvedFixtureIdentity
    date: datetime
    home_id: int
    away_id: int
    home_goals: int
    away_goals: int
    league_id: int
    season: int
    status: str
    score_semantic: str

    @property
    def provider_fixture_id(self) -> int:
        return api_football_provider_fixture_id(self.fixture_identity)


@dataclass(frozen=True, slots=True, init=False)
class ApiFootballTrainingDataset:
    """Immutable provider-proven records; construction is acquisition-internal."""

    _records: tuple[ApiFootballCompletedMatch, ...]
    _provenance: object

    def __init__(
        self,
        records: Sequence[ApiFootballCompletedMatch],
        *,
        _provenance: object | None = None,
    ) -> None:
        if _provenance is not _DATASET_PROVENANCE:
            raise TypeError("ApiFootballTrainingDataset is created only by trusted acquisition")
        object.__setattr__(self, "_records", tuple(records))
        object.__setattr__(self, "_provenance", _provenance)

    @property
    def records(self) -> tuple[ApiFootballCompletedMatch, ...]:
        return self._records

    @property
    def team_id_namespace(self) -> str:
        return API_FOOTBALL_PROVIDER

    def __len__(self) -> int:
        return len(self._records)

    def __iter__(self) -> Iterator[ApiFootballCompletedMatch]:
        return iter(self._records)


def _is_trusted_api_football_training_dataset(value: object) -> bool:
    """Internal authority check shared with production artifact orchestration."""
    return type(value) is ApiFootballTrainingDataset and value._provenance is _DATASET_PROVENANCE


class ApiFootballCompletedMatchAdapter:
    """Normalize one provider fixture under the conservative FT score contract."""

    def adapt(
        self,
        payload: Mapping[str, Any],
        *,
        scope: ApiFootballTrainingScope,
    ) -> ApiFootballCompletedMatch:
        if not isinstance(payload, Mapping):
            raise TypeError("API-Football fixture item must be an object")
        fixture = _mapping(payload, "fixture")
        league = _mapping(payload, "league")
        teams = _mapping(payload, "teams")
        goals = _mapping(payload, "goals")
        score = _mapping(payload, "score")

        fixture_id = _positive_int(fixture.get("id"), "fixture.id")
        identity = api_football_fixture_identity(fixture_id)
        kickoff = _provider_datetime(fixture.get("date"), "fixture.date")
        status = _mapping(fixture, "status").get("short")
        if status != FT_STATUS:
            raise ValueError("fixture.status.short must be exactly FT")

        league_id = _positive_int(league.get("id"), "league.id")
        season = _positive_int(league.get("season"), "league.season")
        if league_id != scope.league_id:
            raise ValueError("returned league.id does not match the requested scope")
        if season != scope.season:
            raise ValueError("returned league.season does not match the requested scope")

        home = _mapping(teams, "home")
        away = _mapping(teams, "away")
        home_id = _positive_int(home.get("id"), "teams.home.id")
        away_id = _positive_int(away.get("id"), "teams.away.id")
        if home_id == away_id:
            raise ValueError("home and away team IDs must be distinct")

        home_goals = _nonnegative_int(goals.get("home"), "goals.home")
        away_goals = _nonnegative_int(goals.get("away"), "goals.away")
        fulltime = _mapping(score, "fulltime")
        fulltime_home = _nonnegative_int(fulltime.get("home"), "score.fulltime.home")
        fulltime_away = _nonnegative_int(fulltime.get("away"), "score.fulltime.away")
        if (home_goals, away_goals) != (fulltime_home, fulltime_away):
            raise ValueError("goals and score.fulltime must agree for an FT fixture")
        for period in ("extratime", "penalty"):
            period_score = _mapping(score, period)
            if "home" not in period_score or "away" not in period_score:
                raise ValueError(f"score.{period} must contain home and away")
            if period_score["home"] is not None or period_score["away"] is not None:
                raise ValueError(f"score.{period} home and away must be null for FT training")

        return ApiFootballCompletedMatch(
            fixture_identity=identity,
            date=kickoff,
            home_id=home_id,
            away_id=away_id,
            home_goals=home_goals,
            away_goals=away_goals,
            league_id=league_id,
            season=season,
            status=FT_STATUS,
            score_semantic=FT_SCORE_SEMANTIC,
        )


@dataclass(frozen=True, slots=True, init=False)
class ApiFootballHistoricalResults:
    """Production-bound acquisition authorized to mint trusted datasets."""

    _fetch_completed_fixtures: Callable[..., Mapping[str, Any]]
    _load_cached_payload: Callable[..., Mapping[str, Any] | None] | None
    _save_cached_payload: Callable[..., None] | None
    _clock: Callable[[], datetime]
    _authority: object

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError(
            "ApiFootballHistoricalResults is created only by "
            "build_trusted_api_football_historical_results()"
        )

    def acquire(self, scope: ApiFootballTrainingScope) -> ApiFootballTrainingDataset:
        if type(self) is not ApiFootballHistoricalResults or (
            self._authority is not _ACQUISITION_AUTHORITY
        ):
            raise TypeError("historical results service must come from trusted production construction")
        if not isinstance(scope, ApiFootballTrainingScope):
            raise TypeError("scope must be an ApiFootballTrainingScope")
        payload = None
        if self._load_cached_payload is not None:
            payload = self._load_cached_payload(
                league_id=scope.league_id,
                season=scope.season,
                start_at=scope.start_at,
                end_at=scope.end_at,
            )
        if payload is None:
            payload = self._fetch_completed_fixtures(
                league_id=scope.league_id,
                season=scope.season,
                start_at=scope.start_at,
                end_at=scope.end_at,
            )
        records = normalize_api_football_historical_response(payload, scope=scope)
        if self._load_cached_payload is not None and self._save_cached_payload is not None:
            # An already cached payload is never written again. A strict successful
            # normalization is required before provider bytes become durable cache data.
            cached = self._load_cached_payload(
                league_id=scope.league_id,
                season=scope.season,
                start_at=scope.start_at,
                end_at=scope.end_at,
            )
            if cached is None:
                self._save_cached_payload(
                    league_id=scope.league_id,
                    season=scope.season,
                    start_at=scope.start_at,
                    end_at=scope.end_at,
                    payload=payload,
                    accepted_match_count=len(records),
                    acquired_at=self._clock(),
                )
        return ApiFootballTrainingDataset(records, _provenance=_DATASET_PROVENANCE)


def normalize_api_football_historical_response(
    payload: Mapping[str, Any],
    *,
    scope: ApiFootballTrainingScope,
) -> tuple[ApiFootballCompletedMatch, ...]:
    """Strictly validate provider-shaped data without granting trusted provenance."""
    if not isinstance(scope, ApiFootballTrainingScope):
        raise TypeError("scope must be an ApiFootballTrainingScope")
    response = _complete_response(payload)
    adapter = ApiFootballCompletedMatchAdapter()

    normalized: dict[str, ApiFootballCompletedMatch] = {}
    for item in response:
        record = adapter.adapt(item, scope=scope)
        fixture_id = record.fixture_identity.fixture_id
        previous = normalized.get(fixture_id)
        if previous is None:
            normalized[fixture_id] = record
        elif previous != record:
            raise ValueError(f"conflicting duplicate API-Football fixture: {fixture_id}")

    in_scope = (
        record for record in normalized.values() if scope.start_at <= record.date < scope.end_at
    )
    return tuple(sorted(in_scope, key=lambda item: (item.date, item.provider_fixture_id)))


def _trusted_api_football_historical_results(
    client: ApiFootballClient,
    *,
    load_cached_payload: Callable[..., Mapping[str, Any] | None] | None = None,
    save_cached_payload: Callable[..., None] | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> ApiFootballHistoricalResults:
    """Internal composition hook; only the production factory may call this."""
    if not isinstance(client, ApiFootballClient):
        raise TypeError("client must be an ApiFootballClient")
    service = object.__new__(ApiFootballHistoricalResults)
    object.__setattr__(service, "_fetch_completed_fixtures", client.fetch_completed_fixtures)
    object.__setattr__(service, "_load_cached_payload", load_cached_payload)
    object.__setattr__(service, "_save_cached_payload", save_cached_payload)
    object.__setattr__(service, "_clock", clock)
    object.__setattr__(service, "_authority", _ACQUISITION_AUTHORITY)
    return service


def fit_api_football_dixon_coles(
    dataset: ApiFootballTrainingDataset,
    *,
    reference_time: datetime,
    xi: float,
    ridge: float = 0.01,
    min_matches: int = 80,
    should_abort: Callable[[], bool] | None = None,
) -> DixonColesModel:
    """Fit Dixon-Coles with the namespace proven by trusted acquisition."""
    if not _is_trusted_api_football_training_dataset(dataset):
        raise TypeError("dataset must come from trusted API-Football acquisition")
    return DixonColesModel.fit(
        list(dataset.records),
        team_id_namespace=dataset.team_id_namespace,
        reference_time=reference_time,
        xi=xi,
        ridge=ridge,
        min_matches=min_matches,
        should_abort=should_abort,
    )


def _complete_response(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    if not isinstance(payload, Mapping):
        raise TypeError("API-Football fixtures response must be an object")
    if "errors" not in payload:
        raise ValueError("API-Football response is missing errors")
    errors = payload["errors"]
    if not isinstance(errors, (list, Mapping)):
        raise TypeError("API-Football errors must be an array or object")
    if errors:
        raise RuntimeError(f"API-Football returned errors: {errors}")

    response = payload.get("response")
    if not isinstance(response, list):
        raise TypeError("API-Football response must be a list")
    results = _nonnegative_int(payload.get("results"), "results")
    if results != len(response):
        raise ValueError("API-Football results count does not match response length")

    paging = _mapping(payload, "paging")
    current = _positive_int(paging.get("current"), "paging.current")
    total = _positive_int(paging.get("total"), "paging.total")
    if current != 1 or total != 1:
        raise ValueError("API-Football fixtures response is incomplete or paged")
    return response


def _mapping(value: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    nested = value.get(key)
    if not isinstance(nested, Mapping):
        raise TypeError(f"{key} must be an object")
    return nested


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _aware_datetime(value: Any, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _provider_datetime(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty ISO datetime string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid ISO datetime string") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone offset")
    return parsed.astimezone(UTC)
