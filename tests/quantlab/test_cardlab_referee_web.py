from h2h.quantlab.card_lab.referee_web import (
    parse_statbunker_referee_profiles,
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
