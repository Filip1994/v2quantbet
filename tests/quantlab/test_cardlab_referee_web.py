from datetime import UTC, datetime

from h2h.quantlab.card_lab.referee_web import (
    current_web_season,
    parse_statbunker_referee_profiles,
    proactive_web_targets,
    referee_web_league_key,
    referee_web_referee_key,
    supported_web_seasons,
)


def test_referee_web_league_scope_is_top_five_only() -> None:
    assert referee_web_league_key("England", "Premier League") == "england_premier_league"
    assert referee_web_league_key("Spain", "La Liga") == "spain_la_liga"
    assert referee_web_league_key("Italy", "Serie A") == "italy_serie_a"
    assert referee_web_league_key("Germany", "Bundesliga") == "germany_bundesliga"
    assert referee_web_league_key("France", "Ligue 1") == "france_ligue_1"
    assert referee_web_league_key("Netherlands", "Eredivisie") is None
    assert referee_web_league_key("England", "Championship") is None


def test_referee_web_normalizes_provider_suffixes_and_accents() -> None:
    assert referee_web_referee_key("José María Sánchez, Spain") == "jose maria sanchez"
    assert referee_web_referee_key("  Michael   Oliver  ") == "michael oliver"


def test_statbunker_parser_extracts_referee_card_profile() -> None:
    html = """
    <html><body>
      <table>
        <tr>
          <th>Referee</th><th>P</th><th>FH(AM)</th><th>SH(AM)</th>
          <th>H</th><th>A</th><th>Yellow Card</th><th>Red+Yellow</th>
          <th>Red</th><th>Yellow/Match</th><th>Cards/Match</th>
        </tr>
        <tr>
          <td>Michael Oliver</td><td>12</td><td>1.0</td><td>1.0</td>
          <td>32</td><td>29</td><td>58</td><td>2</td><td>1</td>
          <td>4.83</td><td>5.08</td>
        </tr>
        <tr>
          <td>Anthony Taylor</td><td>10</td><td>1.0</td><td>1.0</td>
          <td>25</td><td>26</td><td>48</td><td>2</td><td>1</td>
          <td>4.80</td><td>5.10</td>
        </tr>
      </table>
    </body></html>
    """

    profiles = parse_statbunker_referee_profiles(html)

    assert len(profiles) == 2
    assert profiles[0] == {
        "referee": "Michael Oliver",
        "matches": 12,
        "home_cards": 32,
        "away_cards": 29,
        "yellow_cards": 58,
        "second_yellow_cards": 2,
        "red_cards": 1,
        "yellow_cards_per_match": 4.83,
        "cards_per_match": 5.08,
    }


def test_supported_web_seasons_uses_only_known_source_ids() -> None:
    assert supported_web_seasons("england_premier_league", 2026, limit=3) == (2026, 2025)
    assert supported_web_seasons("germany_bundesliga", 2026, limit=3) == (2026, 2024)



def test_current_web_season_uses_domestic_july_boundary() -> None:
    assert current_web_season(datetime(2026, 10, 2, tzinfo=UTC)) == 2026
    assert current_web_season(datetime(2026, 2, 2, tzinfo=UTC)) == 2025


def test_proactive_web_targets_cover_all_top_five_leagues_without_fixtures() -> None:
    targets = proactive_web_targets(
        datetime(2026, 10, 2, tzinfo=UTC),
        seasons_per_league=3,
    )

    league_keys = {league_key for league_key, _season, _comp_id in targets}
    assert league_keys == {
        "england_premier_league",
        "spain_la_liga",
        "italy_serie_a",
        "germany_bundesliga",
        "france_ligue_1",
    }
    assert ("england_premier_league", 2026, 791) in targets
    assert ("spain_la_liga", 2026, 792) in targets
    assert ("france_ligue_1", 2026, 796) in targets
    assert ("italy_serie_a", 2026, 797) in targets
    assert ("germany_bundesliga", 2026, 798) in targets
