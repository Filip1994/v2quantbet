"""API-Football league/season coverage parsing for QuantLab."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


COVERAGE_KEYS = (
    "statistics_fixtures",
    "statistics_players",
    "lineups",
    "standings",
    "players",
    "injuries",
    "predictions",
    "odds",
)


def parse_league_coverage_flags(
    payload: Mapping[str, Any],
    *,
    league_id: int,
    season: int,
) -> dict[str, bool | None]:
    """Return known coverage flags for one exact league-season.

    None means the provider response did not expose an unambiguous boolean. Missing
    metadata is never converted to False.
    """
    if league_id <= 0 or season <= 0:
        raise ValueError("league_id and season must be positive")
    errors = payload.get("errors")
    if errors:
        raise RuntimeError(f"API-Football returned errors: {errors}")
    response = payload.get("response", [])
    if not isinstance(response, Sequence) or isinstance(response, (str, bytes)):
        raise TypeError("API-Football leagues response must be a list")

    result = {key: None for key in COVERAGE_KEYS}
    for item in response:
        if not isinstance(item, Mapping):
            continue
        league = item.get("league")
        if not isinstance(league, Mapping):
            continue
        try:
            item_league_id = int(league.get("id"))
        except (TypeError, ValueError):
            continue
        if item_league_id != league_id:
            continue
        seasons = item.get("seasons", [])
        if not isinstance(seasons, Sequence) or isinstance(seasons, (str, bytes)):
            continue
        for season_item in seasons:
            if not isinstance(season_item, Mapping):
                continue
            try:
                year = int(season_item.get("year"))
            except (TypeError, ValueError):
                continue
            if year != season:
                continue
            coverage = season_item.get("coverage")
            if not isinstance(coverage, Mapping):
                return result
            fixtures = coverage.get("fixtures")
            if isinstance(fixtures, Mapping):
                for key in ("statistics_fixtures", "statistics_players", "lineups"):
                    value = fixtures.get(key)
                    result[key] = value if isinstance(value, bool) else None
            for key in (
                "standings",
                "players",
                "injuries",
                "predictions",
                "odds",
            ):
                value = coverage.get(key)
                result[key] = value if isinstance(value, bool) else None
            return result
    return result


def parse_fixture_statistics_coverage(
    payload: Mapping[str, Any],
    *,
    league_id: int,
    season: int,
) -> bool | None:
    """Backward-compatible fixture-statistics coverage accessor."""
    return parse_league_coverage_flags(
        payload,
        league_id=league_id,
        season=season,
    )["statistics_fixtures"]
