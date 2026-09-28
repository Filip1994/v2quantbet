from __future__ import annotations

from datetime import UTC, datetime, timedelta

from h2h.quantlab.goal_lab.audit import (
    METHOD_VERSION,
    _leakage_audit,
    build_goal_model_validation,
)


NOW = datetime(2026, 9, 27, 0, 0, tzinfo=UTC)
MODEL_VERSION = "DC_PLUS_PRO_STRUCTURAL_V1:" + "d" * 64


def _row(index: int) -> dict[str, object]:
    return {
        "fixture_id": f"history-{index}",
        "league_id": 39,
        "season": 2026,
        "competition_name": "Premier League",
        "home_team_id": 1 if index % 2 == 0 else 2,
        "away_team_id": 2 if index % 2 == 0 else 1,
        "kickoff_at": NOW - timedelta(days=40 - index),
        "home_goals": index % 3,
        "away_goals": (index + 1) % 2,
    }


class Repo:
    def goal_model_contract(self, model_version=None):
        assert model_version == MODEL_VERSION
        return {
            "model_version": MODEL_VERSION,
            "training_cutoff": NOW,
            "feature_version": "GOALLAB_DC_PLUS_STRUCTURAL_FEATURES_V1",
            "training_sample_size": 5,
            "history_match_count": 10,
            "training_payload": {"contract_coverage": {"A_BASE_DC": {"status": "FULL"}}},
        }

    def goal_model_history(self, *, before, limit):
        assert before == NOW
        assert limit == 10_000
        return tuple(_row(index) for index in range(10))


def test_goal_validation_records_insufficient_history_without_granting_review() -> None:
    validation = build_goal_model_validation(
        Repo(),
        model_version=MODEL_VERSION,
        evaluated_at=NOW,
    )

    assert validation.method_version == METHOD_VERSION
    assert validation.status == "INSUFFICIENT_HISTORY"
    assert validation.authority_review_status == "NOT_READY"
    assert validation.common_evaluation_size == 0
    assert validation.leakage_audit["status"] == "PASS"


def test_goal_validation_leakage_contract_forbids_target_live_and_market_inputs() -> None:
    audit = _leakage_audit()

    assert audit["status"] == "PASS"
    checks = audit["checks"]
    assert checks["chronological_feature_construction"] is True
    assert checks["target_result_excluded_from_target_features"] is True
    assert checks["target_match_live_statistics_used"] is False
    assert checks["bookmaker_features_used_in_probability_model"] is False
    assert checks["provider_predictions_used_in_probability_model"] is False


def test_existing_validation_is_logged_with_diagnostics() -> None:
    import inspect

    from h2h.quantlab.goal_lab import audit

    source = inspect.getsource(audit.ensure_latest_goal_model_validation)

    assert "GoalLab DC+ validation existing" in source
    assert "existing.get(\"contract_snapshot\")" in source
    assert "existing.get(\"comparison\")" in source
