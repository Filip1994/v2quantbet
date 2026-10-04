from datetime import UTC, datetime, timedelta

import pytest

from h2h.quantlab.dashboard import QuantLabDashboardService
from h2h.quantlab.h2h_lab.engine import dc_weight_for_sample, h2h_probability
from h2h.quantlab.h2h_lab.history import parse_h2h_response
from h2h.quantlab.h2h_lab.settlement import settle_h2h_shadow_bet


NOW = datetime(2026, 10, 4, 0, tzinfo=UTC)


def _meeting(index: int, *, hit: bool = True, same_venue: bool = True) -> dict[str, object]:
    return {
        "provider_fixture_id": 1000 + index,
        "kickoff_at": (NOW - timedelta(days=30 * (index + 1))).isoformat(),
        "home_team_id": 10 if same_venue else 20,
        "away_team_id": 20 if same_venue else 10,
        "home_team": "Home" if same_venue else "Away",
        "away_team": "Away" if same_venue else "Home",
        "home_goals": 2 if hit else 1,
        "away_goals": 1 if hit else 0,
        "competition_name": "League",
        "league_id": 1,
    }


def test_dc_weight_is_capped_at_seventy_percent_and_declines_with_sample() -> None:
    assert dc_weight_for_sample(5) == pytest.approx(0.70)
    assert dc_weight_for_sample(6) == pytest.approx(0.68)
    assert dc_weight_for_sample(10) == pytest.approx(0.60)
    assert dc_weight_for_sample(15) == pytest.approx(0.60)
    with pytest.raises(ValueError):
        dc_weight_for_sample(4)


def test_h2h_probability_requires_five_and_shrinks_perfect_small_sample() -> None:
    meetings = tuple(_meeting(index) for index in range(5))
    raw, shrunk, evidence = h2h_probability(
        meetings,
        target_home_team_id=10,
        target_away_team_id=20,
        market_key="OU_25",
        selection="OVER",
    )
    assert raw == pytest.approx(1.0)
    assert 0.5 < shrunk < 1.0
    assert len(evidence) == 5
    assert evidence[0]["final_weight"] > evidence[-1]["final_weight"]
    with pytest.raises(ValueError):
        h2h_probability(
            meetings[:4],
            target_home_team_id=10,
            target_away_team_id=20,
            market_key="OU_25",
            selection="OVER",
        )


def test_reverse_venue_is_discounted() -> None:
    meetings = (
        _meeting(0, same_venue=True),
        _meeting(1, same_venue=False),
        _meeting(2, same_venue=True),
        _meeting(3, same_venue=False),
        _meeting(4, same_venue=True),
    )
    _, _, evidence = h2h_probability(
        meetings,
        target_home_team_id=10,
        target_away_team_id=20,
        market_key="BTTS",
        selection="YES",
    )
    assert evidence[0]["venue_weight"] == 1.0
    assert evidence[1]["venue_weight"] == 0.75


def test_h2h_parser_is_direct_final_and_pre_kickoff_only() -> None:
    def row(
        fid: int, date: datetime, status: str, home: int, away: int
    ) -> dict[str, object]:
        return {
            "fixture": {"id": fid, "date": date.isoformat(), "status": {"short": status}},
            "teams": {
                "home": {"id": home, "name": str(home)},
                "away": {"id": away, "name": str(away)},
            },
            "league": {"id": 1, "name": "League"},
            "score": {"fulltime": {"home": 2, "away": 1}},
        }

    payload = {
        "response": [
            row(1, NOW - timedelta(days=10), "FT", 10, 20),
            row(2, NOW - timedelta(days=20), "FT", 20, 10),
            row(3, NOW - timedelta(days=30), "AET", 10, 20),
            row(4, NOW - timedelta(days=40), "PEN", 20, 10),
            row(5, NOW - timedelta(days=50), "FT", 10, 20),
            row(6, NOW + timedelta(days=1), "FT", 10, 20),
            row(7, NOW - timedelta(days=60), "NS", 10, 20),
            row(8, NOW - timedelta(days=70), "FT", 99, 20),
        ]
    }
    parsed = parse_h2h_response(
        payload,
        target_home_team_id=10,
        target_away_team_id=20,
        before=NOW,
        maximum=10,
    )
    assert [item["provider_fixture_id"] for item in parsed] == [1, 2, 3, 4, 5]


def test_h2h_settlement_supports_ou25_btts_and_void() -> None:
    base = {
        "shadow_bet_id": "quantlab-shadow-v1:" + "a" * 64,
        "fixture_id": "api-football:1",
        "market_key": "OU_25",
        "selection": "OVER",
        "odds": 2.0,
        "stake_minor": 10_000,
        "provider_status": "FT",
        "home_goals": 2,
        "away_goals": 1,
    }
    over = settle_h2h_shadow_bet(base, settled_at=NOW)
    assert over is not None and over.outcome == "WIN" and over.pnl_minor == 10_000

    btts = settle_h2h_shadow_bet(
        {
            **base,
            "market_key": "BTTS",
            "selection": "NO",
            "home_goals": 1,
            "away_goals": 0,
        },
        settled_at=NOW,
    )
    assert btts is not None and btts.outcome == "WIN"

    void = settle_h2h_shadow_bet({**base, "provider_status": "CANC"}, settled_at=NOW)
    assert void is not None and void.outcome == "VOID" and void.pnl_minor == 0


def _h2h_pick() -> dict[str, object]:
    return {
        "shadow_bet_id": "quantlab-shadow-v1:" + "b" * 64,
        "fixture_id": "api-football:99",
        "lab": "H2H",
        "bookmaker_id": 8,
        "bookmaker_name": "Bet365",
        "provider_bet_id": 8,
        "provider_bet_name": "Both Teams Score",
        "market_key": "BTTS",
        "selection": "NO",
        "line": None,
        "model_name": "DC + H2H Composite",
        "model_version": "dc-v1",
        "policy_version": "H2HLAB_DC_H2H_POLICY_V1",
        "model_probability": 0.66,
        "market_probability": 0.55,
        "edge": 0.11,
        "expected_value": 0.20,
        "odds": 1.82,
        "quote_observed_at": NOW - timedelta(hours=2),
        "decision_at": NOW - timedelta(hours=1),
        "closing_odds": None,
        "closing_observed_at": None,
        "stake_minor": 10_000,
        "outcome": "WIN",
        "pnl_minor": 8_200,
        "settled_at": NOW,
        "home_team": "Home",
        "away_team": "Away",
        "competition_name": "League",
        "country": "England",
        "kickoff_at": NOW - timedelta(hours=3),
        "dc_probability": 0.63,
        "h2h_probability": 0.73,
        "dc_weight": 0.68,
        "h2h_weight": 0.32,
        "h2h_sample_size": 6,
        "decision_details": {
            "dc_probability": 0.63,
            "h2h_probability": 0.73,
            "dc_weight": 0.68,
            "h2h_weight": 0.32,
            "h2h_sample_size": 6,
            "agreement": "CONFIRM",
        },
    }


class _DashboardRepo:
    def list_bets(self, lab: str, **_kwargs: object):
        return (_h2h_pick(),) if lab == "H2H" else ()

    def list_all_bets(self, lab: str, **_kwargs: object):
        return self.list_bets(lab)

    def api_usage_today(self) -> int:
        return 12


def test_h2h_is_a_program_in_both_dashboard_and_analytics_cards() -> None:
    service = QuantLabDashboardService(_DashboardRepo(), view_cache_ttl_seconds=0)
    dashboard = service.render_html("view=dashboard&lab=h2h")
    analytics = service.render_html("view=analytics&lab=h2h")

    assert "H2HLab" in dashboard
    assert ">GoalLab<" in dashboard
    assert ">CornerLab<" in dashboard
    assert ">CardLab<" in dashboard
    assert "H2HLab Analytics" in analytics
    assert "DC × H2H confirmation" in analytics
    assert "DC is capped at 70%" in analytics
