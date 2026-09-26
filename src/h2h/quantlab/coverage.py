"""API-Football league/season coverage parsing for QuantLab."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def parse_fixture_statistics_coverage(
    payload: Mapping[str, Any],
    *,
    league_id: int,
    season: int,
) -> bool | None:
    """Return statistics_fixtures coverage for one exact league-season.

    None means the provider response did not contain an unambiguous boolean flag.
    It is not converted to False because missing coverage metadata is not evidence
    that fixture statistics are unavailable.
    """
    if league_id <= 0 or season <= 0:
        raise ValueError("league_id and season must be positive")
    errors = payload.get("errors")
    if errors:
        raise RuntimeError(f"API-Football returned errors: {errors}")
    response = payload.get("response", [])
    if not isinstance(response, Sequence) or isinstance(response, (str, bytes)):
        raise TypeError("API-Football leagues response must be a list")

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
                return None
            fixtures = coverage.get("fixtures")
            if not isinstance(fixtures, Mapping):
                return None
            value = fixtures.get("statistics_fixtures")
            return value if isinstance(value, bool) else None
    return None
