"""Read-only CardLab referee directory regression tests."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from h2h.quantlab.card_lab import referee_directory as directory


NOW = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)


def _web(
    *,
    name: str = "José Ref",
    league: str = "spain_la_liga",
    season: int = 2026,
    matches: int = 10,
    yellow: int = 40,
    second: int = 1,
    red: int = 2,
    url: str = "https://www.statbunker.com/competitions/RefereeYellowCards?comp_id=792",
) -> dict:
    return {
        "referee_name": name,
        "league_key": league,
        "season": season,
        "matches": matches,
        "yellow_cards": yellow,
        "second_yellow_cards": second,
        "red_cards": red,
        "captured_at": NOW,
        "source_url": url,
    }


def _api(
    name: str = "Jose Ref, Spain",
    league: str | None = "spain_la_liga",
    *,
    sample: int = 8,
) -> dict:
    return {
        "referee": name,
        "referee_card_rate": 4.1,
        "referee_sample_size": sample,
        "referee_foul_rate": 23,
        "referee_foul_sample_size": 8,
        "feature_payload": {
            "raw_features": {
                "web_referee_league_key": league,
                "referee_l5_cards": 4.4,
                "referee_l10_cards": 4.0,
                "referee_l5_fouls": 21.0,
                "referee_l10_fouls": 22.5,
            }
        },
        "decision_at": NOW,
    }


def test_web_seasons_are_aggregated_once_and_join_to_api_l5_l10() -> None:
    rows = directory.build_referee_directory(
        (_web(), _web(season=2025, matches=8, yellow=30, second=0, red=1)),
        (_api(),),
    )
    assert len(rows) == 1
    entry = rows[0]
    assert entry["web_matches"] == 18
    assert entry["web_cards"] == 74
    assert entry["web_cards_per_match"] == 74 / 18
    assert entry["seasons"] == (2026, 2025)
    assert entry["api_sample"] == 8
    assert entry["l5_cards"] == 4.4
    assert entry["l10_fouls"] == 22.5
    assert entry["sources"] == ("API-Football", "StatBunker")


def test_ambiguous_names_do_not_cross_attach_without_league() -> None:
    rows = directory.build_referee_directory(
        (_web(league="spain_la_liga"), _web(league="italy_serie_a")),
        (_api(league=None),),
    )
    assert len(rows) == 3
    web_entries = [row for row in rows if row["web_matches"]]
    assert all(entry["api_sample"] == 0 for entry in web_entries)
    orphan = next(row for row in rows if row["league_key"] == "api_other")
    assert orphan["api_sample"] == 8


def test_name_search_season_and_missing_numeric_sort() -> None:
    rows = directory.build_referee_directory(
        (_web(name="Luis Ref"), _web(name="Anna Ref", matches=3)),
        (_api(name="Luis Ref", sample=10),),
    )
    found, _sort, _dir = directory.filter_sort_directory(
        rows, {"q": ["Luis"], "season": ["2026"], "sort": ["l10_cards"]}
    )
    assert len(found) == 1
    assert found[0]["name"] == "Luis Ref"
    sorted_rows, _, _ = directory.filter_sort_directory(
        rows, {"sort": ["l10_cards"], "dir": ["desc"]}
    )
    assert sorted_rows[0]["name"] == "Luis Ref"
    assert sorted_rows[-1]["l10_cards"] is None


def test_page_escapes_user_data_and_filters(monkeypatch) -> None:
    monkeypatch.setattr(
        directory,
        "load_referee_directory_data",
        lambda repo: ((_web(name="<script>alert(1)</script>", url="javascript:alert(1)"),), ()),
    )
    html = directory.render_referee_directory(object(), "q=%3Cscript%3E&league=spain_la_liga")
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert(1)</script>" not in html
    assert 'href="javascript:' not in html
    assert "Referee Database" in html
    assert "API L10 fouls" in html


def test_queries_deduplicate_immutable_captures_and_are_read_only() -> None:
    class Cursor:
        description = [SimpleNamespace(name="referee_name")]

        def __init__(self) -> None:
            self.queries = []

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def execute(self, statement: str) -> None:
            self.queries.append(statement)

        def fetchall(self):
            return []

    class Connection:
        def __init__(self):
            self.cursor_instance = Cursor()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def cursor(self):
            return self.cursor_instance

    connection = Connection()

    class Repo:
        def connect(self):
            return connection

    web, features = directory.load_referee_directory_data(Repo())
    assert web == features == ()
    assert len(connection.cursor_instance.queries) == 2
    assert all(query.lstrip().startswith("SELECT DISTINCT ON") for query in connection.cursor_instance.queries)
    assert "league_key, season, referee_key" in connection.cursor_instance.queries[0]
    assert "decision_at DESC" in connection.cursor_instance.queries[1]
