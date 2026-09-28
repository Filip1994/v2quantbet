from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
import numpy as np

from h2h.quantlab.goal_lab import audit


NOW = datetime(2026, 9, 28, 0, 0, tzinfo=UTC)
MODEL_VERSION = "DC_PLUS_PRO_STRUCTURAL_V3:" + "e" * 64


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
            "feature_version": "GOALLAB_DC_PLUS_STRUCTURAL_FEATURES_V2",
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


def test_validation_v4_uses_sparse_pooled_control_and_blocks_weak_challenger(monkeypatch) -> None:
    pooled_fit_sizes: list[int] = []

    def fake_pooled_fit(records, **_kwargs):
        pooled_fit_sizes.append(len(records))
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

    original_market_probabilities = audit._market_probabilities
    market_calls = 0

    def one_invalid_rho_row(lambda_home, lambda_away, rho):
        nonlocal market_calls
        market_calls += 1
        if market_calls == 1:
            raise ValueError("invalid DC+ rho correction")
        return original_market_probabilities(lambda_home, lambda_away, rho)

    monkeypatch.setattr(audit, "_fit_sparse_pooled_control", fake_pooled_fit)
    monkeypatch.setattr(audit, "_fit_dc_plus", fake_dc_plus_fit)
    monkeypatch.setattr(audit, "_market_probabilities", one_invalid_rho_row)

    validation = audit.build_goal_model_validation(
        Repo(),
        model_version=MODEL_VERSION,
        evaluated_at=NOW,
    )

    assert validation.method_version == "GOALLAB_CHRONOLOGICAL_HOLDOUT_V5"
    assert validation.status == "OK"
    assert validation.common_evaluation_size >= audit.MIN_COMMON_EVALUATION
    assert validation.authority_review_status == "NOT_READY"
    assert validation.comparison["promotion_gate"]["common_evaluation_ok"] is True
    assert validation.comparison["promotion_gate"]["leakage_ok"] is True
    assert not all(validation.comparison["promotion_gate"].values())
    assert validation.comparison["control_leagues_fitted"] == []
    assert validation.comparison["pooled_control_fitted"] is True
    assert validation.comparison["control_scope_counts"]["pooled"] >= audit.MIN_COMMON_EVALUATION
    assert validation.comparison["invalid_holdout_rows"] == 1
    assert validation.comparison["valid_common_coverage_pct"] > 90.0
    assert pooled_fit_sizes
    assert min(pooled_fit_sizes) >= audit.CONTROL_MIN_MATCHES


def test_validation_repository_lookup_is_method_specific() -> None:
    import inspect

    source = inspect.getsource(audit.ensure_latest_goal_model_validation)

    assert "method_version=METHOD_VERSION" in source



def test_sparse_pooled_control_keeps_sparse_team_matches() -> None:
    from types import SimpleNamespace

    records = []
    stable_teams = (1, 2, 3, 4)
    for index in range(10):
        records.append(
            SimpleNamespace(
                date=NOW - timedelta(days=110 - index),
                home_id=stable_teams[index % 4],
                away_id=stable_teams[(index + 1) % 4],
                home_goals=index % 3,
                away_goals=(index + 1) % 2,
            )
        )
    for index in range(90):
        records.append(
            SimpleNamespace(
                date=NOW - timedelta(days=100 - index),
                home_id=1000 + index * 2,
                away_id=1001 + index * 2,
                home_goals=index % 4,
                away_goals=(index + 2) % 3,
            )
        )

    control = audit._fit_sparse_pooled_control(records, reference_time=NOW)

    assert control.fitted_matches == 100
    assert 1000 in control.team_ids
    sparse_index = control.team_ids.index(1000)
    assert control.attacks[sparse_index] == 0.0
    assert control.defenses[sparse_index] == 0.0
    lambda_home, lambda_away = control.expected_goals(1000, 1001)
    assert lambda_home > 0.0
    assert lambda_away > 0.0


def test_validation_waits_for_active_v2_artifact() -> None:
    class HistoricalRepo:
        def goal_model_contract(self, model_version=None):
            assert model_version is None
            return {
                "model_version": "DC_PLUS_PRO_STRUCTURAL_V1:" + "f" * 64,
                "feature_version": "GOALLAB_DC_PLUS_STRUCTURAL_FEATURES_V1",
            }

        def goal_model_validation(self, *_args, **_kwargs):
            raise AssertionError("historical artifact must not enter V4 validation")

    class Logger:
        def info(self, *_args, **_kwargs):
            return None

    result = audit.ensure_latest_goal_model_validation(HistoricalRepo(), Logger())

    assert result["status"] == "WAITING_ACTIVE_MODEL"
    assert result["active_model_prefix"] == "DC_PLUS_PRO_STRUCTURAL_V3:"
    assert result["active_feature_version"] == "GOALLAB_DC_PLUS_STRUCTURAL_FEATURES_V2"
