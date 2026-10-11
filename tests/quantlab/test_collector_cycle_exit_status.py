from __future__ import annotations

from unittest.mock import Mock

import pytest

from h2h.quantlab import entrypoint


@pytest.mark.parametrize("failure", [None, RuntimeError("provider failed")])
def test_one_shot_cycle_exit_matches_runtime_result(
    monkeypatch: pytest.MonkeyPatch, failure: RuntimeError | None
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://example.invalid/quantbet")
    monkeypatch.setenv("API_FOOTBALL_KEY", "test-only")
    monkeypatch.setenv("QUANTBET_QUANTLAB_COLLECTOR_ONLY", "true")
    monkeypatch.setenv("QUANTBET_QUANTLAB_ONE_SHOT", "true")
    for lab in ("GOAL", "CORNER", "CARD", "H2H"):
        monkeypatch.setenv(f"QUANTBET_QUANTLAB_{lab}_ENABLED", "false")

    repository = Mock()
    repository.check_database.return_value = True
    repository.api_usage_today.return_value = 0
    monkeypatch.setattr(entrypoint, "configure_logging", Mock())
    monkeypatch.setattr(entrypoint, "install_shutdown_handlers", Mock())
    monkeypatch.setattr(entrypoint, "PostgreSQLQuantLabRepository", Mock(return_value=repository))
    monkeypatch.setattr(entrypoint, "assert_goallab_v1_contract", Mock(return_value={
        "lock_version": "test", "model_prefix": "test", "feature_version": "test",
        "evaluation_policy_version": "test", "pick_policy_version": "test",
        "settlement_rule_version": "test", "validation_method_version": "test",
    }))
    for constructor in (
        "QuantLabRequestBudget", "QuantLabApiFootballClient",
        "LoadActiveDixonColesModel", "PostgreSQLDixonColesModelVersionRepository",
        "PostgreSQLActiveDixonColesModelRepository", "GoalLabShadowPickEngine",
        "GoalLabStructuralShadowEngine", "StructuralGoalPolicy", "GoalLabCompositeEngine",
        "H2HLabEngine", "CornerLabShadowPickEngine", "CardLabShadowPickEngine",
        "QuantLabRuntimeSettings",
    ):
        monkeypatch.setattr(entrypoint, constructor, Mock())
    monkeypatch.setattr(entrypoint, "_market_archive_writer", Mock(return_value=None))

    runtime = Mock()
    if failure is not None:
        runtime.run_once.side_effect = failure
    else:
        runtime.run_once.return_value = {}
    monkeypatch.setattr(entrypoint, "QuantLabRuntime", Mock(return_value=runtime))

    if failure is None:
        entrypoint.main()
    else:
        with pytest.raises(RuntimeError, match="provider failed"):
            entrypoint.main()

    runtime.run_once.assert_called_once_with()
