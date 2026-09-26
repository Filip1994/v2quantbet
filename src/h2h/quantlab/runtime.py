"""Independent QuantLab collection/context runtime."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from h2h.odds.budget import ApiBudgetExceededError
from h2h.quantlab.card_lab.context import parse_fixture_context, parse_fixture_statistics
from h2h.quantlab.card_lab.features import FeatureLeakageError, build_cardlab_snapshot
from h2h.quantlab.fixture_discovery import parse_fixture_discovery_response
from h2h.quantlab.market_collector import QuantLabMarketCollector
from h2h.quantlab.scope import card_corner_scope, goal_scope


LOGGER = logging.getLogger("quantbet.quantlab")


@dataclass(frozen=True, slots=True)
class QuantLabRuntimeSettings:
    lookahead_hours: int = 36
    discovery_lookback_days: int = 1
    fixture_limit: int = 250
    fixture_discovery_refresh_seconds: int = 21600
    market_refresh_seconds: int = 43200
    context_refresh_seconds: int = 21600
    standings_refresh_seconds: int = 21600
    feature_refresh_seconds: int = 1800
    history_backfill_per_cycle: int = 0

    def __post_init__(self) -> None:
        for name, value in (
            ("lookahead_hours", self.lookahead_hours),
            ("fixture_limit", self.fixture_limit),
            ("fixture_discovery_refresh_seconds", self.fixture_discovery_refresh_seconds),
            ("market_refresh_seconds", self.market_refresh_seconds),
            ("context_refresh_seconds", self.context_refresh_seconds),
            ("standings_refresh_seconds", self.standings_refresh_seconds),
            ("feature_refresh_seconds", self.feature_refresh_seconds),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        for name, value in (
            ("discovery_lookback_days", self.discovery_lookback_days),
            ("history_backfill_per_cycle", self.history_backfill_per_cycle),
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
        corner_engine: Any | None = None,
        card_engine: Any | None = None,
    ) -> None:
        self._repository = repository
        self._provider = provider
        self._settings = settings or QuantLabRuntimeSettings()
        self._clock = clock
        self._collector = QuantLabMarketCollector(repository, provider)
        self._goal_engine = goal_engine
        self._corner_engine = corner_engine
        self._card_engine = card_engine

    @staticmethod
    def _scope_kwargs(fixture: dict[str, Any]) -> dict[str, object]:
        return {
            "country": fixture.get("country"),
            "competition_name": fixture.get("competition_name"),
            "competition_type": fixture.get("competition_type"),
            "home_team": fixture.get("home_team"),
            "away_team": fixture.get("away_team"),
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
            if not card_corner_scope(**self._scope_kwargs(fixture)).allowed:
                continue
            fixture_id = str(fixture["fixture_id"])
            context = self._repository.latest_context_before(fixture_id, decision_at=now)
            if context is None:
                payload = self._provider.fetch_fixture(int(fixture["provider_fixture_id"]))
                parsed = parse_fixture_context(
                    payload,
                    fixture_id=fixture_id,
                    provider_fixture_id=int(fixture["provider_fixture_id"]),
                    captured_at=now,
                )
                self._repository.save_fixture_context(parsed)
                context = {
                    "referee": parsed.referee,
                    "kickoff_at": parsed.kickoff_at,
                    "available_at": parsed.available_at,
                }
            if not context.get("referee"):
                continue
            if not self._repository.statistics_exists(fixture_id):
                payload = self._provider.fetch_statistics(int(fixture["provider_fixture_id"]))
                parsed_stats = parse_fixture_statistics(
                    payload,
                    fixture_id=fixture_id,
                    provider_fixture_id=int(fixture["provider_fixture_id"]),
                    home_team_id=int(fixture["home_team_id"]),
                    away_team_id=int(fixture["away_team_id"]),
                    captured_at=now,
                )
                self._repository.save_match_statistics(parsed_stats)
            completed += 1
        return completed

    def _collect_upcoming(self, now: datetime) -> tuple[int, int]:
        fixtures = self._repository.upcoming_fixtures(
            start_at=now,
            end_at=now + timedelta(hours=self._settings.lookahead_hours),
            limit=self._settings.fixture_limit,
        )
        market_fixtures = 0
        card_snapshots = 0
        for fixture in fixtures:
            scope = self._scope_kwargs(fixture)
            goal_allowed = goal_scope(**scope).allowed
            context_allowed = card_corner_scope(**scope).allowed
            if not goal_allowed and not context_allowed:
                continue

            fixture_id = str(fixture["fixture_id"])
            allowed_labs = {"GOAL"} if goal_allowed else set()
            if context_allowed:
                allowed_labs.update({"CORNER", "CARD", "UNCLASSIFIED"})
            if self._repository.market_capture_due(
                fixture_id,
                now=now,
                refresh_seconds=self._settings.market_refresh_seconds,
            ):
                self._collector.collect_fixture(
                    fixture_id=fixture_id,
                    provider_fixture_id=int(fixture["provider_fixture_id"]),
                    captured_at=now,
                    allowed_labs=allowed_labs,
                )
                market_fixtures += 1

            if not context_allowed:
                continue
            context = self._capture_context(fixture, now)
            standings = self._standings(fixture, now)
            if context is None:
                continue
            if not self._repository.feature_snapshot_due(
                fixture_id,
                now=now,
                refresh_seconds=self._settings.feature_refresh_seconds,
            ):
                continue
            referee = context.get("referee")
            history = (
                self._repository.referee_history(str(referee), decision_at=now)
                if referee
                else ()
            )
            snapshot = build_cardlab_snapshot(
                fixture_id=fixture_id,
                decision_at=now,
                kickoff_at=context.get("kickoff_at") or fixture["kickoff_at"],
                referee=None if referee is None else str(referee),
                referee_available_at=context.get("available_at"),
                referee_history=history,
                home_team=str(fixture["home_team"]),
                away_team=str(fixture["away_team"]),
                home_team_id=int(fixture["home_team_id"]),
                away_team_id=int(fixture["away_team_id"]),
                competition_name=str(fixture["competition_name"]),
                standings_payload=None if standings is None else standings["raw_payload"],
                standings_available_at=None if standings is None else standings["available_at"],
            )
            self._repository.save_card_feature_snapshot(snapshot)
            card_snapshots += 1
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
            outcome = self._goal_engine.run_fixture(fixture, decision_at=now)
            decisions += int(outcome.decisions_inserted)
            picks += int(outcome.picks_inserted)
        return decisions, picks

    def _evaluate_count_picks(self, now: datetime) -> tuple[int, int, int, int]:
        if self._corner_engine is None and self._card_engine is None:
            return 0, 0, 0, 0
        fixtures = self._repository.upcoming_fixtures(
            start_at=now,
            end_at=now + timedelta(hours=self._settings.lookahead_hours),
            limit=self._settings.fixture_limit,
        )
        corner_decisions = 0
        corner_picks = 0
        card_decisions = 0
        card_picks = 0
        for fixture in fixtures:
            if not card_corner_scope(**self._scope_kwargs(fixture)).allowed:
                continue
            if self._corner_engine is not None:
                outcome = self._corner_engine.run_fixture(fixture, decision_at=now)
                corner_decisions += int(outcome.decisions_inserted)
                corner_picks += int(outcome.picks_inserted)
            if self._card_engine is not None:
                outcome = self._card_engine.run_fixture(fixture, decision_at=now)
                card_decisions += int(outcome.decisions_inserted)
                card_picks += int(outcome.picks_inserted)
        return corner_decisions, corner_picks, card_decisions, card_picks

    def run_once(self) -> dict[str, int]:
        now = self._clock().astimezone(UTC)
        result = {
            "fixtures_discovered": 0,
            "history_backfilled": 0,
            "market_fixtures": 0,
            "card_snapshots": 0,
            "goal_decisions": 0,
            "goal_picks": 0,
            "corner_decisions": 0,
            "corner_picks": 0,
            "card_decisions": 0,
            "card_picks": 0,
        }
        try:
            result["fixtures_discovered"] = self._discover_fixtures(now)
            result["history_backfilled"] = self._backfill_history(now)
            market_fixtures, card_snapshots = self._collect_upcoming(now)
            result["market_fixtures"] = market_fixtures
            result["card_snapshots"] = card_snapshots
        except ApiBudgetExceededError:
            LOGGER.warning("QuantLab API hard ceiling reached; collection stopped for UTC day")
        except FeatureLeakageError:
            LOGGER.exception("QuantLab rejected a feature snapshot because of timestamp leakage")

        # Shadow evaluation is intentionally independent from provider budget. Existing
        # persisted quotes can still produce auditable PASS/PICK decisions after the
        # daily API ceiling has stopped collection.
        try:
            goal_decisions, goal_picks = self._evaluate_goal_picks(now)
            result["goal_decisions"] = goal_decisions
            result["goal_picks"] = goal_picks
        except Exception:
            LOGGER.exception("QuantLab GoalLab shadow evaluation failed")

        try:
            (
                corner_decisions,
                corner_picks,
                card_decisions,
                card_picks,
            ) = self._evaluate_count_picks(now)
            result["corner_decisions"] = corner_decisions
            result["corner_picks"] = corner_picks
            result["card_decisions"] = card_decisions
            result["card_picks"] = card_picks
        except Exception:
            LOGGER.exception("QuantLab CornerLab/CardLab shadow evaluation failed")

        LOGGER.info(
            "QuantLab cycle completed fixtures_discovered=%d history_backfilled=%d "
            "market_fixtures=%d card_snapshots=%d goal_decisions=%d goal_picks=%d "
            "corner_decisions=%d corner_picks=%d card_decisions=%d card_picks=%d",
            result["fixtures_discovered"],
            result["history_backfilled"],
            result["market_fixtures"],
            result["card_snapshots"],
            result["goal_decisions"],
            result["goal_picks"],
            result["corner_decisions"],
            result["corner_picks"],
            result["card_decisions"],
            result["card_picks"],
        )
        return result
