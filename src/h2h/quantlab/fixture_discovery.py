"""QuantLab-owned global API-Football fixture discovery parsing."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from h2h.domain.competition_scope import is_womens_football
from h2h.domain.fixture import Fixture
from h2h.use_cases.api_football_fixture_adapter import ApiFootballFixtureAdapter


@dataclass(frozen=True, slots=True)
class QuantLabFixtureObservation:
    fixture_observation_id: str
    fixture: Fixture
    captured_at: datetime
    raw_payload: dict[str, Any]


def _aware_utc(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _identifier(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return "quantlab-fixture-v1:" + sha256(canonical).hexdigest()


def parse_fixture_discovery_response(
    payload: Mapping[str, Any],
    *,
    captured_at: datetime,
) -> tuple[QuantLabFixtureObservation, ...]:
    """Parse one global date shard, dropping globally prohibited women fixtures."""
    captured = _aware_utc(captured_at, "captured_at")
    if not isinstance(payload, Mapping):
        raise TypeError("fixture discovery payload must be a mapping")
    errors = payload.get("errors")
    if errors:
        raise RuntimeError(f"API-Football returned errors: {errors}")
    response = payload.get("response", [])
    if not isinstance(response, Sequence) or isinstance(response, (str, bytes)):
        raise TypeError("API-Football fixture discovery response must be a list")

    adapter = ApiFootballFixtureAdapter()
    observations: list[QuantLabFixtureObservation] = []
    for raw in response:
        if not isinstance(raw, Mapping):
            continue
        fixture = adapter.adapt(raw)
        if is_womens_football(
            competition_name=fixture.competition_name,
            competition_type=fixture.competition_type,
            home_team=fixture.home_team,
            away_team=fixture.away_team,
        ):
            continue
        raw_payload = dict(raw)
        observation_id = _identifier(
            {
                "fixture_id": fixture.fixture_id,
                "provider_fixture_id": fixture.provider_fixture_id,
                "kickoff_at": fixture.kickoff_at.isoformat(),
                "status": fixture.status,
                "captured_at": captured.isoformat(),
                "raw_payload": raw_payload,
            }
        )
        observations.append(
            QuantLabFixtureObservation(
                fixture_observation_id=observation_id,
                fixture=fixture,
                captured_at=captured,
                raw_payload=raw_payload,
            )
        )
    return tuple(observations)
