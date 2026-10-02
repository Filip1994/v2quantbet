"""Public-web referee profile ingestion for CardLab."""

from __future__ import annotations

import re
import unicodedata
from html.parser import HTMLParser
from urllib.request import Request, urlopen


SOURCE_NAME = "STATBUNKER"
SOURCE_BASE_URL = "https://www.statbunker.com/competitions/RefereeYellowCards"
DEFAULT_USER_AGENT = "v2quantbet-cardlab-referee/1.0"

TOP_LEAGUES: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "england_premier_league": ("England", "Premier League", ("premier league",)),
    "spain_la_liga": ("Spain", "La Liga", ("la liga", "laliga", "primera division")),
    "italy_serie_a": ("Italy", "Serie A", ("serie a",)),
    "germany_bundesliga": ("Germany", "Bundesliga", ("bundesliga",)),
    "france_ligue_1": ("France", "Ligue 1", ("ligue 1",)),
}

STATBUNKER_COMPETITION_IDS: dict[tuple[str, int], int] = {
    ("england_premier_league", 2026): 791,
    ("spain_la_liga", 2026): 792,
    ("france_ligue_1", 2026): 796,
    ("italy_serie_a", 2026): 797,
    ("germany_bundesliga", 2026): 798,
    ("england_premier_league", 2025): 776,
    ("spain_la_liga", 2025): 777,
    ("italy_serie_a", 2025): 785,
    ("germany_bundesliga", 2025): 786,
    ("france_ligue_1", 2025): 787,
    ("germany_bundesliga", 2024): 762,
}


def _ascii(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def referee_web_referee_key(value: object) -> str:
    return _ascii(str(value or "").split(",", 1)[0])


def referee_web_league_key(country: object, competition_name: object) -> str | None:
    country_key = _ascii(country)
    competition_key = _ascii(competition_name)
    for key, (expected_country, _display, aliases) in TOP_LEAGUES.items():
        if country_key != _ascii(expected_country):
            continue
        if any(competition_key == _ascii(alias) for alias in aliases):
            return key
    return None


def statbunker_competition_id(league_key: str, season: int) -> int | None:
    return STATBUNKER_COMPETITION_IDS.get((league_key, season))


def supported_web_seasons(
    league_key: str, current_season: int, *, limit: int = 3
) -> tuple[int, ...]:
    seasons: list[int] = []
    for season in range(current_season, max(0, current_season - 4), -1):
        if statbunker_competition_id(league_key, season) is not None:
            seasons.append(season)
        if len(seasons) >= limit:
            break
    return tuple(seasons)


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[tuple[str, ...]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []
        elif tag == "img" and self._cell is not None:
            alt = next((value for key, value in attrs if key == "alt" and value), None)
            if alt:
                self._cell.append(alt)

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._row is not None and self._cell is not None:
            self._row.append(" ".join(" ".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(tuple(self._row))
            self._row = None
            self._cell = None


def _integer(value: object) -> int:
    text = str(value or "").strip()
    if not text or text == "-":
        return 0
    match = re.search(r"-?\d+", text.replace(",", ""))
    if not match:
        raise ValueError(f"not an integer: {text!r}")
    return int(match.group())


def _float(value: object) -> float | None:
    text = str(value or "").strip()
    if not text or text == "-":
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", text.replace(",", "."))
    return None if not match else float(match.group())


def parse_statbunker_referee_profiles(html: str) -> tuple[dict[str, object], ...]:
    parser = _TableParser()
    parser.feed(html)
    in_referee_table = False
    profiles: list[dict[str, object]] = []
    for row in parser.rows:
        if len(row) >= 2 and row[0].strip().casefold() == "referee":
            in_referee_table = row[1].strip().casefold() in {"p", "matches"}
            continue
        if not in_referee_table:
            continue
        referee = row[0].strip() if row else ""
        if not referee:
            break
        if len(row) < 11:
            continue
        try:
            matches = _integer(row[1])
            if matches <= 0:
                continue
            profiles.append(
                {
                    "referee": referee,
                    "matches": matches,
                    "home_cards": _integer(row[4]),
                    "away_cards": _integer(row[5]),
                    "yellow_cards": _integer(row[6]),
                    "second_yellow_cards": _integer(row[7]),
                    "red_cards": _integer(row[8]),
                    "yellow_cards_per_match": _float(row[9]),
                    "cards_per_match": _float(row[10]),
                }
            )
        except ValueError:
            continue
    return tuple(profiles)


class StatBunkerRefereeSource:
    def __init__(
        self, *, timeout: float = 10.0, user_agent: str = DEFAULT_USER_AGENT
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self._timeout = timeout
        self._user_agent = user_agent

    @staticmethod
    def source_url(league_key: str, season: int) -> str | None:
        comp_id = statbunker_competition_id(league_key, season)
        if comp_id is None:
            return None
        return f"{SOURCE_BASE_URL}?comp_id={comp_id}"

    def fetch_profiles(
        self, league_key: str, season: int
    ) -> tuple[str, tuple[dict[str, object], ...]]:
        if league_key not in TOP_LEAGUES:
            raise ValueError("unsupported referee web league")
        url = self.source_url(league_key, season)
        if url is None:
            raise ValueError("unsupported referee web league/season")
        request = Request(
            url,
            headers={
                "User-Agent": self._user_agent,
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        with urlopen(request, timeout=self._timeout) as response:  # noqa: S310
            charset = response.headers.get_content_charset() or "utf-8"
            html = response.read().decode(charset, errors="replace")

        _country, display_name, _aliases = TOP_LEAGUES[league_key]
        season_label = f"{str(season)[-2:]}/{str(season + 1)[-2:]}"
        page_key = _ascii(re.sub(r"<[^>]+>", " ", html))
        if _ascii(display_name) not in page_key or _ascii(season_label) not in page_key:
            raise ValueError("StatBunker league/season validation failed")

        profiles = parse_statbunker_referee_profiles(html)
        if not profiles:
            raise ValueError("StatBunker referee table was empty or unparseable")
        return url, profiles
