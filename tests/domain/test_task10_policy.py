from dataclasses import replace
from decimal import Decimal

import pytest

from h2h.domain.odds import Market, Selection
from h2h.domain.registration_policy import RegistrationPolicyConfig


def policy(**changes) -> RegistrationPolicyConfig:
    values = {
        "allowed_market_selections": (
            (Market.OU_25, Selection.OVER),
            (Market.OU_25, Selection.UNDER),
            (Market.BTTS, Selection.YES),
            (Market.BTTS, Selection.NO),
        ),
        "allowed_devig_methods": ("PROPORTIONAL_TWO_WAY_V1",),
        "allowed_fixture_statuses": ("NS",),
        "minimum_edge": Decimal("0.03"),
        "minimum_expected_value": Decimal("0.02"),
        "minimum_odds": Decimal("1.40"),
        "maximum_odds": Decimal("3.50"),
        "maximum_quote_age_seconds": 300,
        "minimum_time_to_kickoff_seconds": 600,
        "bankroll_account_id": "pilot-rsd",
        "currency": "RSD",
        "initial_bankroll_minor": 3_000_000,
        "fixed_stake_minor": 30_000,
        "max_stake_per_pick_minor": 30_000,
        "max_open_exposure_minor": 300_000,
    }
    values.update(changes)
    return RegistrationPolicyConfig(**values)


def test_policy_contains_explicit_pilot_money_and_versions() -> None:
    value = policy()
    assert value.initial_bankroll_minor == 3_000_000
    assert value.fixed_stake_minor == 30_000
    assert value.max_open_exposure_minor == 300_000
    assert value.staking_policy_version == "FIXED_STAKE_V1"
    assert "DATABASE_URL" not in value.canonical_json


def test_fingerprint_is_order_independent_for_set_like_values() -> None:
    first = policy()
    second = replace(
        first,
        allowed_market_selections=tuple(reversed(first.allowed_market_selections)),
        allowed_fixture_statuses=("PENDING", "NS"),
    )
    third = replace(first, allowed_fixture_statuses=("NS", "PENDING"))
    assert second.fingerprint == third.fingerprint
    assert first.fingerprint != second.fingerprint


def test_policy_fingerprint_golden_vector() -> None:
    assert policy().fingerprint == (
        "pick-policy-config-v1:b0ee3241f613d36d5fe62aa8f1a53cfc72b1c25fdaa4fd260f6ae97280410d8a"
    )


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"allowed_fixture_statuses": ()}, "allowed_fixture_statuses"),
        ({"fixed_stake_minor": 0}, "fixed_stake_minor"),
        ({"minimum_odds": Decimal(1)}, "minimum_odds"),
        ({"maximum_odds": Decimal("1.2")}, "maximum_odds"),
    ],
)
def test_invalid_policy_fails_closed(change, message) -> None:
    with pytest.raises(ValueError, match=message):
        policy(**change)
