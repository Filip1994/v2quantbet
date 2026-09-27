import inspect

from h2h.quantlab.card_lab.audit import (
    BOOKMAKER_ID,
    MODEL_VERSION,
    POLICY_VERSION,
    PROVIDER_BET_ID,
    collect_cardlab_v4_audit,
)


def test_cardlab_v4_audit_is_read_only_and_single_book() -> None:
    source = inspect.getsource(collect_cardlab_v4_audit)

    assert POLICY_VERSION == "CARDLAB_1XBET_POISSON_POLICY_V4"
    assert MODEL_VERSION == "CARDLAB_REFEREE_POISSON_V1"
    assert BOOKMAKER_ID == 11
    assert PROVIDER_BET_ID == 119
    assert "quantlab_context_market_decisions" in source
    assert "quantlab_market_observations" in source
    assert "quantlab_card_feature_snapshots" in source
    assert "edge >= 0.03" in source
    assert "expected_value >= 0.03" in source
    assert "INSERT " not in source
    assert "UPDATE " not in source
    assert "DELETE " not in source
