from __future__ import annotations

from datetime import UTC, datetime, timedelta

from h2h.quantlab.corner_lab.readiness_audit import _market_summary


NOW = datetime(2026, 9, 26, 14, 0, tzinfo=UTC)


def _pair(name: str, line: float, fixture_id: str = "fixture-1") -> dict[str, object]:
    return {
        "fixture_id": fixture_id,
        "bookmaker_id": 8,
        "bookmaker_name": "Bet365",
        "provider_bet_id": 99,
        "provider_bet_name": name,
        "parsed_line": line,
        "captured_at": NOW - timedelta(hours=1),
        "kickoff_at": NOW + timedelta(hours=3),
    }


def test_readiness_market_summary_keeps_only_full_match_half_line_totals() -> None:
    summary, fixtures = _market_summary(
        (
            _pair("Total Corners", 10.5),
            _pair("Team Total Corners", 5.5, "fixture-2"),
            _pair("Total Corners", 10.0, "fixture-3"),
        ),
        now=NOW,
    )

    assert summary["complete_two_sided_logical_pairs_before_semantic_filter"] == 3
    assert summary["supported_upcoming_pairs"] == 1
    assert summary["supported_upcoming_fixtures"] == 1
    assert fixtures == {"fixture-1"}
