"""Timestamp-safe CardLab raw-statistics feature calculations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from h2h.quantlab.card_lab.rivalry import (
    RIVALRY_REGISTRY_VERSION,
    rivalry_indicator,
)
from h2h.quantlab.card_lab.referee import referee_key


CARDLAB_FEATURE_VERSION = "CARDLAB_FEATURES_V4"
CARD_COUNT_RULE_VERSION = "CARD_COUNT_RULE_V2"
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
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
    event_samples = 0
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
        if referee and referee_key(row.get("referee")) != referee_key(referee):
            continue

        yellow = _number(row.get("yellow_cards"))
        red = _number(row.get("red_cards"))
        second_yellow = _number(row.get("second_yellow_cards"))
        event_total = _number(row.get("card_total"))
        fouls = _number(row.get("fouls"))
        if event_total is not None or (yellow is not None and red is not None):
            total = (
                event_total
                if event_total is not None
                else yellow + red + (0.0 if second_yellow is None else second_yellow)
            )
            event_samples += int(event_total is not None)
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
        "quantlab_card_events_and_fixture_statistics",
        latest,
        CARD_COUNT_RULE_VERSION,
        card_quality,
        {
            "sample_size": len(card_totals),
            "event_samples": event_samples,
            "count_rule": (
                "verified 1xBet event total where available; otherwise provider-reported "
                "yellow, red and separately reported second-yellow"
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



def _mean(values: list[float]) -> float | None:
    return None if not values else sum(values) / len(values)


def _recent_mean(samples: list[dict[str, float | str | None]], key: str, count: int) -> float | None:
    values = [
        float(value)
        for sample in samples[-count:]
        if (value := sample.get(key)) is not None
    ]
    return _mean(values)


def _recent_rate(
    samples: list[dict[str, float | str | None]],
    key: str,
    count: int,
    predicate: Any,
) -> float | None:
    values = [
        float(value)
        for sample in samples[-count:]
        if (value := sample.get(key)) is not None
    ]
    return None if not values else sum(bool(predicate(value)) for value in values) / len(values)


def _cards_for_side(row: dict[str, Any], side: str) -> float | None:
    yellow = _number(row.get(f"{side}_yellow_cards"))
    red = _number(row.get(f"{side}_red_cards"))
    second = _number(row.get(f"{side}_second_yellow_cards"))
    if yellow is None or red is None:
        return None
    return yellow + red + (0.0 if second is None else second)


def _row_total_cards(row: dict[str, Any]) -> float | None:
    home = _cards_for_side(row, "home")
    away = _cards_for_side(row, "away")
    return None if home is None or away is None else home + away


def _valid_history_rows(
    rows: tuple[dict[str, Any], ...],
    *,
    decision_at: datetime,
) -> list[dict[str, Any]]:
    decision = _utc(decision_at, "decision_at")
    valid: list[dict[str, Any]] = []
    for row in rows:
        kickoff = row.get("kickoff_at")
        available = row.get("available_at")
        if not isinstance(kickoff, datetime) or not isinstance(available, datetime):
            continue
        if _utc(kickoff, "history.kickoff_at") >= decision:
            continue
        if _utc(available, "history.available_at") > decision:
            continue
        valid.append(row)
    valid.sort(key=lambda row: _utc(row["kickoff_at"], "history.kickoff_at"))
    return valid


def _team_samples(
    rows: list[dict[str, Any]],
    *,
    team_id: int,
) -> list[dict[str, float | str | None]]:
    samples: list[dict[str, float | str | None]] = []
    for row in rows:
        home_id = row.get("home_team_id")
        away_id = row.get("away_team_id")
        if team_id == home_id:
            side, opponent = "home", "away"
            venue = "HOME"
        elif team_id == away_id:
            side, opponent = "away", "home"
            venue = "AWAY"
        else:
            continue
        cards_for = _cards_for_side(row, side)
        cards_against = _cards_for_side(row, opponent)
        fouls_for = _number(row.get(f"{side}_fouls"))
        fouls_against = _number(row.get(f"{opponent}_fouls"))
        possession = _number(row.get(f"{side}_ball_possession"))
        total_cards = (
            None if cards_for is None or cards_against is None
            else cards_for + cards_against
        )
        total_fouls = (
            None if fouls_for is None or fouls_against is None
            else fouls_for + fouls_against
        )
        samples.append(
            {
                "venue": venue,
                "cards_for": cards_for,
                "cards_against": cards_against,
                "fouls_committed": fouls_for,
                "fouls_suffered": fouls_against,
                "cards_per_foul": (
                    None
                    if cards_for is None or fouls_for is None or fouls_for <= 0
                    else cards_for / fouls_for
                ),
                "fouls_per_card": (
                    None
                    if cards_for is None or cards_for <= 0 or fouls_for is None
                    else fouls_for / cards_for
                ),
                "match_total_cards": total_cards,
                "match_total_fouls": total_fouls,
                "possession": possession,
            }
        )
    return samples


def _venue_samples(
    samples: list[dict[str, float | str | None]],
    venue: str,
) -> list[dict[str, float | str | None]]:
    return [sample for sample in samples if sample.get("venue") == venue]


def _team_raw_features(
    samples: list[dict[str, float | str | None]],
    *,
    prefix: str,
    venue: str,
) -> dict[str, float | int | None]:
    venue_rows = _venue_samples(samples, venue)
    result: dict[str, float | int | None] = {
        f"{prefix}_history_n": len(samples),
    }
    for window in (5, 10):
        for metric in (
            "cards_for",
            "cards_against",
            "fouls_committed",
            "fouls_suffered",
            "cards_per_foul",
            "fouls_per_card",
            "match_total_cards",
            "match_total_fouls",
            "possession",
        ):
            result[f"{prefix}_l{window}_{metric}"] = _recent_mean(samples, metric, window)
    for metric in (
        "cards_for",
        "cards_against",
        "fouls_committed",
        "fouls_suffered",
        "match_total_cards",
        "possession",
    ):
        result[f"{prefix}_venue_l5_{metric}"] = _recent_mean(venue_rows, metric, 5)

    for threshold in (2.0, 3.0, 4.0):
        key = str(int(threshold))
        result[f"{prefix}_cards_{key}plus_rate_l10"] = _recent_rate(
            samples, "cards_for", 10, lambda value, t=threshold: value >= t
        )
    for line in (3.5, 4.5, 5.5):
        key = str(line).replace(".", "_")
        result[f"{prefix}_match_over_{key}_rate_l10"] = _recent_rate(
            samples, "match_total_cards", 10, lambda value, t=line: value > t
        )

    l5_cards = result.get(f"{prefix}_l5_cards_for")
    l10_cards = result.get(f"{prefix}_l10_cards_for")
    result[f"{prefix}_cards_trend_l5_minus_l10"] = (
        None if l5_cards is None or l10_cards is None else float(l5_cards) - float(l10_cards)
    )
    l5_fouls = result.get(f"{prefix}_l5_fouls_committed")
    l10_fouls = result.get(f"{prefix}_l10_fouls_committed")
    result[f"{prefix}_fouls_trend_l5_minus_l10"] = (
        None if l5_fouls is None or l10_fouls is None else float(l5_fouls) - float(l10_fouls)
    )
    return result


def _percentile(value: float | None, population: list[float]) -> float | None:
    if value is None or not population:
        return None
    return sum(item <= value for item in population) / len(population)


def _standings_fact(datum: FeatureDatum, key: str) -> float | None:
    value = datum.components.get(key)
    return _number(value)


def _raw_card_features(
    *,
    referee_history: tuple[dict[str, Any], ...],
    referee_web_profiles: tuple[dict[str, Any], ...],
    referee_web_league_key: str | None,
    team_history: tuple[dict[str, Any], ...],
    league_history: tuple[dict[str, Any], ...],
    market_context: dict[str, Any],
    home_team_id: int,
    away_team_id: int,
    home_pressure: FeatureDatum,
    away_pressure: FeatureDatum,
    stage: float | None,
    derby: FeatureDatum,
    importance: FeatureDatum,
    competition_name: str,
    competition_type: str,
    decision_at: datetime,
) -> tuple[
    dict[str, Any],
    dict[str, float],
    dict[str, float],
    dict[str, list[float]],
    dict[str, float],
]:
    team_rows = _valid_history_rows(team_history, decision_at=decision_at)
    league_rows = _valid_history_rows(league_history, decision_at=decision_at)
    home_samples = _team_samples(team_rows, team_id=home_team_id)
    away_samples = _team_samples(team_rows, team_id=away_team_id)

    raw: dict[str, Any] = {}
    raw.update(_team_raw_features(home_samples, prefix="home", venue="HOME"))
    raw.update(_team_raw_features(away_samples, prefix="away", venue="AWAY"))

    referee_rows: list[dict[str, Any]] = []
    decision = _utc(decision_at, "decision_at")
    for row in referee_history:
        kickoff = row.get("kickoff_at")
        available = row.get("available_at")
        if not isinstance(kickoff, datetime) or not isinstance(available, datetime):
            continue
        if _utc(kickoff, "referee.kickoff_at") >= decision or _utc(available, "referee.available_at") > decision:
            continue
        referee_rows.append(row)
    referee_rows.sort(key=lambda row: _utc(row["kickoff_at"], "referee.kickoff_at"))

    referee_samples: list[dict[str, float | str | None]] = []
    for row in referee_rows:
        yellow = _number(row.get("yellow_cards"))
        red = _number(row.get("red_cards"))
        second = _number(row.get("second_yellow_cards"))
        total = _number(row.get("card_total"))
        if total is None and yellow is not None and red is not None:
            total = yellow + red + (0.0 if second is None else second)
        home_cards = None
        away_cards = None
        hy = _number(row.get("home_yellow_cards"))
        ay = _number(row.get("away_yellow_cards"))
        hr = _number(row.get("home_red_cards"))
        ar = _number(row.get("away_red_cards"))
        hs = _number(row.get("home_second_yellow_cards"))
        ass = _number(row.get("away_second_yellow_cards"))
        if hy is not None and hr is not None:
            home_cards = hy + hr + (0.0 if hs is None else hs)
        if ay is not None and ar is not None:
            away_cards = ay + ar + (0.0 if ass is None else ass)
        fouls = _number(row.get("fouls"))
        referee_samples.append(
            {
                "cards": total,
                "yellows": yellow,
                "reds": red,
                "fouls": fouls,
                "cards_per_foul": (
                    None if total is None or fouls is None or fouls <= 0 else total / fouls
                ),
                "fouls_per_card": (
                    None if total is None or total <= 0 or fouls is None else fouls / total
                ),
                "home_cards": home_cards,
                "away_cards": away_cards,
            }
        )
    raw["referee_history_n"] = len(referee_samples)
    for window in (5, 10):
        for metric in ("cards", "yellows", "reds", "fouls", "cards_per_foul", "fouls_per_card", "home_cards", "away_cards"):
            raw[f"referee_l{window}_{metric}"] = _recent_mean(referee_samples, metric, window)
    home_ref = raw.get("referee_l10_home_cards")
    away_ref = raw.get("referee_l10_away_cards")
    raw["referee_home_away_bias_l10"] = (
        None if home_ref is None or away_ref is None else float(home_ref) - float(away_ref)
    )
    for line in (3.5, 4.5, 5.5):
        key = str(line).replace(".", "_")
        raw[f"referee_over_{key}_rate_l10"] = _recent_rate(
            referee_samples, "cards", 10, lambda value, t=line: value > t
        )

    web_rows: list[dict[str, Any]] = []
    for row in referee_web_profiles:
        captured_at = row.get("captured_at")
        matches = int(row.get("matches") or 0)
        if not isinstance(captured_at, datetime) or matches <= 0:
            continue
        if _utc(captured_at, "referee_web.captured_at") > decision:
            continue
        web_rows.append(row)
    web_matches = sum(int(row.get("matches") or 0) for row in web_rows)
    web_yellows = sum(int(row.get("yellow_cards") or 0) for row in web_rows)
    web_second_yellows = sum(int(row.get("second_yellow_cards") or 0) for row in web_rows)
    web_reds = sum(int(row.get("red_cards") or 0) for row in web_rows)
    web_home_cards = sum(int(row.get("home_cards") or 0) for row in web_rows)
    web_away_cards = sum(int(row.get("away_cards") or 0) for row in web_rows)
    web_total_cards = web_yellows + web_second_yellows + web_reds
    raw["web_referee_supported_league"] = int(bool(referee_web_league_key))
    raw["web_referee_league_key"] = referee_web_league_key
    raw["web_referee_seasons"] = len(web_rows)
    raw["web_referee_matches"] = web_matches
    raw["web_referee_cards_per_match"] = (
        None if web_matches <= 0 else web_total_cards / web_matches
    )
    raw["web_referee_yellows_per_match"] = (
        None if web_matches <= 0 else web_yellows / web_matches
    )
    raw["web_referee_second_yellows_per_match"] = (
        None if web_matches <= 0 else web_second_yellows / web_matches
    )
    raw["web_referee_reds_per_match"] = (
        None if web_matches <= 0 else web_reds / web_matches
    )
    raw["web_referee_home_cards_per_match"] = (
        None if web_matches <= 0 else web_home_cards / web_matches
    )
    raw["web_referee_away_cards_per_match"] = (
        None if web_matches <= 0 else web_away_cards / web_matches
    )
    raw["web_referee_home_away_bias"] = (
        None if web_matches <= 0 else (web_home_cards - web_away_cards) / web_matches
    )
    raw["web_referee_coverage_ok"] = int(web_matches >= 10)

    def combine(a: Any, b: Any) -> float | None:
        left, right = _number(a), _number(b)
        return None if left is None or right is None else left + right

    raw["combined_team_cards_for_l5"] = combine(raw.get("home_l5_cards_for"), raw.get("away_l5_cards_for"))
    raw["combined_team_cards_for_l10"] = combine(raw.get("home_l10_cards_for"), raw.get("away_l10_cards_for"))
    raw["combined_fouls_committed_l5"] = combine(raw.get("home_l5_fouls_committed"), raw.get("away_l5_fouls_committed"))
    raw["combined_fouls_committed_l10"] = combine(raw.get("home_l10_fouls_committed"), raw.get("away_l10_fouls_committed"))

    home_for = _number(raw.get("home_l10_cards_for"))
    home_against = _number(raw.get("home_l10_cards_against"))
    away_for = _number(raw.get("away_l10_cards_for"))
    away_against = _number(raw.get("away_l10_cards_against"))
    raw["matchup_expected_cards_l10"] = (
        None
        if None in (home_for, home_against, away_for, away_against)
        else ((home_for + away_against) / 2.0) + ((away_for + home_against) / 2.0)
    )
    home_fc = _number(raw.get("home_l10_fouls_committed"))
    home_fs = _number(raw.get("home_l10_fouls_suffered"))
    away_fc = _number(raw.get("away_l10_fouls_committed"))
    away_fs = _number(raw.get("away_l10_fouls_suffered"))
    raw["matchup_expected_fouls_l10"] = (
        None
        if None in (home_fc, home_fs, away_fc, away_fs)
        else ((home_fc + away_fs) / 2.0) + ((away_fc + home_fs) / 2.0)
    )
    expected_fouls = _number(raw.get("matchup_expected_fouls_l10"))
    referee_cpf = _number(raw.get("referee_l10_cards_per_foul"))
    raw["referee_foul_conversion_cards"] = (
        None if expected_fouls is None or referee_cpf is None
        else expected_fouls * referee_cpf
    )
    home_cpf = _number(raw.get("home_l10_cards_per_foul"))
    away_cpf = _number(raw.get("away_l10_cards_per_foul"))
    team_cpf_values = [value for value in (home_cpf, away_cpf) if value is not None]
    raw["team_cards_per_foul_l10"] = _mean(team_cpf_values)
    raw["team_foul_conversion_cards"] = (
        None
        if expected_fouls is None or raw["team_cards_per_foul_l10"] is None
        else expected_fouls * float(raw["team_cards_per_foul_l10"])
    )
    raw["home_aggression_x_away_foul_draw"] = (
        None if home_cpf is None or away_fs is None else home_cpf * away_fs
    )
    raw["away_aggression_x_home_foul_draw"] = (
        None if away_cpf is None or home_fs is None else away_cpf * home_fs
    )
    interaction_values = [
        value for value in (
            _number(raw.get("home_aggression_x_away_foul_draw")),
            _number(raw.get("away_aggression_x_home_foul_draw")),
        )
        if value is not None
    ]
    raw["aggression_foul_draw_interaction"] = _mean(interaction_values)

    home_pos = _number(raw.get("home_l10_possession"))
    away_pos = _number(raw.get("away_l10_possession"))
    raw["expected_possession_imbalance"] = (
        None if home_pos is None or away_pos is None else abs(home_pos - away_pos)
    )

    h2h = [
        row for row in team_rows
        if {row.get("home_team_id"), row.get("away_team_id")} == {home_team_id, away_team_id}
    ][-5:]
    h2h_cards = [value for row in h2h if (value := _row_total_cards(row)) is not None]
    h2h_fouls = [
        float(row["home_fouls"]) + float(row["away_fouls"])
        for row in h2h
        if row.get("home_fouls") is not None and row.get("away_fouls") is not None
    ]
    raw["h2h_n"] = len(h2h_cards)
    raw["h2h_total_cards_l5"] = _mean(h2h_cards)
    raw["h2h_total_fouls_l5"] = _mean(h2h_fouls)

    league_total_cards: list[float] = []
    league_total_fouls: list[float] = []
    league_team_cards: list[float] = []
    league_team_fouls: list[float] = []
    for row in league_rows:
        hc = _cards_for_side(row, "home")
        ac = _cards_for_side(row, "away")
        hf = _number(row.get("home_fouls"))
        af = _number(row.get("away_fouls"))
        if hc is not None and ac is not None:
            league_total_cards.append(hc + ac)
            league_team_cards.extend((hc, ac))
        if hf is not None and af is not None:
            league_total_fouls.append(hf + af)
            league_team_fouls.extend((hf, af))
    raw["league_history_n"] = len(league_total_cards)
    raw["league_total_cards"] = _mean(league_total_cards[-200:])
    raw["league_total_fouls"] = _mean(league_total_fouls[-200:])
    raw["league_cards_per_team"] = _mean(league_team_cards[-400:])
    raw["league_fouls_per_team"] = _mean(league_team_fouls[-400:])
    raw["home_cards_for_league_percentile"] = _percentile(
        _number(raw.get("home_l10_cards_for")), league_team_cards[-400:]
    )
    raw["away_cards_for_league_percentile"] = _percentile(
        _number(raw.get("away_l10_cards_for")), league_team_cards[-400:]
    )
    raw["home_fouls_league_percentile"] = _percentile(
        _number(raw.get("home_l10_fouls_committed")), league_team_fouls[-400:]
    )
    raw["away_fouls_league_percentile"] = _percentile(
        _number(raw.get("away_l10_fouls_committed")), league_team_fouls[-400:]
    )
    referee_cards = _number(raw.get("referee_l10_cards"))
    league_cards = _number(raw.get("league_total_cards"))
    raw["referee_vs_league_cards_delta"] = (
        None if referee_cards is None or league_cards is None else referee_cards - league_cards
    )
    team_cards = _number(raw.get("combined_team_cards_for_l10"))
    raw["referee_vs_teams_cards_delta"] = (
        None if referee_cards is None or team_cards is None else referee_cards - team_cards
    )
    raw["referee_x_team_cards"] = (
        None if referee_cards is None or team_cards is None else referee_cards * team_cards
    )

    raw["stage_of_season"] = stage
    raw["late_season_indicator"] = None if stage is None else int(stage >= 0.75)
    competition_key = f"{competition_type} {competition_name}".casefold()
    cup = int(any(token in competition_key for token in ("cup", "copa", "coppa", "pokal", "coupe")))
    raw["cup_indicator"] = cup
    raw["knockout_proxy"] = cup
    raw["derby_rivalry_indicator"] = derby.value
    raw["home_table_pressure"] = home_pressure.value
    raw["away_table_pressure"] = away_pressure.value
    raw["table_pressure"] = max(
        [float(v) for v in (home_pressure.value, away_pressure.value) if v is not None],
        default=None,
    )
    raw["match_importance"] = importance.value
    raw["home_rank"] = _standings_fact(home_pressure, "team_rank")
    raw["away_rank"] = _standings_fact(away_pressure, "team_rank")
    raw["home_points"] = _standings_fact(home_pressure, "team_points")
    raw["away_points"] = _standings_fact(away_pressure, "team_points")

    for side, datum in (("home", home_pressure), ("away", away_pressure)):
        for race in ("title", "continental", "promotion", "playoff", "relegation"):
            component = datum.components.get(race)
            component = component if isinstance(component, dict) else {}
            raw[f"{side}_{race}_pressure"] = _number(component.get("pressure"))
            raw[f"{side}_{race}_points_gap"] = _number(component.get("points_gap"))
    for race in ("title", "continental", "promotion", "playoff", "relegation"):
        race_values = [
            value
            for value in (
                _number(raw.get(f"home_{race}_pressure")),
                _number(raw.get(f"away_{race}_pressure")),
            )
            if value is not None
        ]
        raw[f"{race}_pressure"] = max(race_values) if race_values else None
    raw["rank_gap"] = (
        None if raw["home_rank"] is None or raw["away_rank"] is None
        else abs(float(raw["home_rank"]) - float(raw["away_rank"]))
    )
    raw["points_gap"] = (
        None if raw["home_points"] is None or raw["away_points"] is None
        else abs(float(raw["home_points"]) - float(raw["away_points"]))
    )
    pressure = _number(raw.get("table_pressure"))
    raw["must_win_proxy"] = (
        None if pressure is None else pressure * (0.5 + 0.5 * (stage if stage is not None else 0.5))
    )
    raw["last_rounds_indicator"] = None if stage is None else int(stage >= 0.85)
    rank_gap_value = _number(raw.get("rank_gap"))
    points_gap_value = _number(raw.get("points_gap"))
    raw["close_table_position_indicator"] = int(
        (rank_gap_value is not None and rank_gap_value <= 3.0)
        or (points_gap_value is not None and points_gap_value <= 4.0)
    )
    raw["relegation_battle_indicator"] = int(
        (_number(raw.get("relegation_pressure")) or 0.0) >= 0.65
    )
    raw["title_race_indicator"] = int(
        (_number(raw.get("title_pressure")) or 0.0) >= 0.65
    )
    raw["promotion_race_indicator"] = int(
        max(
            _number(raw.get("promotion_pressure")) or 0.0,
            _number(raw.get("playoff_pressure")) or 0.0,
        )
        >= 0.65
    )

    for key, value in market_context.items():
        if key != "available_at":
            raw[f"market_{key}"] = value
    balance = _number(raw.get("market_one_x_two_balance"))
    rank_gap = _number(raw.get("rank_gap"))
    raw["similar_strength_indicator"] = int(
        (balance is not None and balance >= 0.80)
        or (rank_gap is not None and rank_gap <= 3.0)
    )

    raw["referee_penalties_per_match"] = None
    raw["referee_penalty_source_coverage"] = 0

    anchors: dict[str, float] = {}
    anchor_weights: dict[str, float] = {}
    candidates = {
        "referee_l10_cards": (raw.get("referee_l10_cards"), 1.25),
        "web_referee_cards_per_match": (
            raw.get("web_referee_cards_per_match")
            if int(raw.get("web_referee_matches") or 0) >= 5
            else None,
            1.15,
        ),
        "combined_team_cards_for_l10": (raw.get("combined_team_cards_for_l10"), 1.00),
        "matchup_expected_cards_l10": (raw.get("matchup_expected_cards_l10"), 1.00),
        "home_match_total_cards_l10": (raw.get("home_l10_match_total_cards"), 0.75),
        "away_match_total_cards_l10": (raw.get("away_l10_match_total_cards"), 0.75),
        "referee_foul_conversion_cards": (raw.get("referee_foul_conversion_cards"), 1.00),
        "team_foul_conversion_cards": (raw.get("team_foul_conversion_cards"), 1.00),
        "h2h_total_cards_l5": (
            raw.get("h2h_total_cards_l5") if int(raw.get("h2h_n") or 0) >= 2 else None,
            0.35,
        ),
        "league_total_cards": (raw.get("league_total_cards"), 0.60),
    }
    for key, (value, weight) in candidates.items():
        number = _number(value)
        if number is not None:
            anchors[key] = number
            anchor_weights[key] = weight

    weighted = sorted((anchors[key], anchor_weights[key]) for key in anchors)
    total_weight = sum(weight for _, weight in weighted)
    halfway = total_weight / 2.0
    cumulative = 0.0
    weighted_consensus: float | None = None
    for value, weight in weighted:
        cumulative += weight
        if cumulative >= halfway:
            weighted_consensus = value
            break

    raw["raw_anchor_count"] = len(anchors)
    raw["raw_anchor_weight_sum"] = total_weight
    raw["raw_consensus_cards"] = weighted_consensus

    raw_samples = {
        "referee_total_cards": [
            float(value)
            for sample in referee_samples[-10:]
            if (value := sample.get("cards")) is not None
        ],
        "home_match_total_cards": [
            float(value)
            for sample in home_samples[-10:]
            if (value := sample.get("match_total_cards")) is not None
        ],
        "away_match_total_cards": [
            float(value)
            for sample in away_samples[-10:]
            if (value := sample.get("match_total_cards")) is not None
        ],
        "h2h_total_cards": h2h_cards,
    }
    sample_weights = {
        "referee_total_cards": 1.25,
        "home_match_total_cards": 1.00,
        "away_match_total_cards": 1.00,
        "h2h_total_cards": 0.35,
    }
    return raw, anchors, anchor_weights, raw_samples, sample_weights


def build_cardlab_snapshot(
    *,
    fixture_id: str,
    decision_at: datetime,
    kickoff_at: datetime,
    referee: str | None,
    referee_available_at: datetime | None,
    referee_history: tuple[dict[str, Any], ...],
    referee_web_profiles: tuple[dict[str, Any], ...] = (),
    referee_web_league_key: str | None = None,
    team_history: tuple[dict[str, Any], ...] = (),
    league_history: tuple[dict[str, Any], ...] = (),
    market_context: dict[str, Any] | None = None,
    home_team: str,
    away_team: str,
    home_team_id: int,
    away_team_id: int,
    competition_name: str,
    competition_type: str = "",
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
        {"home": home_pressure.value, "away": away_pressure.value},
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

    raw_features, raw_anchors, raw_anchor_weights, raw_samples, raw_sample_weights = _raw_card_features(
        referee_history=referee_history,
        referee_web_profiles=referee_web_profiles,
        referee_web_league_key=referee_web_league_key,
        team_history=team_history,
        league_history=league_history,
        market_context=dict(market_context or {}),
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        home_pressure=home_pressure,
        away_pressure=away_pressure,
        stage=stage,
        derby=derby,
        importance=importance,
        competition_name=competition_name,
        competition_type=competition_type,
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
        "raw_features": raw_features,
        "raw_anchors": raw_anchors,
        "raw_anchor_weights": raw_anchor_weights,
        "raw_samples": raw_samples,
        "raw_sample_weights": raw_sample_weights,
        "market_context": dict(market_context or {}),
        "raw_stat_contract": {
            "version": "CARDLAB_RAW_STATS_V2",
            "price_independent_selection": True,
            "referee_web_source": "STATBUNKER",
            "referee_web_top_league_gate": True,
            "referee_web_minimum_matches": 10,
            "ev_is_pick_gate": False,
            "edge_is_pick_gate": False,
            "penalty_rate_available": False,
        },
    }
    available_candidates = [
        datum.available_at
        for datum in (
            card_rate,
            foul_rate,
            derby,
            home_pressure,
            away_pressure,
            overall_pressure,
            importance,
        )
        if datum.available_at is not None
    ]
    for row in (*team_history, *league_history, *referee_web_profiles):
        available = row.get("available_at") or row.get("captured_at")
        if isinstance(available, datetime):
            available_utc = _utc(available, "history.available_at")
            if available_utc <= decision:
                available_candidates.append(available_utc)
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
