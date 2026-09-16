"""Versioned configuration for durable pick registration decisions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256

from h2h.domain.odds import Market, Selection


POLICY_SCHEMA_VERSION = 1
ELIGIBILITY_POLICY_VERSION = "ELIGIBILITY_V1"
RISK_POLICY_VERSION = "RISK_V1"
STAKING_POLICY_VERSION = "FIXED_STAKE_V1"
BOOKMAKER_POLICY_VERSION = "SERBIA_ALLOWLIST_V1"
POLICY_FINGERPRINT_PREFIX = "pick-policy-config-v1:"


def _decimal(value: object, name: str) -> Decimal:
    if isinstance(value, bool):
        raise TypeError(f"{name} must be a decimal value")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception as exc:
        raise ValueError(f"{name} must be a decimal value") from exc
    if not result.is_finite():
        raise ValueError(f"{name} must be finite")
    return result


def _canonical_decimal(value: Decimal) -> str:
    normalized = value.normalize()
    return "0" if normalized == 0 else format(normalized, "f")


@dataclass(frozen=True, slots=True)
class RegistrationPolicyConfig:
    """All decision-affecting V1 registration configuration."""

    allowed_market_selections: tuple[tuple[Market, Selection], ...]
    allowed_devig_methods: tuple[str, ...]
    allowed_fixture_statuses: tuple[str, ...]
    minimum_edge: Decimal
    minimum_expected_value: Decimal
    minimum_odds: Decimal
    maximum_odds: Decimal
    maximum_quote_age_seconds: int
    minimum_time_to_kickoff_seconds: int
    bankroll_account_id: str
    currency: str
    initial_bankroll_minor: int
    fixed_stake_minor: int
    max_stake_per_pick_minor: int
    max_open_exposure_minor: int
    schema_version: int = POLICY_SCHEMA_VERSION
    eligibility_policy_version: str = ELIGIBILITY_POLICY_VERSION
    risk_policy_version: str = RISK_POLICY_VERSION
    staking_policy_version: str = STAKING_POLICY_VERSION
    bookmaker_policy_version: str = BOOKMAKER_POLICY_VERSION

    def __post_init__(self) -> None:
        pairs = tuple(self.allowed_market_selections)
        if not pairs:
            raise ValueError("allowed_market_selections must not be empty")
        valid = {
            Market.OU_25: {Selection.OVER, Selection.UNDER},
            Market.BTTS: {Selection.YES, Selection.NO},
        }
        for market, selection in pairs:
            if not isinstance(market, Market) or not isinstance(selection, Selection):
                raise TypeError("allowed market selections must use canonical enums")
            if selection not in valid[market]:
                raise ValueError(f"invalid market/selection pair: {market}/{selection}")
        if len(set(pairs)) != len(pairs):
            raise ValueError("allowed_market_selections must not contain duplicates")
        object.__setattr__(self, "allowed_market_selections", pairs)

        for name in ("allowed_devig_methods", "allowed_fixture_statuses"):
            values = tuple(
                value.strip() if isinstance(value, str) else value for value in getattr(self, name)
            )
            if not values or any(
                not isinstance(value, str) or not value.strip() for value in values
            ):
                raise ValueError(f"{name} must contain nonblank strings")
            if len(set(values)) != len(values):
                raise ValueError(f"{name} must not contain duplicates")
            object.__setattr__(self, name, values)

        for name in (
            "minimum_edge",
            "minimum_expected_value",
            "minimum_odds",
            "maximum_odds",
        ):
            object.__setattr__(self, name, _decimal(getattr(self, name), name))
        if self.minimum_odds <= 1:
            raise ValueError("minimum_odds must be greater than 1")
        if self.maximum_odds < self.minimum_odds:
            raise ValueError("maximum_odds must be at least minimum_odds")

        for name in ("maximum_quote_age_seconds", "minimum_time_to_kickoff_seconds"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        for name in (
            "initial_bankroll_minor",
            "fixed_stake_minor",
            "max_stake_per_pick_minor",
            "max_open_exposure_minor",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if not isinstance(self.bankroll_account_id, str) or not self.bankroll_account_id.strip():
            raise ValueError("bankroll_account_id must not be blank")
        if not isinstance(self.currency, str) or len(self.currency.strip()) != 3:
            raise ValueError("currency must be a three-letter code")
        object.__setattr__(self, "currency", self.currency.strip().upper())
        if self.schema_version != POLICY_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {POLICY_SCHEMA_VERSION}")
        expected_versions = {
            "eligibility_policy_version": ELIGIBILITY_POLICY_VERSION,
            "risk_policy_version": RISK_POLICY_VERSION,
            "staking_policy_version": STAKING_POLICY_VERSION,
            "bookmaker_policy_version": BOOKMAKER_POLICY_VERSION,
        }
        for name, expected in expected_versions.items():
            if getattr(self, name) != expected:
                raise ValueError(f"{name} must be {expected}")

    def canonical_payload(self) -> dict[str, object]:
        return {
            "allowed_devig_methods": sorted(self.allowed_devig_methods),
            "allowed_fixture_statuses": sorted(self.allowed_fixture_statuses),
            "allowed_market_selections": sorted(
                f"{market.value}/{selection.value}"
                for market, selection in self.allowed_market_selections
            ),
            "bankroll_account_id": self.bankroll_account_id,
            "bookmaker_policy_version": self.bookmaker_policy_version,
            "currency": self.currency,
            "eligibility_policy_version": self.eligibility_policy_version,
            "fixed_stake_minor": self.fixed_stake_minor,
            "initial_bankroll_minor": self.initial_bankroll_minor,
            "max_open_exposure_minor": self.max_open_exposure_minor,
            "max_stake_per_pick_minor": self.max_stake_per_pick_minor,
            "maximum_odds": _canonical_decimal(self.maximum_odds),
            "maximum_quote_age_seconds": self.maximum_quote_age_seconds,
            "minimum_edge": _canonical_decimal(self.minimum_edge),
            "minimum_expected_value": _canonical_decimal(self.minimum_expected_value),
            "minimum_odds": _canonical_decimal(self.minimum_odds),
            "minimum_time_to_kickoff_seconds": self.minimum_time_to_kickoff_seconds,
            "risk_policy_version": self.risk_policy_version,
            "schema_version": self.schema_version,
            "staking_policy_version": self.staking_policy_version,
        }

    @property
    def canonical_json(self) -> str:
        return json.dumps(
            self.canonical_payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=True
        )

    @property
    def fingerprint(self) -> str:
        digest = sha256(self.canonical_json.encode("utf-8")).hexdigest()
        return POLICY_FINGERPRINT_PREFIX + digest
