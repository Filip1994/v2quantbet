from datetime import UTC, datetime

from h2h.domain.pick_decision import (
    DecisionOutcome,
    PickDecision,
    RegistrationResult,
    RejectionStage,
)
from h2h.use_cases.register_pick import BootstrapBankroll, RegisterEligiblePick
from tests.domain.test_task10_policy import policy


NOW = datetime(2026, 9, 16, 12, tzinfo=UTC)


class Repository:
    def __init__(self):
        self.register_call = None
        self.bootstrap_call = None

    def register(self, evaluation_id, request_id, configured_policy, *, decided_at):
        self.register_call = (evaluation_id, request_id, configured_policy, decided_at)
        decision = PickDecision(
            "pick-decision-v1:" + "a" * 64,
            request_id,
            evaluation_id,
            "fixture-observation-v1:" + "b" * 64,
            configured_policy.fingerprint,
            decided_at,
            DecisionOutcome.REJECTED,
            RejectionStage.ELIGIBILITY,
            ("EDGE_BELOW_MINIMUM",),
        )
        return RegistrationResult(decision, None)

    def bootstrap_bankroll(self, configured_policy, *, occurred_at):
        self.bootstrap_call = (configured_policy, occurred_at)
        return "bootstrapped"


def test_registration_use_case_supplies_one_utc_decision_time() -> None:
    repository = Repository()
    result = RegisterEligiblePick(repository, policy(), clock=lambda: NOW).execute(
        "evaluation-1", "request-1"
    )
    assert result.decision.outcome is DecisionOutcome.REJECTED
    assert repository.register_call[3] == NOW


def test_minimum_playable_odds_uses_configured_minimum_ev() -> None:
    subject = RegisterEligiblePick(Repository(), policy(), clock=lambda: NOW)

    assert subject.minimum_playable_odds(0.5) == 2.04


def test_bankroll_bootstrap_is_explicit_not_a_composition_side_effect() -> None:
    repository = Repository()
    assert BootstrapBankroll(repository, policy(), clock=lambda: NOW).execute() == "bootstrapped"
    assert repository.bootstrap_call[1] == NOW
