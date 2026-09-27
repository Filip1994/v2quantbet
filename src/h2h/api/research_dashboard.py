"""Read-only dashboard for QuantBet shadow/research signals."""

from __future__ import annotations

import base64
import hmac
import json
import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit
from zoneinfo import ZoneInfo

from h2h.api.research_analytics import (
    DIAGNOSTIC_BUCKETS,
    build_research_analytics_snapshot,
    cohort_metrics,
    diagnostic_bucket,
    market_fair_probability_bucket,
    render_research_analytics_html,
)
from h2h.domain.settlement import realized_clv_ppm
from h2h.persistence.postgres_research_signals import PostgreSQLResearchSignalRepository


BELGRADE = ZoneInfo("Europe/Belgrade")


def _number(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _pct(value: Any) -> str:
    number = _number(value)
    return "—" if number is None else f"{number * 100:.1f}%"


def _odd(value: Any) -> str:
    number = _number(value)
    return "—" if number is None else f"{number:.2f}"


def _time(value: Any) -> str:
    if not isinstance(value, datetime):
        return "—"
    return value.astimezone(BELGRADE).strftime("%Y-%m-%d %H:%M")


def _bookmaker_key(value: Any) -> str:
    return "".join(character for character in str(value or "").casefold() if character.isalnum())


def _bookmaker_badge(bookmaker: Any) -> str:
    raw = str(bookmaker or "Unavailable").strip() or "Unavailable"
    key = _bookmaker_key(raw)
    canonical = {
        "bet365": "Bet365",
        "1xbet": "1xBet",
        "superbet": "Superbet",
        "pinnacle": "Pinnacle",
        "betfair": "Betfair",
        "bwin": "Bwin",
        "unibet": "Unibet",
        "betway": "Betway",
        "williamhill": "William Hill",
        "mozzart": "Mozzart",
        "mozzartbet": "Mozzart",
        "maxbet": "MaxBet",
        "meridian": "MeridianBet",
        "meridianbet": "MeridianBet",
        "admiral": "AdmiralBet",
        "admiralbet": "AdmiralBet",
        "soccerbet": "SoccerBet",
    }.get(key, raw)
    if key == "bet365":
        mark = '<span class="brand-bet365"><b>bet</b><strong>365</strong></span>'
    elif key == "1xbet":
        mark = '<span class="brand-1xbet"><b>1X</b><strong>BET</strong></span>'
    elif key == "superbet":
        mark = '<span class="brand-superbet"><b>SUPER</b><strong>BET</strong></span>'
    elif key == "pinnacle":
        mark = '<span class="brand-pinnacle"><b>PIN</b><strong>NACLE</strong></span>'
    elif key == "betfair":
        mark = '<span class="brand-betfair"><b>BET</b><strong>FAIR</strong></span>'
    elif key == "bwin":
        mark = '<span class="brand-bwin"><b>bwin</b></span>'
    elif key == "unibet":
        mark = '<span class="brand-unibet"><b>UNIBET</b><i>••••••</i></span>'
    elif key == "betway":
        mark = '<span class="brand-betway"><b>BETWAY</b></span>'
    elif key == "williamhill":
        mark = '<span class="brand-williamhill"><b>William</b><strong>HILL</strong></span>'
    elif key in {"mozzart", "mozzartbet"}:
        mark = '<span class="brand-mozzart"><b>MOZZART</b></span>'
    elif key == "maxbet":
        mark = '<span class="brand-maxbet"><b>MAX</b><strong>BET</strong></span>'
    elif key in {"meridian", "meridianbet"}:
        mark = '<span class="brand-meridian"><b>MERIDIAN</b><strong>BET</strong></span>'
    elif key in {"admiral", "admiralbet"}:
        mark = '<span class="brand-admiral"><b>ADMIRAL</b><strong>BET</strong></span>'
    elif key == "soccerbet":
        mark = '<span class="brand-soccerbet"><b>SOCCER</b><strong>BET</strong></span>'
    else:
        initials = "".join(part[:1] for part in raw.replace("-", " ").split())[:3].upper() or "?"
        mark = (
            f'<span class="brand-generic"><i>{escape(initials)}</i>'
            f'<b>{escape(canonical)}</b></span>'
        )
    return (
        f'<span class="bookmaker-mark bookmaker-{escape(key or "generic")}" '
        f'aria-label="{escape(canonical, quote=True)}" '
        f'title="{escape(canonical, quote=True)}">{mark}</span>'
    )


def _probability_bucket(value: Any) -> str:
    p = _number(value)
    if p is None:
        return "—"
    pct = p * 100
    for low, high in ((40, 45), (45, 50), (50, 55), (55, 60), (60, 65), (65, 70), (70, 75)):
        if low <= pct < high:
            return f"{low}–{high}%"
    if pct >= 75:
        return "75%+"
    return "<40%"


def _ev_bucket(value: Any) -> str:
    ev = _number(value)
    if ev is None:
        return "—"
    pct = ev * 100
    for low, high in ((7, 10), (10, 15), (15, 20), (20, 30)):
        if low <= pct < high:
            return f"{low}–{high}%"
    if pct >= 30:
        return "30%+"
    return "<7%"


def _odds_bucket(value: Any) -> str:
    odds = _number(value)
    if odds is None:
        return "—"
    for low, high, label in (
        (1.40, 1.60, "1.40–1.60"),
        (1.60, 1.80, "1.61–1.80"),
        (1.80, 2.00, "1.81–2.00"),
        (2.00, 2.50, "2.01–2.50"),
        (2.50, 3.00, "2.51–3.00"),
        (3.00, 3.50, "3.01–3.50"),
    ):
        if low <= odds <= high:
            return label
    return "other"


def counterfactual_outcome(row: dict[str, Any]) -> str:
    classification = row.get("result_classification")
    if classification == "NON_PLAYED_VOIDABLE":
        return "VOID"
    if classification != "PLAYED_SETTLEABLE":
        return "PENDING"
    home = row.get("regulation_home_goals")
    away = row.get("regulation_away_goals")
    if home is None or away is None:
        return "PENDING"
    home, away = int(home), int(away)
    market, selection = row.get("market"), row.get("selection")
    if market == "OU_25":
        over = home + away > 2
        won = over if selection == "OVER" else not over
    elif market == "BTTS":
        yes = home > 0 and away > 0
        won = yes if selection == "YES" else not yes
    else:
        return "PENDING"
    return "WIN" if won else "LOSS"


def counterfactual_pnl_minor(row: dict[str, Any], stake_minor: int) -> int | None:
    outcome = counterfactual_outcome(row)
    if outcome == "PENDING":
        return None
    if outcome == "VOID":
        return 0
    if outcome == "LOSS":
        return -stake_minor
    odd = Decimal(str(row["odds"]))
    return int(
        (Decimal(stake_minor) * (odd - Decimal(1))).quantize(
            Decimal(1), rounding=ROUND_HALF_UP
        )
    )


def research_clv_ppm(row: dict[str, Any]) -> int | None:
    closing = row.get("closing_odds")
    closing_at = row.get("closing_observed_at")
    entry_at = row.get("quote_observed_at")
    if closing is None or not isinstance(closing_at, datetime) or not isinstance(entry_at, datetime):
        return None
    if closing_at <= entry_at:
        return None
    return realized_clv_ppm(Decimal(str(row["odds"])), Decimal(str(closing)))


def _parse_fraction(raw: str | None) -> float | None:
    if raw is None or not raw.strip():
        return None
    value = float(raw)
    return value / 100 if abs(value) > 1 else value


def _parse_float(raw: str | None) -> float | None:
    if raw is None or not raw.strip():
        return None
    return float(raw)


def _one_signal_per_fixture(
    rows: tuple[dict[str, Any], ...],
) -> tuple[dict[str, Any], ...]:
    """Project historical shadow rows onto the production one-pick-per-fixture rule."""

    def strength(row: dict[str, Any], name: str) -> float:
        value = _number(row.get(name))
        return float("-inf") if value is None else value

    chosen: dict[str, tuple[tuple[Any, ...], dict[str, Any]]] = {}
    for row in rows:
        fixture_id = str(row["fixture_id"])
        qualified_at = row.get("qualified_at") or row.get("first_blocked_at")
        if not isinstance(qualified_at, datetime):
            raise TypeError("qualified_at must be a datetime")

        rank = (
            qualified_at,
            -strength(row, "expected_value"),
            -strength(row, "edge"),
            -strength(row, "odds"),
            str(row["evaluation_id"]),
        )
        current = chosen.get(fixture_id)
        if current is None or rank < current[0]:
            chosen[fixture_id] = (rank, row)

    return tuple(
        sorted(
            (item[1] for item in chosen.values()),
            key=lambda row: (
                row.get("qualified_at") or row.get("last_blocked_at"),
                str(row["evaluation_id"]),
            ),
            reverse=True,
        )
    )


class ResearchDashboardService:
    def __init__(
        self,
        repository: PostgreSQLResearchSignalRepository,
        *,
        fixed_stake_minor: int = 30_000,
        strict_quote_age_seconds: int = 300,
        provider_snapshot_max_age_seconds: int = 28_800,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repository = repository
        self._stake = fixed_stake_minor
        self._strict_age = strict_quote_age_seconds
        self._provider_age = provider_snapshot_max_age_seconds
        self._clock = clock

    def _derived(self, row: dict[str, Any]) -> dict[str, Any]:
        item = dict(row)
        qualified_at = item.get("qualified_at") or item.get("first_blocked_at")
        if not isinstance(qualified_at, datetime):
            raise TypeError("qualified_at must be a datetime")
        quote_age = max(
            0,
            int((qualified_at - item["quote_observed_at"]).total_seconds()),
        )
        item["quote_age_seconds"] = quote_age
        item["freshness"] = (
            "FRESH"
            if quote_age <= self._strict_age
            else "USABLE_STALE"
            if quote_age <= self._provider_age
            else "HARD_STALE"
        )
        item["outcome"] = counterfactual_outcome(item)
        item["pnl_minor"] = counterfactual_pnl_minor(item, self._stake)
        item["clv_ppm"] = research_clv_ppm(item)
        item["probability_bucket"] = _probability_bucket(item["model_probability"])
        item["market_fair_probability_bucket"] = market_fair_probability_bucket(
            item["market_fair_probability"]
        )
        item["ev_bucket"] = _ev_bucket(item["expected_value"])
        item["odds_bucket"] = _odds_bucket(item["odds"])
        return item

    def _system_health(self) -> tuple[dict[str, str], ...]:
        unavailable = (
            {"label": "Database", "state": "unknown", "summary": "No status", "detail": "Operational status is unavailable."},
            {"label": "Engine", "state": "unknown", "summary": "No status", "detail": "Operational status is unavailable."},
            {"label": "Models", "state": "unknown", "summary": "No status", "detail": "Operational status is unavailable."},
            {"label": "Odds", "state": "unknown", "summary": "No status", "detail": "Operational status is unavailable."},
            {"label": "Results", "state": "unknown", "summary": "No status", "detail": "Operational status is unavailable."},
            {"label": "Research", "state": "unknown", "summary": "No status", "detail": "Operational status is unavailable."},
        )
        connect = getattr(self._repository, "connect", None)
        if not callable(connect):
            return unavailable

        try:
            with connect() as connection, connection.cursor() as cursor:
                cursor.execute("SELECT CURRENT_TIMESTAMP")
                database_now = cursor.fetchone()[0]
                cursor.execute(
                    "SELECT worker_name, last_success_at, last_failure_at, next_due_at, "
                    "consecutive_failures, updated_at FROM production_worker_status "
                    "ORDER BY worker_name"
                )
                workers = tuple(
                    {
                        "worker_name": row[0],
                        "last_success_at": row[1],
                        "last_failure_at": row[2],
                        "next_due_at": row[3],
                        "consecutive_failures": int(row[4]),
                        "updated_at": row[5],
                    }
                    for row in cursor.fetchall()
                )
                cursor.execute(
                    "SELECT COUNT(*), MAX(qualified_at) FROM research_signals"
                )
                research_count, latest_research = cursor.fetchone()
                cursor.execute(
                    "SELECT COUNT(*) FILTER (WHERE freshness_state = 'FRESH'), "
                    "COUNT(*) FILTER (WHERE freshness_state = 'STALE'), "
                    "COUNT(*) FILTER (WHERE freshness_state = 'NO_USABLE_QUOTE'), "
                    "MAX(updated_at) FROM production_quote_refresh_states"
                )
                quote_fresh, quote_stale, quote_unusable, quote_updated = cursor.fetchone()
                cursor.execute(
                    "SELECT COUNT(*) FILTER (WHERE phase <> 'COMPLETE'), "
                    "COUNT(*) FILTER (WHERE correction_required), MAX(updated_at) "
                    "FROM fixture_result_acquisition_states"
                )
                pending_results, corrections, results_updated = cursor.fetchone()
        except Exception:  # noqa: BLE001 - health UI must degrade without breaking Research
            return (
                {"label": "Database", "state": "bad", "summary": "Unreachable", "detail": "Research could not read operational PostgreSQL facts."},
                *unavailable[1:],
            )

        if not isinstance(database_now, datetime):
            database_now = datetime.now(UTC)
        elif database_now.tzinfo is None or database_now.utcoffset() is None:
            database_now = database_now.replace(tzinfo=UTC)

        by_name = {str(item["worker_name"]): item for item in workers}

        def worker_component(
            label: str,
            names: tuple[str, ...],
            *,
            tolerate_partial: bool = False,
        ) -> dict[str, str]:
            selected = [by_name[name] for name in names if name in by_name]
            if not selected:
                return {
                    "label": label,
                    "state": "bad",
                    "summary": "No heartbeat",
                    "detail": f"No status rows for {', '.join(names)}.",
                }
            missing = [name for name in names if name not in by_name]
            stale: list[str] = []
            failing: list[str] = []
            never_succeeded: list[str] = []
            for item in selected:
                name = str(item["worker_name"])
                success = item["last_success_at"]
                failure = item["last_failure_at"]
                next_due = item["next_due_at"]
                if success is None:
                    never_succeeded.append(name)
                if (
                    isinstance(next_due, datetime)
                    and database_now > next_due + timedelta(seconds=120)
                ):
                    stale.append(name)
                if int(item["consecutive_failures"]) > 0 and (
                    success is None
                    or not isinstance(failure, datetime)
                    or failure >= success
                ):
                    failing.append(name)

            problems = set(stale + failing + never_succeeded)
            if never_succeeded or (problems and not tolerate_partial):
                state = "bad"
            elif problems or missing:
                state = "warn"
            else:
                state = "ok"

            if state == "ok":
                summary = f"{len(selected)} worker{'s' if len(selected) != 1 else ''} healthy"
            elif state == "warn":
                summary = f"{len(problems) + len(missing)} warning{'s' if len(problems) + len(missing) != 1 else ''}"
            else:
                summary = f"{len(problems) or len(missing)} problem{'s' if (len(problems) or len(missing)) != 1 else ''}"
            details: list[str] = []
            if stale:
                details.append("stale: " + ", ".join(stale))
            if failing:
                details.append("failing: " + ", ".join(failing))
            if never_succeeded:
                details.append("never succeeded: " + ", ".join(never_succeeded))
            if missing:
                details.append("missing: " + ", ".join(missing))
            if not details:
                latest = max(
                    (
                        item["last_success_at"]
                        for item in selected
                        if isinstance(item["last_success_at"], datetime)
                    ),
                    default=None,
                )
                details.append(
                    "last success "
                    + (_time(latest) if isinstance(latest, datetime) else "unavailable")
                )
            return {
                "label": label,
                "state": state,
                "summary": summary,
                "detail": "; ".join(details),
            }

        engine_names = tuple(sorted(by_name))
        engine = worker_component("Engine", engine_names) if engine_names else {
            "label": "Engine",
            "state": "bad",
            "summary": "No heartbeat",
            "detail": "production_worker_status is empty.",
        }
        models = worker_component("Models", ("model_lifecycle",))
        odds = worker_component(
            "Odds",
            ("opportunity", "monitoring", "closing_proxy"),
            tolerate_partial=True,
        )
        results = worker_component("Results", ("results",))

        if int(corrections or 0) > 0 and results["state"] == "ok":
            results = {
                **results,
                "state": "warn",
                "summary": f"{int(corrections)} correction pending",
                "detail": (
                    f"{int(pending_results or 0)} result states pending; "
                    f"{int(corrections)} correction-required; last state update {_time(results_updated)}"
                ),
            }
        elif results["state"] == "ok":
            results = {
                **results,
                "summary": f"{int(pending_results or 0)} pending",
                "detail": (
                    f"No correction-required states; last state update {_time(results_updated)}"
                ),
            }

        if odds["state"] == "ok":
            odds = {
                **odds,
                "summary": f"{int(quote_fresh or 0)} fresh",
                "detail": (
                    f"{int(quote_fresh or 0)} fresh / {int(quote_stale or 0)} stale / "
                    f"{int(quote_unusable or 0)} unusable refresh states; "
                    f"last update {_time(quote_updated)}"
                ),
            }

        research_state = "ok" if int(research_count or 0) > 0 else "warn"
        research = {
            "label": "Research",
            "state": research_state,
            "summary": f"{int(research_count or 0)} signals",
            "detail": (
                "latest qualified "
                + (_time(latest_research) if isinstance(latest_research, datetime) else "none")
            ),
        }

        return (
            {
                "label": "Database",
                "state": "ok",
                "summary": "Connected",
                "detail": "PostgreSQL operational facts are readable.",
            },
            engine,
            models,
            odds,
            results,
            research,
        )

    @staticmethod
    def _health_html(items: tuple[dict[str, str], ...]) -> str:
        return "".join(
            (
                f'<div class="health-item health-{escape(item["state"])}" '
                f'title="{escape(item["detail"], quote=True)}">'
                f'<span class="health-lamp" aria-hidden="true"></span>'
                f'<span><b>{escape(item["label"])}</b>'
                f'<small>{escape(item["summary"])}</small></span></div>'
            )
            for item in items
        )

    def _all_signal_rows(self) -> tuple[dict[str, Any], ...]:
        loader = getattr(self._repository, "list_all_signals", None)
        if callable(loader):
            return tuple(loader())
        return tuple(self._repository.list_signals(limit=5000))

    def signals(self, params: dict[str, list[str]]) -> tuple[dict[str, Any], ...]:
        canonical = _one_signal_per_fixture(self._all_signal_rows())
        rows = tuple(self._derived(row) for row in canonical)
        market = params.get("market", [""])[0].strip().upper()
        league = params.get("league", [""])[0].strip().casefold()
        result = params.get("result", [""])[0].strip().upper()
        disposition = params.get("disposition", [""])[0].strip().upper()
        p_bucket = params.get("p_bucket", [""])[0].strip()
        ev_bucket = params.get("ev_bucket", [""])[0].strip()
        odds_bucket = params.get("odds_bucket", [""])[0].strip()
        p_min = _parse_fraction(params.get("p_min", [""])[0])
        p_max = _parse_fraction(params.get("p_max", [""])[0])
        ev_min = _parse_fraction(params.get("ev_min", [""])[0])
        ev_max = _parse_fraction(params.get("ev_max", [""])[0])
        odds_min = _parse_float(params.get("odds_min", [""])[0])
        odds_max = _parse_float(params.get("odds_max", [""])[0])

        def keep(row: dict[str, Any]) -> bool:
            p, ev, odds = (
                float(row["model_probability"]),
                float(row["expected_value"]),
                float(row["odds"]),
            )
            if market and row["market"].upper() != market:
                return False
            if league and league not in (row.get("competition_name") or "").casefold():
                return False
            if result and row["outcome"] != result:
                return False
            if disposition and row.get("disposition") != disposition:
                return False
            if p_bucket and row["probability_bucket"] != p_bucket:
                return False
            if ev_bucket and row["ev_bucket"] != ev_bucket:
                return False
            if odds_bucket and row["odds_bucket"] != odds_bucket:
                return False
            if p_min is not None and p < p_min:
                return False
            if p_max is not None and p > p_max:
                return False
            if ev_min is not None and ev < ev_min:
                return False
            if ev_max is not None and ev > ev_max:
                return False
            if odds_min is not None and odds < odds_min:
                return False
            return not (odds_max is not None and odds > odds_max)

        return tuple(row for row in rows if keep(row))

    def analytics_snapshot(self) -> dict[str, Any]:
        return build_research_analytics_snapshot(
            self.signals({}),
            fixed_stake_minor=self._stake,
        )

    def diagnostic_details(self, bucket: str = "OTHER_EXTREME") -> dict[str, Any]:
        """Return exact settled Research rows behind one analytics diagnostic bucket."""
        name = bucket.strip().upper()
        if name not in DIAGNOSTIC_BUCKETS:
            raise ValueError("invalid diagnostic bucket")

        settled = tuple(
            row
            for row in self.signals({})
            if row.get("outcome") in {"WIN", "LOSS", "VOID"}
            and diagnostic_bucket(row) == name
        )
        rows = sorted(
            settled,
            key=lambda row: (
                row.get("kickoff_at")
                if isinstance(row.get("kickoff_at"), datetime)
                else datetime.min.replace(tzinfo=UTC),
                str(row.get("evaluation_id") or ""),
            ),
            reverse=True,
        )

        def iso(value: Any) -> str | None:
            if not isinstance(value, datetime):
                return None
            if value.tzinfo is None or value.utcoffset() is None:
                value = value.replace(tzinfo=UTC)
            return value.astimezone(UTC).isoformat()

        def integer(value: Any) -> int | None:
            return None if value is None else int(value)

        items = []
        for row in rows:
            home_goals = integer(row.get("regulation_home_goals"))
            away_goals = integer(row.get("regulation_away_goals"))
            clv_ppm = integer(row.get("clv_ppm"))
            items.append(
                {
                    "research_signal_id": str(row.get("research_signal_id") or ""),
                    "evaluation_id": str(row.get("evaluation_id") or ""),
                    "fixture_id": str(row.get("fixture_id") or ""),
                    "provider_fixture_id": str(row.get("provider_fixture_id") or ""),
                    "home_team": row.get("home_team"),
                    "away_team": row.get("away_team"),
                    "competition_name": row.get("competition_name"),
                    "country": row.get("country"),
                    "kickoff_at": iso(row.get("kickoff_at")),
                    "market": row.get("market"),
                    "selection": row.get("selection"),
                    "bookmaker": row.get("bookmaker"),
                    "odds": float(row["odds"]),
                    "model_probability": float(row["model_probability"]),
                    "market_fair_probability": float(row["market_fair_probability"]),
                    "edge": float(row["edge"]),
                    "expected_value": float(row["expected_value"]),
                    "outcome": row.get("outcome"),
                    "score": (
                        None
                        if home_goals is None or away_goals is None
                        else {"home": home_goals, "away": away_goals}
                    ),
                    "result_provider_status": row.get("result_provider_status"),
                    "pnl_minor": integer(row.get("pnl_minor")),
                    "clv_ppm": clv_ppm,
                    "clv_pct": None if clv_ppm is None else clv_ppm / 10_000,
                    "disposition": row.get("disposition"),
                    "production_pick_id": row.get("production_pick_id"),
                    "freshness": row.get("freshness"),
                    "quote_observed_at": iso(row.get("quote_observed_at")),
                    "closing_odds": (
                        None
                        if row.get("closing_odds") is None
                        else float(row["closing_odds"])
                    ),
                    "closing_observed_at": iso(row.get("closing_observed_at")),
                }
            )

        return {
            "contract_version": "RESEARCH_DIAGNOSTIC_DRILLDOWN_V1",
            "bucket": name,
            "definition": (
                "not low-scoring and (expected_value >= 0.30 or edge >= 0.20)"
                if name == "OTHER_EXTREME"
                else "See RESEARCH_ANALYTICS_V2 diagnostic bucket classifier."
            ),
            "count": len(items),
            "wins": sum(item["outcome"] == "WIN" for item in items),
            "losses": sum(item["outcome"] == "LOSS" for item in items),
            "voids": sum(item["outcome"] == "VOID" for item in items),
            "rows": items,
        }

    def model_version_details(self, model_version_id: str) -> dict[str, Any]:
        """Return exact settled Research picks belonging to one model version."""
        model_version_id = model_version_id.strip()
        if not model_version_id:
            raise ValueError("model_version_id is required")

        def belongs_to_model(row: dict[str, Any]) -> bool:
            recorded = str(row.get("model_version_id") or "").strip()
            if model_version_id == "UNRECORDED_MODEL":
                return not recorded
            return recorded == model_version_id

        settled = tuple(
            row
            for row in self.signals({})
            if row.get("outcome") in {"WIN", "LOSS", "VOID"}
            and belongs_to_model(row)
        )
        rows = sorted(
            settled,
            key=lambda row: (
                row.get("kickoff_at")
                if isinstance(row.get("kickoff_at"), datetime)
                else datetime.min.replace(tzinfo=UTC),
                str(row.get("evaluation_id") or ""),
            ),
            reverse=True,
        )

        def iso(value: Any) -> str | None:
            if not isinstance(value, datetime):
                return None
            if value.tzinfo is None or value.utcoffset() is None:
                value = value.replace(tzinfo=UTC)
            return value.astimezone(UTC).isoformat()

        def integer(value: Any) -> int | None:
            return None if value is None else int(value)

        items = []
        for row in rows:
            home_goals = integer(row.get("regulation_home_goals"))
            away_goals = integer(row.get("regulation_away_goals"))
            clv_ppm = integer(row.get("clv_ppm"))
            items.append(
                {
                    "research_signal_id": str(row.get("research_signal_id") or ""),
                    "evaluation_id": str(row.get("evaluation_id") or ""),
                    "fixture_id": str(row.get("fixture_id") or ""),
                    "provider_fixture_id": str(row.get("provider_fixture_id") or ""),
                    "home_team": row.get("home_team"),
                    "away_team": row.get("away_team"),
                    "competition_name": row.get("competition_name"),
                    "country": row.get("country"),
                    "kickoff_at": iso(row.get("kickoff_at")),
                    "market": row.get("market"),
                    "selection": row.get("selection"),
                    "bookmaker": row.get("bookmaker"),
                    "odds": float(row["odds"]),
                    "model_probability": float(row["model_probability"]),
                    "market_fair_probability": float(row["market_fair_probability"]),
                    "edge": float(row["edge"]),
                    "expected_value": float(row["expected_value"]),
                    "outcome": row.get("outcome"),
                    "score": (
                        None
                        if home_goals is None or away_goals is None
                        else {"home": home_goals, "away": away_goals}
                    ),
                    "pnl_minor": integer(row.get("pnl_minor")),
                    "clv_pct": None if clv_ppm is None else clv_ppm / 10_000,
                    "disposition": row.get("disposition"),
                    "qualified_at": iso(row.get("qualified_at")),
                    "quote_observed_at": iso(row.get("quote_observed_at")),
                    "closing_odds": (
                        None
                        if row.get("closing_odds") is None
                        else float(row["closing_odds"])
                    ),
                    "closing_observed_at": iso(row.get("closing_observed_at")),
                    "policy_config_fingerprint": row.get("policy_config_fingerprint"),
                    "prediction_method_version": row.get("prediction_method_version"),
                    "devig_method_version": row.get("devig_method_version"),
                    "production_pick_id": row.get("production_pick_id"),
                }
            )

        return {
            "contract_version": "RESEARCH_MODEL_VERSION_DRILLDOWN_V1",
            "model_version_id": model_version_id,
            "summary": cohort_metrics(
                settled,
                fixed_stake_minor=self._stake,
            ),
            "rows": items,
        }

    def league_details(self, league_id: int, season: int) -> dict[str, Any]:
        """Return settled Research performance for one league-season across retrains."""
        if isinstance(league_id, bool) or not isinstance(league_id, int) or league_id <= 0:
            raise ValueError("league_id must be a positive integer")
        if isinstance(season, bool) or not isinstance(season, int) or season <= 0:
            raise ValueError("season must be a positive integer")

        settled = tuple(
            row
            for row in self.signals({})
            if row.get("outcome") in {"WIN", "LOSS", "VOID"}
            and int(row.get("league_id") or 0) == league_id
            and int(row.get("season") or 0) == season
        )
        rows = sorted(
            settled,
            key=lambda row: (
                row.get("kickoff_at")
                if isinstance(row.get("kickoff_at"), datetime)
                else datetime.min.replace(tzinfo=UTC),
                str(row.get("evaluation_id") or ""),
            ),
            reverse=True,
        )

        def iso(value: Any) -> str | None:
            if not isinstance(value, datetime):
                return None
            if value.tzinfo is None or value.utcoffset() is None:
                value = value.replace(tzinfo=UTC)
            return value.astimezone(UTC).isoformat()

        def integer(value: Any) -> int | None:
            return None if value is None else int(value)

        items = []
        grouped_models: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            model_version_id = str(row.get("model_version_id") or "").strip()
            model_version_id = model_version_id or "UNRECORDED_MODEL"
            grouped_models.setdefault(model_version_id, []).append(row)

            home_goals = integer(row.get("regulation_home_goals"))
            away_goals = integer(row.get("regulation_away_goals"))
            clv_ppm = integer(row.get("clv_ppm"))
            items.append(
                {
                    "research_signal_id": str(row.get("research_signal_id") or ""),
                    "evaluation_id": str(row.get("evaluation_id") or ""),
                    "fixture_id": str(row.get("fixture_id") or ""),
                    "provider_fixture_id": str(row.get("provider_fixture_id") or ""),
                    "league_id": league_id,
                    "season": season,
                    "home_team": row.get("home_team"),
                    "away_team": row.get("away_team"),
                    "competition_name": row.get("competition_name"),
                    "country": row.get("country"),
                    "kickoff_at": iso(row.get("kickoff_at")),
                    "market": row.get("market"),
                    "selection": row.get("selection"),
                    "bookmaker": row.get("bookmaker"),
                    "odds": float(row["odds"]),
                    "model_probability": float(row["model_probability"]),
                    "market_fair_probability": float(row["market_fair_probability"]),
                    "edge": float(row["edge"]),
                    "expected_value": float(row["expected_value"]),
                    "outcome": row.get("outcome"),
                    "score": (
                        None
                        if home_goals is None or away_goals is None
                        else {"home": home_goals, "away": away_goals}
                    ),
                    "pnl_minor": integer(row.get("pnl_minor")),
                    "clv_pct": None if clv_ppm is None else clv_ppm / 10_000,
                    "disposition": row.get("disposition"),
                    "qualified_at": iso(row.get("qualified_at")),
                    "closing_odds": (
                        None
                        if row.get("closing_odds") is None
                        else float(row["closing_odds"])
                    ),
                    "closing_observed_at": iso(row.get("closing_observed_at")),
                    "model_version_id": model_version_id,
                    "policy_config_fingerprint": row.get("policy_config_fingerprint"),
                    "production_pick_id": row.get("production_pick_id"),
                }
            )

        model_versions = [
            {
                "model_version_id": model_version_id,
                **cohort_metrics(
                    tuple(model_rows),
                    fixed_stake_minor=self._stake,
                ),
            }
            for model_version_id, model_rows in grouped_models.items()
        ]
        model_versions.sort(
            key=lambda item: (
                -int(item["graded_n"]),
                str(item["model_version_id"]),
            )
        )

        first = rows[0] if rows else {}
        return {
            "contract_version": "RESEARCH_LEAGUE_DRILLDOWN_V1",
            "league": {
                "league_id": league_id,
                "season": season,
                "competition_name": first.get("competition_name"),
                "country": first.get("country"),
            },
            "summary": cohort_metrics(
                settled,
                fixed_stake_minor=self._stake,
            ),
            "model_version_count": len(model_versions),
            "model_versions": model_versions,
            "rows": items,
        }

    def render_league_html(self, league_id: int, season: int) -> str:
        """Render League -> model versions -> settled picks hierarchy."""
        payload = self.league_details(league_id, season)
        league = payload["league"]
        summary = payload["summary"]
        model_versions = payload["model_versions"]
        rows = payload["rows"]

        def metric(value: Any, suffix: str = "", *, signed: bool = False) -> str:
            if value is None:
                return "—"
            number = float(value)
            prefix = "+" if signed and number > 0 else ""
            return f"{prefix}{number:.2f}{suffix}"

        def short_model(value: str) -> str:
            if ":" not in value:
                return value if len(value) <= 24 else value[:23] + "…"
            prefix, digest = value.split(":", 1)
            return f"{prefix}:{digest[:12]}…" if len(digest) > 12 else value

        cards = "".join(
            f'<div class="card"><small>{escape(label)}</small><b>{escape(value)}</b></div>'
            for label, value in (
                ("Settled", str(summary["n"])),
                (
                    "W-L-V",
                    f'{summary["wins"]}-{summary["losses"]}-{summary["voids"]}',
                ),
                ("Win rate", metric(summary["win_rate_pct"], "%")),
                ("Expected", metric(summary["expected_win_rate_pct"], "%")),
                ("ROI", metric(summary["roi_pct"], "%", signed=True)),
                ("Flat P/L", f'{summary["flat_pnl_minor"] / 100:+.0f} RSD'),
                ("Avg CLV", metric(summary["avg_clv_pct"], "%", signed=True)),
                ("Retrains", str(payload["model_version_count"])),
            )
        )

        model_body = []
        for model in model_versions:
            model_version_id = str(model["model_version_id"])
            model_query = urlencode({"model_version_id": model_version_id})
            label = escape(short_model(model_version_id))
            href = "/research/analytics/model?" + model_query
            model_body.append(
                "<tr>"
                f'<td><a class="model-link" href="{escape(href, quote=True)}" '
                f'title="{escape(model_version_id, quote=True)}">{label}</a></td>'
                f'<td>{model["n"]}</td>'
                f'<td>{model["wins"]}-{model["losses"]}-{model["voids"]}</td>'
                f'<td>{metric(model["win_rate_pct"], "%")}</td>'
                f'<td>{metric(model["expected_win_rate_pct"], "%")}</td>'
                f'<td>{metric(model["roi_pct"], "%", signed=True)}</td>'
                f'<td>{metric(model["avg_clv_pct"], "%", signed=True)}</td>'
                f'<td>{escape(str(model["sample_band"]))}</td>'
                "</tr>"
            )
        model_rows_html = "".join(model_body) or (
            '<tr><td colspan="8" class="empty">No settled model versions.</td></tr>'
        )

        pick_body = []
        for row in rows:
            score = row["score"]
            score_text = "—" if score is None else f'{score["home"]}:{score["away"]}'
            pnl_minor = row["pnl_minor"]
            pnl_text = "—" if pnl_minor is None else f"{pnl_minor / 100:+.0f} RSD"
            clv = row["clv_pct"]
            clv_text = "—" if clv is None else f"{clv:+.2f}%"
            close = (
                "—"
                if row["closing_odds"] is None
                else f'{float(row["closing_odds"]):.2f}'
            )
            model_version_id = str(row["model_version_id"])
            model_query = urlencode({"model_version_id": model_version_id})
            model_href = "/research/analytics/model?" + model_query
            match = (
                f'{escape(str(row["home_team"] or "—"))} – '
                f'{escape(str(row["away_team"] or "—"))}'
            )
            outcome = escape(str(row["outcome"] or "—"))
            outcome_class = str(row["outcome"] or "").casefold()
            pick_body.append(
                f'<tr class="row-{outcome_class}">'
                f'<td class="match"><b>{match}</b><small>'
                f'fixture {escape(str(row["provider_fixture_id"] or "—"))}</small></td>'
                f'<td><b class="result result-{outcome_class}">{outcome}</b>'
                f'<small>{score_text}</small></td>'
                f'<td><b>{escape(str(row["market"] or "—"))} '
                f'{escape(str(row["selection"] or "—"))}</b></td>'
                f'<td><b>{float(row["odds"]):.2f}</b><small>'
                f'{escape(str(row["bookmaker"] or "—"))}</small></td>'
                f'<td>{_pct(row["model_probability"])}</td>'
                f'<td>{_pct(row["expected_value"])}</td>'
                f'<td>{close}</td>'
                f'<td>{clv_text}</td>'
                f'<td>{pnl_text}</td>'
                f'<td><a class="model-link" href="{escape(model_href, quote=True)}" '
                f'title="{escape(model_version_id, quote=True)}">'
                f'{escape(short_model(model_version_id))}</a></td>'
                f'<td>{escape(str(row["kickoff_at"] or "—"))}</td>'
                "</tr>"
            )
        pick_rows_html = "".join(pick_body) or (
            '<tr><td colspan="11" class="empty">'
            "No settled Research picks belong to this league-season.</td></tr>"
        )

        competition_name = escape(str(league.get("competition_name") or f"League {league_id}"))
        country = escape(str(league.get("country") or "—"))
        query = urlencode({"league_id": league_id, "season": season})

        return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Research league performance</title>
<style>
:root{{--bg:#111315;--panel:#181b1f;--line:#30363d;--text:#eceff1;--muted:#9299a1;
--win:#69c98f;--loss:#e06f78;--void:#9aa1a8}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);
font-family:Inter,ui-sans-serif,system-ui,sans-serif}}main{{max-width:1920px;margin:auto;padding:24px}}
header{{display:flex;justify-content:space-between;gap:18px;align-items:flex-start;margin-bottom:14px}}
h1{{margin:4px 0 0;font-size:24px}}h2{{margin:0 0 11px;font-size:15px}}
p,small{{color:var(--muted)}}a{{color:#d8dcdf}}.meta{{color:var(--muted);font-size:12px}}
.cards{{display:grid;grid-template-columns:repeat(8,minmax(120px,1fr));gap:9px;margin:14px 0}}
.card,.panel{{background:var(--panel);border:1px solid var(--line);border-radius:12px}}
.card{{padding:13px}}.card small{{text-transform:uppercase;font-size:10px;letter-spacing:.08em}}
.card b{{display:block;font-size:18px;margin-top:7px}}.panel{{padding:14px;margin:12px 0}}
.scroll{{overflow:auto;max-height:65vh}}table{{width:100%;border-collapse:collapse;font-size:12px}}
th,td{{padding:9px 10px;border-bottom:1px solid #272c31;white-space:nowrap;text-align:left;
vertical-align:top}}th{{position:sticky;top:0;background:#1b1f23;color:#9aa1a8;font-size:10px;
text-transform:uppercase;letter-spacing:.05em}}td.match{{min-width:240px}}td small{{display:block;
margin-top:4px}}.model-link{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
text-decoration:none;border-bottom:1px dotted #778089}}.model-link:hover{{color:#fff;
border-bottom-color:#fff}}.result{{display:inline-block;padding:4px 7px;border-radius:999px;
font-size:10px}}.result-win{{color:var(--win)}}.result-loss{{color:var(--loss)}}
.result-void{{color:var(--void)}}.row-win{{box-shadow:inset 3px 0 var(--win)}}
.row-loss{{box-shadow:inset 3px 0 var(--loss)}}.row-void{{box-shadow:inset 3px 0 var(--void)}}
.empty{{text-align:center;color:var(--muted);padding:36px!important}}@media(max-width:900px){{
.cards{{grid-template-columns:repeat(2,1fr)}}main{{padding:14px}}header{{display:block}}}}
</style></head><body><main>
<header><div><small>RESEARCH_LEAGUE_DRILLDOWN_V1</small>
<h1>{competition_name} · {season}</h1>
<div class="meta">{country} · League ID {league_id} · all DC retrains combined</div>
<p>League performance first; model versions remain available as the audit layer.</p></div>
<div><a href="/research/analytics">← Analytics V2</a> ·
<a href="/research/analytics/league.json?{escape(query, quote=True)}">JSON</a></div></header>
<section class="cards">{cards}</section>
<section class="panel"><h2>Model versions · retrain history</h2>
<div class="scroll"><table><thead><tr>
<th>Model version</th><th>N</th><th>W-L-V</th><th>Win%</th><th>Expected</th>
<th>ROI</th><th>Avg CLV</th><th>Evidence</th>
</tr></thead><tbody>{model_rows_html}</tbody></table></div></section>
<section class="panel"><h2>All settled picks · all retrains</h2>
<div class="scroll"><table><thead><tr>
<th>Match</th><th>Result</th><th>Pick</th><th>Entry</th><th>Model P</th><th>EV</th>
<th>Close</th><th>CLV</th><th>P/L</th><th>Model version</th><th>Kickoff UTC</th>
</tr></thead><tbody>{pick_rows_html}</tbody></table></div></section>
</main></body></html>"""

    def render_model_version_html(self, model_version_id: str) -> str:
        """Render the exact settled picks behind one model-version analytics cohort."""
        payload = self.model_version_details(model_version_id)
        summary = payload["summary"]
        rows = payload["rows"]

        def metric(value: Any, suffix: str = "", *, signed: bool = False) -> str:
            if value is None:
                return "—"
            number = float(value)
            prefix = "+" if signed and number > 0 else ""
            return f"{prefix}{number:.2f}{suffix}"

        cards = "".join(
            f'<div class="card"><small>{escape(label)}</small><b>{escape(value)}</b></div>'
            for label, value in (
                ("Settled", str(summary["n"])),
                (
                    "W-L-V",
                    f'{summary["wins"]}-{summary["losses"]}-{summary["voids"]}',
                ),
                ("Win rate", metric(summary["win_rate_pct"], "%")),
                ("Expected", metric(summary["expected_win_rate_pct"], "%")),
                ("ROI", metric(summary["roi_pct"], "%", signed=True)),
                ("Flat P/L", f'{summary["flat_pnl_minor"] / 100:+.0f} RSD'),
                ("Avg CLV", metric(summary["avg_clv_pct"], "%", signed=True)),
                ("Evidence", str(summary["sample_band"])),
            )
        )

        body = []
        for row in rows:
            score = row["score"]
            score_text = (
                "—"
                if score is None
                else f'{score["home"]}:{score["away"]}'
            )
            pnl_minor = row["pnl_minor"]
            pnl_text = "—" if pnl_minor is None else f"{pnl_minor / 100:+.0f} RSD"
            clv = row["clv_pct"]
            clv_text = "—" if clv is None else f"{clv:+.2f}%"
            close = (
                "—"
                if row["closing_odds"] is None
                else f'{float(row["closing_odds"]):.2f}'
            )
            match = (
                f'{escape(str(row["home_team"] or "—"))} – '
                f'{escape(str(row["away_team"] or "—"))}'
            )
            outcome = escape(str(row["outcome"] or "—"))
            outcome_class = str(row["outcome"] or "").casefold()
            policy = escape(
                str(row["policy_config_fingerprint"] or "LEGACY_UNRECORDED_POLICY")
            )
            body.append(
                f'<tr class="row-{outcome_class}">'
                f'<td class="match"><b>{match}</b><small>'
                f'{escape(str(row["competition_name"] or "—"))} · '
                f'fixture {escape(str(row["provider_fixture_id"] or "—"))}</small></td>'
                f'<td><b class="result result-{outcome_class}">{outcome}</b>'
                f'<small>{score_text}</small></td>'
                f'<td><b>{escape(str(row["market"] or "—"))} '
                f'{escape(str(row["selection"] or "—"))}</b></td>'
                f'<td><b>{float(row["odds"]):.2f}</b><small>'
                f'{escape(str(row["bookmaker"] or "—"))}</small></td>'
                f'<td>{_pct(row["model_probability"])}</td>'
                f'<td>{_pct(row["market_fair_probability"])}</td>'
                f'<td>{_pct(row["edge"])}</td>'
                f'<td>{_pct(row["expected_value"])}</td>'
                f'<td>{close}<small>{escape(str(row["closing_observed_at"] or "—"))}</small></td>'
                f'<td>{clv_text}</td>'
                f'<td>{pnl_text}</td>'
                f'<td>{escape(str(row["disposition"] or "—"))}</td>'
                f'<td>{escape(str(row["kickoff_at"] or "—"))}</td>'
                f'<td>{escape(str(row["qualified_at"] or "—"))}</td>'
                f'<td class="policy">{policy}</td>'
                "</tr>"
            )
        rows_html = "".join(body) or (
            '<tr><td colspan="15" class="empty">'
            "No settled Research picks belong to this model version.</td></tr>"
        )
        query = urlencode({"model_version_id": model_version_id})
        model_label = escape(model_version_id)

        return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Research model drilldown</title>
<style>
:root{{--bg:#111315;--panel:#181b1f;--line:#30363d;--text:#eceff1;--muted:#9299a1;
--win:#69c98f;--loss:#e06f78;--void:#9aa1a8}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);
font-family:Inter,ui-sans-serif,system-ui,sans-serif}}main{{max-width:1920px;margin:auto;padding:24px}}
header{{display:flex;justify-content:space-between;gap:18px;align-items:flex-start;margin-bottom:14px}}
h1{{margin:4px 0 0;font-size:22px}}p,small{{color:var(--muted)}}a{{color:#d8dcdf}}
.model-id{{display:block;max-width:1150px;overflow-wrap:anywhere;font-family:ui-monospace,
SFMono-Regular,Menlo,monospace;color:#d7dce0}}.cards{{display:grid;
grid-template-columns:repeat(8,minmax(120px,1fr));gap:9px;margin:14px 0}}
.card,.panel{{background:var(--panel);border:1px solid var(--line);border-radius:12px}}
.card{{padding:13px}}.card small{{text-transform:uppercase;font-size:10px;letter-spacing:.08em}}
.card b{{display:block;font-size:18px;margin-top:7px}}.panel{{padding:14px}}.scroll{{overflow:auto;
max-height:72vh}}table{{width:100%;border-collapse:collapse;font-size:12px}}th,td{{padding:9px 10px;
border-bottom:1px solid #272c31;white-space:nowrap;text-align:left;vertical-align:top}}
th{{position:sticky;top:0;background:#1b1f23;color:#9aa1a8;font-size:10px;text-transform:uppercase;
letter-spacing:.05em}}td.match{{min-width:240px}}td.policy{{max-width:360px;overflow:hidden;
text-overflow:ellipsis;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}}td small{{display:block;
margin-top:4px}}.result{{display:inline-block;padding:4px 7px;border-radius:999px;font-size:10px}}
.result-win{{color:var(--win)}}.result-loss{{color:var(--loss)}}.result-void{{color:var(--void)}}
.row-win{{box-shadow:inset 3px 0 var(--win)}}.row-loss{{box-shadow:inset 3px 0 var(--loss)}}
.row-void{{box-shadow:inset 3px 0 var(--void)}}.empty{{text-align:center;color:var(--muted);
padding:36px!important}}@media(max-width:900px){{.cards{{grid-template-columns:repeat(2,1fr)}}
main{{padding:14px}}header{{display:block}}}}
</style></head><body><main>
<header><div><small>RESEARCH_MODEL_VERSION_DRILLDOWN_V1</small>
<h1>Model version picks</h1><span class="model-id">{model_label}</span>
<p>Exact settled Research rows behind this Analytics V2 model cohort.</p></div>
<div><a href="/research/analytics">← Analytics V2</a> ·
<a href="/research/analytics/model.json?{escape(query, quote=True)}">JSON</a></div></header>
<section class="cards">{cards}</section>
<section class="panel"><div class="scroll"><table><thead><tr>
<th>Match</th><th>Result</th><th>Pick</th><th>Entry</th><th>Model P</th>
<th>Fair P</th><th>Edge</th><th>EV</th><th>Close</th><th>CLV</th><th>P/L</th>
<th>Route</th><th>Kickoff UTC</th><th>Qualified UTC</th><th>Policy config</th>
</tr></thead><tbody>{rows_html}</tbody></table></div></section>
</main></body></html>"""

    def render_analytics_html(self) -> str:
        return render_research_analytics_html(self.analytics_snapshot())

    def render_html(self, query: str = "") -> str:
        params = parse_qs(query, keep_blank_values=True)
        tab = params.get("tab", ["active"])[0].strip().casefold()
        if tab not in {"active", "awaiting", "history"}:
            tab = "active"

        metric_params = {
            key: value
            for key, value in params.items()
            if key not in {"tab", "result"}
        }
        filtered = self.signals(metric_params)

        def kickoff_timestamp(row: dict[str, Any]) -> float:
            kickoff = row.get("kickoff_at")
            return kickoff.timestamp() if isinstance(kickoff, datetime) else float("inf")

        now = self._clock()
        if not isinstance(now, datetime):
            raise TypeError("clock must return a datetime")
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        now = now.astimezone(UTC)

        pending_rows = tuple(row for row in filtered if row["outcome"] == "PENDING")
        active_rows = tuple(
            sorted(
                (
                    row
                    for row in pending_rows
                    if not isinstance(row.get("kickoff_at"), datetime)
                    or row["kickoff_at"].astimezone(UTC) > now
                ),
                key=kickoff_timestamp,
            )
        )
        awaiting_rows = tuple(
            sorted(
                (
                    row
                    for row in pending_rows
                    if isinstance(row.get("kickoff_at"), datetime)
                    and row["kickoff_at"].astimezone(UTC) <= now
                ),
                key=kickoff_timestamp,
            )
        )
        history_rows = tuple(
            sorted(
                (row for row in filtered if row["outcome"] != "PENDING"),
                key=kickoff_timestamp,
                reverse=True,
            )
        )
        result_filter = params.get("result", [""])[0].strip().upper()
        if tab == "history":
            rows = tuple(
                row
                for row in history_rows
                if not result_filter or row["outcome"] == result_filter
            )
        elif tab == "awaiting":
            rows = awaiting_rows
        else:
            rows = active_rows

        settled = history_rows
        wins = sum(row["outcome"] == "WIN" for row in settled)
        clvs = [row["clv_ppm"] for row in settled if row["clv_ppm"] is not None]
        pnl = sum(row["pnl_minor"] or 0 for row in settled)
        win_rate = (wins / len(settled) * 100) if settled else None
        avg_clv = (sum(clvs) / len(clvs) / 10_000) if clvs else None
        played_count = sum(row.get("disposition") == "PLAYED" for row in filtered)
        skipped_count = sum(row.get("disposition") == "SKIPPED" for row in filtered)
        blocked_count = sum(
            row.get("disposition") == "BLOCKED_EXPOSURE" for row in filtered
        )
        health_html = self._health_html(self._system_health())

        def field(name: str) -> str:
            return escape(params.get(name, [""])[0], quote=True)

        def tab_href(next_tab: str) -> str:
            query_params = {
                key: value[0]
                for key, value in params.items()
                if value and value[0] and key not in {"tab", "result"}
            }
            query_params["tab"] = next_tab
            return "/research?" + urlencode(query_params)

        def signed_class(value: float | None) -> str:
            if value is None or value == 0:
                return "neutral"
            return "positive" if value > 0 else "negative"

        def market_label(row: dict[str, Any]) -> str:
            market = "O/U 2.5" if row["market"] == "OU_25" else row["market"]
            return f'{market} {row["selection"]}'

        def result_badge(outcome: str) -> str:
            css = {
                "WIN": "win",
                "LOSS": "loss",
                "VOID": "void",
                "PENDING": "pending",
            }.get(outcome, "void")
            return f'<span class="badge result-{css}">{escape(outcome)}</span>'

        def disposition_badge(disposition: str) -> str:
            css = {
                "PLAYED": "played",
                "SKIPPED": "skipped",
                "BLOCKED_EXPOSURE": "blocked",
            }.get(disposition, "skipped")
            label = disposition.replace("_", " ")
            return f'<span class="badge route-{css}">{escape(label)}</span>'

        def freshness_badge(value: str) -> str:
            css = {
                "FRESH": "fresh",
                "USABLE_STALE": "stale",
                "HARD_STALE": "hard-stale",
            }.get(value, "void")
            label = value.replace("_", " ")
            return f'<span class="mini-badge freshness-{css}">{escape(label)}</span>'

        body_rows: list[str] = []
        if tab in {"active", "awaiting"}:
            for row in rows:
                exposure = (
                    "—"
                    if row["last_open_exposure_minor"] is None
                    or row["exposure_cap_minor"] is None
                    else (
                        f'{row["last_open_exposure_minor"] / 100:.0f}/'
                        f'{row["exposure_cap_minor"] / 100:.0f} RSD'
                    )
                )
                match = f'{escape(row["home_team"])} – {escape(row["away_team"])}'
                competition = escape(row.get("competition_name") or "—")
                body_rows.append(
                    '<tr class="row-pending">'
                    f'<td class="match"><b>{match}</b>'
                    f'<small>{competition} · fixture {escape(str(row["provider_fixture_id"]))}</small></td>'
                    f'<td><b>{_time(row["kickoff_at"])}</b></td>'
                    f'<td><span class="pick-pill">{escape(market_label(row))}</span></td>'
                    f'<td><b>{_pct(row["model_probability"])}</b>'
                    f'<small>fair {_pct(row["market_fair_probability"])} · {escape(row["probability_bucket"])}</small></td>'
                    f'<td><b>{_odd(row["odds"])}</b><small>{escape(row["odds_bucket"])}</small></td>'
                    f'<td>{disposition_badge(row["disposition"])}</td>'
                    f'<td class="{signed_class(row["edge"])}"><b>{_pct(row["edge"])}</b></td>'
                    f'<td class="{signed_class(row["expected_value"])}"><b>{_pct(row["expected_value"])}</b>'
                    f'<small>{escape(row["ev_bucket"])}</small></td>'
                    f'<td class="bookmaker-cell">{_bookmaker_badge(row["bookmaker"])}<small>{escape(row["source"])}</small></td>'
                    f'<td>{_time(row["qualified_at"])}'
                    f'<small>{row["quote_age_seconds"]}s · {freshness_badge(row["freshness"])}</small></td>'
                    f'<td><b>{exposure}</b><small>'
                    f'{"blocked ×" + str(row["blocked_count"]) if row["blocked_count"] is not None else "production candidate"}'
                    f'</small></td>'
                    f'<td>{result_badge(row["outcome"])}'
                    + (
                        f'<small>{escape(row.get("result_phase") or "WAITING")} · '
                        f'{escape(row.get("result_provider_status") or row.get("fixture_status") or "unknown")}</small>'
                        if tab == "awaiting"
                        else ""
                    )
                    + "</td></tr>"
                )
            headers = (
                "<th>Match</th><th>Kickoff</th><th>Pick</th><th>Model</th>"
                "<th>Odds</th><th>Route</th><th>Edge</th><th>EV</th><th>Bookmaker</th>"
                "<th>Qualified</th><th>Exposure</th><th>Status</th>"
            )
            empty_text = (
                "No awaiting-result research picks match these filters."
                if tab == "awaiting"
                else "No active research picks match these filters."
            )
            colspan = 12
        else:
            for row in rows:
                clv_value = (
                    None if row["clv_ppm"] is None else row["clv_ppm"] / 10_000
                )
                clv = "—" if clv_value is None else f"{clv_value:+.2f}%"
                pnl_value = None if row["pnl_minor"] is None else row["pnl_minor"] / 100
                pnl_rsd = "—" if pnl_value is None else f"{pnl_value:+.0f} RSD"
                match = f'{escape(row["home_team"])} – {escape(row["away_team"])}'
                competition = escape(row.get("competition_name") or "—")
                home = row.get("regulation_home_goals")
                away = row.get("regulation_away_goals")
                score = (
                    f"{home}–{away}"
                    if home is not None and away is not None
                    else "—"
                )
                row_class = f'row-{row["outcome"].casefold()}'
                provider_status = escape(
                    row.get("result_provider_status")
                    or row.get("result_phase")
                    or "settled"
                )
                result_panel = (
                    f'<div class="result-panel result-panel-{row["outcome"].casefold()}">'
                    f'<div class="score">{score.replace("–", " : ")}</div>'
                    f'<div class="result-meta">{result_badge(row["outcome"])}'
                    f'<span>{provider_status}</span></div></div>'
                )
                body_rows.append(
                    f'<tr class="{row_class}">'
                    f'<td class="match"><b>{match}</b>'
                    f'<small>{competition} · fixture {escape(str(row["provider_fixture_id"]))}</small></td>'
                    f'<td class="result-cell">{result_panel}</td>'
                    f'<td><span class="pick-pill">{escape(market_label(row))}</span></td>'
                    f'<td>{_time(row["kickoff_at"])}</td>'
                    f'<td><b>{_odd(row["odds"])}</b><small>{escape(row["odds_bucket"])} · {escape(row["bookmaker"])}</small></td>'
                    f'<td><b>{_odd(row["closing_odds"])}</b><small>{_time(row["closing_observed_at"])}</small></td>'
                    f'<td class="{signed_class(clv_value)}"><b>{clv}</b></td>'
                    f'<td><b>{_pct(row["model_probability"])}</b>'
                    f'<small>{escape(row["probability_bucket"])} · fair {_pct(row["market_fair_probability"])}</small></td>'
                    f'<td class="{signed_class(row["expected_value"])}"><b>{_pct(row["expected_value"])}</b>'
                    f'<small>{escape(row["ev_bucket"])}</small></td>'
                    f'<td>{disposition_badge(row["disposition"])}</td>'
                    f'<td class="{signed_class(pnl_value)}"><b>{pnl_rsd}</b></td>'
                    f'<td class="bookmaker-cell">{_bookmaker_badge(row["bookmaker"])}<small>{escape(row["source"])}</small></td>'
                    f'<td>{_time(row["qualified_at"])}</td>'
                    "</tr>"
                )
            headers = (
                "<th>Match</th><th>Result</th><th>Pick</th><th>Kickoff</th><th>Entry</th>"
                "<th>Research close</th><th>CLV</th><th>Model</th><th>EV</th>"
                "<th>Route</th><th>P/L</th><th>Bookmaker</th><th>Qualified</th>"
            )
            empty_text = "No historical research picks match these filters."
            colspan = 13

        rows_html = (
            "".join(body_rows)
            or f'<tr><td class="empty" colspan="{colspan}">{empty_text}</td></tr>'
        )
        win_rate_text = "—" if win_rate is None else f"{win_rate:.1f}%"
        avg_clv_text = "—" if avg_clv is None else f"{avg_clv:+.2f}%"
        pnl_text = f"{pnl / 100:+.0f} RSD"
        pnl_class = signed_class(pnl)
        avg_clv_class = signed_class(avg_clv)

        def option_list(name: str, values: tuple[str, ...]) -> str:
            selected = field(name)
            return "".join(
                f'<option value="{escape(value, quote=True)}" '
                f'{"selected" if selected == value else ""}>{escape(value)}</option>'
                for value in values
            )

        result_filter_html = ""
        if tab == "history":
            options = "".join(
                f'<option {"selected" if field("result") == value else ""}>{value}</option>'
                for value in ("WIN", "LOSS", "VOID")
            )
            result_filter_html = (
                '<select name="result" aria-label="Result filter">'
                '<option value="">All results</option>'
                + options
                + "</select>"
            )

        active_class = "active" if tab == "active" else ""
        awaiting_class = "active" if tab == "awaiting" else ""
        history_class = "active" if tab == "history" else ""
        active_href = escape(tab_href("active"), quote=True)
        awaiting_href = escape(tab_href("awaiting"), quote=True)
        history_href = escape(tab_href("history"), quote=True)
        clear_href = f"/research?tab={tab}"

        return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>QuantBet Research</title><style>
:root{{--bg:#111315;--panel:#181b1f;--panel-2:#1c2024;--panel-3:#22272c;--line:#30363d;--line-soft:#252a2f;--text:#eceff1;--muted:#9299a1;--accent:#c2c8ce;--accent-soft:rgba(194,200,206,.10);--blue:#86a6c2;--win:#69c98f;--loss:#e06f78;--warn:#c6a35d;--void:#9aa1a8;color-scheme:dark;background:var(--bg);color:var(--text);font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
*{{box-sizing:border-box}}body{{margin:0;background:linear-gradient(180deg,#14171a 0%,var(--bg) 180px);color:var(--text)}}
main{{max-width:1920px;margin:auto;padding:24px}}.topbar{{display:flex;align-items:center;justify-content:space-between;gap:20px;margin-bottom:22px}}
.brand{{display:flex;align-items:center;gap:14px}}.sportsbook-logo{{height:46px;min-width:154px;display:flex;align-items:center;padding:0 13px;border-radius:10px;background:linear-gradient(180deg,#25292d,#1a1d20);border:1px solid #3d4349;box-shadow:inset 0 1px rgba(255,255,255,.04),0 10px 28px rgba(0,0,0,.22);font-weight:950;letter-spacing:-.03em}}.logo-q{{display:grid;place-items:center;width:31px;height:31px;margin-right:8px;border:2px solid #d4d8dc;border-radius:50%;color:#f0f2f3;font-size:18px;line-height:1}}.logo-word{{color:#d8dcdf;font-size:15px}}.logo-bet{{margin-left:2px;color:#d3aa5f;font-size:15px}}
h1{{font-size:24px;line-height:1.1;margin:0}}.eyebrow{{font-size:11px;text-transform:uppercase;letter-spacing:.14em;color:#aab1b8;font-weight:800;margin-bottom:4px}}
.subtitle{{margin:0;color:var(--muted);font-size:13px}}.readonly{{border:1px solid var(--line);background:#1a1e22;padding:8px 11px;border-radius:999px;color:#aeb5bc;font-size:12px;white-space:nowrap}}
.health-strip{{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:-8px 0 16px;padding:9px 10px;background:#15181b;border:1px solid var(--line);border-radius:12px}}.health-label{{font-size:10px;text-transform:uppercase;letter-spacing:.09em;color:#737b83;font-weight:900;margin:0 4px}}.health-item{{display:flex;align-items:center;gap:7px;padding:6px 9px;border:1px solid #2a3035;border-radius:9px;background:#1a1e22;min-width:112px}}.health-item>span:last-child{{display:block}}.health-item b{{display:block;font-size:11px;line-height:1.05}}.health-item small{{display:block;margin:3px 0 0;font-size:9px;line-height:1;color:#858d94}}.health-lamp{{width:9px;height:9px;border-radius:50%;flex:0 0 9px;background:#677079;box-shadow:0 0 0 3px rgba(103,112,121,.10)}}.health-ok .health-lamp{{background:var(--win);box-shadow:0 0 0 3px rgba(105,201,143,.11),0 0 10px rgba(105,201,143,.28)}}.health-warn .health-lamp{{background:var(--warn);box-shadow:0 0 0 3px rgba(198,163,93,.11),0 0 10px rgba(198,163,93,.24)}}.health-bad .health-lamp{{background:var(--loss);box-shadow:0 0 0 3px rgba(224,111,120,.11),0 0 10px rgba(224,111,120,.26)}}.health-unknown .health-lamp{{background:#677079}}
.tabs{{display:flex;gap:8px;margin:0 0 16px;padding:5px;background:#171a1d;border:1px solid var(--line);border-radius:12px;width:max-content}}
.tabs a{{text-decoration:none;color:#9ca3aa;padding:9px 16px;border-radius:8px;font-weight:800;font-size:13px;transition:.15s ease}}
.tabs a:hover{{color:var(--text);background:#24292e}}.tabs a.active{{background:#d4d8dc;color:#17191b;box-shadow:0 5px 16px rgba(0,0,0,.24)}}
.cards{{display:grid;grid-template-columns:repeat(8,minmax(130px,1fr));gap:10px;margin-bottom:14px}}
.card{{position:relative;overflow:hidden;background:linear-gradient(180deg,var(--panel-2),var(--panel));border:1px solid var(--line);border-radius:12px;padding:14px 15px;min-height:84px}}
.card:after{{content:"";position:absolute;width:72px;height:72px;border-radius:50%;right:-26px;top:-30px;background:rgba(255,255,255,.028)}}
.card small{{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.08em;font-weight:800}}.card b{{display:block;font-size:22px;margin-top:8px;letter-spacing:-.02em}}
.card .positive{{color:var(--win)}}.card .negative{{color:var(--loss)}}.card .neutral{{color:var(--text)}}
.toolbar{{display:flex;align-items:center;justify-content:space-between;gap:12px;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:10px 12px;margin-bottom:12px}}
form{{display:flex;gap:7px;flex-wrap:wrap;align-items:center;flex:1}}input,select,button{{height:36px;background:#14171a;color:var(--text);border:1px solid #3a4046;border-radius:8px;padding:0 10px;font:inherit;font-size:12px;outline:none}}
input{{width:132px}}input[name="league"]{{width:170px}}input:focus,select:focus{{border-color:#8f969d;box-shadow:0 0 0 2px rgba(194,200,206,.08)}}
button{{background:#d4d8dc;color:#17191b;border-color:#d4d8dc;font-weight:900;cursor:pointer;padding:0 14px}}button:hover{{background:#e2e5e8;border-color:#e2e5e8}}
.clear{{color:#a4b4ab;text-decoration:none;font-size:12px;padding:8px 6px}}.clear:hover{{color:white}}
.table-shell{{background:var(--panel);border:1px solid var(--line);border-radius:13px;overflow:hidden;box-shadow:0 18px 60px rgba(0,0,0,.17)}}
.table-title{{display:flex;align-items:center;justify-content:space-between;padding:13px 15px;border-bottom:1px solid var(--line);background:linear-gradient(180deg,#1e2226,#191c20)}}
.table-title b{{font-size:14px}}.table-title span{{font-size:12px;color:var(--muted)}}.table{{overflow:auto;max-height:70vh}}
table{{border-collapse:separate;border-spacing:0;width:100%;font-size:12px}}th,td{{padding:11px 12px;border-bottom:1px solid var(--line-soft);text-align:left;white-space:nowrap;vertical-align:middle}}
th{{position:sticky;top:0;z-index:3;background:#1b1f23;color:#959da5;text-transform:uppercase;letter-spacing:.06em;font-size:10px;font-weight:900}}
tbody tr{{transition:background .12s ease}}tbody tr:hover{{background:#20252a}}tbody tr:last-child td{{border-bottom:0}}
td.match{{min-width:250px}}td b{{font-weight:800}}small{{display:block;color:var(--muted);margin-top:4px;font-size:10px}}
.pick-pill{{display:inline-flex;align-items:center;padding:6px 9px;border-radius:7px;background:#24292e;border:1px solid #3a4046;color:#e6e9ec;font-weight:900;font-size:11px}}
.bookmaker-cell{{min-width:132px}}.bookmaker-mark{{display:inline-flex;align-items:center;justify-content:center;height:28px;min-width:86px;padding:0 9px;border-radius:7px;border:1px solid #3a4046;background:#22272c;box-shadow:inset 0 1px rgba(255,255,255,.04);font-size:10px;font-weight:950;line-height:1;letter-spacing:-.02em}}.bookmaker-mark b,.bookmaker-mark strong{{font:inherit}}.brand-bet365 b{{color:#f5f5f5}}.brand-bet365 strong{{color:#f1d24b;margin-left:1px}}.bookmaker-bet365{{background:#146947;border-color:#2a8967}}.brand-1xbet b{{color:#61aef4}}.brand-1xbet strong{{color:#f5f6f7;margin-left:2px}}.bookmaker-1xbet{{background:#182f47;border-color:#305f8b}}.brand-superbet b{{color:#fff}}.brand-superbet strong{{color:#ffdc32;margin-left:1px}}.bookmaker-superbet{{background:#d8262e;border-color:#ef4c52}}.brand-pinnacle b{{color:#f6a428}}.brand-pinnacle strong{{color:#f1f1f1}}.bookmaker-pinnacle{{background:#20262b;border-color:#5f6870}}.brand-betfair b{{color:#14181b}}.brand-betfair strong{{color:#14181b;margin-left:1px}}.bookmaker-betfair{{background:#f2a51a;border-color:#ffc255}}.brand-bwin b{{color:#fff;text-transform:lowercase;font-size:13px}}.bookmaker-bwin{{background:#151515;border-color:#4a4a4a}}.brand-unibet b{{color:#fff}}.brand-unibet i{{display:block;color:#56c54f;font-style:normal;font-size:8px;letter-spacing:1px;margin-left:5px}}.bookmaker-unibet{{background:#222;border-color:#4b4b4b}}.brand-betway b{{color:#fff}}.bookmaker-betway{{background:#1f6c45;border-color:#3b9369}}.brand-williamhill b{{color:#f3cc43}}.brand-williamhill strong{{color:#fff;margin-left:2px}}.bookmaker-williamhill{{background:#17365c;border-color:#315f93}}.brand-mozzart b{{color:#fff}}.bookmaker-mozzart,.bookmaker-mozzartbet{{background:#1765b5;border-color:#3e8bd5}}.brand-maxbet b{{color:#fff}}.brand-maxbet strong{{color:#ffce2f;margin-left:2px}}.bookmaker-maxbet{{background:#d1242c;border-color:#ed5056}}.brand-meridian b{{color:#fff}}.brand-meridian strong{{color:#e8473f;margin-left:2px}}.bookmaker-meridian,.bookmaker-meridianbet{{background:#273748;border-color:#485b6d}}.brand-admiral b{{color:#fff}}.brand-admiral strong{{color:#e62e39;margin-left:2px}}.bookmaker-admiral,.bookmaker-admiralbet{{background:#232323;border-color:#555}}.brand-soccerbet b{{color:#fff}}.brand-soccerbet strong{{color:#f4bf32;margin-left:2px}}.bookmaker-soccerbet{{background:#145a92;border-color:#337caf}}.brand-generic{{display:flex;align-items:center;gap:6px}}.brand-generic i{{display:grid;place-items:center;width:18px;height:18px;border-radius:5px;background:#343a40;color:#dfe3e6;font-style:normal;font-size:8px}}.brand-generic b{{color:#dfe3e6;font-size:9px;max-width:80px;overflow:hidden;text-overflow:ellipsis}}
.badge{{display:inline-flex;align-items:center;justify-content:center;min-width:68px;padding:6px 9px;border-radius:999px;font-weight:950;font-size:10px;letter-spacing:.06em}}
.route-played{{background:rgba(134,166,194,.12);border:1px solid rgba(134,166,194,.32);color:#a9c3d9}}.route-skipped{{background:rgba(154,161,168,.10);border:1px solid rgba(154,161,168,.25);color:#aab1b8}}.route-blocked{{background:rgba(198,163,93,.11);border:1px solid rgba(198,163,93,.30);color:var(--warn)}}
.result-win{{background:rgba(105,201,143,.15);border:1px solid rgba(105,201,143,.42);color:#82dda6}}.result-loss{{background:rgba(224,111,120,.15);border:1px solid rgba(224,111,120,.42);color:#f08790}}.result-void{{background:rgba(154,169,161,.12);border:1px solid rgba(154,169,161,.28);color:#b4c1ba}}.result-pending{{background:rgba(242,189,88,.12);border:1px solid rgba(242,189,88,.32);color:var(--warn)}}
.result-cell{{min-width:154px;padding-top:7px!important;padding-bottom:7px!important}}.result-panel{{min-width:132px;padding:8px 10px;border-radius:10px;border:1px solid #3a4046;background:#202428;box-shadow:inset 0 1px rgba(255,255,255,.03)}}.result-panel .score{{font-size:23px;line-height:1;font-weight:950;letter-spacing:.04em;color:#f4f6f7;margin-bottom:7px}}.result-meta{{display:flex;align-items:center;gap:7px}}.result-meta .badge{{min-width:57px;padding:4px 7px;font-size:9px}}.result-meta>span:last-child{{font-size:9px;text-transform:uppercase;letter-spacing:.05em;color:#9199a0;font-weight:800}}.result-panel-win{{background:linear-gradient(135deg,rgba(105,201,143,.14),#202428 62%);border-color:rgba(105,201,143,.34)}}.result-panel-loss{{background:linear-gradient(135deg,rgba(224,111,120,.15),#202428 62%);border-color:rgba(224,111,120,.36)}}.result-panel-void{{background:linear-gradient(135deg,rgba(154,161,168,.10),#202428 62%)}}
.mini-badge{{display:inline-flex;padding:2px 6px;border-radius:999px;font-size:9px;font-weight:850;vertical-align:1px}}.freshness-fresh{{background:rgba(105,201,143,.10);color:var(--win)}}.freshness-stale{{background:rgba(198,163,93,.11);color:var(--warn)}}.freshness-hard-stale{{background:rgba(224,111,120,.10);color:var(--loss)}}
.positive{{color:var(--win)}}.negative{{color:var(--loss)}}.neutral{{color:var(--text)}}.row-win{{box-shadow:inset 4px 0 var(--win);background:linear-gradient(90deg,rgba(105,201,143,.045),transparent 25%)}}.row-loss{{box-shadow:inset 4px 0 var(--loss);background:linear-gradient(90deg,rgba(224,111,120,.05),transparent 25%)}}.row-void{{box-shadow:inset 4px 0 var(--void);background:linear-gradient(90deg,rgba(154,161,168,.035),transparent 25%)}}.row-pending{{box-shadow:inset 3px 0 var(--warn)}}
.empty{{text-align:center!important;color:var(--muted);padding:40px!important}}footer{{display:flex;justify-content:space-between;gap:15px;color:#7f878e;margin-top:12px;font-size:11px}}
@media(max-width:1200px){{.cards{{grid-template-columns:repeat(3,1fr)}}.toolbar{{align-items:flex-start}}}}
@media(max-width:720px){{main{{padding:14px}}.topbar{{align-items:flex-start;flex-direction:column}}.health-strip{{align-items:stretch}}.health-label{{width:100%;margin-bottom:1px}}.health-item{{min-width:calc(50% - 4px);flex:1}}.cards{{grid-template-columns:repeat(2,1fr)}}.toolbar{{display:block}}form{{margin-bottom:7px}}input,input[name="league"],select{{width:calc(50% - 4px)}}footer{{display:block;line-height:1.6}}}}
</style></head><body><main>
<header class="topbar">
<div class="brand"><div class="sportsbook-logo" aria-label="QuantBet"><span class="logo-q">Q</span><span class="logo-word">QUANT</span><span class="logo-bet">BET</span></div><div><div class="eyebrow">Research universe</div><h1>Research Board</h1><p class="subtitle">All final-gate candidates · production + exposure blocked · one canonical pick per fixture</p></div></div>
<div class="readonly">● READ-ONLY RESEARCH</div>
</header>
<section class="health-strip" aria-label="System status"><span class="health-label">System status</span>{health_html}</section>
<nav class="tabs" aria-label="Research sections">
<a class="{active_class}" href="{active_href}">Active <span>({len(active_rows)})</span></a>
<a class="{awaiting_class}" href="{awaiting_href}">Awaiting result <span>({len(awaiting_rows)})</span></a>
<a class="{history_class}" href="{history_href}">History <span>({len(history_rows)})</span></a>
<a href="/research/analytics">Analytics V2</a>
</nav>
<section class="cards">
<div class="card"><small>Active</small><b>{len(active_rows)}</b></div>
<div class="card"><small>Awaiting result</small><b>{len(awaiting_rows)}</b></div>
<div class="card"><small>Settled</small><b>{len(history_rows)}</b></div>
<div class="card"><small>Played</small><b>{played_count}</b></div>
<div class="card"><small>Skipped</small><b>{skipped_count}</b></div>
<div class="card"><small>Exposure blocked</small><b>{blocked_count}</b></div>
<div class="card"><small>Win rate</small><b>{win_rate_text}</b></div>
<div class="card"><small>Flat P/L</small><b class="{pnl_class}">{pnl_text}</b></div>
<div class="card"><small>Avg CLV</small><b class="{avg_clv_class}">{avg_clv_text}</b></div>
</section>
<div class="toolbar">
<form method="get">
<input type="hidden" name="tab" value="{tab}">
<select name="market" aria-label="Market filter"><option value="">All markets</option><option {"selected" if field("market")=="BTTS" else ""}>BTTS</option><option {"selected" if field("market")=="OU_25" else ""}>OU_25</option></select>
<select name="disposition" aria-label="Route filter"><option value="">All routes</option>{option_list("disposition", ("PLAYED","SKIPPED","BLOCKED_EXPOSURE"))}</select>
<select name="p_bucket" aria-label="Probability bucket"><option value="">All p buckets</option>{option_list("p_bucket", ("40–45%","45–50%","50–55%","55–60%","60–65%","65–70%","70–75%","75%+"))}</select>
<select name="ev_bucket" aria-label="EV bucket"><option value="">All EV buckets</option>{option_list("ev_bucket", ("7–10%","10–15%","15–20%","20–30%","30%+"))}</select>
<select name="odds_bucket" aria-label="Odds bucket"><option value="">All odds buckets</option>{option_list("odds_bucket", ("1.40–1.60","1.61–1.80","1.81–2.00","2.01–2.50","2.51–3.00","3.01–3.50","other"))}</select>
<input name="league" placeholder="League" value="{field("league")}">
<input name="p_min" placeholder="Model p min %" value="{field("p_min")}">
<input name="p_max" placeholder="Model p max %" value="{field("p_max")}">
<input name="ev_min" placeholder="EV min %" value="{field("ev_min")}">
<input name="ev_max" placeholder="EV max %" value="{field("ev_max")}">
<input name="odds_min" placeholder="Odds min" value="{field("odds_min")}">
<input name="odds_max" placeholder="Odds max" value="{field("odds_max")}">
{result_filter_html}
<button type="submit">Apply filters</button><a class="clear" href="{clear_href}">Clear</a>
</form>
</div>
<section class="table-shell">
<div class="table-title"><b>{("Active research board" if tab == "active" else "Awaiting result" if tab == "awaiting" else "Settled research history")}</b><span>{len(rows)} shown</span></div>
<div class="table"><table><thead><tr>{headers}</tr></thead><tbody>{rows_html}</tbody></table></div>
</section>
<footer><span>Universe = every canonical candidate that reached production eligibility: PLAYED/SKIPPED production picks plus exposure-blocked candidates. Research close = last stored same-series/source pre-kickoff quote.</span><span>Times: Europe/Belgrade · Counterfactual flat stake only · buckets use research entry evaluation</span></footer>
</main></body></html>"""


class ResearchDashboardHTTPService:
    def __init__(self, dashboard: ResearchDashboardService, *, host: str, port: int) -> None:
        service = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                parsed = urlsplit(self.path)
                if parsed.path == "/livez":
                    service._text(self, 200, "ok\n", "text/plain; charset=utf-8")
                    return
                if parsed.path not in {
                    "/",
                    "/research",
                    "/research/analytics",
                    "/research/analytics.json",
                    "/research/analytics/diagnostic.json",
                    "/research/analytics/model",
                    "/research/analytics/model.json",
                    "/research/analytics/league",
                    "/research/analytics/league.json",
                }:
                    service._text(self, 404, "not_found\n", "text/plain; charset=utf-8")
                    return
                if not service._authorize(self):
                    return
                try:
                    if parsed.path == "/research/analytics/league.json":
                        params = parse_qs(parsed.query, keep_blank_values=True)
                        league_id = int(params.get("league_id", ["0"])[0])
                        season = int(params.get("season", ["0"])[0])
                        body = json.dumps(
                            dashboard.league_details(league_id, season),
                            ensure_ascii=False,
                            indent=2,
                        )
                        content_type = "application/json; charset=utf-8"
                    elif parsed.path == "/research/analytics/league":
                        params = parse_qs(parsed.query, keep_blank_values=True)
                        league_id = int(params.get("league_id", ["0"])[0])
                        season = int(params.get("season", ["0"])[0])
                        body = dashboard.render_league_html(league_id, season)
                        content_type = "text/html; charset=utf-8"
                    elif parsed.path == "/research/analytics/model.json":
                        params = parse_qs(parsed.query, keep_blank_values=True)
                        model_version_id = params.get("model_version_id", [""])[0]
                        body = json.dumps(
                            dashboard.model_version_details(model_version_id),
                            ensure_ascii=False,
                            indent=2,
                        )
                        content_type = "application/json; charset=utf-8"
                    elif parsed.path == "/research/analytics/model":
                        params = parse_qs(parsed.query, keep_blank_values=True)
                        model_version_id = params.get("model_version_id", [""])[0]
                        body = dashboard.render_model_version_html(model_version_id)
                        content_type = "text/html; charset=utf-8"
                    elif parsed.path == "/research/analytics/diagnostic.json":
                        params = parse_qs(parsed.query, keep_blank_values=True)
                        bucket = params.get("bucket", ["OTHER_EXTREME"])[0]
                        body = json.dumps(
                            dashboard.diagnostic_details(bucket),
                            ensure_ascii=False,
                            indent=2,
                        )
                        content_type = "application/json; charset=utf-8"
                    elif parsed.path == "/research/analytics.json":
                        body = json.dumps(
                            dashboard.analytics_snapshot(),
                            ensure_ascii=False,
                            indent=2,
                        )
                        content_type = "application/json; charset=utf-8"
                    elif parsed.path == "/research/analytics":
                        body = dashboard.render_analytics_html()
                        content_type = "text/html; charset=utf-8"
                    else:
                        body = dashboard.render_html(parsed.query)
                        content_type = "text/html; charset=utf-8"
                    service._text(
                        self,
                        200,
                        body,
                        content_type,
                    )
                except (TypeError, ValueError):
                    service._text(self, 400, "invalid_filter\n", "text/plain; charset=utf-8")
                except Exception as exc:  # noqa: BLE001 - bounded read-only failure response
                    service._text(
                        self, 503, type(exc).__name__ + "\n", "text/plain; charset=utf-8"
                    )

            def do_POST(self) -> None:
                service._text(self, 405, "read_only\n", "text/plain; charset=utf-8")

            def log_message(self, _format: str, *_args: object) -> None:
                return

        self._server = ThreadingHTTPServer((host, port), Handler)
        self._thread = Thread(target=self._server.serve_forever, daemon=True)

    @staticmethod
    def _text(
        handler: BaseHTTPRequestHandler, status: int, body: str, content_type: str
    ) -> None:
        encoded = body.encode()
        handler.send_response(status)
        handler.send_header("Content-Type", content_type)
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'")
        handler.send_header("X-Content-Type-Options", "nosniff")
        handler.send_header("X-Frame-Options", "DENY")
        handler.send_header("Content-Length", str(len(encoded)))
        handler.end_headers()
        handler.wfile.write(encoded)

    @staticmethod
    def _authorize(handler: BaseHTTPRequestHandler) -> bool:
        public = os.environ.get("QUANTBET_RESEARCH_PUBLIC", "").strip().casefold()
        if public in {"1", "true", "yes", "on"}:
            return True
        password = os.environ.get("QUANTBET_RESEARCH_PASSWORD", "")
        username = os.environ.get("QUANTBET_RESEARCH_USER", "quantbet")
        if not password:
            ResearchDashboardHTTPService._text(
                handler, 404, "not_found\n", "text/plain; charset=utf-8"
            )
            return False
        supplied_user = supplied_password = ""
        authorization = handler.headers.get("Authorization", "")
        if authorization.startswith("Basic "):
            try:
                decoded = base64.b64decode(authorization[6:], validate=True).decode()
                supplied_user, supplied_password = decoded.split(":", 1)
            except (ValueError, UnicodeDecodeError):
                pass
        if hmac.compare_digest(supplied_user, username) and hmac.compare_digest(
            supplied_password, password
        ):
            return True
        encoded = b'authentication_required\n'
        handler.send_response(401)
        handler.send_header("WWW-Authenticate", 'Basic realm="QuantBet Research"')
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Content-Type", "text/plain; charset=utf-8")
        handler.send_header("Content-Length", str(len(encoded)))
        handler.end_headers()
        handler.wfile.write(encoded)
        return False

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
