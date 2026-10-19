import pytest

from h2h.domain.competition_scope import (
    CompetitionMetadata,
    RejectionReason,
    classify_phase_i,
)


@pytest.mark.parametrize(
    "metadata",
    [
        CompetitionMetadata("England", "Premier League", "league", 1),
        CompetitionMetadata("Spain", "La Liga", "league", 1),
        CompetitionMetadata("Italy", "Serie B", "league", 2),
        CompetitionMetadata("Germany", "Bundesliga", "league", 1),
        CompetitionMetadata("Germany", "2. Bundesliga", "league", 2),
        CompetitionMetadata("England", "League One", "league", 3),
        CompetitionMetadata("USA", "Major League Soccer", "league", 1),
        CompetitionMetadata("Sweden", "Allsvenskan", "league", 1),
        CompetitionMetadata("Sweden", "Superettan", "league", 2),
        CompetitionMetadata("Finland", "Veikkausliiga", "league", 1),
        CompetitionMetadata("Finland", "Ykkösliiga", "league", 2),
        CompetitionMetadata("Norway", "Eliteserien", "league", 1),
        CompetitionMetadata("Norway", "OBOS-ligaen", "league", 2),
        CompetitionMetadata("Norway", "1. Division", "league", 2),
    ],
)
def test_accepts_representative_senior_leagues(metadata: CompetitionMetadata) -> None:
    assert classify_phase_i(metadata).eligible


@pytest.mark.parametrize(
    ("metadata", "reason"),
    [
        (
            CompetitionMetadata("England", "EFL Trophy", "league"),
            RejectionReason.CUP,
        ),
        (
            CompetitionMetadata("Netherlands", "KNVB Beker", "league"),
            RejectionReason.CUP,
        ),
        (
            CompetitionMetadata("Chile", "Copa Chile", "league"),
            RejectionReason.CUP,
        ),
        (
            CompetitionMetadata("Italy", "Coppa Italia", "league"),
            RejectionReason.CUP,
        ),
        (
            CompetitionMetadata("England", "Non League Premier - Isthmian", "league"),
            RejectionReason.ENGLISH_TIER,
        ),
        (
            CompetitionMetadata("Germany", "Oberliga - Bremen", "league"),
            RejectionReason.GERMAN_TIER,
        ),
        (
            CompetitionMetadata("Spain", "Primera Division U19", "league"),
            RejectionReason.YOUTH,
        ),
        (
            CompetitionMetadata("Argentina", "Reserve League", "league"),
            RejectionReason.YOUTH,
        ),
        (
            CompetitionMetadata("South Africa", "Premier Soccer League", "league"),
            RejectionReason.AFRICA,
        ),
        (
            CompetitionMetadata("World", "CAF Champions League", "league"),
            RejectionReason.AFRICA,
        ),
        (
            CompetitionMetadata("Japan", "J1 League", "league"),
            RejectionReason.ASIA,
        ),
        (
            CompetitionMetadata("Saudi-Arabia", "Pro League", "league"),
            RejectionReason.ASIA,
        ),
        (
            CompetitionMetadata("Australia", "A-League", "league"),
            RejectionReason.ASIA,
        ),
        (
            CompetitionMetadata("World", "AFC Champions League", "league"),
            RejectionReason.ASIA,
        ),
        (
            CompetitionMetadata("England", "League Two", "league", 4),
            RejectionReason.ENGLISH_TIER,
        ),
        (
            CompetitionMetadata("Germany", "3. Liga", "league", 3),
            RejectionReason.GERMAN_TIER,
        ),
        (
            CompetitionMetadata("Germany", "Regionalliga West", "league", 4),
            RejectionReason.GERMAN_TIER,
        ),
        (
            CompetitionMetadata("Czech-Republic", "3. liga - MSFL", "league", 3),
            RejectionReason.EXPLICIT_COMPETITION,
        ),
        (
            CompetitionMetadata(
                country="Wales",
                name="FAW Championship",
                type="league",
                level=2,
                league_id=111,
            ),
            RejectionReason.EXPLICIT_COMPETITION,
        ),
        (
            CompetitionMetadata("Sweden", "Ettan Norra", "league", 3),
            RejectionReason.SWEDEN_TIER,
        ),
        (
            CompetitionMetadata("Sweden", "Division 2 - Norrland", "league", 4),
            RejectionReason.SWEDEN_TIER,
        ),
        (
            CompetitionMetadata("Finland", "Ykkönen", "league", 3),
            RejectionReason.FINLAND_TIER,
        ),
        (
            CompetitionMetadata("Finland", "Kakkonen", "league", 4),
            RejectionReason.FINLAND_TIER,
        ),
        (
            CompetitionMetadata("Norway", "2. Division - Group 1", "league", 3),
            RejectionReason.NORWAY_TIER,
        ),
        (
            CompetitionMetadata("Norway", "3. Division - Group 4", "league", 4),
            RejectionReason.NORWAY_TIER,
        ),
    ],
)
def test_rejects_real_provider_exclusions(
    metadata: CompetitionMetadata, reason: str
) -> None:
    decision = classify_phase_i(metadata)

    assert decision.eligible is False
    assert decision.rejection_reason == reason


@pytest.mark.parametrize(
    "metadata",
    [
        CompetitionMetadata("France", "", "league", 1),
        CompetitionMetadata("France", "Ligue 1", "", 1),
        CompetitionMetadata("France", "Ligue 1", "tournament", 1),
    ],
)
def test_fails_closed_on_ambiguous_metadata(metadata: CompetitionMetadata) -> None:
    decision = classify_phase_i(metadata)

    assert decision.eligible is False
    assert decision.rejection_reason == RejectionReason.AMBIGUOUS


@pytest.mark.parametrize(
    "metadata",
    [
        CompetitionMetadata("England", "Women's Super League", "league", 1),
        CompetitionMetadata("USA", "NWSL", "league", 1),
        CompetitionMetadata("Spain", "Liga F", "league", 1),
        CompetitionMetadata("Germany", "Frauen Bundesliga", "league", 1),
        CompetitionMetadata("Italy", "Serie A Femminile", "league", 1),
        CompetitionMetadata("Mexico", "Liga MX Femenil", "league", 1),
        CompetitionMetadata("Sweden", "Damallsvenskan", "league", 1),
        CompetitionMetadata("Norway", "Toppserien", "league", 1),
        CompetitionMetadata("Denmark", "Kvindeliga", "league", 1),
        CompetitionMetadata("World", "Senior League", "league", 1, "Arsenal W", "Chelsea W"),
    ],
)
def test_rejects_womens_football_globally(metadata: CompetitionMetadata) -> None:
    decision = classify_phase_i(metadata)

    assert decision.eligible is False
    assert decision.rejection_reason == RejectionReason.WOMEN


@pytest.mark.parametrize(
    "metadata",
    [
        CompetitionMetadata("World", "Friendlies", "Cup", league_id=10),
        CompetitionMetadata("World", "Friendlies Clubs", "Cup"),
        CompetitionMetadata("World", "Club Friendlies", "Cup"),
        CompetitionMetadata("England", "International Friendly", "Friendly"),
    ],
)
def test_rejects_friendlies_globally(metadata: CompetitionMetadata) -> None:
    decision = classify_phase_i(metadata)

    assert decision.eligible is False
    assert decision.rejection_reason == RejectionReason.FRIENDLY


@pytest.mark.parametrize(
    "metadata",
    [
        CompetitionMetadata("World", "World Cup", "Cup", league_id=1),
        CompetitionMetadata("World", "Euro Championship", "Cup", league_id=4),
        CompetitionMetadata("World", "UEFA Nations League", "Cup", league_id=5),
        CompetitionMetadata("World", "Africa Cup of Nations", "Cup", league_id=6),
        CompetitionMetadata("World", "Asian Cup", "Cup", league_id=7),
        CompetitionMetadata("World", "Copa America", "Cup", league_id=9),
        CompetitionMetadata("World", "CONCACAF Nations League", "Cup"),
        CompetitionMetadata("World", "World Cup - Qualification Europe", "Cup"),
        CompetitionMetadata("World", "Concacaf Gold Cup", "Cup"),
        CompetitionMetadata("World", "FIFA Series", "Cup"),
        CompetitionMetadata("World", "CONMEBOL-UEFA Finalissima", "Cup"),
    ],
)
def test_rejects_national_team_football_globally(metadata: CompetitionMetadata) -> None:
    decision = classify_phase_i(metadata)

    assert decision.eligible is False
    assert decision.rejection_reason == RejectionReason.NATIONAL_TEAM


@pytest.mark.parametrize("league_id", [40, 72, 75, 135, 236, 365, 595])
def test_rejects_global_blacklisted_league_ids(league_id: int) -> None:
    decision = classify_phase_i(
        CompetitionMetadata(
            country="Brazil",
            name="Senior League",
            type="league",
            league_id=league_id,
        )
    )

    assert decision.eligible is False
    assert decision.rejection_reason == RejectionReason.BLACKLISTED_LEAGUE

@pytest.mark.parametrize(
    "metadata",
    [
        CompetitionMetadata("Ecuador", "Liga Pro", "league", 1),
        CompetitionMetadata("ECUADOR", "Serie B", "league", 2),
        CompetitionMetadata("Ecuador", "Any Competition", "cup"),
        CompetitionMetadata("Bolivia", "Primera División", "league", 1),
        CompetitionMetadata("BOLIVIA", "Any Competition", "cup"),
        CompetitionMetadata("Ireland", "Premier Division", "league", 1),
        CompetitionMetadata("IRELAND", "First Division", "league", 2),
        CompetitionMetadata("Republic of Ireland", "Senior League", "league", 1),
    ],
)
def test_rejects_blocked_country_across_entire_universe(
    metadata: CompetitionMetadata,
) -> None:
    decision = classify_phase_i(metadata)

    assert decision.eligible is False
    assert decision.rejection_reason == RejectionReason.BLOCKED_COUNTRY



@pytest.mark.parametrize(
    "metadata",
    [
        CompetitionMetadata(
            country="Finland",
            name="Ykkösliiga",
            type="league",
            level=2,
            home_team="Klubi-04",
            away_team="EIF",
        ),
        CompetitionMetadata(
            country="Finland",
            name="Ykkösliiga",
            type="league",
            level=2,
            home_team="JäPS",
            away_team="KLUBI04",
        ),
    ],
)
def test_rejects_klubi_04_across_entire_universe(metadata: CompetitionMetadata) -> None:
    decision = classify_phase_i(metadata)

    assert decision.eligible is False
    assert decision.rejection_reason == RejectionReason.BLOCKED_TEAM


@pytest.mark.parametrize(
    ("country", "competition_name", "league_id"),
    [
        ("Latvia", "Virslīga", 365),
        ("LATVIA", "Virsliga", "365"),
        ("Latvia", "Virslīga", None),
        ("latvia", "VIRSLIGA", None),
        ("Other Country", "Other Competition", 365),
    ],
)
def test_virsliga_global_hard_ban_cannot_be_bypassed_by_metadata_aliases(
    country: str, competition_name: str, league_id: object,
) -> None:
    from h2h.domain.competition_scope import (
        is_universe_blocked_competition,
        universe_block_reason,
    )

    kwargs = {
        "country": country,
        "competition_name": competition_name,
        "league_id": league_id,
    }
    assert universe_block_reason(**kwargs) == RejectionReason.BLACKLISTED_LEAGUE
    assert is_universe_blocked_competition(**kwargs)
    assert classify_phase_i(
        CompetitionMetadata(
            country=country, name=competition_name, type="league", league_id=league_id,
        )
    ).eligible is False


@pytest.mark.parametrize(
    ("competition_name", "league_id"),
    [("1. Liga", 368), ("2. Liga", 369), ("Latvian Cup", 367)],
)
def test_other_latvian_leagues_are_not_globally_blacklisted(
    competition_name: str, league_id: int,
) -> None:
    from h2h.domain.competition_scope import universe_block_reason

    assert universe_block_reason(
        country="Latvia", competition_name=competition_name, league_id=league_id
    ) is None


@pytest.mark.parametrize(
    ("country", "competition_name", "league_id"),
    [
        ("England", "Championship", 40),
        ("England", "Championship", "40"),
        ("ENGLAND", "CHAMPIONSHIP", None),
        ("England", "Championship", None),
        ("England", "Other League Label", 40),
        ("Other Country", "Different League", 40),
    ],
)
def test_england_championship_is_globally_banned_with_id_or_exact_country_name(
    country: str, competition_name: str, league_id: object,
) -> None:
    from h2h.domain.competition_scope import (
        is_universe_blocked_competition,
        universe_block_reason,
    )

    kwargs = {
        "country": country,
        "competition_name": competition_name,
        "league_id": league_id,
    }
    assert universe_block_reason(**kwargs) == RejectionReason.BLACKLISTED_LEAGUE
    assert is_universe_blocked_competition(**kwargs)
    assert classify_phase_i(CompetitionMetadata(
        country=country,
        name=competition_name,
        type="league",
        league_id=league_id,
    )).rejection_reason == RejectionReason.BLACKLISTED_LEAGUE


@pytest.mark.parametrize(
    ("country", "competition_name", "league_id"),
    [
        ("England", "Premier League", 39),
        ("England", "League One", 41),
        ("Scotland", "Championship", 179),
        ("Scotland", "Championship", None),
    ],
)
def test_championship_ban_does_not_block_other_domestic_leagues(
    country: str, competition_name: str, league_id: object,
) -> None:
    from h2h.domain.competition_scope import universe_block_reason

    assert universe_block_reason(
        country=country,
        competition_name=competition_name,
        league_id=league_id,
    ) is None


@pytest.mark.parametrize(
    ("country", "name", "league_id"),
    [
        ("Italy", "Serie A", 135),
        ("ITALY", "SERIE A", None),
        ("Italia", "Serie A - Championship Round", None),
        ("Italy", "Serie A - Relegation Round", None),
        ("Other Country", "Other League", "135"),
    ],
)
def test_italy_serie_a_globally_blocked_by_id_or_competition_family(
    country: str, name: str, league_id: object,
) -> None:
    from h2h.domain.competition_scope import is_universe_blocked_competition, universe_block_reason

    kwargs = {"country": country, "competition_name": name, "league_id": league_id}
    assert universe_block_reason(**kwargs) == RejectionReason.BLACKLISTED_LEAGUE
    assert is_universe_blocked_competition(**kwargs)
    assert not classify_phase_i(CompetitionMetadata(country, name, "league", league_id=league_id)).eligible


@pytest.mark.parametrize(
    ("country", "name"),
    [
        ("Israel", "Ligat HaAl"),
        ("ISRAËL", "Liga Leumit"),
        ("State of Israel", "Liga Alef North"),
        ("ISR", "State Cup"),
    ],
)
def test_entire_israeli_domestic_football_is_globally_blocked(country: str, name: str) -> None:
    from h2h.domain.competition_scope import universe_block_reason

    assert universe_block_reason(country=country, competition_name=name) == RejectionReason.BLOCKED_COUNTRY
    assert classify_phase_i(CompetitionMetadata(country, name, "league")).rejection_reason == RejectionReason.BLOCKED_COUNTRY


@pytest.mark.parametrize(
    ("country", "name", "league_id"),
    [
        ("Italy", "Serie B", 136),
        ("Italy", "Serie C", 137),
        ("Brazil", "Serie A", 71),
        ("Spain", "La Liga", 140),
    ],
)
def test_ban_does_not_expand_to_other_italian_leagues_or_countries(
    country: str, name: str, league_id: int,
) -> None:
    from h2h.domain.competition_scope import universe_block_reason

    assert universe_block_reason(country=country, competition_name=name, league_id=league_id) is None
