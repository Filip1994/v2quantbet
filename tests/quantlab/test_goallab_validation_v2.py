from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
import numpy as np

from h2h.quantlab.goal_lab import audit


NOW = datetime(2026, 9, 28, 0, 0, tzinfo=UTC)
MODEL_VERSION = "DC_PLUS_PRO_STRUCTURAL_V1:" + "e" * 64


def _history_rows() -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    index = 0
    for match_index in range(50):
        for league_offset in range(20):
            league_id = 1000 + league_offset
            teams = [league_id * 10 + offset for offset in range(4)]
            home_team = teams[match_index % 4]
            away_team = teams[(match_index + 1) % 4]
            rows.append(
                {
                    "fixture_id": f"history-{index}",
                    "league_id": league_id,
                    "season": 2026,
                    "competition_name": f"League {league_id}",
                    "home_team_id": home_team,
                    "away_team_id": away_team,
                    "kickoff_at": NOW - timedelta(days=1000 - index),
                    "home_goals": match_index % 4,
                    "away_goals": (match_index + league_offset) % 3,
                }
            )
            index += 1
    return tuple(rows)


class Repo:
    def goal_model_contract(self, model_version=None):
        assert model_version == MODEL_VERSION
        return {
            "model_version": MODEL_VERSION,
            "training_cutoff": NOW,
            "feature_version": "GOALLAB_DC_PLUS_STRUCTURAL_FEATURES_V1",
            "training_sample_size": 700,
            "history_match_count": 1000,
            "training_payload": {"contract_coverage": {"A_BASE_DC": {"status": "FULL"}}},
        }

    def goal_model_history(self, *, before, limit):
        assert before == NOW
        assert limit == 10_000
        return _history_rows()


class FakeControl:
    def __init__(self, records):
        self.team_ids = tuple(
            sorted(
                {record.home_id for record in records}
                | {record.away_id for record in records}
            )
        )
        self.rho = -0.05

    def expected_goals(self, home_id: int, away_id: int) -> tuple[float, float]:
        assert home_id in self.team_ids
        assert away_id in self.team_ids
        return 1.35, 1.10


def test_validation_v2_uses_pooled_control_when_leagues_are_too_small(monkeypatch) -> None:
    control_fit_sizes: list[int] = []

    def fake_control_fit(records, **_kwargs):
        control_fit_sizes.append(len(records))
        return FakeControl(records)

    def fake_dc_plus_fit(
        x,
        _y_home,
        _y_away,
        home_ids,
        away_ids,
        league_ids,
        _dates,
        _feature_names,
        *,
        reference_time,
    ):
        assert reference_time <= NOW
        teams = sorted(set(home_ids.tolist()) | set(away_ids.tolist()))
        leagues = sorted(set(league_ids.tolist()))
        params = {
            "attacks": {str(team_id): 0.0 for team_id in teams},
            "defenses": {str(team_id): 0.0 for team_id in teams},
            "league_effects": {str(league_id): 0.0 for league_id in leagues},
            "intercept": math.log(1.2),
            "home_advantage": 0.10,
            "rho": -0.05,
            "beta_home": np.zeros(x.shape[1], dtype=float).tolist(),
            "beta_away": np.zeros(x.shape[1], dtype=float).tolist(),
        }
        return params, 1.0

    monkeypatch.setattr(audit.DixonColesModel, "fit", staticmethod(fake_control_fit))
    monkeypatch.setattr(audit, "_fit_dc_plus", fake_dc_plus_fit)

    validation = audit.build_goal_model_validation(
        Repo(),
        model_version=MODEL_VERSION,
        evaluated_at=NOW,
    )

    assert validation.method_version == "GOALLAB_CHRONOLOGICAL_HOLDOUT_V2"
    assert validation.status == "OK"
    assert validation.common_evaluation_size >= audit.MIN_COMMON_EVALUATION
    assert validation.authority_review_status == "READY_FOR_MANUAL_REVIEW"
    assert validation.comparison["control_leagues_fitted"] == []
    assert validation.comparison["pooled_control_fitted"] is True
    assert validation.comparison["control_scope_counts"]["pooled"] >= audit.MIN_COMMON_EVALUATION
    assert control_fit_sizes
    assert min(control_fit_sizes) >= audit.CONTROL_MIN_MATCHES


def test_validation_repository_lookup_is_method_specific() -> None:
    import inspect

    source = inspect.getsource(audit.ensure_latest_goal_model_validation)

    assert "method_version=METHOD_VERSION" in source
