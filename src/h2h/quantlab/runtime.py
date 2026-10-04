"""Independent QuantLab collection/context runtime."""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from h2h.odds.budget import ApiBudgetExceededError
from h2h.quantlab.card_lab.context import (
    parse_fixture_context,
    parse_fixture_contexts_from_fixture_response,
    parse_fixture_statistics,
)
from h2h.quantlab.card_lab.features import FeatureLeakageError, build_cardlab_snapshot
from h2h.quantlab.card_lab.referee import referee_key
from h2h.quantlab.card_lab.referee_web import (
    proactive_web_targets,
    referee_web_league_key,
)
from h2h.quantlab.card_lab.settlement import (
    parse_1xbet_card_events,
    settle_card_shadow_bet,
)
from h2h.quantlab.corner_lab.settlement import settle_corner_shadow_bet
from h2h.quantlab.coverage import (
    parse_fixture_statistics_coverage,
    parse_league_coverage_flags,
)
from h2h.quantlab.fixture_discovery import parse_fixture_discovery_response
from h2h.quantlab.h2h_lab.history import parse_h2h_response
from h2h.quantlab.h2h_lab.settlement import settle_h2h_shadow_bet
from h2h.quantlab.goal_lab.picks import (
    GOAL_RESULT_FINALITY_DELAY_SECONDS,
    GOAL_RESULT_INITIAL_DELAY_SECONDS,
    GOAL_RESULT_POSTPONED_REFRESH_SECONDS,
    GOAL_RESULT_REFRESH_SECONDS,
    settle_goal_pick,
    stable_goal_result_evidence,
)
from h2h.quantlab.market_collector import QuantLabMarketCollector
from h2h.quantlab.scope import card_corner_scope, goal_scope


LOGGER = logging.getLogger("quantbet.quantlab")


def _utc_fixture_time(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("fixture kickoff must be timezone-aware")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class QuantLabRuntimeSettings:
    lookahead_hours: int = 36
    discovery_lookback_days: int = 1
    fixture_limit: int = 1000
    fixture_discovery_refresh_seconds: int = 21600
    market_refresh_seconds: int = 3600
    context_refresh_seconds: int = 21600
    standings_refresh_seconds: int = 21600
    feature_refresh_seconds: int = 1800
    goal_injury_refresh_seconds: int = 14400
    goal_lineup_refresh_seconds: int = 900
    goal_lineup_window_minutes: int = 120
    goal_coach_refresh_seconds: int = 86400
    h2h_refresh_seconds: int = 21600
    history_backfill_per_cycle: int = 25
    goal_team_history_last: int = 15
    goal_team_history_teams_per_cycle: int = 120
    goal_team_statistics_per_cycle: int = 360
    goal_player_history_per_cycle: int = 60
    goal_team_history_refresh_seconds: int = 21600
    corner_team_history_last: int = 12
    corner_team_history_teams_per_cycle: int = 120
    corner_team_statistics_per_cycle: int = 360
    corner_team_history_refresh_seconds: int = 21600
    card_referee_history_target: int = 8
    card_referee_history_lookback_days: int = 1100
    card_referee_prior_seasons: int = 3
    card_referee_history_days_per_cycle: int = 12
    card_referee_history_scopes_per_cycle: int = 24
    card_referee_statistics_per_cycle: int = 128
    card_referee_history_refresh_seconds: int = 604800
    card_referee_statistics_retry_seconds: int = 86400
    card_referee_web_refresh_seconds: int = 21600
    card_referee_web_seasons: int = 3
    league_coverage_refresh_seconds: int = 21600

    def __post_init__(self) -> None:
        for name, value in (
            ("lookahead_hours", self.lookahead_hours),
            ("fixture_limit", self.fixture_limit),
            ("fixture_discovery_refresh_seconds", self.fixture_discovery_refresh_seconds),
            ("market_refresh_seconds", self.market_refresh_seconds),
            ("context_refresh_seconds", self.context_refresh_seconds),
            ("standings_refresh_seconds", self.standings_refresh_seconds),
            ("feature_refresh_seconds", self.feature_refresh_seconds),
            ("goal_injury_refresh_seconds", self.goal_injury_refresh_seconds),
            ("goal_lineup_refresh_seconds", self.goal_lineup_refresh_seconds),
            ("goal_lineup_window_minutes", self.goal_lineup_window_minutes),
            ("goal_coach_refresh_seconds", self.goal_coach_refresh_seconds),
            ("h2h_refresh_seconds", self.h2h_refresh_seconds),
            ("goal_team_history_last", self.goal_team_history_last),
            ("goal_team_history_teams_per_cycle", self.goal_team_history_teams_per_cycle),
            ("goal_team_statistics_per_cycle", self.goal_team_statistics_per_cycle),
            ("goal_player_history_per_cycle", self.goal_player_history_per_cycle),
            ("goal_team_history_refresh_seconds", self.goal_team_history_refresh_seconds),
            ("corner_team_history_last", self.corner_team_history_last),
            ("corner_team_history_teams_per_cycle", self.corner_team_history_teams_per_cycle),
            ("corner_team_statistics_per_cycle", self.corner_team_statistics_per_cycle),
            ("corner_team_history_refresh_seconds", self.corner_team_history_refresh_seconds),
            ("card_referee_history_target", self.card_referee_history_target),
            ("card_referee_history_lookback_days", self.card_referee_history_lookback_days),
            ("card_referee_history_days_per_cycle", self.card_referee_history_days_per_cycle),
            ("card_referee_history_scopes_per_cycle", self.card_referee_history_scopes_per_cycle),
            ("card_referee_statistics_per_cycle", self.card_referee_statistics_per_cycle),
            ("card_referee_history_refresh_seconds", self.card_referee_history_refresh_seconds),
            ("card_referee_statistics_retry_seconds", self.card_referee_statistics_retry_seconds),
            ("card_referee_web_refresh_seconds", self.card_referee_web_refresh_seconds),
            ("card_referee_web_seasons", self.card_referee_web_seasons),
            ("league_coverage_refresh_seconds", self.league_coverage_refresh_seconds),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        for name, value in (
            ("discovery_lookback_days", self.discovery_lookback_days),
            ("history_backfill_per_cycle", self.history_backfill_per_cycle),
            ("card_referee_prior_seasons", self.card_referee_prior_seasons),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be non-negative")


class QuantLabRuntime:
    def __init__(
        self,
        repository: Any,
        provider: Any,
        *,
        settings: QuantLabRuntimeSettings | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        goal_engine: Any | None = None,
        h2h_engine: Any | None = None,
        corner_engine: Any | None = None,
        card_engine: Any | None = None,
        market_archive_writer: Any | None = None,
        referee_web_source: Any | None = None,
    ) -> None:
        self._repository = repository
        self._provider = provider
        self._settings = settings or QuantLabRuntimeSettings()
        self._clock = clock
        self._collector = QuantLabMarketCollector(
            repository,
            provider,
            archive_writer=market_archive_writer,
        )
        self._goal_engine = goal_engine
        self._h2h_engine = h2h_engine
        self._corner_engine = corner_engine
        self._card_engine = card_engine
        self._referee_web_source = referee_web_source

    @staticmethod
    def _scope_kwargs(fixture: dict[str, Any]) -> dict[str, object]:
        return {
            "country": fixture.get("country"),
            "competition_name": fixture.get("competition_name"),
            "competition_type": fixture.get("competition_type"),
            "home_team": fixture.get("home_team"),
            "away_team": fixture.get("away_team"),
            "league_id": fixture.get("league_id"),
        }

    def _capture_context(self, fixture: dict[str, Any], now: datetime) -> dict[str, Any] | None:
        fixture_id = str(fixture["fixture_id"])
        if self._repository.context_due(
            fixture_id,
            now=now,
            refresh_seconds=self._settings.context_refresh_seconds,
        ):
            payload = self._provider.fetch_fixture(int(fixture["provider_fixture_id"]))
            context = parse_fixture_context(
                payload,
                fixture_id=fixture_id,
                provider_fixture_id=int(fixture["provider_fixture_id"]),
                captured_at=now,
            )
            self._repository.save_fixture_context(context)
        return self._repository.latest_context_before(fixture_id, decision_at=now)

    def _persist_team_history_contexts(
        self,
        payload: dict[str, Any],
        observations: tuple[Any, ...],
        now: datetime,
    ) -> int:
        """Persist referee context already present in team-history fixture payloads."""
        allowed_fixture_ids = {
            str(item.fixture.fixture_id)
            for item in observations
        }
        saved = 0
        for context in parse_fixture_contexts_from_fixture_response(
            payload,
            captured_at=now,
        ):
            if context.fixture_id not in allowed_fixture_ids:
                continue
            self._repository.save_fixture_context(context)
            saved += 1
        return saved

    def _standings(self, fixture: dict[str, Any], now: datetime) -> dict[str, Any] | None:
        if fixture.get("season") is None:
            return None
        league_id = int(fixture["league_id"])
        season = int(fixture["season"])
        latest = self._repository.latest_standings_before(
            league_id,
            season,
            decision_at=now,
        )
        stale = (
            latest is None
            or latest["available_at"]
            <= now - timedelta(seconds=self._settings.standings_refresh_seconds)
        )
        if stale:
            payload = self._provider.fetch_standings(league_id, season)
            self._repository.save_standings_snapshot(
                league_id=league_id,
                season=season,
                available_at=now,
                raw_payload=dict(payload),
            )
            latest = self._repository.latest_standings_before(
                league_id,
                season,
                decision_at=now,
            )
        return latest

    def _discover_fixtures(self, now: datetime) -> int:
        first_day = now.date() - timedelta(days=self._settings.discovery_lookback_days)
        last_day = (now + timedelta(hours=self._settings.lookahead_hours)).date()
        day = first_day
        discovered = 0
        while day <= last_day:
            if self._repository.fixture_discovery_due(
                day,
                now=now,
                refresh_seconds=self._settings.fixture_discovery_refresh_seconds,
            ):
                try:
                    payload = self._provider.fetch_fixtures_for_date(day)
                    observations = parse_fixture_discovery_response(
                        payload,
                        captured_at=now,
                    )
                    discovered += self._repository.save_fixture_discovery(
                        fixture_date=day,
                        captured_at=now,
                        observations=observations,
                    )
                except ApiBudgetExceededError:
                    raise
                except Exception:
                    LOGGER.exception(
                        "QuantLab fixture date-shard discovery failed",
                        extra={"fixture_date": day.isoformat()},
                    )
            day += timedelta(days=1)
        return discovered

    def _fixture_statistics_coverage(
        self,
        fixture: dict[str, Any],
        now: datetime,
    ) -> dict[str, Any] | None:
        league_raw = fixture.get("league_id")
        season_raw = fixture.get("season")
        if league_raw is None or season_raw is None:
            return None
        try:
            league_id = int(league_raw)
            season = int(season_raw)
        except (TypeError, ValueError):
            return None
        if league_id <= 0 or season <= 0:
            return None

        cached = self._repository.latest_league_statistics_coverage(
            league_id,
            season,
            now=now,
            refresh_seconds=self._settings.league_coverage_refresh_seconds,
        )
        if cached is not None:
            return cached

        payload = self._provider.fetch_league_coverage(league_id, season)
        coverage_flags = parse_league_coverage_flags(
            payload,
            league_id=league_id,
            season=season,
        )
        statistics_fixtures = parse_fixture_statistics_coverage(
            payload,
            league_id=league_id,
            season=season,
        )
        response = payload.get("response") if isinstance(payload, dict) else None
        response_item_count = len(response) if isinstance(response, list) else 0
        self._repository.save_league_statistics_coverage(
            league_id=league_id,
            season=season,
            captured_at=now,
            statistics_fixtures=statistics_fixtures,
            statistics_players=coverage_flags["statistics_players"],
            lineups=coverage_flags["lineups"],
            standings=coverage_flags["standings"],
            players=coverage_flags["players"],
            injuries=coverage_flags["injuries"],
            predictions=coverage_flags["predictions"],
            odds=coverage_flags["odds"],
            response_item_count=response_item_count,
            raw_payload=dict(payload),
        )
        return {
            "captured_at": now,
            **coverage_flags,
            "statistics_fixtures": statistics_fixtures,
            "response_item_count": response_item_count,
            "raw_payload": dict(payload),
        }

    def _capture_goal_injuries(
        self,
        fixture: dict[str, Any],
        now: datetime,
    ) -> bool:
        fixture_id = str(fixture["fixture_id"])
        provider_fixture_id = int(fixture["provider_fixture_id"])
        if provider_fixture_id <= 0:
            raise ValueError("provider_fixture_id must be positive")
        if not self._repository.goal_injury_capture_due(
            fixture_id,
            now=now,
            refresh_seconds=self._settings.goal_injury_refresh_seconds,
        ):
            return False

        coverage = self._fixture_statistics_coverage(fixture, now)
        if coverage is not None and coverage.get("injuries") is False:
            raw_coverage = coverage.get("raw_payload")
            self._repository.save_goal_injury_capture(
                fixture_id=fixture_id,
                provider_fixture_id=provider_fixture_id,
                available_at=now,
                status="UNAVAILABLE",
                response_item_count=0,
                reason="league-season-injuries-false",
                source="api-football:leagues",
                raw_payload=(
                    dict(raw_coverage)
                    if isinstance(raw_coverage, dict)
                    else {"coverage": raw_coverage}
                ),
            )
            return False

        payload = self._provider.fetch_injuries(provider_fixture_id)
        response = payload.get("response") if isinstance(payload, dict) else None
        response_item_count = len(response) if isinstance(response, list) else 0
        self._repository.save_goal_injury_capture(
            fixture_id=fixture_id,
            provider_fixture_id=provider_fixture_id,
            available_at=now,
            status="AVAILABLE",
            response_item_count=response_item_count,
            reason=None,
            source="api-football:injuries",
            raw_payload=dict(payload),
        )
        return True

    def _capture_goal_lineup(
        self,
        fixture: dict[str, Any],
        now: datetime,
    ) -> bool:
        fixture_id = str(fixture["fixture_id"])
        provider_fixture_id = int(fixture["provider_fixture_id"])
        kickoff = fixture.get("kickoff_at")
        if provider_fixture_id <= 0 or not isinstance(kickoff, datetime):
            return False
        kickoff_utc = kickoff.astimezone(UTC)
        seconds_to_kickoff = (kickoff_utc - now).total_seconds()
        if (
            seconds_to_kickoff <= 0
            or seconds_to_kickoff > self._settings.goal_lineup_window_minutes * 60
        ):
            return False
        if not self._repository.goal_lineup_capture_due(
            fixture_id,
            now=now,
            refresh_seconds=self._settings.goal_lineup_refresh_seconds,
        ):
            return False

        coverage = self._fixture_statistics_coverage(fixture, now)
        if coverage is not None and coverage.get("lineups") is False:
            raw_coverage = coverage.get("raw_payload")
            self._repository.save_goal_lineup_capture(
                fixture_id=fixture_id,
                provider_fixture_id=provider_fixture_id,
                available_at=now,
                status="UNAVAILABLE",
                response_team_count=0,
                reason="league-season-lineups-false",
                source="api-football:leagues",
                raw_payload=(
                    dict(raw_coverage)
                    if isinstance(raw_coverage, dict)
                    else {"coverage": raw_coverage}
                ),
            )
            return False

        payload = self._provider.fetch_lineups(provider_fixture_id)
        response = payload.get("response") if isinstance(payload, dict) else None
        response_team_count = len(response) if isinstance(response, list) else 0
        self._repository.save_goal_lineup_capture(
            fixture_id=fixture_id,
            provider_fixture_id=provider_fixture_id,
            available_at=now,
            status="AVAILABLE",
            response_team_count=response_team_count,
            reason=None,
            source="api-football:fixtures/lineups",
            raw_payload=dict(payload),
        )
        return True

    def _capture_goal_coaches(
        self,
        fixture: dict[str, Any],
        now: datetime,
    ) -> int:
        captured = 0
        for key in ("home_team_id", "away_team_id"):
            team_id = int(fixture[key])
            if team_id <= 0:
                continue
            if not self._repository.goal_coach_capture_due(
                team_id,
                now=now,
                refresh_seconds=self._settings.goal_coach_refresh_seconds,
            ):
                continue
            payload = self._provider.fetch_team_coaches(team_id)
            response = payload.get("response") if isinstance(payload, dict) else None
            response_item_count = len(response) if isinstance(response, list) else 0
            self._repository.save_goal_coach_capture(
                team_id=team_id,
                available_at=now,
                status="AVAILABLE",
                response_item_count=response_item_count,
                reason=None,
                raw_payload=dict(payload),
            )
            captured += 1
        return captured

    def _capture_historical_players(
        self,
        fixture: dict[str, Any],
        now: datetime,
    ) -> bool:
        fixture_id = str(fixture["fixture_id"])
        provider_fixture_id = int(fixture["provider_fixture_id"])
        if provider_fixture_id <= 0:
            raise ValueError("provider_fixture_id must be positive")

        coverage = self._fixture_statistics_coverage(fixture, now)
        if coverage is not None and coverage.get("statistics_players") is False:
            raw_coverage = coverage.get("raw_payload")
            self._repository.save_goal_player_capture(
                fixture_id=fixture_id,
                provider_fixture_id=provider_fixture_id,
                available_at=now,
                status="UNAVAILABLE",
                response_team_count=0,
                reason="league-season-statistics-players-false",
                source="api-football:leagues",
                raw_payload=(
                    dict(raw_coverage)
                    if isinstance(raw_coverage, dict)
                    else {"coverage": raw_coverage}
                ),
            )
            return True

        payload = self._provider.fetch_fixture_players(provider_fixture_id)
        response = payload.get("response") if isinstance(payload, dict) else None
        response_team_count = len(response) if isinstance(response, list) else 0
        self._repository.save_goal_player_capture(
            fixture_id=fixture_id,
            provider_fixture_id=provider_fixture_id,
            available_at=now,
            status="AVAILABLE",
            response_team_count=response_team_count,
            reason=None,
            source="api-football:fixtures/players",
            raw_payload=dict(payload),
        )
        return True

    def _capture_historical_statistics(
        self,
        fixture: dict[str, Any],
        now: datetime,
        *,
        allow_retry: bool = False,
    ) -> bool:
        fixture_id = str(fixture["fixture_id"])
        if not allow_retry and self._repository.statistics_capture_exists(fixture_id):
            return False
        provider_fixture_id = int(fixture["provider_fixture_id"])
        home_team_id = int(fixture["home_team_id"])
        away_team_id = int(fixture["away_team_id"])
        if provider_fixture_id <= 0 or home_team_id <= 0 or away_team_id <= 0:
            raise ValueError("fixture/provider team IDs must be positive")
        if home_team_id == away_team_id:
            raise ValueError("home and away team IDs must differ")

        coverage = self._fixture_statistics_coverage(fixture, now)
        if coverage is not None and coverage.get("statistics_fixtures") is False:
            raw_coverage = coverage.get("raw_payload")
            self._repository.save_statistics_capture(
                fixture_id=fixture_id,
                provider_fixture_id=provider_fixture_id,
                captured_at=now,
                status="UNAVAILABLE",
                response_team_count=0,
                reason="league-season-statistics-fixtures-false",
                raw_payload=(
                    dict(raw_coverage)
                    if isinstance(raw_coverage, dict)
                    else {"coverage": raw_coverage}
                ),
            )
            LOGGER.debug(
                "QuantLab statistics coverage skip fixture=%s provider_fixture_id=%s "
                "league_id=%s season=%s",
                fixture_id,
                provider_fixture_id,
                fixture.get("league_id"),
                fixture.get("season"),
            )
            return False

        payload = self._provider.fetch_statistics(provider_fixture_id)
        response = payload.get("response") if isinstance(payload, dict) else None
        response_team_count = len(response) if isinstance(response, list) else 0
        try:
            parsed_stats = parse_fixture_statistics(
                payload,
                fixture_id=fixture_id,
                provider_fixture_id=provider_fixture_id,
                home_team_id=home_team_id,
                away_team_id=away_team_id,
                captured_at=now,
            )
        except ValueError as exc:
            if (
                "does not contain both fixture teams" not in str(exc)
                or not isinstance(response, list)
            ):
                raise
            self._repository.save_statistics_capture(
                fixture_id=fixture_id,
                provider_fixture_id=provider_fixture_id,
                captured_at=now,
                status="UNAVAILABLE",
                response_team_count=response_team_count,
                reason=str(exc),
                raw_payload=dict(payload),
            )
            LOGGER.info(
                "QuantLab statistics unavailable fixture=%s provider_fixture_id=%s "
                "response_team_count=%s",
                fixture_id,
                provider_fixture_id,
                response_team_count,
            )
        else:
            self._repository.save_match_statistics(parsed_stats)
            self._repository.save_statistics_capture(
                fixture_id=fixture_id,
                provider_fixture_id=provider_fixture_id,
                captured_at=now,
                status="AVAILABLE",
                response_team_count=response_team_count,
                reason=None,
                raw_payload=dict(payload),
            )
        return True

    def _backfill_history(self, now: datetime) -> int:
        target = self._settings.history_backfill_per_cycle
        if target <= 0:
            return 0
        candidates = self._repository.completed_for_context_backfill(
            before=now,
            limit=max(40, target * 20),
        )
        completed = 0
        for fixture in candidates:
            if completed >= target:
                break
            fixture_id = str(fixture.get("fixture_id") or "")
            scope = self._scope_kwargs(fixture)
            if (
                not goal_scope(**scope).allowed
                and not card_corner_scope(**scope).allowed
            ):
                continue
            try:
                provider_fixture_id = int(fixture["provider_fixture_id"])
                home_team_id = int(fixture["home_team_id"])
                away_team_id = int(fixture["away_team_id"])
                if provider_fixture_id <= 0 or home_team_id <= 0 or away_team_id <= 0:
                    raise ValueError("fixture/provider team IDs must be positive")
                if home_team_id == away_team_id:
                    raise ValueError("home and away team IDs must differ")

                # Referee/context is useful for CardLab, but historical match statistics
                # also feed CornerLab and GoalLab DC+. Do not make the stats backfill
                # depend on referee/context availability.
                context = self._repository.latest_context_before(
                    fixture_id, decision_at=now
                )
                if context is None:
                    try:
                        payload = self._provider.fetch_fixture(provider_fixture_id)
                        parsed = parse_fixture_context(
                            payload,
                            fixture_id=fixture_id,
                            provider_fixture_id=provider_fixture_id,
                            captured_at=now,
                        )
                        self._repository.save_fixture_context(parsed)
                    except ApiBudgetExceededError:
                        raise
                    except Exception as exc:  # noqa: BLE001
                        LOGGER.warning(
                            "QuantLab history context unavailable fixture=%s "
                            "error_class=%s error=%s",
                            fixture_id,
                            type(exc).__name__,
                            str(exc),
                        )

                already_captured = self._repository.statistics_capture_exists(fixture_id)
                attempted = self._capture_historical_statistics(fixture, now)
                if attempted or already_captured:
                    completed += 1
            except ApiBudgetExceededError:
                raise
            except Exception as exc:
                error_text = str(exc)
                LOGGER.exception(
                    "QuantLab history backfill fixture failed fixture=%s "
                    "error_class=%s error=%s",
                    fixture_id,
                    type(exc).__name__,
                    error_text,
                )
        return completed

    def _goal_target_team_ids(self, now: datetime) -> tuple[int, ...]:
        teams: list[int] = []
        seen: set[int] = set()
        fixtures = self._repository.upcoming_fixtures(
            start_at=now,
            end_at=now + timedelta(hours=self._settings.lookahead_hours),
            limit=self._settings.fixture_limit,
        )
        for fixture in fixtures:
            fixture_id = str(fixture["fixture_id"])
            if not goal_scope(**self._scope_kwargs(fixture)).allowed:
                continue
            if "GOAL" not in self._repository.market_labs_for_fixture(fixture_id):
                continue
            for key in ("home_team_id", "away_team_id"):
                team_id = int(fixture[key])
                if team_id <= 0 or team_id in seen:
                    continue
                seen.add(team_id)
                teams.append(team_id)
        return tuple(teams)

    def _bootstrap_goal_team_history(self, now: datetime) -> tuple[int, int]:
        root_team_ids = self._goal_target_team_ids(now)
        if not root_team_ids:
            return 0, 0

        discovery_limit = self._settings.goal_team_history_teams_per_cycle
        queue: deque[tuple[int, int]] = deque((team_id, 0) for team_id in root_team_ids)
        queued = set(root_team_ids)
        processed: set[int] = set()
        expanded_team_ids: list[int] = []
        discoveries = 0

        while queue:
            team_id, depth = queue.popleft()
            if team_id in processed:
                continue
            processed.add(team_id)
            expanded_team_ids.append(team_id)

            if (
                discoveries < discovery_limit
                and self._repository.team_history_due(
                    team_id,
                    now=now,
                    refresh_seconds=self._settings.goal_team_history_refresh_seconds,
                    minimum_requested_last=self._settings.goal_team_history_last,
                )
            ):
                payload = self._provider.fetch_team_recent_fixtures(
                    team_id,
                    last=self._settings.goal_team_history_last,
                )
                observations = parse_fixture_discovery_response(payload, captured_at=now)
                self._repository.save_fixture_observations(observations)
                self._persist_team_history_contexts(payload, observations, now)
                self._repository.save_team_history_capture(
                    team_id=team_id,
                    captured_at=now,
                    requested_last=self._settings.goal_team_history_last,
                    response_fixture_count=len(observations),
                    raw_payload=dict(payload),
                )
                discoveries += 1

            # One-hop opponents provide connected rolling histories without recursive
            # expansion across the global GoalLab universe.
            if depth >= 1:
                continue
            opponents = self._repository.recent_team_opponent_ids(
                team_id,
                before=now,
                limit=self._settings.goal_team_history_last,
            )
            for opponent_id in reversed(opponents):
                if opponent_id <= 0 or opponent_id in queued or opponent_id in processed:
                    continue
                queued.add(opponent_id)
                queue.appendleft((opponent_id, depth + 1))

        stats_target = self._settings.goal_team_statistics_per_cycle
        candidates = self._repository.completed_for_team_statistics(
            expanded_team_ids,
            before=now,
            limit=max(6000, stats_target * 50),
        )
        by_team: dict[int, list[dict[str, Any]]] = {
            team_id: [] for team_id in expanded_team_ids
        }
        target_set = set(expanded_team_ids)
        for fixture in candidates:
            home_id = int(fixture["home_team_id"])
            away_id = int(fixture["away_team_id"])
            if home_id in target_set:
                by_team[home_id].append(fixture)
            if away_id in target_set and away_id != home_id:
                by_team[away_id].append(fixture)

        stats_backfilled = 0
        attempted_fixtures: set[str] = set()
        for team_id in expanded_team_ids:
            for fixture in by_team[team_id]:
                if stats_backfilled >= stats_target:
                    return discoveries, stats_backfilled
                fixture_id = str(fixture["fixture_id"])
                if fixture_id in attempted_fixtures:
                    continue
                attempted_fixtures.add(fixture_id)
                if not goal_scope(**self._scope_kwargs(fixture)).allowed:
                    continue
                try:
                    if self._capture_historical_statistics(fixture, now):
                        stats_backfilled += 1
                except ApiBudgetExceededError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    LOGGER.warning(
                        "QuantLab targeted GoalLab statistics failed fixture=%s "
                        "team_id=%s error_class=%s error=%s",
                        fixture_id,
                        team_id,
                        type(exc).__name__,
                        str(exc),
                    )
        return discoveries, stats_backfilled

    def _bootstrap_goal_player_history(self, now: datetime) -> int:
        team_ids = self._goal_target_team_ids(now)
        if not team_ids:
            return 0
        target = self._settings.goal_player_history_per_cycle
        candidates = self._repository.completed_for_goal_player_backfill(
            team_ids,
            before=now,
            limit=max(3000, target * 30),
        )
        processed = 0
        for fixture in candidates:
            if processed >= target:
                break
            fixture_id = str(fixture.get("fixture_id") or "")
            try:
                if not goal_scope(**self._scope_kwargs(fixture)).allowed:
                    continue
                if self._capture_historical_players(fixture, now):
                    processed += 1
            except ApiBudgetExceededError:
                raise
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning(
                    "QuantLab targeted GoalLab player history failed fixture=%s "
                    "error_class=%s error=%s",
                    fixture_id,
                    type(exc).__name__,
                    str(exc),
                )
        return processed

    def _corner_target_team_ids(self, now: datetime) -> tuple[int, ...]:
        teams: list[int] = []
        seen: set[int] = set()
        for fixture in self._context_upcoming(now):
            fixture_id = str(fixture["fixture_id"])
            if not card_corner_scope(**self._scope_kwargs(fixture)).allowed:
                continue
            market_labs = self._repository.market_labs_for_fixture(fixture_id)
            if not ({"CORNER", "CARD"} & set(market_labs)):
                continue
            for key in ("home_team_id", "away_team_id"):
                team_id = int(fixture[key])
                if team_id <= 0 or team_id in seen:
                    continue
                seen.add(team_id)
                teams.append(team_id)
        return tuple(teams)

    def _bootstrap_corner_team_history(self, now: datetime) -> tuple[int, int]:
        root_team_ids = self._corner_target_team_ids(now)
        if not root_team_ids:
            return 0, 0

        discovery_limit = self._settings.corner_team_history_teams_per_cycle
        queue: deque[tuple[int, int]] = deque((team_id, 0) for team_id in root_team_ids)
        queued = set(root_team_ids)
        processed: set[int] = set()
        expanded_team_ids: list[int] = []
        discoveries = 0

        while queue:
            team_id, depth = queue.popleft()
            if team_id in processed:
                continue
            processed.add(team_id)
            expanded_team_ids.append(team_id)

            if (
                discoveries < discovery_limit
                and self._repository.team_history_due(
                    team_id,
                    now=now,
                    refresh_seconds=self._settings.corner_team_history_refresh_seconds,
                    minimum_requested_last=self._settings.corner_team_history_last,
                )
            ):
                payload = self._provider.fetch_team_recent_fixtures(
                    team_id,
                    last=self._settings.corner_team_history_last,
                )
                observations = parse_fixture_discovery_response(payload, captured_at=now)
                self._repository.save_fixture_observations(observations)
                self._persist_team_history_contexts(payload, observations, now)
                self._repository.save_team_history_capture(
                    team_id=team_id,
                    captured_at=now,
                    requested_last=self._settings.corner_team_history_last,
                    response_fixture_count=len(observations),
                    raw_payload=dict(payload),
                )
                discoveries += 1

            # One-hop opponent expansion creates a connected historical graph so
            # _build_training can satisfy MIN_TEAM_HISTORY for both sides.
            if depth >= 1:
                continue
            opponents = self._repository.recent_team_opponent_ids(
                team_id,
                before=now,
                limit=self._settings.corner_team_history_last,
            )
            for opponent_id in reversed(opponents):
                if opponent_id <= 0 or opponent_id in queued or opponent_id in processed:
                    continue
                queued.add(opponent_id)
                queue.appendleft((opponent_id, depth + 1))

        stats_target = self._settings.corner_team_statistics_per_cycle
        candidates = self._repository.completed_for_team_statistics(
            expanded_team_ids,
            before=now,
            limit=max(6000, stats_target * 50),
        )
        by_team: dict[int, list[dict[str, Any]]] = {
            team_id: [] for team_id in expanded_team_ids
        }
        target_set = set(expanded_team_ids)
        for fixture in candidates:
            home_id = int(fixture["home_team_id"])
            away_id = int(fixture["away_team_id"])
            if home_id in target_set:
                by_team[home_id].append(fixture)
            if away_id in target_set and away_id != home_id:
                by_team[away_id].append(fixture)

        stats_backfilled = 0
        attempted_fixtures: set[str] = set()
        for team_id in expanded_team_ids:
            for fixture in by_team[team_id]:
                if stats_backfilled >= stats_target:
                    return discoveries, stats_backfilled
                fixture_id = str(fixture["fixture_id"])
                if fixture_id in attempted_fixtures:
                    continue
                attempted_fixtures.add(fixture_id)
                if not card_corner_scope(**self._scope_kwargs(fixture)).allowed:
                    continue
                try:
                    if self._capture_historical_statistics(fixture, now):
                        stats_backfilled += 1
                except ApiBudgetExceededError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    LOGGER.warning(
                        "QuantLab targeted Card/Corner statistics failed fixture=%s "
                        "team_id=%s error_class=%s error=%s",
                        fixture_id,
                        team_id,
                        type(exc).__name__,
                        str(exc),
                    )
        return discoveries, stats_backfilled

    def _context_upcoming(self, now: datetime) -> tuple[dict[str, Any], ...]:
        """Return the broad market-driven CardLab/CornerLab upcoming queue."""
        return self._repository.upcoming_fixtures(
            start_at=now,
            end_at=now + timedelta(hours=self._settings.lookahead_hours),
            limit=self._settings.fixture_limit,
        )

    @staticmethod
    def _card_history_sample_size(rows: tuple[dict[str, Any], ...]) -> int:
        return sum(
            1
            for row in rows
            if row.get("card_total") is not None
            or (row.get("yellow_cards") is not None and row.get("red_cards") is not None)
        )

    def _capture_referee_card_events(self, fixture: dict[str, Any], now: datetime) -> bool:
        """Use events only when their yellow count agrees with fixture statistics."""
        payload = self._provider.fetch_events(int(fixture["provider_fixture_id"]))
        observation = parse_1xbet_card_events(
            payload,
            fixture_id=str(fixture["fixture_id"]),
            provider_fixture_id=int(fixture["provider_fixture_id"]),
            captured_at=now,
        )
        yellow_events = sum(
            str(event["detail"]).casefold() == "yellow card"
            for event in observation.event_payload
        )
        expected_yellows = int(fixture["home_yellow_cards"]) + int(
            fixture["away_yellow_cards"]
        )
        if yellow_events != expected_yellows:
            LOGGER.info(
                "QuantLab CardLab referee events disagree with statistics fixture=%s "
                "event_yellows=%d statistic_yellows=%d",
                fixture["fixture_id"],
                yellow_events,
                expected_yellows,
            )
            return False
        return self._repository.save_card_event_observation(observation)

    def _card_referee_history_targets(
        self,
        now: datetime,
    ) -> dict[tuple[int, int], set[str]]:
        targets: dict[tuple[int, int], set[str]] = {}
        fixtures = self._context_upcoming(now)
        for fixture in fixtures:
            fixture_id = str(fixture["fixture_id"])
            if not card_corner_scope(**self._scope_kwargs(fixture)).allowed:
                continue
            if "CARD" not in self._repository.market_labs_for_fixture(fixture_id):
                continue
            context = self._repository.latest_context_before(fixture_id, decision_at=now)
            if context is None:
                continue
            referee = str(context.get("referee") or "").strip()
            if not referee:
                continue
            history = self._repository.referee_history(referee, decision_at=now)
            if self._card_history_sample_size(history) >= self._settings.card_referee_history_target:
                continue
            league_id = int(fixture.get("league_id") or 0)
            season = int(fixture.get("season") or 0)
            if league_id <= 0 or season <= 0:
                continue
            targets.setdefault((league_id, season), set()).add(referee)
        return targets

    def _bootstrap_card_referee_history(
        self,
        now: datetime,
    ) -> tuple[int, int, frozenset[str]]:
        """Fill referee history from league fixtures, then fetch only missing match stats."""
        current_targets = self._card_referee_history_targets(now)
        if not current_targets:
            return 0, 0, frozenset()
        target_referees: dict[str, str] = {}
        for referees in current_targets.values():
            for referee in referees:
                target_referees.setdefault(referee_key(referee), referee)
        baseline_samples = {
            key: self._card_history_sample_size(
                self._repository.referee_history(referee, decision_at=now)
            )
            for key, referee in target_referees.items()
        }
        self._scan_card_referee_days(now)
        targets: dict[tuple[int, int], set[str]] = {}
        for (league_id, season), referees in current_targets.items():
            for prior in range(self._settings.card_referee_prior_seasons + 1):
                historical_season = season - prior
                if historical_season > 0:
                    targets.setdefault((league_id, historical_season), set()).update(referees)
        LOGGER.info(
            "QuantLab CardLab referee bootstrap targets scopes=%d referees=%d",
            len(targets),
            len(target_referees),
        )
        scopes_refreshed = 0
        statistics_backfilled = 0
        statistics_attempts = 0
        event_attempts = 0
        updated_referees: set[str] = set()
        window_start = (now - timedelta(days=self._settings.card_referee_history_lookback_days)).date()
        window_end = now.date()

        for (league_id, season), referees in sorted(
            targets.items(),
            key=lambda item: (-len(item[1]), -item[0][1], item[0][0]),
        ):
            active_referees: set[str] = set()
            for referee in referees:
                current_sample = self._card_history_sample_size(
                    self._repository.referee_history(referee, decision_at=now)
                )
                key = referee_key(referee)
                if current_sample > baseline_samples.get(key, 0):
                    updated_referees.add(key)
                    baseline_samples[key] = current_sample
                if current_sample < self._settings.card_referee_history_target:
                    active_referees.add(referee)
            if not active_referees:
                continue
            if (
                scopes_refreshed < self._settings.card_referee_history_scopes_per_cycle
                and self._repository.referee_history_scope_due(
                    league_id,
                    season,
                    now=now,
                    refresh_seconds=self._settings.card_referee_history_refresh_seconds,
                )
            ):
                payload = self._provider.fetch_completed_league_fixtures(
                    league_id,
                    season,
                    start_date=window_start,
                    end_date=window_end,
                )
                observations = parse_fixture_discovery_response(payload, captured_at=now)
                self._repository.save_fixture_observations(observations)
                saved_contexts = self._persist_team_history_contexts(
                    dict(payload),
                    observations,
                    now,
                )
                response = payload.get("response") if isinstance(payload, dict) else None
                response_count = len(response) if isinstance(response, list) else 0
                self._repository.save_referee_history_scope_capture(
                    league_id=league_id,
                    season=season,
                    window_start=window_start,
                    window_end=window_end,
                    captured_at=now,
                    response_fixture_count=response_count,
                    referee_fixture_count=saved_contexts,
                    raw_payload=dict(payload),
                )
                scopes_refreshed += 1
                LOGGER.info(
                    "QuantLab CardLab referee scope refreshed league_id=%d season=%d "
                    "response_fixtures=%d referee_contexts=%d target_referees=%d",
                    league_id,
                    season,
                    response_count,
                    saved_contexts,
                    len(active_referees),
                )

            for referee in sorted(active_referees):
                referee_key_value = referee_key(referee)
                history = self._repository.referee_history(referee, decision_at=now)
                current_sample = self._card_history_sample_size(history)
                baseline_sample = baseline_samples.get(referee_key_value, 0)
                if current_sample > baseline_sample:
                    updated_referees.add(referee_key_value)
                    baseline_samples[referee_key_value] = current_sample
                    LOGGER.info(
                        "QuantLab CardLab referee history unlocked referee=%s sample=%d",
                        referee,
                        current_sample,
                    )
                if current_sample >= self._settings.card_referee_history_target:
                    continue
                event_candidates = self._repository.referee_card_event_backfill_candidates(
                    referee,
                    decision_at=now,
                    limit=max(12, self._settings.card_referee_history_target * 2),
                )
                for fixture in event_candidates:
                    if current_sample >= self._settings.card_referee_history_target:
                        break
                    if event_attempts >= self._settings.card_referee_statistics_per_cycle:
                        break
                    event_attempts += 1
                    try:
                        saved_event = self._capture_referee_card_events(fixture, now)
                    except ApiBudgetExceededError:
                        raise
                    except Exception as exc:  # noqa: BLE001
                        LOGGER.warning(
                            "QuantLab CardLab referee events failed referee=%s "
                            "fixture=%s error_class=%s error=%s",
                            referee,
                            fixture.get("fixture_id"),
                            type(exc).__name__,
                            str(exc),
                        )
                        continue
                    if saved_event:
                        history = self._repository.referee_history(referee, decision_at=now)
                        current_sample = self._card_history_sample_size(history)
                        if current_sample > baseline_samples.get(referee_key_value, 0):
                            updated_referees.add(referee_key_value)
                            baseline_samples[referee_key_value] = current_sample
                if current_sample >= self._settings.card_referee_history_target:
                    continue
                candidates = self._repository.referee_statistics_backfill_candidates(
                    referee,
                    decision_at=now,
                    retry_after_seconds=self._settings.card_referee_statistics_retry_seconds,
                    limit=max(12, self._settings.card_referee_history_target * 2),
                )
                for fixture in candidates:
                    if current_sample >= self._settings.card_referee_history_target:
                        break
                    if statistics_attempts >= self._settings.card_referee_statistics_per_cycle:
                        break
                    statistics_attempts += 1
                    try:
                        saved = self._capture_historical_statistics(
                            fixture,
                            now,
                            allow_retry=True,
                        )
                    except ApiBudgetExceededError:
                        raise
                    except Exception as exc:  # noqa: BLE001
                        LOGGER.warning(
                            "QuantLab CardLab referee statistics failed referee=%s "
                            "fixture=%s error_class=%s error=%s",
                            referee,
                            fixture.get("fixture_id"),
                            type(exc).__name__,
                            str(exc),
                        )
                        continue
                    if not saved:
                        continue
                    statistics_backfilled += 1
                    history = self._repository.referee_history(referee, decision_at=now)
                    current_sample = self._card_history_sample_size(history)
                    if current_sample > baseline_samples.get(referee_key_value, 0):
                        updated_referees.add(referee_key_value)
                        baseline_samples[referee_key_value] = current_sample

        LOGGER.info(
            "QuantLab CardLab referee bootstrap completed scopes_refreshed=%d "
            "statistics_attempts=%d event_attempts=%d statistics_backfilled=%d updated_referees=%d",
            scopes_refreshed,
            statistics_attempts,
            event_attempts,
            statistics_backfilled,
            len(updated_referees),
        )
        return scopes_refreshed, statistics_backfilled, frozenset(updated_referees)

    def _scan_card_referee_days(self, now: datetime) -> int:
        """Index finished referee fixtures across competitions, newest dates first."""
        first_day = (now - timedelta(days=self._settings.card_referee_history_lookback_days)).date()
        last_day = now.date() - timedelta(days=1)
        days = self._repository.unscanned_referee_history_days(
            first_day=first_day,
            last_day=last_day,
            limit=self._settings.card_referee_history_days_per_cycle,
        )
        scanned = 0
        for day in days:
            try:
                first = self._provider.fetch_fixtures_for_date(day)
                paging = first.get("paging")
                if not isinstance(paging, dict):
                    raise TypeError("referee date response has no paging")
                total_pages = int(paging.get("total") or 0)
                if not 1 <= total_pages <= 20:
                    raise ValueError(f"referee date response has invalid page count: {total_pages}")
                response_count = 0
                referee_count = 0
                for page in range(1, total_pages + 1):
                    payload = first if page == 1 else self._provider.fetch_fixtures_for_date(day, page=page)
                    if payload.get("errors"):
                        raise RuntimeError(f"API-Football referee date errors: {payload['errors']}")
                    response = payload.get("response")
                    if not isinstance(response, list):
                        raise TypeError("referee date response must be a list")
                    response_count += len(response)
                    selected = [
                        item for item in response
                        if isinstance(item, dict)
                        and isinstance(item.get("fixture"), dict)
                        and referee_key(item["fixture"].get("referee"))
                        and isinstance(item["fixture"].get("status"), dict)
                        and item["fixture"]["status"].get("short") in {"FT", "AET", "PEN"}
                    ]
                    selected_payload = {"errors": [], "response": selected}
                    observations = parse_fixture_discovery_response(selected_payload, captured_at=now)
                    self._repository.save_fixture_observations(observations)
                    referee_count += self._persist_team_history_contexts(
                        selected_payload, observations, now
                    )
                self._repository.save_referee_day_scan(
                    scan_date=day,
                    captured_at=now,
                    response_fixture_count=response_count,
                    referee_fixture_count=referee_count,
                    page_count=total_pages,
                )
                scanned += 1
            except ApiBudgetExceededError:
                raise
            except Exception:
                LOGGER.exception("QuantLab CardLab referee date scan failed date=%s", day)
        if scanned:
            LOGGER.info("QuantLab CardLab referee date scans completed days=%d", scanned)
        return scanned

    def _bootstrap_referee_web(
        self,
        now: datetime,
    ) -> tuple[int, int, frozenset[str]]:
        if self._referee_web_source is None:
            return 0, 0, frozenset()

        captures = 0
        profiles_saved = 0
        refreshed_leagues: set[str] = set()
        targets = proactive_web_targets(
            now,
            seasons_per_league=self._settings.card_referee_web_seasons,
        )
        for league_key, season, comp_id in targets:
            if not self._repository.referee_web_profile_due(
                league_key,
                season,
                now=now,
                refresh_seconds=self._settings.card_referee_web_refresh_seconds,
            ):
                continue
            try:
                source_url, profiles = self._referee_web_source.fetch_profiles(
                    league_key,
                    season,
                )
                self._repository.save_referee_web_capture(
                    league_key=league_key,
                    season=season,
                    source_competition_id=comp_id,
                    source_url=source_url,
                    captured_at=now,
                    profiles=profiles,
                )
                captures += 1
                profiles_saved += len(profiles)
                refreshed_leagues.add(league_key)
                LOGGER.info(
                    "QuantLab CardLab referee web refreshed league=%s season=%d profiles=%d",
                    league_key,
                    season,
                    len(profiles),
                )
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning(
                    "QuantLab CardLab referee web refresh failed league=%s season=%d "
                    "error_class=%s error=%s",
                    league_key,
                    season,
                    type(exc).__name__,
                    str(exc),
                )

        LOGGER.info(
            "QuantLab CardLab proactive referee web bootstrap completed "
            "targets=%d captures=%d profiles=%d refreshed_leagues=%d",
            len(targets),
            captures,
            profiles_saved,
            len(refreshed_leagues),
        )
        return captures, profiles_saved, frozenset(refreshed_leagues)

    def _collect_upcoming(
        self,
        now: datetime,
        *,
        force_card_referees: frozenset[str] = frozenset(),
        force_card_web_leagues: frozenset[str] = frozenset(),
    ) -> tuple[int, int]:
        goal_queue = self._repository.upcoming_fixtures(
            start_at=now,
            end_at=now + timedelta(hours=self._settings.lookahead_hours),
            limit=self._settings.fixture_limit,
        )
        context_queue = self._context_upcoming(now)
        prioritized: dict[str, dict[str, Any]] = {}
        for fixture in (*context_queue, *goal_queue):
            prioritized.setdefault(str(fixture["fixture_id"]), fixture)
            if len(prioritized) >= self._settings.fixture_limit:
                break
        fixtures = tuple(prioritized.values())
        market_fixtures = 0
        card_snapshots = 0
        for fixture in fixtures:
            fixture_id = str(fixture.get("fixture_id") or "")
            try:
                scope = self._scope_kwargs(fixture)
                goal_allowed = goal_scope(**scope).allowed
                context_allowed = card_corner_scope(**scope).allowed
                if not goal_allowed and not context_allowed:
                    continue

                provider_fixture_id = int(fixture["provider_fixture_id"])
                if provider_fixture_id <= 0:
                    raise ValueError("provider_fixture_id must be positive")
                allowed_labs = {"GOAL"} if goal_allowed else set()
                if context_allowed:
                    allowed_labs.update({"CORNER", "CARD", "GOAL", "UNCLASSIFIED"})
                if self._repository.market_capture_due(
                    fixture_id,
                    now=now,
                    refresh_seconds=self._settings.market_refresh_seconds,
                ):
                    self._collector.collect_fixture(
                        fixture_id=fixture_id,
                        provider_fixture_id=provider_fixture_id,
                        captured_at=now,
                        allowed_labs=allowed_labs,
                    )
                    market_fixtures += 1

                market_labs = self._repository.market_labs_for_fixture(fixture_id)
                standings = None
                if goal_allowed and "GOAL" in market_labs:
                    standings = self._standings(fixture, now)
                    self._capture_goal_injuries(fixture, now)
                    self._capture_goal_lineup(fixture, now)
                    self._capture_goal_coaches(fixture, now)

                if not context_allowed:
                    continue
                if "CARD" not in market_labs:
                    continue
                referee_web_key = referee_web_league_key(
                    fixture.get("country"),
                    fixture.get("competition_name"),
                )
                context = self._capture_context(fixture, now)
                if standings is None:
                    standings = self._standings(fixture, now)
                if context is None:
                    continue
                referee = context.get("referee")
                referee_key_value = referee_key(referee)
                force_snapshot = bool(
                    (referee_key_value and referee_key_value in force_card_referees)
                    or (
                        referee_web_key is not None
                        and referee_web_key in force_card_web_leagues
                    )
                )
                if (
                    not force_snapshot
                    and not self._repository.feature_snapshot_due(
                        fixture_id,
                        now=now,
                        refresh_seconds=self._settings.feature_refresh_seconds,
                    )
                ):
                    continue
                history = (
                    self._repository.referee_history(str(referee), decision_at=now)
                    if referee
                    else ()
                )
                home_team_id = int(fixture["home_team_id"])
                away_team_id = int(fixture["away_team_id"])
                if home_team_id <= 0 or away_team_id <= 0 or home_team_id == away_team_id:
                    raise ValueError("invalid home/away team IDs for CardLab feature snapshot")
                snapshot = build_cardlab_snapshot(
                    fixture_id=fixture_id,
                    decision_at=now,
                    kickoff_at=context.get("kickoff_at") or fixture["kickoff_at"],
                    referee=None if referee is None else str(referee),
                    referee_available_at=context.get("available_at"),
                    referee_history=history,
                    referee_web_profiles=(
                        self._repository.referee_web_profiles(
                            str(referee),
                            referee_web_key,
                            season=int(fixture.get("season") or 0),
                            decision_at=now,
                            season_lookback=self._settings.card_referee_web_seasons,
                        )
                        if referee and referee_web_key and int(fixture.get("season") or 0) > 0
                        else ()
                    ),
                    referee_web_league_key=referee_web_key,
                    team_history=self._repository.card_team_history(
                        home_team_id,
                        away_team_id,
                        before=now,
                    ),
                    league_history=self._repository.card_league_history(
                        str(fixture["competition_name"]),
                        before=now,
                        league_id=(
                            int(fixture["league_id"])
                            if fixture.get("league_id") is not None
                            else None
                        ),
                        season=(
                            int(fixture["season"])
                            if fixture.get("season") is not None
                            else None
                        ),
                    ),
                    market_context=self._repository.card_market_context(
                        fixture_id,
                        decision_at=now,
                    ),
                    home_team=str(fixture["home_team"]),
                    away_team=str(fixture["away_team"]),
                    home_team_id=home_team_id,
                    away_team_id=away_team_id,
                    competition_name=str(fixture["competition_name"]),
                    competition_type=str(fixture.get("competition_type") or ""),
                    standings_payload=None if standings is None else standings["raw_payload"],
                    standings_available_at=(
                        None if standings is None else standings["available_at"]
                    ),
                )
                self._repository.save_card_feature_snapshot(snapshot)
                card_snapshots += 1
            except ApiBudgetExceededError:
                raise
            except FeatureLeakageError as exc:
                LOGGER.warning(
                    "QuantLab feature snapshot rejected fixture=%s error=%s",
                    fixture_id,
                    str(exc),
                )
            except Exception as exc:
                error_text = str(exc)
                LOGGER.exception(
                    "QuantLab upcoming fixture collection failed fixture=%s "
                    "error_class=%s error=%s",
                    fixture_id,
                    type(exc).__name__,
                    error_text,
                )
        return market_fixtures, card_snapshots

    def _evaluate_goal_picks(self, now: datetime) -> tuple[int, int]:
        if self._goal_engine is None:
            return 0, 0
        fixtures = self._repository.upcoming_fixtures(
            start_at=now,
            end_at=now + timedelta(hours=self._settings.lookahead_hours),
            limit=self._settings.fixture_limit,
        )
        decisions = 0
        picks = 0
        for fixture in fixtures:
            if not goal_scope(**self._scope_kwargs(fixture)).allowed:
                continue
            fixture_id = str(fixture.get("fixture_id") or "")
            try:
                outcome = self._goal_engine.run_fixture(fixture, decision_at=now)
            except ApiBudgetExceededError:
                raise
            except Exception as exc:
                LOGGER.exception(
                    "GoalLab fixture evaluation failed fixture=%s error_class=%s",
                    fixture_id,
                    type(exc).__name__,
                )
                continue
            decisions += int(outcome.decisions_inserted)
            picks += int(outcome.picks_inserted)
        return decisions, picks

    def _refresh_goal_pick_results(self, now: datetime) -> int:
        """Refresh post-match result evidence for unsettled GoalLab canonical picks."""
        rows = self._repository.goal_pick_result_refresh_candidates(
            now=now,
            post_kickoff_delay_seconds=GOAL_RESULT_INITIAL_DELAY_SECONDS,
            refresh_after_seconds=GOAL_RESULT_REFRESH_SECONDS,
            postponed_refresh_seconds=GOAL_RESULT_POSTPONED_REFRESH_SECONDS,
            limit=25,
        )
        refreshed = 0
        for fixture in rows:
            fixture_id = str(fixture["fixture_id"])
            provider_fixture_id = int(fixture["provider_fixture_id"])
            payload = self._provider.fetch_fixture(provider_fixture_id)
            observations = parse_fixture_discovery_response(payload, captured_at=now)
            matching = tuple(
                item for item in observations if str(item.fixture.fixture_id) == fixture_id
            )
            if not matching:
                LOGGER.warning(
                    "QuantLab GoalLab result refresh returned no matching fixture fixture=%s",
                    fixture_id,
                )
                continue
            refreshed += int(self._repository.save_fixture_observations(matching))
        return refreshed

    def _settle_goal_picks(self, now: datetime) -> int:
        settled = 0
        rows = self._repository.goal_pick_settlement_candidates(limit=500)
        for row in rows:
            fixture_id = str(row.get("fixture_id") or "")
            goal_pick_id = str(row.get("goal_pick_id") or "")
            try:
                result_evidence = stable_goal_result_evidence(
                    row,
                    finality_delay_seconds=GOAL_RESULT_FINALITY_DELAY_SECONDS,
                )
                if result_evidence is None:
                    continue
                settlement_row = dict(row)
                settlement_row.update(result_evidence)
                settlement = settle_goal_pick(settlement_row, settled_at=now)
                if settlement is None:
                    continue
                settled += int(
                    bool(self._repository.save_goal_pick_settlement(settlement))
                )
            except Exception as exc:
                LOGGER.exception(
                    "GoalLab settlement failed fixture=%s goal_pick_id=%s "
                    "error_class=%s",
                    fixture_id,
                    goal_pick_id,
                    type(exc).__name__,
                )
        return settled

    def _refresh_corner_pick_results(self, now: datetime) -> int:
        """Refresh post-match fixture status for open CornerLab picks inside QuantLab."""
        rows = self._repository.corner_shadow_result_refresh_candidates(
            now=now,
            post_kickoff_delay_seconds=5400,
            refresh_after_seconds=900,
            limit=25,
        )
        refreshed = 0
        for fixture in rows:
            fixture_id = str(fixture["fixture_id"])
            provider_fixture_id = int(fixture["provider_fixture_id"])
            payload = self._provider.fetch_fixture(provider_fixture_id)
            observations = parse_fixture_discovery_response(payload, captured_at=now)
            matching = tuple(
                item
                for item in observations
                if str(item.fixture.fixture_id) == fixture_id
            )
            if not matching:
                LOGGER.warning(
                    "QuantLab CornerLab result refresh returned no matching fixture fixture=%s",
                    fixture_id,
                )
                continue
            refreshed += int(self._repository.save_fixture_observations(matching))
        return refreshed

    def _refresh_corner_pick_statistics(self, now: datetime) -> int:
        """Retry transiently unavailable corner stats only for unsettled CornerLab picks."""
        rows = self._repository.corner_shadow_statistics_retry_candidates(
            now=now,
            retry_after_seconds=1800,
            limit=25,
        )
        refreshed = 0
        for fixture in rows:
            try:
                refreshed += int(
                    self._capture_historical_statistics(
                        fixture,
                        now,
                        allow_retry=True,
                    )
                )
            except ApiBudgetExceededError:
                raise
            except Exception:
                LOGGER.exception(
                    "QuantLab CornerLab settlement statistics retry failed fixture=%s",
                    fixture.get("fixture_id"),
                )
        return refreshed

    def _settle_corner_picks(self, now: datetime) -> int:
        settled = 0
        rows = self._repository.corner_shadow_settlement_candidates(limit=500)
        for row in rows:
            settlement = settle_corner_shadow_bet(row, settled_at=now)
            if settlement is None:
                continue
            settled += int(bool(self._repository.save_corner_settlement_event(settlement)))
        return settled

    def _refresh_card_pick_results(self, now: datetime) -> int:
        rows = self._repository.card_shadow_result_refresh_candidates(
            now=now,
            post_kickoff_delay_seconds=5400,
            refresh_after_seconds=900,
            limit=25,
        )
        refreshed = 0
        for fixture in rows:
            fixture_id = str(fixture["fixture_id"])
            provider_fixture_id = int(fixture["provider_fixture_id"])
            payload = self._provider.fetch_fixture(provider_fixture_id)
            observations = parse_fixture_discovery_response(payload, captured_at=now)
            matching = tuple(
                item for item in observations if str(item.fixture.fixture_id) == fixture_id
            )
            if not matching:
                LOGGER.warning(
                    "QuantLab CardLab result refresh returned no matching fixture fixture=%s",
                    fixture_id,
                )
                continue
            refreshed += int(self._repository.save_fixture_observations(matching))
        return refreshed

    def _capture_card_pick_events(self, now: datetime) -> int:
        rows = self._repository.card_event_capture_candidates(limit=25)
        captured = 0
        for fixture in rows:
            fixture_id = str(fixture["fixture_id"])
            provider_fixture_id = int(fixture["provider_fixture_id"])
            payload = self._provider.fetch_events(provider_fixture_id)
            observation = parse_1xbet_card_events(
                payload,
                fixture_id=fixture_id,
                provider_fixture_id=provider_fixture_id,
                captured_at=now,
            )
            captured += int(bool(self._repository.save_card_event_observation(observation)))
        return captured

    def _settle_card_picks(self, now: datetime) -> int:
        settled = 0
        rows = self._repository.card_shadow_settlement_candidates(limit=500)
        for row in rows:
            settlement = settle_card_shadow_bet(row, settled_at=now)
            if settlement is None:
                continue
            settled += int(bool(self._repository.save_card_settlement_event(settlement)))
        return settled

    def _collect_h2h_snapshots(self, now: datetime) -> int:
        """Collect at most one timestamp-safe direct-H2H snapshot per upcoming fixture."""
        if self._h2h_engine is None:
            return 0
        fixtures = self._repository.upcoming_fixtures(
            start_at=now,
            end_at=now + timedelta(hours=self._settings.lookahead_hours),
            limit=self._settings.fixture_limit,
        )
        captured = 0
        for fixture in fixtures:
            if not goal_scope(**self._scope_kwargs(fixture)).allowed:
                continue
            fixture_id = str(fixture.get("fixture_id") or "")
            if "GOAL" not in self._repository.market_labs_for_fixture(fixture_id):
                continue
            if not self._repository.h2h_snapshot_due(
                fixture_id, now=now, refresh_seconds=self._settings.h2h_refresh_seconds
            ):
                continue
            home_team_id = int(fixture.get("home_team_id") or 0)
            away_team_id = int(fixture.get("away_team_id") or 0)
            if home_team_id <= 0 or away_team_id <= 0 or home_team_id == away_team_id:
                continue
            try:
                payload = self._provider.fetch_head_to_head(home_team_id, away_team_id, last=10)
                meetings = parse_h2h_response(
                    payload,
                    target_home_team_id=home_team_id,
                    target_away_team_id=away_team_id,
                    before=_utc_fixture_time(fixture["kickoff_at"]),
                    maximum=10,
                )
                self._repository.save_h2h_snapshot(
                    fixture_id=fixture_id,
                    home_team_id=home_team_id,
                    away_team_id=away_team_id,
                    captured_at=now,
                    meetings=meetings,
                    raw_payload=dict(payload),
                )
                captured += 1
            except ApiBudgetExceededError:
                raise
            except (KeyError, TypeError, ValueError) as exc:
                LOGGER.warning(
                    "QuantLab H2HLab snapshot rejected fixture=%s error_class=%s error=%s",
                    fixture_id,
                    type(exc).__name__,
                    str(exc),
                )
        return captured

    def _evaluate_h2h_picks(self, now: datetime) -> tuple[int, int]:
        if self._h2h_engine is None:
            return 0, 0
        fixtures = self._repository.upcoming_fixtures(
            start_at=now,
            end_at=now + timedelta(hours=self._settings.lookahead_hours),
            limit=self._settings.fixture_limit,
        )
        decisions = picks = 0
        for fixture in fixtures:
            if not goal_scope(**self._scope_kwargs(fixture)).allowed:
                continue
            try:
                outcome = self._h2h_engine.run_fixture(fixture, decision_at=now)
            except Exception as exc:
                LOGGER.exception(
                    "H2HLab fixture evaluation failed fixture=%s error_class=%s",
                    fixture.get("fixture_id"), type(exc).__name__,
                )
                continue
            decisions += int(outcome.decisions_inserted)
            picks += int(outcome.picks_inserted)
        return decisions, picks

    def _refresh_h2h_pick_results(self, now: datetime) -> int:
        rows = self._repository.h2h_shadow_result_refresh_candidates(now=now, limit=25)
        refreshed = 0
        for fixture in rows:
            fixture_id = str(fixture["fixture_id"])
            payload = self._provider.fetch_fixture(int(fixture["provider_fixture_id"]))
            observations = parse_fixture_discovery_response(payload, captured_at=now)
            matching = tuple(item for item in observations if str(item.fixture.fixture_id) == fixture_id)
            if matching:
                refreshed += int(self._repository.save_fixture_observations(matching))
        return refreshed

    def _settle_h2h_picks(self, now: datetime) -> int:
        settled = 0
        for row in self._repository.h2h_shadow_settlement_candidates(limit=500):
            settlement = settle_h2h_shadow_bet(row, settled_at=now)
            if settlement is not None:
                settled += int(bool(self._repository.save_h2h_settlement(settlement)))
        return settled

    def _evaluate_context_picks(
        self,
        engine: Any | None,
        lab: str,
        now: datetime,
    ) -> tuple[int, int]:
        if engine is None:
            return 0, 0
        if lab not in {"CORNER", "CARD"}:
            raise ValueError("lab must be CORNER or CARD")
        fixtures = self._context_upcoming(now)
        decisions = 0
        picks = 0
        for fixture in fixtures:
            fixture_id = str(fixture["fixture_id"])
            if not card_corner_scope(**self._scope_kwargs(fixture)).allowed:
                continue
            if lab not in self._repository.market_labs_for_fixture(fixture_id):
                continue
            outcome = engine.run_fixture(fixture, decision_at=now)
            decisions += int(outcome.decisions_inserted)
            picks += int(outcome.picks_inserted)
        return decisions, picks

    def run_once(self) -> dict[str, int]:
        now = self._clock().astimezone(UTC)
        result = {
            "fixtures_discovered": 0,
            "history_backfilled": 0,
            "goal_team_history_discovered": 0,
            "goal_team_statistics_backfilled": 0,
            "goal_player_history_backfilled": 0,
            "corner_team_history_discovered": 0,
            "corner_team_statistics_backfilled": 0,
            "card_referee_scopes_refreshed": 0,
            "card_referee_statistics_backfilled": 0,
            "card_referee_web_captures": 0,
            "card_referee_web_profiles": 0,
            "market_fixtures": 0,
            "card_snapshots": 0,
            "goal_decisions": 0,
            "goal_picks": 0,
            "goal_result_refreshes": 0,
            "goal_settlements": 0,
            "h2h_snapshots": 0,
            "h2h_decisions": 0,
            "h2h_picks": 0,
            "h2h_result_refreshes": 0,
            "h2h_settlements": 0,
            "corner_decisions": 0,
            "corner_picks": 0,
            "corner_settlements": 0,
            "card_decisions": 0,
            "card_picks": 0,
            "card_event_captures": 0,
            "card_settlements": 0,
        }

        # GoalLab is the current research priority. Fit/evaluate DC+ from already
        # persisted history and quotes before any provider-backed refresh or backfill.
        # Fresh collection later in this cycle becomes input to the next evaluation.
        try:
            goal_decisions, goal_picks = self._evaluate_goal_picks(now)
            result["goal_decisions"] = goal_decisions
            result["goal_picks"] = goal_picks
        except Exception:
            LOGGER.exception("QuantLab GoalLab shadow evaluation failed")

        try:
            result["goal_result_refreshes"] = self._refresh_goal_pick_results(now)
            if result["goal_result_refreshes"]:
                LOGGER.info(
                    "QuantLab GoalLab post-match result observations refreshed=%d",
                    result["goal_result_refreshes"],
                )
        except ApiBudgetExceededError:
            LOGGER.warning(
                "Shared football API daily budget reached; GoalLab result refresh skipped"
            )
        except Exception:
            LOGGER.exception("QuantLab GoalLab post-match result refresh failed")

        try:
            result["goal_settlements"] = self._settle_goal_picks(now)
        except Exception:
            LOGGER.exception("QuantLab GoalLab settlement failed")
        # Existing CornerLab picks must settle even if collection or GoalLab model work is slow.
        try:
            refreshed_results = self._refresh_corner_pick_results(now)
            if refreshed_results:
                LOGGER.info(
                    "QuantLab CornerLab post-match result observations refreshed=%d",
                    refreshed_results,
                )
        except ApiBudgetExceededError:
            LOGGER.warning(
                "Shared football API daily budget reached; CornerLab result refresh skipped"
            )
        except Exception:
            LOGGER.exception("QuantLab CornerLab post-match result refresh failed")

        try:
            refreshed = self._refresh_corner_pick_statistics(now)
            if refreshed:
                LOGGER.info(
                    "QuantLab CornerLab settlement statistics refreshed=%d",
                    refreshed,
                )
        except ApiBudgetExceededError:
            LOGGER.warning(
                "Shared football API daily budget reached; CornerLab settlement statistics retry skipped"
            )
        except Exception:
            LOGGER.exception("QuantLab CornerLab settlement statistics retry failed")

        try:
            result["corner_settlements"] = self._settle_corner_picks(now)
        except Exception:
            LOGGER.exception("QuantLab CornerLab settlement failed")

        try:
            refreshed_card_results = self._refresh_card_pick_results(now)
            if refreshed_card_results:
                LOGGER.info(
                    "QuantLab CardLab post-match result observations refreshed=%d",
                    refreshed_card_results,
                )
        except ApiBudgetExceededError:
            LOGGER.warning(
                "Shared football API daily budget reached; CardLab result refresh skipped"
            )
        except Exception:
            LOGGER.exception("QuantLab CardLab post-match result refresh failed")

        try:
            result["card_event_captures"] = self._capture_card_pick_events(now)
        except ApiBudgetExceededError:
            LOGGER.warning(
                "Shared football API daily budget reached; CardLab event capture skipped"
            )
        except Exception:
            LOGGER.exception("QuantLab CardLab event capture failed")

        try:
            result["card_settlements"] = self._settle_card_picks(now)
        except Exception:
            LOGGER.exception("QuantLab CardLab settlement failed")

        refreshed_card_web_leagues: frozenset[str] = frozenset()
        try:
            (
                result["card_referee_web_captures"],
                result["card_referee_web_profiles"],
                refreshed_card_web_leagues,
            ) = self._bootstrap_referee_web(now)
        except Exception:
            LOGGER.exception("QuantLab CardLab proactive referee web bootstrap failed")

        collection_budget_exhausted = False
        updated_card_referees: frozenset[str] = frozenset()
        try:
            (
                result["card_referee_scopes_refreshed"],
                result["card_referee_statistics_backfilled"],
                updated_card_referees,
            ) = self._bootstrap_card_referee_history(now)
        except ApiBudgetExceededError:
            collection_budget_exhausted = True
            LOGGER.warning(
                "Shared football API daily budget reached; CardLab referee bootstrap stopped"
            )
        except Exception:
            LOGGER.exception("QuantLab CardLab referee bootstrap failed")

        if not collection_budget_exhausted:
            try:
                result["fixtures_discovered"] = self._discover_fixtures(now)
                result["history_backfilled"] = self._backfill_history(now)
                market_fixtures, card_snapshots = self._collect_upcoming(
                    now,
                    force_card_referees=updated_card_referees,
                    force_card_web_leagues=refreshed_card_web_leagues,
                )
                result["market_fixtures"] = market_fixtures
                result["card_snapshots"] = card_snapshots
                result["h2h_snapshots"] = self._collect_h2h_snapshots(now)
            except ApiBudgetExceededError:
                collection_budget_exhausted = True
                LOGGER.warning(
                    "Shared football API daily budget reached; core collection stopped for UTC day"
                )
            except FeatureLeakageError:
                LOGGER.exception(
                    "QuantLab rejected a feature snapshot because of timestamp leakage"
                )

        if not collection_budget_exhausted:
            try:
                goal_discoveries, goal_stats = self._bootstrap_goal_team_history(now)
                result["goal_team_history_discovered"] = goal_discoveries
                result["goal_team_statistics_backfilled"] = goal_stats
                result["goal_player_history_backfilled"] = self._bootstrap_goal_player_history(now)
            except ApiBudgetExceededError:
                collection_budget_exhausted = True
                LOGGER.warning(
                    "Shared football API daily budget reached; GoalLab history collection stopped"
                )
            except FeatureLeakageError:
                LOGGER.exception(
                    "QuantLab rejected a GoalLab feature snapshot because of timestamp leakage"
                )

        if not collection_budget_exhausted:
            try:
                team_discoveries, team_stats = self._bootstrap_corner_team_history(now)
                result["corner_team_history_discovered"] = team_discoveries
                result["corner_team_statistics_backfilled"] = team_stats
            except ApiBudgetExceededError:
                collection_budget_exhausted = True
                LOGGER.warning(
                    "Shared football API daily budget reached; CornerLab history collection stopped"
                )
            except FeatureLeakageError:
                LOGGER.exception(
                    "QuantLab rejected a CornerLab feature snapshot because of timestamp leakage"
                )

        try:
            h2h_decisions, h2h_picks = self._evaluate_h2h_picks(now)
            result["h2h_decisions"] = h2h_decisions
            result["h2h_picks"] = h2h_picks
        except Exception:
            LOGGER.exception("QuantLab H2HLab shadow evaluation failed")

        try:
            result["h2h_result_refreshes"] = self._refresh_h2h_pick_results(now)
        except ApiBudgetExceededError:
            LOGGER.warning("Shared football API daily budget reached; H2HLab result refresh skipped")
        except Exception:
            LOGGER.exception("QuantLab H2HLab result refresh failed")

        try:
            result["h2h_settlements"] = self._settle_h2h_picks(now)
        except Exception:
            LOGGER.exception("QuantLab H2HLab settlement failed")

        try:
            corner_decisions, corner_picks = self._evaluate_context_picks(
                self._corner_engine, "CORNER", now
            )
            result["corner_decisions"] = corner_decisions
            result["corner_picks"] = corner_picks
        except Exception:
            LOGGER.exception("QuantLab CornerLab shadow evaluation failed")

        try:
            card_decisions, card_picks = self._evaluate_context_picks(
                self._card_engine, "CARD", now
            )
            result["card_decisions"] = card_decisions
            result["card_picks"] = card_picks
        except Exception:
            LOGGER.exception("QuantLab CardLab shadow evaluation failed")

        LOGGER.info(
            "QuantLab cycle completed fixtures_discovered=%d history_backfilled=%d "
            "goal_team_history_discovered=%d goal_team_statistics_backfilled=%d "
            "goal_player_history_backfilled=%d "
            "corner_team_history_discovered=%d corner_team_statistics_backfilled=%d "
            "card_referee_scopes_refreshed=%d card_referee_statistics_backfilled=%d "
            "card_referee_web_captures=%d card_referee_web_profiles=%d "
            "market_fixtures=%d card_snapshots=%d goal_decisions=%d goal_picks=%d "
            "goal_result_refreshes=%d goal_settlements=%d h2h_snapshots=%d "
            "h2h_decisions=%d h2h_picks=%d h2h_result_refreshes=%d h2h_settlements=%d corner_decisions=%d "
            "corner_picks=%d corner_settlements=%d "
            "card_decisions=%d card_picks=%d",
            result["fixtures_discovered"],
            result["history_backfilled"],
            result["goal_team_history_discovered"],
            result["goal_team_statistics_backfilled"],
            result["goal_player_history_backfilled"],
            result["corner_team_history_discovered"],
            result["corner_team_statistics_backfilled"],
            result["card_referee_scopes_refreshed"],
            result["card_referee_statistics_backfilled"],
            result["card_referee_web_captures"],
            result["card_referee_web_profiles"],
            result["market_fixtures"],
            result["card_snapshots"],
            result["goal_decisions"],
            result["goal_picks"],
            result["goal_result_refreshes"],
            result["goal_settlements"],
            result["h2h_snapshots"],
            result["h2h_decisions"],
            result["h2h_picks"],
            result["h2h_result_refreshes"],
            result["h2h_settlements"],
            result["corner_decisions"],
            result["corner_picks"],
            result["corner_settlements"],
            result["card_decisions"],
            result["card_picks"],
        )
        return result
