"""API-Football league/season coverage parsing for QuantLab."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def fixture_statistics_coverage(
    payload: Mapping[str, Any],
    *,
    league_id: int,
    season: int,
) -> tuple[bool | None, int]:
    """Return provider-declared fixture-statistics coverage and response item count.

    False is authoritative enough to skip fixture-statistics calls while cached.
    True is only a capability signal and does not guarantee every fixture has data.
    None means the response did not provide a usable coverage flag.
    """
    if league_id <= 0 or season <= 0:
        raise ValueError("league_id and season must be positive")
    if not isinstance(payload, Mapping):
        raise TypeError("coverage payload must be a mapping")
    errors = payload.get("errors")
    if errors:
        raise RuntimeError(f"API-Football returned errors: {errors}")
    response = payload.get("response", [])
    if not isinstance(response, Sequence) or isinstance(response, (str, bytes)):
        raise TypeError("API-Football coverage response must be a list")

    item_count = len(response)
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
                return None, item_count
            fixtures = coverage.get("fixtures")
            if not isinstance(fixtures, Mapping):
                return None, item_count
            flag = fixtures.get("statistics_fixtures")
            return (flag if isinstance(flag, bool) else None), item_count
    return None, item_count
