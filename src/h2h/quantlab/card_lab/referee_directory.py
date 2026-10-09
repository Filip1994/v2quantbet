"""Read-only, searchable CardLab referee database.

StatBunker rows are season-level public referee aggregates. L5/L10 values come
from the latest timestamp-safe API-Football CardLab feature snapshot; they are
NOT backfilled into earlier decisions or used to create picks here.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from html import escape
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

from h2h.quantlab.card_lab.referee_web import (
    TOP_LEAGUES,
    referee_web_referee_key,
)

PAGE_SIZE = 75
BASE_PATH = "/quantlab/card/referees"


def _dict_rows(cursor: Any) -> tuple[dict[str, Any], ...]:
    columns = tuple(column.name for column in cursor.description)
    return tuple(dict(zip(columns, row, strict=True)) for row in cursor.fetchall())


def load_referee_directory_data(
    repository: Any,
) -> tuple[tuple[dict[str, Any], ...], tuple[dict[str, Any], ...]]:
    """Read only latest season captures and latest per-referee model snapshots.

    Deduplicate immutable repeated StatBunker captures BEFORE summing season
    statistics. Old feature snapshots stay in the ledger, but this directory
    displays the most recent one for each referee/league combination.
    """
    with repository.connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT DISTINCT ON (league_key, season, referee_key) "
            "league_key, season, referee_name, referee_key, matches, "
            "yellow_cards, second_yellow_cards, red_cards, "
            "home_cards, away_cards, cards_per_match, captured_at, source_url "
            "FROM quantlab_referee_web_profiles "
            "ORDER BY league_key, season, referee_key, "
            "captured_at DESC, referee_web_profile_id DESC"
        )
        web = _dict_rows(cursor)
        cursor.execute(
            "SELECT DISTINCT ON ("
            " lower(btrim(split_part(referee, ',', 1))), "
            " COALESCE(feature_payload #>> '{raw_features,web_referee_league_key}', '')"
            ") referee, referee_card_rate, referee_sample_size, "
            "referee_foul_rate, referee_foul_sample_size, "
            "feature_payload, decision_at, available_at "
            "FROM quantlab_card_feature_snapshots "
            "WHERE referee IS NOT NULL AND btrim(referee) <> '' "
            "ORDER BY lower(btrim(split_part(referee, ',', 1))), "
            " COALESCE(feature_payload #>> '{raw_features,web_referee_league_key}', ''), "
            "decision_at DESC, feature_snapshot_id DESC"
        )
        features = _dict_rows(cursor)
    return web, features


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _date(value: Any) -> str:
    return value.strftime("%Y-%m-%d %H:%M UTC") if isinstance(value, datetime) else "—"


def _metric(value: Any) -> str:
    number = _number(value)
    return "—" if number is None else f"{number:.2f}"


def _safe_source_url(value: Any) -> str | None:
    url = str(value or "")
    parsed = urlsplit(url)
    if parsed.scheme == "https" and parsed.hostname == "www.statbunker.com":
        return url
    return None


def _league_label(key: str) -> str:
    if key in TOP_LEAGUES:
        country, name, _aliases = TOP_LEAGUES[key]
        return f"{name} · {country}"
    return "Other competitions · API-Football"


def build_referee_directory(
    web_rows: tuple[dict[str, Any], ...],
    feature_rows: tuple[dict[str, Any], ...],
) -> list[dict[str, Any]]:
    """One display row per normalized referee per league, never per scrape.

    Season sums are safe only because load_referee_directory_data selects the
    latest capture for each referee, league and season.
    """
    result: dict[tuple[str, str], dict[str, Any]] = {}

    for row in web_rows:
        name = str(row.get("referee_name") or "").strip()
        league = str(row.get("league_key") or "").strip()
        key = referee_web_referee_key(name)
        count = int(row.get("matches") or 0)
        if not name or not key or not league or count <= 0:
            continue
        group = result.setdefault(
            (league, key),
            {
                "name": name,
                "league_key": league,
                "seasons": set(),
                "web_matches": 0,
                "web_cards": 0,
                "web_yellow": 0,
                "web_second_yellow": 0,
                "web_red": 0,
                "web_captured_at": None,
                "web_source_url": None,
                "feature_at": None,
                "api_sample": 0,
                "api_foul_sample": 0,
                "api_card_rate": None,
                "api_foul_rate": None,
                "l5_cards": None,
                "l10_cards": None,
                "l5_fouls": None,
                "l10_fouls": None,
                "sources": {"StatBunker"},
            },
        )
        group["seasons"].add(int(row["season"]))
        group["web_matches"] += count
        group["web_yellow"] += int(row.get("yellow_cards") or 0)
        group["web_second_yellow"] += int(row.get("second_yellow_cards") or 0)
        group["web_red"] += int(row.get("red_cards") or 0)
        group["web_cards"] += (
            int(row.get("yellow_cards") or 0)
            + int(row.get("second_yellow_cards") or 0)
            + int(row.get("red_cards") or 0)
        )
        capture_at = row.get("captured_at")
        if group["web_captured_at"] is None or (
            isinstance(capture_at, datetime) and capture_at > group["web_captured_at"]
        ):
            group["web_captured_at"] = capture_at
            group["web_source_url"] = _safe_source_url(row.get("source_url"))

    # Attach API data only to an explicit league, or a unique name match.
    # A name appearing in multiple leagues is not enough to identify a referee.
    by_name: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for group_key in result:
        by_name[group_key[1]].append(group_key)

    for row in feature_rows:
        name = str(row.get("referee") or "").split(",", 1)[0].strip()
        key = referee_web_referee_key(name)
        if not key:
            continue
        payload = row.get("feature_payload")
        payload = payload if isinstance(payload, dict) else {}
        raw = payload.get("raw_features")
        raw = raw if isinstance(raw, dict) else {}
        league = str(raw.get("web_referee_league_key") or "").strip()
        target = (league, key) if league else None
        if target not in result:
            candidates = by_name.get(key, [])
            target = candidates[0] if len(candidates) == 1 and not league else (league or "api_other", key)
        if target not in result:
            result[target] = {
                "name": name,
                "league_key": target[0],
                "seasons": set(),
                "web_matches": 0,
                "web_cards": 0,
                "web_yellow": 0,
                "web_second_yellow": 0,
                "web_red": 0,
                "web_captured_at": None,
                "web_source_url": None,
                "feature_at": None,
                "api_sample": 0,
                "api_foul_sample": 0,
                "api_card_rate": None,
                "api_foul_rate": None,
                "l5_cards": None,
                "l10_cards": None,
                "l5_fouls": None,
                "l10_fouls": None,
                "sources": set(),
            }
        group = result[target]
        at = row.get("decision_at")
        if group["feature_at"] is not None and (
            not isinstance(at, datetime) or at <= group["feature_at"]
        ):
            continue
        group["sources"].add("API-Football")
        group["feature_at"] = at
        group["api_sample"] = int(row.get("referee_sample_size") or 0)
        group["api_foul_sample"] = int(row.get("referee_foul_sample_size") or 0)
        group["api_card_rate"] = _number(row.get("referee_card_rate"))
        group["api_foul_rate"] = _number(row.get("referee_foul_rate"))
        for field in ("l5_cards", "l10_cards", "l5_fouls", "l10_fouls"):
            group[field] = _number(raw.get("referee_" + field))
    for item in result.values():
        item["web_cards_per_match"] = (
            item["web_cards"] / item["web_matches"] if item["web_matches"] else None
        )
        item["seasons"] = tuple(sorted(item["seasons"], reverse=True))
        item["sources"] = tuple(sorted(item["sources"]))
    return list(result.values())


def _sort_value(row: dict[str, Any], key: str) -> Any:
    if key == "name":
        return row["name"].casefold()
    if key == "league":
        return _league_label(row["league_key"]).casefold()
    if key == "season":
        return max(row["seasons"], default=0)
    if key == "matches":
        return row["web_matches"]
    if key == "cards":
        return row["web_cards_per_match"]
    if key in {"l5_cards", "l10_cards", "l10_fouls"}:
        return row[key]
    if key == "sample":
        return row["api_sample"]
    return None


def filter_sort_directory(
    rows: list[dict[str, Any]],
    params: dict[str, list[str]],
) -> tuple[list[dict[str, Any]], str, str]:
    q = params.get("q", [""])[0].strip().casefold()[:100]
    league = params.get("league", [""])[0]
    season = params.get("season", [""])[0]
    sort = params.get("sort", ["matches"])[0]
    if sort not in {"name", "league", "season", "matches", "cards", "l5_cards", "l10_cards", "l10_fouls", "sample"}:
        sort = "matches"
    direction = params.get("dir", ["desc"])[0]
    direction = direction if direction in {"asc", "desc"} else "desc"
    selected = [
        row for row in rows
        if (not q or q in row["name"].casefold())
        and (not league or row["league_key"] == league)
        and (not season or season in {str(value) for value in row["seasons"]})
    ]
    # Missing metrics always last. Tie-break by referee + league for stable pages.
    selected.sort(key=lambda r: (r["name"].casefold(), r["league_key"]))
    selected.sort(
        key=lambda r: _sort_value(r, sort),
        reverse=direction == "desc",
    ) if all(_sort_value(r, sort) is not None for r in selected) else selected.sort(
        key=lambda r: (
            _sort_value(r, sort) is None,
            -(float(_sort_value(r, sort)) or 0) if direction == "desc" else (float(_sort_value(r, sort)) or 0),
        ) if sort not in {"name", "league"} else (
            _sort_value(r, sort) is None,
            _sort_value(r, sort) or "",
        ),
    )
    if sort in {"name", "league"} and direction == "desc":
        selected.reverse()
    return selected, sort, direction


def render_referee_directory(repository: Any, raw_query: str = "") -> str:
    params = parse_qs(raw_query, keep_blank_values=True)
    data = build_referee_directory(*load_referee_directory_data(repository))
    selected, sort, direction = filter_sort_directory(data, params)
    try:
        page = max(1, min(10000, int(params.get("page", ["1"])[0])))
    except ValueError:
        page = 1
    max_page = max(1, (len(selected) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(page, max_page)
    visible = selected[(page - 1) * PAGE_SIZE:page * PAGE_SIZE]

    def url(**changes: str) -> str:
        merged = {key: val[0] for key, val in params.items()
                  if key in {"q", "league", "season", "sort", "dir", "page"} and val}
        merged.update(changes)
        return BASE_PATH + "?" + urlencode(merged)

    options = ['<option value="">All leagues</option>']
    present = {row["league_key"] for row in data}
    for key in sorted(present, key=_league_label):
        selected_attr = ' selected' if params.get("league", [""])[0] == key else ""
        options.append(
            f'<option value="{escape(key, quote=True)}"{selected_attr}>'
            f'{escape(_league_label(key))}</option>'
        )
    season_options = ['<option value="">All seasons</option>']
    seasons = sorted({s for row in data for s in row["seasons"]}, reverse=True)
    for season in seasons:
        selected_attr = ' selected' if params.get("season", [""])[0] == str(season) else ""
        season_options.append(
            f'<option value="{season}"{selected_attr}>{season}/{str(season + 1)[-2:]}</option>'
        )

    labels = (
        ("name", "Referee"), ("league", "League"), ("season", "Seasons"),
        ("matches", "Web matches"), ("cards", "Web cards / match"),
        ("l5_cards", "API L5 cards"), ("l10_cards", "API L10 cards"),
        ("l10_fouls", "API L10 fouls"), ("sample", "API card n"),
    )
    th = []
    for key, label in labels:
        new_dir = "asc" if key != sort or direction == "desc" else "desc"
        href = escape(url(sort=key, dir=new_dir, page="1"), quote=True)
        marker = (" ▲" if direction == "asc" else " ▼") if key == sort else ""
        th.append(f'<th><a href="{href}">{escape(label)}{marker}</a></th>')
    th.append("<th>Evidence / updated</th>")

    body = []
    for row in visible:
        web_n = row["web_matches"]
        api_n = row["api_sample"]
        evidence = ", ".join(row["sources"])
        state = "Web 10+" if web_n >= 10 else "API 5+" if api_n >= 5 else "Limited history"
        source_url = row["web_source_url"]
        source_link = (
            f'<a href="{escape(source_url, quote=True)}" target="_blank" '
            'rel="noopener noreferrer">StatBunker ↗</a>'
            if source_url else ""
        )
        body.append(
            "<tr>"
            f'<td><strong>{escape(row["name"])}</strong><small>{escape(state)}</small></td>'
            f'<td>{escape(_league_label(row["league_key"]))}</td>'
            f'<td>{escape(", ".join(str(s) + "/" + str(s + 1)[-2:] for s in row["seasons"]) or "—")}</td>'
            f'<td class="num">{web_n if web_n else "—"}</td>'
            f'<td class="num">{_metric(row["web_cards_per_match"])}</td>'
            f'<td class="num">{_metric(row["l5_cards"])}</td>'
            f'<td class="num">{_metric(row["l10_cards"])}</td>'
            f'<td class="num">{_metric(row["l10_fouls"])}</td>'
            f'<td class="num">{api_n if "API-Football" in row["sources"] else "—"}</td>'
            f'<td><small>{escape(evidence)}<br>Web: {_date(row["web_captured_at"])}<br>'
            f'API snapshot: {_date(row["feature_at"])}</small>{source_link}</td>'
            "</tr>"
        )
    if not body:
        body = ['<tr><td colspan="10" class="empty">No referees match these filters.</td></tr>']

    p_links = (
        f'<a href="{escape(url(page=str(page - 1)), quote=True)}">← Previous</a> '
        if page > 1 else ""
    )
    p_links += f'Page {page}/{max_page} · {len(selected)} matching'
    if page < max_page:
        p_links += (
            f' <a href="{escape(url(page=str(page + 1)), quote=True)}">Next →</a>'
        )
    q = escape(params.get("q", [""])[0][:100], quote=True)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Referee Database · CardLab · QuantBet</title>
<style>
:root{{color-scheme:dark;--bg:#0b1018;--panel:#151c29;--border:#293447;--text:#e8eef8;--muted:#a4b2c6;--link:#8fbaf9}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 system-ui,sans-serif}}
main{{max-width:1600px;margin:auto;padding:24px}}h1{{margin:0;font-size:26px}}
p{{color:var(--muted)}}a{{color:var(--link)}}.nav{{display:flex;gap:18px;margin-bottom:16px}}
.eyebrow{{font-size:12px;text-transform:uppercase;letter-spacing:1.5px;color:var(--muted)}}
.stats{{display:flex;flex-wrap:wrap;gap:12px;margin:20px 0}}.stat{{border:1px solid var(--border);border-radius:10px;background:var(--panel);padding:14px 20px}}
.stat b{{display:block;font-size:24px}}.stat small{{color:var(--muted)}}
form{{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0}}
input,select,button{{padding:10px 12px;background:var(--panel);border:1px solid var(--border);color:var(--text);border-radius:6px}}
input{{min-width:240px;flex:2}}select{{flex:1}}button{{cursor:pointer;background:#284774}}
.panel{{border:1px solid var(--border);border-radius:10px;overflow:hidden;background:var(--panel)}}
.scroller{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;min-width:1120px}}th,td{{text-align:left;border-bottom:1px solid var(--border);padding:10px 12px;vertical-align:top}}
th{{white-space:nowrap;background:#1c2635}}th a{{color:var(--text);text-decoration:none}}
tr:hover td{{background:#1c2635}}td small{{display:block;color:var(--muted);font-size:11px}}td.num{{text-align:right;font-variant-numeric:tabular-nums}}
.empty{{text-align:center;color:var(--muted);padding:34px}}.footer{{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-top:16px}}
.note{{max-width:1000px;font-size:12px;line-height:1.7}}@media(max-width:700px){{main{{padding:14px}}h1{{font-size:22px}}}}
</style></head><body><main>
<div class="nav"><a href="/?lab=card">← CardLab dashboard</a><a href="/?lab=card&amp;view=analytics">CardLab analytics</a></div>
<div class="eyebrow">QuantBet · CardLab · read-only</div>
<h1>Referee Database</h1>
<p>Distinct referees by league. Latest StatBunker capture per season; independent API-Football L5/L10 snapshots.</p>
<div class="stats">
<div class="stat"><b>{len(data)}</b><small>Referee / league records</small></div>
<div class="stat"><b>{sum(1 for x in data if x["web_matches"] >= 10)}</b><small>With 10+ web matches</small></div>
<div class="stat"><b>{sum(1 for x in data if x["api_sample"] >= 5)}</b><small>With 5+ API card samples</small></div>
<div class="stat"><b>{sum(1 for x in data if x["web_matches"] > 0)}</b><small>With StatBunker evidence</small></div>
</div>
<form method="get" action="{BASE_PATH}">
<input name="q" aria-label="Search referee" placeholder="Search referee name" value="{q}" maxlength="100">
<select name="league" aria-label="League">{''.join(options)}</select>
<select name="season" aria-label="Season">{''.join(season_options)}</select>
<button type="submit">Apply filters</button>
<a href="{BASE_PATH}" style="align-self:center">Reset</a>
</form>
<div class="panel"><div class="scroller"><table>
<thead><tr>{''.join(th)}</tr></thead>
<tbody>{''.join(body)}</tbody>
</table></div></div>
<div class="footer"><div>{p_links}</div><a href="/?lab=card">Back to CardLab</a></div>
<p class="note">Web cards/match = (yellow + second-yellow + red) / matches for the selected stored seasons, each included once.
API L5/L10 are averages over <em>up to</em> 5/10 pre-decision matches with available statistics, from the latest stored feature snapshot;
API card n counts complete card-history matches, not all fixtures. Blank cells mean missing evidence, not zero.
Web 10+ and API 5+ describe coverage, not a recommendation or guarantee of model readiness.
Nothing on this page writes picks, alters decisions, or recalculates historical features.</p>
</main></body></html>"""
