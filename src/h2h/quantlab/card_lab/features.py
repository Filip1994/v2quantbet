"""Timestamp-safe CardLab v1 context feature calculations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from h2h.quantlab.card_lab.rivalry import (
    RIVALRY_REGISTRY_VERSION,
    rivalry_indicator,
)


CARDLAB_FEATURE_VERSION = "CARDLAB_FEATURES_V1"
CARD_COUNT_RULE_VERSION = "CARD_COUNT_RULE_V1"
TABLE_PRESSURE_VERSION = "TABLE_PRESSURE_V1"
MATCH_IMPORTANCE_VERSION = "MATCH_IMPORTANCE_V1"
RIVALRY_REGISTRY_RELEASED_AT = datetime(2026, 9, 26, 1, 0, tzinfo=UTC)


class FeatureLeakageError(ValueError):
    """Raised when an input became available after the target decision time."""


def _utc(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


@dataclass(frozen=True, slots=True)
class FeatureDatum:
    value: float | int | None
    source: str
    available_at: datetime | None
    version: str
    quality: str
    components: dict[str, Any]

    def payload(self) -> dict[str, Any]:
        result = asdict(self)
        result["available_at"] = (
            None if self.available_at is None else self.available_at.astimezone(UTC).isoformat()
        )
        result["lab_owner"] = "CARD"
        return result


@dataclass(frozen=True, slots=True)
class CardLabFeatureSnapshot:
    fixture_id: str
    decision_at: datetime
    available_at: datetime
    referee: str | None
    referee_card_rate: float | None
    referee_sample_size: int
    referee_foul_rate: float | None
    referee_foul_sample_size: int
    derby_rivalry_indicator: int | None
    home_table_pressure: float | None
    away_table_pressure: float | None
    table_pressure: float | None
    match_importance: float | None
    feature_version: str
    feature_payload: dict[str, Any]


def _require_input_available(available_at: datetime, decision_at: datetime, label: str) -> datetime:
    available = _utc(available_at, f"{label}.available_at")
    decision = _utc(decision_at, "decision_at")
    if available > decision:
        raise FeatureLeakageError(f"{label} became available after decision_at")
    return available


def referee_rates(
    history: tuple[dict[str, Any], ...],
    *,
    referee: str | None,
    decision_at: datetime,
) -> tuple[FeatureDatum, FeatureDatum, int, int]:
    """Use only matches completed and observed before decision_at."""
    decision = _utc(decision_at, "decision_at")
    card_totals: list[float] = []
    foul_totals: list[float] = []
    used_available_at: list[datetime] = []
    for row in history:
        kickoff = row.get("kickoff_at")
        available_at = row.get("available_at")
        if not isinstance(kickoff, datetime) or not isinstance(available_at, datetime):
            continue
        kickoff_utc = _utc(kickoff, "history.kickoff_at")
        available_utc = _utc(available_at, "history.available_at")
        if kickoff_utc >= decision or available_utc > decision:
            continue
        if referee and str(row.get("referee") or "").strip().casefold() != referee.strip().casefold():
            continue

        yellow = _number(row.get("yellow_cards"))
        red = _number(row.get("red_cards"))
        second_yellow = _number(row.get("second_yellow_cards"))
        fouls = _number(row.get("fouls"))
        if yellow is not None and red is not None:
            total = yellow + red + (0.0 if second_yellow is None else second_yellow)
            card_totals.append(total)
            used_available_at.append(available_utc)
        if fouls is not None:
            foul_totals.append(fouls)
            used_available_at.append(available_utc)

    latest = max(used_available_at) if used_available_at else None
    card_rate = None if not card_totals else sum(card_totals) / len(card_totals)
    foul_rate = None if not foul_totals else sum(foul_totals) / len(foul_totals)
    card_quality = (
        "NO_HISTORY"
        if not card_totals
        else "SMALL_SAMPLE" if len(card_totals) < 5 else "OBSERVED"
    )
    foul_quality = (
        "NO_HISTORY"
        if not foul_totals
        else "SMALL_SAMPLE" if len(foul_totals) < 5 else "OBSERVED"
    )
    card = FeatureDatum(
        card_rate,
        "quantlab_completed_fixture_statistics",
        latest,
        CARD_COUNT_RULE_VERSION,
        card_quality,
        {
            "sample_size": len(card_totals),
            "count_rule": (
                "one per provider-reported yellow, red and second-yellow; "
                "second-yellow contributes only when separately reported"
            ),
        },
    )
    foul = FeatureDatum(
        foul_rate,
        "quantlab_completed_fixture_statistics",
        latest,
        CARDLAB_FEATURE_VERSION,
        foul_quality,
        {"sample_size": len(foul_totals)},
    )
    return card, foul, len(card_totals), len(foul_totals)


def _standings_group(payload: dict[str, Any], team_id: int) -> list[dict[str, Any]] | None:
    response = payload.get("response")
    if not isinstance(response, list):
        return None
    for record in response:
        if not isinstance(record, dict):
            continue
        league = record.get("league")
        if not isinstance(league, dict):
            continue
        groups = league.get("standings")
        if not isinstance(groups, list):
            continue
        for group in groups:
            if not isinstance(group, list):
                continue
            rows = [row for row in group if isinstance(row, dict)]
            for row in rows:
                team = row.get("team")
                if isinstance(team, dict) and team.get("id") == team_id:
                    return rows
    return None


def _threshold_component(team_points: float, target_points: float, target_rank: int) -> dict[str, Any]:
    gap = abs(team_points - target_points)
    score = max(0.0, 1.0 - min(gap, 12.0) / 12.0)
    return {
        "target_rank": target_rank,
        "target_points": target_points,
        "points_gap": gap,
        "pressure": score,
    }


def table_pressure(
    standings_payload: dict[str, Any] | None,
    *,
    team_id: int,
    competition_name: str,
    available_at: datetime | None,
    decision_at: datetime,
) -> FeatureDatum:
    if standings_payload is None or available_at is None:
        return FeatureDatum(
            None,
            "api-football:standings",
            None,
            TABLE_PRESSURE_VERSION,
            "UNAVAILABLE",
            {},
        )
    available = _require_input_available(available_at, decision_at, "standings")
    rows = _standings_group(standings_payload, team_id)
    if not rows:
        return FeatureDatum(
            None,
            "api-football:standings",
            available,
            TABLE_PRESSURE_VERSION,
            "TEAM_NOT_IN_STANDINGS",
            {},
        )

    normalized: list[dict[str, Any]] = []
    for row in rows:
        rank = row.get("rank")
        points = _number(row.get("points"))
        team = row.get("team")
        if (
            isinstance(rank, int)
            and rank > 0
            and points is not None
            and isinstance(team, dict)
            and isinstance(team.get("id"), int)
        ):
            normalized.append({"rank": rank, "points": points, "team_id": int(team["id"]), "all": row.get("all")})
    normalized.sort(key=lambda item: item["rank"])
    own = next((row for row in normalized if row["team_id"] == team_id), None)
    if own is None or len(normalized) < 4:
        return FeatureDatum(
            None,
            "api-football:standings",
            available,
            TABLE_PRESSURE_VERSION,
            "INSUFFICIENT_TABLE",
            {},
        )

    second_tier = any(
        token in competition_name.casefold()
        for token in ("championship", "serie b", "segunda", "2. bundesliga", "2 bundesliga", "ligue 2")
    )
    n = len(normalized)
    target_ranks = (
        {"promotion": min(2, n), "playoff": min(6, n), "relegation": max(1, n - 2)}
        if second_tier
        else {"title": 1, "continental": min(4, n), "relegation": max(1, n - 2)}
    )
    by_rank = {row["rank"]: row for row in normalized}
    components: dict[str, Any] = {}
    pressures: list[float] = []
    for name, rank in target_ranks.items():
        target = by_rank.get(rank)
        if target is None:
            continue
        component = _threshold_component(own["points"], target["points"], rank)
        components[name] = component
        pressures.append(float(component["pressure"]))
    score = None if not pressures else max(pressures)
    components["team_rank"] = own["rank"]
    components["team_points"] = own["points"]
    components["table_size"] = n
    return FeatureDatum(
        score,
        "api-football:standings",
        available,
        TABLE_PRESSURE_VERSION,
        "OBSERVED" if score is not None else "UNAVAILABLE",
        components,
    )


def stage_of_season(standings_payload: dict[str, Any] | None, team_id: int) -> float | None:
    if standings_payload is None:
        return None
    rows = _standings_group(standings_payload, team_id)
    if not rows or len(rows) < 2:
        return None
    team_row = next(
        (
            row
            for row in rows
            if isinstance(row.get("team"), dict) and row["team"].get("id") == team_id
        ),
        None,
    )
    if not isinstance(team_row, dict):
        return None
    all_stats = team_row.get("all")
    played = _number(all_stats.get("played")) if isinstance(all_stats, dict) else None
    if played is None:
        return None
    expected = max(1.0, 2.0 * (len(rows) - 1))
    return min(1.0, max(0.0, played / expected))


def match_importance(
    *,
    home_pressure: FeatureDatum,
    away_pressure: FeatureDatum,
    derby: FeatureDatum,
    stage: float | None,
    competition_name: str,
    decision_at: datetime,
) -> FeatureDatum:
    decision = _utc(decision_at, "decision_at")
    competition_key = competition_name.casefold()
    competition_context = (
        1.0
        if any(token in competition_key for token in ("cup", "champions league", "europa league", "conference league"))
        else 0.35
    )
    weighted: list[tuple[float, float]] = []
    if home_pressure.value is not None and away_pressure.value is not None:
        hp = float(home_pressure.value)
        ap = float(away_pressure.value)
        weighted.extend(((0.45, max(hp, ap)), (0.20, (hp + ap) / 2.0)))
    elif home_pressure.value is not None or away_pressure.value is not None:
        one = float(home_pressure.value if home_pressure.value is not None else away_pressure.value)
        weighted.append((0.45, one))
    if stage is not None:
        weighted.append((0.15, stage))
    if derby.value is not None:
        weighted.append((0.10, float(derby.value)))
    weighted.append((0.10, competition_context))
    weight = sum(item[0] for item in weighted)
    value = None if weight <= 0 else sum(w * v for w, v in weighted) / weight
    available_values = [
        datum.available_at
        for datum in (home_pressure, away_pressure, derby)
        if datum.available_at is not None
    ]
    available = max(available_values) if available_values else decision
    _require_input_available(available, decision, "match_importance")
    return FeatureDatum(
        value,
        "derived:cardlab_context",
        available,
        MATCH_IMPORTANCE_VERSION,
        "OBSERVED" if weight >= 0.999 else "PARTIAL",
        {
            "coverage_weight": weight,
            "stage_of_season": stage,
            "competition_context": competition_context,
            "weights": {
                "max_table_pressure": 0.45,
                "mean_table_pressure": 0.20,
                "stage_of_season": 0.15,
                "derby_rivalry": 0.10,
                "competition_context": 0.10,
            },
        },
    )


def build_cardlab_snapshot(
    *,
    fixture_id: str,
    decision_at: datetime,
    kickoff_at: datetime,
    referee: str | None,
    referee_available_at: datetime | None,
    referee_history: tuple[dict[str, Any], ...],
    home_team: str,
    away_team: str,
    home_team_id: int,
    away_team_id: int,
    competition_name: str,
    standings_payload: dict[str, Any] | None,
    standings_available_at: datetime | None,
) -> CardLabFeatureSnapshot:
    decision = _utc(decision_at, "decision_at")
    kickoff = _utc(kickoff_at, "kickoff_at")
    if decision >= kickoff:
        raise FeatureLeakageError("decision_at must be before kickoff_at")
    if referee_available_at is not None:
        _require_input_available(referee_available_at, decision, "referee")

    card_rate, foul_rate, card_n, foul_n = referee_rates(
        referee_history,
        referee=referee,
        decision_at=decision,
    )

    registry = rivalry_indicator(home_team, away_team)
    if RIVALRY_REGISTRY_RELEASED_AT <= decision:
        derby = FeatureDatum(
            registry.value,
            registry.source,
            RIVALRY_REGISTRY_RELEASED_AT,
            RIVALRY_REGISTRY_VERSION,
            registry.quality,
            {},
        )
    else:
        derby = FeatureDatum(
            None,
            registry.source,
            None,
            RIVALRY_REGISTRY_VERSION,
            "NOT_YET_AVAILABLE",
            {},
        )

    home_pressure = table_pressure(
        standings_payload,
        team_id=home_team_id,
        competition_name=competition_name,
        available_at=standings_available_at,
        decision_at=decision,
    )
    away_pressure = table_pressure(
        standings_payload,
        team_id=away_team_id,
        competition_name=competition_name,
        available_at=standings_available_at,
        decision_at=decision,
    )
    pressure_values = [
        float(value)
        for value in (home_pressure.value, away_pressure.value)
        if value is not None
    ]
    pressure_available = [
        value.available_at
        for value in (home_pressure, away_pressure)
        if value.available_at is not None
    ]
    overall_pressure = FeatureDatum(
        None if not pressure_values else max(pressure_values),
        "derived:home_away_table_pressure",
        max(pressure_available) if pressure_available else None,
        TABLE_PRESSURE_VERSION,
        "UNAVAILABLE" if not pressure_values else "OBSERVED",
        {
            "home": home_pressure.value,
            "away": away_pressure.value,
        },
    )
    stage = stage_of_season(standings_payload, home_team_id)
    importance = match_importance(
        home_pressure=home_pressure,
        away_pressure=away_pressure,
        derby=derby,
        stage=stage,
        competition_name=competition_name,
        decision_at=decision,
    )

    features = {
        "referee_card_rate": card_rate.payload(),
        "referee_foul_rate": foul_rate.payload(),
        "derby_rivalry_indicator": derby.payload(),
        "home_table_pressure": home_pressure.payload(),
        "away_table_pressure": away_pressure.payload(),
        "table_pressure": overall_pressure.payload(),
        "match_importance": importance.payload(),
    }
    available_candidates = [
        datum.available_at
        for datum in (card_rate, foul_rate, derby, home_pressure, away_pressure, overall_pressure, importance)
        if datum.available_at is not None
    ]
    snapshot_available_at = max(available_candidates) if available_candidates else decision
    if snapshot_available_at > decision:
        raise FeatureLeakageError("feature snapshot contains post-decision information")
    return CardLabFeatureSnapshot(
        fixture_id=fixture_id,
        decision_at=decision,
        available_at=snapshot_available_at,
        referee=referee,
        referee_card_rate=None if card_rate.value is None else float(card_rate.value),
        referee_sample_size=card_n,
        referee_foul_rate=None if foul_rate.value is None else float(foul_rate.value),
        referee_foul_sample_size=foul_n,
        derby_rivalry_indicator=None if derby.value is None else int(derby.value),
        home_table_pressure=None if home_pressure.value is None else float(home_pressure.value),
        away_table_pressure=None if away_pressure.value is None else float(away_pressure.value),
        table_pressure=None if overall_pressure.value is None else float(overall_pressure.value),
        match_importance=None if importance.value is None else float(importance.value),
        feature_version=CARDLAB_FEATURE_VERSION,
        feature_payload=features,
    )
