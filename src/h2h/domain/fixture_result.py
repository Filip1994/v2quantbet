"""Immutable production fixture-result observations for settlement."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from typing import Any, Final


RESULT_NORMALIZER_VERSION: Final = "API_FOOTBALL_SETTLEMENT_RESULT_V1"
SETTLEABLE_STATUSES: Final = frozenset({"FT", "AET", "PEN"})
VOIDABLE_STATUSES: Final = frozenset({"CANC", "ABD", "AWD", "WO"})
NON_TERMINAL_STATUSES: Final = frozenset(
    {"TBD", "NS", "1H", "HT", "2H", "ET", "BT", "P", "SUSP", "INT", "PST", "LIVE"}
)


class ResultClassification(StrEnum):
    NON_TERMINAL = "NON_TERMINAL"
    PLAYED_SETTLEABLE = "PLAYED_SETTLEABLE"
    NON_PLAYED_VOIDABLE = "NON_PLAYED_VOIDABLE"
    INVALID_TERMINAL = "INVALID_TERMINAL"
    UNKNOWN_STATUS = "UNKNOWN_STATUS"


def _utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _score_pair(value: object, name: str) -> tuple[int | None, int | None]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be an object")
    if "home" not in value or "away" not in value:
        raise ValueError(f"{name} must contain home and away")
    home, away = value["home"], value["away"]
    if home is None and away is None:
        return None, None
    for score, field in ((home, "home"), (away, "away")):
        if isinstance(score, bool) or not isinstance(score, int) or score < 0:
            raise ValueError(f"{name}.{field} must be a non-negative integer or paired null")
    return home, away


@dataclass(frozen=True, slots=True)
class FixtureResultObservation:
    result_observation_id: str
    fixture_id: str
    provider: str
    provider_fixture_id: str
    provider_status: str
    provider_kickoff_at: datetime
    provider_home_team_id: int
    provider_away_team_id: int
    goals: tuple[int | None, int | None]
    fulltime: tuple[int | None, int | None]
    extratime: tuple[int | None, int | None]
    penalty: tuple[int | None, int | None]
    regulation_goals: tuple[int | None, int | None]
    classification: ResultClassification
    settlement_fingerprint: str | None
    normalizer_version: str
    provider_record_sha256: str
    provider_record: Mapping[str, Any]
    first_acquired_at: datetime
    persisted_at: datetime | None = None

    @property
    def is_terminal_candidate(self) -> bool:
        return self.classification in {
            ResultClassification.PLAYED_SETTLEABLE,
            ResultClassification.NON_PLAYED_VOIDABLE,
        }


class ApiFootballSettlementResultNormalizer:
    """Strictly normalize one API-Football fixture record for production settlement."""

    def normalize(
        self,
        payload: Mapping[str, Any],
        *,
        fixture_id: str,
        acquired_at: datetime,
    ) -> FixtureResultObservation:
        if not isinstance(payload, Mapping):
            raise TypeError("API-Football fixture result must be an object")
        acquired = _utc(acquired_at, "acquired_at")
        fixture = self._mapping(payload, "fixture")
        teams = self._mapping(payload, "teams")
        status = self._mapping(fixture, "status").get("short")
        if not isinstance(status, str) or not status.strip():
            raise ValueError("fixture.status.short must be nonblank")
        provider_fixture_id = self._positive_int(fixture.get("id"), "fixture.id")
        expected_fixture_id = f"api-football:{provider_fixture_id}"
        if fixture_id != expected_fixture_id:
            raise ValueError("provider fixture ID contradicts canonical fixture")
        kickoff = self._datetime(fixture.get("date"), "fixture.date")
        home_id = self._positive_int(self._mapping(teams, "home").get("id"), "teams.home.id")
        away_id = self._positive_int(self._mapping(teams, "away").get("id"), "teams.away.id")
        if home_id == away_id:
            raise ValueError("provider team IDs must be distinct")

        goals = _score_pair(self._mapping(payload, "goals"), "goals")
        score = self._mapping(payload, "score")
        fulltime = _score_pair(self._mapping(score, "fulltime"), "score.fulltime")
        extratime = _score_pair(self._mapping(score, "extratime"), "score.extratime")
        penalty = _score_pair(self._mapping(score, "penalty"), "score.penalty")

        classification, regulation = self._classify(
            status, goals=goals, fulltime=fulltime, extratime=extratime, penalty=penalty
        )
        fingerprint = None
        if classification is ResultClassification.PLAYED_SETTLEABLE:
            fingerprint = self._fingerprint(status, regulation)
        elif classification is ResultClassification.NON_PLAYED_VOIDABLE:
            fingerprint = self._fingerprint(status, (None, None))

        canonical = _canonical_json(payload)
        record_digest = sha256(canonical.encode("utf-8")).hexdigest()
        identity_payload = _canonical_json(
            {
                "fixture_id": fixture_id,
                "normalizer_version": RESULT_NORMALIZER_VERSION,
                "provider_record_sha256": record_digest,
            }
        )
        observation_id = "fixture-result-observation-v1:" + sha256(
            identity_payload.encode("utf-8")
        ).hexdigest()
        return FixtureResultObservation(
            observation_id,
            fixture_id,
            "api-football",
            str(provider_fixture_id),
            status,
            kickoff,
            home_id,
            away_id,
            goals,
            fulltime,
            extratime,
            penalty,
            regulation,
            classification,
            fingerprint,
            RESULT_NORMALIZER_VERSION,
            record_digest,
            json.loads(canonical),
            acquired,
        )

    @staticmethod
    def _classify(status: str, *, goals, fulltime, extratime, penalty):
        invalid = (ResultClassification.INVALID_TERMINAL, (None, None))
        if status == "FT":
            if fulltime == (None, None) or goals != fulltime:
                return invalid
            if extratime != (None, None) or penalty != (None, None):
                return invalid
            return ResultClassification.PLAYED_SETTLEABLE, fulltime
        if status == "AET":
            if fulltime == (None, None) or extratime == (None, None):
                return invalid
            if goals != extratime or penalty != (None, None):
                return invalid
            return ResultClassification.PLAYED_SETTLEABLE, fulltime
        if status == "PEN":
            if fulltime == (None, None) or penalty == (None, None):
                return invalid
            played_score = extratime if extratime != (None, None) else fulltime
            if goals != played_score:
                return invalid
            return ResultClassification.PLAYED_SETTLEABLE, fulltime
        if status in VOIDABLE_STATUSES:
            return ResultClassification.NON_PLAYED_VOIDABLE, (None, None)
        if status in NON_TERMINAL_STATUSES:
            return ResultClassification.NON_TERMINAL, (None, None)
        return ResultClassification.UNKNOWN_STATUS, (None, None)

    @staticmethod
    def _fingerprint(status: str, goals: tuple[int | None, int | None]) -> str:
        raw = _canonical_json({"status": status, "regulation_goals": goals})
        return "result-settlement-v1:" + sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _mapping(value: Mapping[str, Any], key: str) -> Mapping[str, Any]:
        nested = value.get(key)
        if not isinstance(nested, Mapping):
            raise TypeError(f"{key} must be an object")
        return nested

    @staticmethod
    def _positive_int(value: object, name: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{name} must be a positive integer")
        return value

    @staticmethod
    def _datetime(value: object, name: str) -> datetime:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be an ISO datetime")
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"{name} must be a valid ISO datetime") from exc
        return _utc(parsed, name)
