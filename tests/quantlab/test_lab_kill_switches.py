from datetime import UTC, datetime, timedelta

from h2h.quantlab.runtime import QuantLabRuntime, QuantLabRuntimeSettings


NOW = datetime(2026, 10, 4, 2, 0, tzinfo=UTC)


class _TrackingRuntime(QuantLabRuntime):
    def __init__(self, settings: QuantLabRuntimeSettings) -> None:
        super().__init__(object(), object(), settings=settings, clock=lambda: NOW)
        self.calls: list[str] = []

    def _evaluate_goal_picks(self, _now):
        self.calls.append("goal:evaluate")
        return 0, 0

    def _refresh_goal_pick_results(self, _now):
        self.calls.append("goal:results")
        return 0

    def _settle_goal_picks(self, _now):
        self.calls.append("goal:settle")
        return 0

    def _refresh_corner_pick_results(self, _now):
        self.calls.append("corner:results")
        return 0

    def _refresh_corner_pick_statistics(self, _now):
        self.calls.append("corner:statistics")
        return 0

    def _settle_corner_picks(self, _now):
        self.calls.append("corner:settle")
        return 0

    def _refresh_card_pick_results(self, _now):
        self.calls.append("card:results")
        return 0

    def _capture_card_pick_events(self, _now):
        self.calls.append("card:events")
        return 0

    def _settle_card_picks(self, _now):
        self.calls.append("card:settle")
        return 0

    def _bootstrap_referee_web(self, _now):
        self.calls.append("card:web")
        return 0, 0, frozenset()

    def _bootstrap_card_referee_history(self, _now):
        self.calls.append("card:referee")
        return 0, 0, frozenset()

    def _discover_fixtures(self, _now):
        self.calls.append("core:discover")
        return 0

    def _backfill_history(self, _now):
        self.calls.append("core:history")
        return 0

    def _collect_upcoming(self, _now, **_kwargs):
        self.calls.append("core:markets")
        return 0, 0

    def _collect_h2h_snapshots(self, _now):
        self.calls.append("h2h:snapshots")
        return 0

    def _bootstrap_goal_team_history(self, _now):
        self.calls.append("goal:team-history")
        return 0, 0

    def _bootstrap_goal_player_history(self, _now):
        self.calls.append("goal:player-history")
        return 0

    def _bootstrap_corner_team_history(self, _now):
        self.calls.append("corner:team-history")
        return 0, 0

    def _evaluate_h2h_picks(self, _now):
        self.calls.append("h2h:evaluate")
        return 0, 0, 0

    def _refresh_h2h_pick_results(self, _now):
        self.calls.append("h2h:results")
        return 0

    def _refresh_h2h_experiment_results(self, _now):
        self.calls.append("h2h:experiment-results")
        return 0

    def _settle_h2h_picks(self, _now):
        self.calls.append("h2h:settle")
        return 0

    def _settle_h2h_experiments(self, _now):
        self.calls.append("h2h:experiment-settle")
        return 0

    def _evaluate_context_picks(self, _engine, lab, _now):
        self.calls.append(f"{lab.casefold()}:evaluate")
        return 0, 0


def test_lab_switch_defaults_are_enabled() -> None:
    settings = QuantLabRuntimeSettings()
    assert settings.goal_enabled is True
    assert settings.corner_enabled is True
    assert settings.card_enabled is True
    assert settings.h2h_enabled is True


def test_cardlab_switch_stops_every_card_branch_while_others_continue() -> None:
    runtime = _TrackingRuntime(
        QuantLabRuntimeSettings(
            goal_enabled=True,
            corner_enabled=True,
            card_enabled=False,
            h2h_enabled=True,
        )
    )

    runtime.run_once()

    assert any(call.startswith("goal:") for call in runtime.calls)
    assert any(call.startswith("corner:") for call in runtime.calls)
    assert any(call.startswith("h2h:") for call in runtime.calls)
    assert "core:discover" in runtime.calls
    assert not any(call.startswith("card:") for call in runtime.calls)


def test_all_lab_switches_off_make_cycle_provider_work_inert() -> None:
    runtime = _TrackingRuntime(
        QuantLabRuntimeSettings(
            goal_enabled=False,
            corner_enabled=False,
            card_enabled=False,
            h2h_enabled=False,
        )
    )

    result = runtime.run_once()

    assert runtime.calls == []
    assert all(value == 0 for value in result.values())


def test_cardlab_disabled_is_removed_from_market_collection_allowlist() -> None:
    fixture = {
        "fixture_id": "api-football:1",
        "provider_fixture_id": 1,
        "league_id": 39,
        "season": 2026,
        "home_team_id": 10,
        "away_team_id": 11,
        "home_team": "Home",
        "away_team": "Away",
        "competition_name": "Premier League",
        "country": "England",
        "competition_type": "League",
        "kickoff_at": NOW + timedelta(hours=2),
        "provider_status": "NS",
    }

    class Repo:
        def upcoming_fixtures(self, **_kwargs):
            return (fixture,)

        def market_capture_due(self, *_args, **_kwargs):
            return True

        def market_labs_for_fixture(self, _fixture_id):
            return frozenset()

    class Collector:
        def __init__(self):
            self.allowed_labs = None

        def collect_fixture(self, **kwargs):
            self.allowed_labs = set(kwargs["allowed_labs"])

    runtime = QuantLabRuntime(
        Repo(),
        object(),
        settings=QuantLabRuntimeSettings(
            goal_enabled=False,
            corner_enabled=True,
            card_enabled=False,
            h2h_enabled=False,
        ),
        clock=lambda: NOW,
    )
    collector = Collector()
    runtime._collector = collector

    market_fixtures, card_snapshots = runtime._collect_upcoming(NOW)

    assert market_fixtures == 1
    assert card_snapshots == 0
    assert collector.allowed_labs == {"CORNER"}


def test_goal_history_cache_released_before_following_labs() -> None:
    runtime = _TrackingRuntime(QuantLabRuntimeSettings())

    class Cache:
        def release_cached_scoring_context(self) -> None:
            runtime.calls.append("goal:cache-released")

    runtime._goal_engine = Cache()
    runtime.run_once()

    assert runtime.calls.index("goal:evaluate") < runtime.calls.index(
        "goal:cache-released"
    ) < runtime.calls.index("goal:results")
    assert "card:referee" in runtime.calls


def test_goal_cache_is_released_even_on_evaluation_failure() -> None:
    class BrokenGoalRuntime(_TrackingRuntime):
        def _evaluate_goal_picks(self, _now):
            self.calls.append("goal:evaluate-failed")
            raise RuntimeError("test failure")

    runtime = BrokenGoalRuntime(QuantLabRuntimeSettings())

    class Cache:
        def release_cached_scoring_context(self) -> None:
            runtime.calls.append("goal:cache-released")

    runtime._goal_engine = Cache()
    result = runtime.run_once()

    assert result["goal_decisions"] == 0
    assert runtime.calls.index("goal:evaluate-failed") < runtime.calls.index(
        "goal:cache-released"
    ) < runtime.calls.index("goal:results")
    assert "corner:results" in runtime.calls
