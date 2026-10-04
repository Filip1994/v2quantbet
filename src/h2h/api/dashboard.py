"""Read-only, server-rendered QuantBet operations dashboard."""

from __future__ import annotations

import base64
import hmac
import json
import os
from uuid import uuid4
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock, Thread
from time import monotonic
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlsplit

from h2h.api.dashboard_time import (
    COUNTDOWN_SCRIPT,
    COUNTDOWN_SCRIPT_CSP,
    kickoff_countdown,
    local_time,
)
from h2h.domain.operator_pick_state import OperatorPickState
from h2h.production_buckets import bucket_spec


WORKER_FRESHNESS_SECONDS = 600
DASHBOARD_CACHE_SECONDS = 10

_COUNTRY_FLAG_CODES = {
    "albania": "AL",
    "andorra": "AD",
    "argentina": "AR",
    "armenia": "AM",
    "austria": "AT",
    "azerbaijan": "AZ",
    "belarus": "BY",
    "belgium": "BE",
    "bolivia": "BO",
    "bosnia": "BA",
    "bosnia and herzegovina": "BA",
    "brazil": "BR",
    "bulgaria": "BG",
    "canada": "CA",
    "chile": "CL",
    "colombia": "CO",
    "costa rica": "CR",
    "croatia": "HR",
    "cyprus": "CY",
    "czech republic": "CZ",
    "czechia": "CZ",
    "denmark": "DK",
    "dominican republic": "DO",
    "ecuador": "EC",
    "el salvador": "SV",
    "england": "GB",
    "estonia": "EE",
    "faroe islands": "FO",
    "finland": "FI",
    "france": "FR",
    "georgia": "GE",
    "germany": "DE",
    "gibraltar": "GI",
    "greece": "GR",
    "guatemala": "GT",
    "haiti": "HT",
    "honduras": "HN",
    "hungary": "HU",
    "iceland": "IS",
    "ireland": "IE",
    "israel": "IL",
    "italy": "IT",
    "jamaica": "JM",
    "kazakhstan": "KZ",
    "kosovo": "XK",
    "latvia": "LV",
    "liechtenstein": "LI",
    "lithuania": "LT",
    "luxembourg": "LU",
    "malta": "MT",
    "mexico": "MX",
    "moldova": "MD",
    "monaco": "MC",
    "montenegro": "ME",
    "netherlands": "NL",
    "nicaragua": "NI",
    "north macedonia": "MK",
    "northern ireland": "GB",
    "norway": "NO",
    "panama": "PA",
    "paraguay": "PY",
    "peru": "PE",
    "poland": "PL",
    "portugal": "PT",
    "puerto rico": "PR",
    "romania": "RO",
    "san marino": "SM",
    "scotland": "GB",
    "serbia": "RS",
    "slovakia": "SK",
    "slovenia": "SI",
    "spain": "ES",
    "sweden": "SE",
    "switzerland": "CH",
    "trinidad and tobago": "TT",
    "turkey": "TR",
    "turkiye": "TR",
    "ukraine": "UA",
    "united states": "US",
    "usa": "US",
    "uruguay": "UY",
    "venezuela": "VE",
    "wales": "GB",
}


def dashboard_is_public() -> bool:
    """Return whether dashboard read routes are intentionally public."""
    return os.environ.get("QUANTBET_DASHBOARD_PUBLIC", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _policy(application: Any) -> Any:
    policy = application.settings.application.registration_policy
    if policy is None:
        raise RuntimeError("dashboard requires a registration policy")
    return policy


def _production_bucket_links_html(bucket_ids: Any) -> str:
    research_base = os.environ.get(
        "QUANTBET_RESEARCH_DASHBOARD_BASE_URL",
        "https://quantbet-research-production.up.railway.app",
    ).rstrip("/")
    quantlab_base = os.environ.get(
        "QUANTBET_QUANTLAB_DASHBOARD_BASE_URL",
        "https://quantbet-quantlab-production.up.railway.app",
    ).rstrip("/")
    links: list[str] = []
    for raw in bucket_ids or ():
        bucket_id = str(raw)
        spec = bucket_spec(bucket_id)
        if spec is None:
            links.append(f'<span class="production-bucket-link unknown">{escape(bucket_id)}</span>')
            continue
        base = research_base if spec.source_universe == "RESEARCH" else quantlab_base
        href = base + spec.analytics_path
        links.append(
            f'<a class="production-bucket-link" href="{escape(href, quote=True)}" '
            'target="_blank" rel="noopener noreferrer" '
            f'title="{escape(bucket_id, quote=True)}">{escape(spec.label)}</a>'
        )
    return '<span class="production-bucket-links">' + " · ".join(links) + "</span>" if links else ""


class DashboardService:
    """Project durable PostgreSQL facts without mutating or recomputing them."""

    def __init__(self, application: Any) -> None:
        self._application = application
        self._snapshot_lock = Lock()
        self._cached_snapshot: dict[str, Any] | None = None
        self._cached_at = 0.0

    def snapshot(self) -> dict[str, Any]:
        with self._snapshot_lock:
            now = monotonic()
            if self._cached_snapshot is None or now - self._cached_at >= DASHBOARD_CACHE_SECONDS:
                snapshot = self._snapshot_uncached()
                self._cached_snapshot = snapshot
                self._cached_at = monotonic()
            return self._cached_snapshot

    def _invalidate_snapshot(self) -> None:
        with self._snapshot_lock:
            self._cached_snapshot = None

    def _snapshot_uncached(self) -> dict[str, Any]:
        generated_at = datetime.now(UTC)
        policy = _policy(self._application)
        picks = self._picks()
        operations = self._operations(generated_at)
        usage = self._application.budget.usage_by_category()
        used = sum(usage.values())

        played_rows = [pick for pick in picks if pick.get("operator_state") == "PLAYED"]
        settled_played = [
            pick for pick in played_rows if pick.get("settlement_outcome") is not None
        ]
        open_played = [
            pick for pick in played_rows if pick.get("settlement_outcome") is None
        ]
        played = len(played_rows)
        skipped = sum(pick.get("operator_state") == "SKIPPED" for pick in picks)
        pending = sum(pick.get("operator_state") == "PENDING" for pick in picks)
        exposure = self._application.production_funnel.exposure_breakdown()
        realized_pnl_minor = sum(
            int(pick.get("realized_pnl_minor") or 0) for pick in settled_played
        )
        gross_returns_minor = sum(
            int(pick.get("gross_return_minor") or 0) for pick in settled_played
        )
        open_exposure_minor = int(exposure["open_exposure_minor"])
        initial_minor = policy.initial_bankroll_minor

        def settled_count(outcome: str) -> int:
            return sum(
                str(pick.get("settlement_outcome") or "").upper() == outcome
                for pick in settled_played
            )

        return {
            "generated_at": generated_at,
            "bankroll": {
                "initial_minor": initial_minor,
                "available_minor": initial_minor + realized_pnl_minor - open_exposure_minor,
                "open_exposure_minor": open_exposure_minor,
                "risk_exposure_minor": open_exposure_minor,
                "max_open_exposure_minor": policy.max_open_exposure_minor,
                "fixed_stake_minor": policy.fixed_stake_minor,
                "total_staked_minor": sum(int(pick["stake_minor"]) for pick in played_rows),
                "settled_stake_minor": sum(
                    int(pick["stake_minor"]) for pick in settled_played
                ),
                "gross_returns_minor": gross_returns_minor,
                "realized_pnl_minor": realized_pnl_minor,
                "pending_minor": sum(int(pick["stake_minor"]) for pick in open_played),
                "currency": policy.currency,
            },
            "counts": {
                "all": len(picks),
                "pending_operator": pending,
                "played": played,
                "skipped": skipped,
                "active": len(open_played),
                "won": settled_count("WIN"),
                "lost": settled_count("LOSS"),
                "void": settled_count("VOID"),
            },
            "system_performance": {
                "registered_picks": len(picks),
                "pending": len(open_played),
                "won": settled_count("WIN"),
                "lost": settled_count("LOSS"),
                "void": settled_count("VOID"),
                "realized_pnl_minor": realized_pnl_minor,
            },
            "provider_budget": {
                "used": used,
                "remaining": max(0, self._application.budget.effective_limit - used),
                "effective_limit": self._application.budget.effective_limit,
                "by_category": usage,
            },
            "operations": operations,
            "picks": picks,
        }

    def _picks(self) -> list[dict[str, Any]]:
        sql = """
            WITH latest_operator AS (
                SELECT DISTINCT ON (pick_id) pick_id, state
                FROM production_funnel_state_events
                ORDER BY pick_id, occurred_at DESC, persisted_at DESC, event_id DESC
            ),
            source_status AS (
                SELECT
                    p.*,
                    CASE
                        WHEN p.source_universe = 'GOALLAB' THEN goal_settlement.outcome
                        WHEN p.source_universe = 'RESEARCH'
                             AND research_result.result_classification = 'NON_PLAYED_VOIDABLE'
                        THEN 'VOID'
                        WHEN p.source_universe = 'RESEARCH'
                             AND research_result.result_classification = 'PLAYED_SETTLEABLE'
                        THEN CASE
                            WHEN p.market_key = 'OU_25' AND p.selection = 'OVER'
                            THEN CASE WHEN
                                research_result.regulation_home_goals
                                + research_result.regulation_away_goals > 2
                                THEN 'WIN' ELSE 'LOSS' END
                            WHEN p.market_key = 'OU_25' AND p.selection = 'UNDER'
                            THEN CASE WHEN
                                research_result.regulation_home_goals
                                + research_result.regulation_away_goals < 3
                                THEN 'WIN' ELSE 'LOSS' END
                            WHEN p.market_key = 'BTTS' AND p.selection = 'YES'
                            THEN CASE WHEN
                                research_result.regulation_home_goals > 0
                                AND research_result.regulation_away_goals > 0
                                THEN 'WIN' ELSE 'LOSS' END
                            WHEN p.market_key = 'BTTS' AND p.selection = 'NO'
                            THEN CASE WHEN NOT (
                                research_result.regulation_home_goals > 0
                                AND research_result.regulation_away_goals > 0
                            ) THEN 'WIN' ELSE 'LOSS' END
                            ELSE NULL
                        END
                        ELSE NULL
                    END AS source_outcome,
                    CASE
                        WHEN p.source_universe = 'GOALLAB' THEN goal_settlement.settled_at
                        WHEN p.source_universe = 'RESEARCH'
                             AND research_result.result_classification IN (
                                 'PLAYED_SETTLEABLE', 'NON_PLAYED_VOIDABLE'
                             )
                        THEN research_result.persisted_at
                        ELSE NULL
                    END AS source_settled_at,
                    CASE
                        WHEN p.source_universe = 'GOALLAB'
                        THEN goal_settlement.regulation_home_goals
                        ELSE research_result.regulation_home_goals
                    END AS source_home_goals,
                    CASE
                        WHEN p.source_universe = 'GOALLAB'
                        THEN goal_settlement.regulation_away_goals
                        ELSE research_result.regulation_away_goals
                    END AS source_away_goals
                FROM production_funnel_picks p
                LEFT JOIN quantlab_goal_pick_settlements goal_settlement
                  ON p.source_universe = 'GOALLAB'
                 AND goal_settlement.goal_pick_id = p.source_pick_id
                LEFT JOIN fixture_result_acquisition_states research_state
                  ON p.source_universe = 'RESEARCH'
                 AND research_state.fixture_id = p.source_fixture_id
                LEFT JOIN fixture_result_observations research_result
                  ON research_result.result_observation_id = research_state.current_observation_id
            )
            SELECT
                p.pick_id, p.cloned_at AS registered_at, p.source_fixture_id AS fixture_id,
                p.home_team, p.away_team, p.competition_name, p.country,
                p.kickoff_at, p.provider_status,
                p.market_key AS market, p.selection, p.stake_minor, p.currency,
                p.odds AS pick_odd, p.source_quote_observed_at AS pick_observed_at,
                p.cloned_at AS pick_captured_at,
                p.odds AS first_seen_odd,
                p.source_quote_observed_at AS first_seen_observed_at,
                p.cloned_at AS first_seen_captured_at,
                p.odds AS last_observed_odd,
                p.source_quote_observed_at AS last_observed_at,
                p.cloned_at AS last_checked_at,
                'SOURCE_CLONE'::text AS last_observed_source,
                'UNAVAILABLE'::text AS last_observed_freshness,
                NULL::numeric AS display_closing_odd,
                NULL::timestamptz AS display_closing_observed_at,
                'UNAVAILABLE'::text AS display_closing_source,
                NULL::text AS closing_status,
                NULL::text AS proxy_closing_status,
                NULL::bigint AS proxy_clv_ppm,
                NULL::bigint AS manual_clv_ppm,
                CASE
                    WHEN p.source_outcome IS NOT NULL THEN 'SETTLED'
                    WHEN p.provider_status IN ('FT', 'AET', 'PEN') THEN 'FINISHED'
                    WHEN p.provider_status IN ('CANC', 'ABD', 'AWD', 'WO') THEN 'CLOSED'
                    WHEN p.kickoff_at <= CURRENT_TIMESTAMP
                         OR p.provider_status IN (
                             '1H', 'HT', '2H', 'ET', 'BT', 'P', 'SUSP', 'INT', 'LIVE'
                         )
                    THEN 'LIVE'
                    ELSE 'PREMATCH'
                END AS dashboard_phase,
                p.bookmaker_name AS bookmaker_key,
                lower(p.source_universe) AS source,
                p.model_probability,
                (1 / p.odds)::numeric AS implied_probability,
                p.market_probability AS devig_probability,
                p.edge, p.expected_value,
                p.source_model_version AS model_version_id,
                p.source_model_name AS prediction_method_version,
                p.intake_contract_version AS config_fingerprint,
                p.source_policy_version AS eligibility_policy_version,
                NULL::text AS risk_policy_version,
                NULL::text AS staking_policy_version,
                FALSE AS stale_quote,
                CASE
                    WHEN p.source_quote_observed_at IS NULL THEN NULL
                    ELSE EXTRACT(EPOCH FROM (
                        p.source_decision_at - p.source_quote_observed_at
                    ))::bigint
                END AS quote_age_seconds,
                ARRAY[]::text[] AS warning_codes,
                'PENDING'::text AS monitoring_state,
                p.source_outcome AS settlement_outcome,
                CASE p.source_outcome
                    WHEN 'WIN' THEN ROUND(p.stake_minor * p.odds)::bigint
                    WHEN 'LOSS' THEN 0::bigint
                    WHEN 'VOID' THEN p.stake_minor
                    ELSE NULL::bigint
                END AS gross_return_minor,
                CASE p.source_outcome
                    WHEN 'WIN' THEN ROUND(p.stake_minor * (p.odds - 1))::bigint
                    WHEN 'LOSS' THEN -p.stake_minor
                    WHEN 'VOID' THEN 0::bigint
                    ELSE NULL::bigint
                END AS realized_pnl_minor,
                p.source_settled_at AS settled_at,
                p.source_home_goals AS result_home_goals,
                p.source_away_goals AS result_away_goals,
                NULL::bigint AS clv_ppm,
                NULL::text AS clv_method_version,
                COALESCE(operator_state.state, 'PENDING') AS operator_state,
                p.source_universe, p.source_pick_id, p.matched_bucket_ids,
                p.bucket_priority, p.intake_contract_version
            FROM source_status p
            LEFT JOIN latest_operator operator_state ON operator_state.pick_id = p.pick_id
            ORDER BY p.cloned_at DESC, p.pick_id DESC
        """
        with self._application.runtime.connect() as connection, connection.cursor() as cursor:
            cursor.execute(sql)
            columns = [item.name for item in cursor.description]
            rows = cursor.fetchall()
        return [dict(zip(columns, row, strict=True)) for row in rows]

    def set_operator_state(self, pick_id: str, state: str, request_id: str) -> dict[str, Any]:
        policy = _policy(self._application)
        event = self._application.operator_picks.set_state(
            pick_id,
            OperatorPickState(state),
            request_id,
            occurred_at=datetime.now(UTC),
            max_open_exposure_minor=policy.max_open_exposure_minor,
        )
        self._invalidate_snapshot()
        return {
            "event_id": event.event_id,
            "pick_id": event.pick_id,
            "state": event.state.value,
            "occurred_at": event.occurred_at.isoformat(),
            "request_id": event.request_id,
        }

    def _operations(self, generated_at: datetime) -> dict[str, Any]:
        statuses, counts = self._application.runtime.readiness_snapshot()
        workers = []
        for status in statuses:
            item = asdict(status)
            item["stale"] = bool(
                status.next_due_at
                and generated_at > status.next_due_at + timedelta(seconds=WORKER_FRESHNESS_SECONDS)
            )
            workers.append(item)
        last_success = max(
            (item["last_success_at"] for item in workers if item["last_success_at"]),
            default=None,
        )
        by_name = {item["worker_name"]: item for item in workers}
        discovery = by_name.get("discovery", {})
        ingestion_candidates = [
            item.get("last_success_at")
            for name, item in by_name.items()
            if name in {"opportunity", "monitoring", "closing_proxy"}
        ]
        last_ingestion = max((value for value in ingestion_candidates if value), default=None)
        return {
            "database_reachable": True,
            "workers": workers,
            "last_engine_refresh": last_success,
            "last_discovery": discovery.get("last_success_at"),
            "last_odds_ingestion": last_ingestion,
            "recent_failures": counts.get("retry", 0),
            "stale_workers": [item["worker_name"] for item in workers if item["stale"]],
            "counts": counts,
        }

    @staticmethod
    def _money(minor: int | None, currency: str | None) -> str:
        if minor is None:
            return "—"
        amount = Decimal(minor) / Decimal(100)
        return f"{amount:,.2f} {currency or ''}".replace(",", " ")

    @staticmethod
    def _pct(value: float | Decimal | None) -> str:
        return "—" if value is None else f"{Decimal(str(value)) * 100:.2f}%"

    @staticmethod
    def _odd(value: float | Decimal | None) -> str:
        return "—" if value is None else f"{Decimal(str(value)):.2f}"

    @staticmethod
    def _dt(value: datetime | None) -> str:
        return local_time(value, "%d %b %Y · %H:%M Belgrade")

    @staticmethod
    def _checkpoint_time(value: datetime | None) -> str:
        return local_time(value, "%d %b %H:%M")

    @staticmethod
    def _relative_age(value: datetime | None, reference: datetime) -> str:
        if value is None:
            return "—"
        seconds = max(0, int((reference.astimezone(UTC) - value.astimezone(UTC)).total_seconds()))
        if seconds < 60:
            return "just now"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes}min ago"
        hours, minutes = divmod(minutes, 60)
        if hours < 24:
            return f"{hours}h {minutes}mins ago" if minutes else f"{hours}h ago"
        days, hours = divmod(hours, 24)
        return f"{days}d {hours}h ago" if hours else f"{days}d ago"

    @staticmethod
    def _short_id(value: Any) -> str:
        text = str(value or "")
        return text[-10:] if len(text) > 10 else text or "—"

    @staticmethod
    def _status(pick: dict[str, Any]) -> tuple[str, str]:
        outcome = pick.get("settlement_outcome")
        if outcome:
            return str(outcome), str(outcome).lower()
        state = pick.get("monitoring_state") or "REGISTERED"
        return str(state).replace("_", " "), "active"

    @staticmethod
    def _quality_summary(
        pick: dict[str, Any],
    ) -> tuple[tuple[str, str, str], tuple[str, ...], str]:
        """Prefer fixture lifecycle after kickoff and quote freshness before kickoff."""
        phase = str(pick.get("dashboard_phase") or "PREMATCH").upper()
        source_universe = str(pick.get("source_universe") or "").upper()
        if phase == "PREMATCH" and source_universe:
            bucket_text = ", ".join(str(item) for item in (pick.get("matched_bucket_ids") or ()))
            primary = (
                source_universe,
                "fresh",
                "Cloned by the Production funnel from: " + (bucket_text or source_universe),
            )
        elif phase == "SETTLED":
            primary = ("SETTLED", "fresh", "Result and settlement are durable")
        elif phase == "FINISHED":
            primary = ("FINISHED", "fresh", "Fixture is finished; settlement may still be pending")
        elif phase == "CLOSED":
            primary = ("CLOSED", "unavailable", "Fixture ended without a normal final result")
        elif phase == "LIVE":
            primary = ("LIVE", "active", "Fixture has started")
        else:
            freshness = str(pick.get("last_observed_freshness") or "UNAVAILABLE").upper()
            if freshness == "FRESH":
                primary = ("FRESH", "fresh", "Latest pre-match observation is fresh")
            elif freshness == "STALE":
                primary = ("STALE", "stale", "Latest pre-match observation is stale")
            else:
                primary = ("UNAVAILABLE", "unavailable", "No pre-match observation is available")

        history: list[str] = []
        history_titles: list[str] = []
        if phase == "PREMATCH":
            warning_codes = [str(value) for value in (pick.get("warning_codes") or ())]
            if pick.get("stale_quote") or "STALE_QUOTE_WARNING" in warning_codes:
                history.append("Entry stale")
                history_titles.append("Registration-time final quote verification was stale")
            other_entry_warnings = [
                warning for warning in warning_codes if warning != "STALE_QUOTE_WARNING"
            ]
            if other_entry_warnings:
                history.append("Entry warning")
                history_titles.append(
                    "Registration warnings: " + ", ".join(other_entry_warnings)
                )
        else:
            closing_source = str(pick.get("display_closing_source") or "UNAVAILABLE").upper()
            if closing_source == "MANUAL":
                history.append("Manual close")
                history_titles.append("Operator-confirmed closing equals the last observed quote")
            elif closing_source == "LIVE_PROXY":
                history.append("Proxy close")
                history_titles.append("Closing uses the API-Football live-market proxy")
            elif closing_source == "UNAVAILABLE":
                history.append("No close")
                history_titles.append("No closing quote is available")

        return primary, tuple(dict.fromkeys(history)), " · ".join(history_titles)

    @staticmethod
    def _country_flag(country: Any) -> str:
        key = " ".join(str(country or "").replace("-", " ").split()).casefold()
        code = _COUNTRY_FLAG_CODES.get(key)
        if code is None or len(code) != 2 or not code.isalpha():
            return ""
        return "".join(chr(0x1F1E6 + ord(letter) - ord("A")) for letter in code.upper())

    def _league_meta(self, pick: dict[str, Any], *, countdown: bool = False) -> str:
        country = str(pick.get("country") or "")
        flag = self._country_flag(country)
        flag_html = (
            f'<span class="country-flag" title="{escape(country)}" '
            f'aria-label="{escape(country)}">{flag}</span>'
            if flag
            else ""
        )
        league = escape(str(pick.get("competition_name") or "—"))
        kickoff = escape(self._dt(pick.get("kickoff_at")))
        return (
            '<small class="league-meta">'
            f"{flag_html}<span>{league} · {kickoff}"
            f"{kickoff_countdown(pick.get('kickoff_at')) if countdown else ''}</span>"
            "</small>"
        )

    @staticmethod
    def _bookmaker_badge(bookmaker: Any) -> str:
        key = str(bookmaker or "").casefold()
        name = {
            "bet365": "Bet365",
            "1xbet": "1xBet",
            "superbet": "Superbet",
        }.get(key, str(bookmaker or "Unavailable"))
        if key == "bet365":
            mark = '<span class="brand-bet365"><b>bet</b><strong>365</strong></span>'
        elif key == "1xbet":
            mark = '<span class="brand-1xbet"><b>1X</b><strong>BET</strong></span>'
        elif key == "superbet":
            mark = '<span class="brand-superbet"><b>SUPER</b><strong>BET</strong></span>'
        else:
            mark = f'<span class="brand-generic">{escape(name)}</span>'
        return (
            f'<span class="bookmaker-mark bookmaker-{escape(key)}" '
            f'aria-label="{escape(name)}" title="{escape(name)}" '
            f'data-bookmaker="{escape(key)}">{mark}</span>'
        )

    @staticmethod
    def _is_history_pick(pick: dict[str, Any]) -> bool:
        return str(pick.get("dashboard_phase") or "").upper() in {
            "FINISHED",
            "CLOSED",
            "SETTLED",
        }

    @staticmethod
    def _clv_summary(pick: dict[str, Any]) -> tuple[str, str, str, str]:
        if pick.get("clv_ppm") is not None:
            source = "SAME-BOOK"
            value = Decimal(pick["clv_ppm"]) / Decimal(10000)
        elif pick.get("manual_clv_ppm") is not None:
            source = "MANUAL"
            value = Decimal(pick["manual_clv_ppm"]) / Decimal(10000)
        elif pick.get("proxy_clv_ppm") is not None:
            source = "LIVE PROXY"
            value = Decimal(pick["proxy_clv_ppm"]) / Decimal(10000)
        else:
            return "—", "unavailable", "NO CLV", "UNAVAILABLE"

        if value > 0:
            css, verdict = "good", "GOOD"
        elif value < 0:
            css, verdict = "bad", "BAD"
        else:
            css, verdict = "flat", "FLAT"
        return f"{value:+.2f}%", css, verdict, source

    def _render_history_row(self, pick: dict[str, Any], currency: str) -> str:
        fixture = f"{pick.get('home_team') or '—'} – {pick.get('away_team') or '—'}"
        outcome = str(pick.get("settlement_outcome") or "").upper()
        if outcome:
            status = outcome
        else:
            status = str(pick.get("dashboard_phase") or "FINISHED").upper()

        result_home = pick.get("result_home_goals")
        result_away = pick.get("result_away_goals")
        final_score = (
            f"{result_home} – {result_away}"
            if result_home is not None and result_away is not None
            else "—"
        )
        pick_market = str(pick.get("market") or "—")
        pick_selection = str(pick.get("selection") or "—")
        outcome_tile_class = (
            "win" if status == "WIN"
            else "loss" if status == "LOSS"
            else "void" if status == "VOID"
            else "pending"
        )

        clv, clv_css, clv_verdict, clv_source = self._clv_summary(pick)
        operator_state = str(pick.get("operator_state") or "PENDING")
        action = f"/api/picks/{quote(str(pick.get('pick_id') or ''), safe='')}/operator-state"
        operator_control = (
            '<div class="history-operator-actions">'
            f'<form class="history-operator-form" method="post" action="{action}">'
            f'<input type="hidden" name="request_id" value="dashboard:{uuid4().hex}">'
            f'<button name="state" value="PLAYED" class="history-operator-button played"'
            f'{" disabled" if operator_state == "PLAYED" else ""}>PLAYED</button></form>'
            f'<form class="history-operator-form" method="post" action="{action}">'
            f'<input type="hidden" name="request_id" value="dashboard:{uuid4().hex}">'
            f'<button name="state" value="SKIPPED" class="history-operator-button skipped"'
            f'{" disabled" if operator_state == "SKIPPED" else ""}>SKIPPED</button></form>'
            '</div>'
        )
        closing_source = str(pick.get("display_closing_source") or "UNAVAILABLE").upper()
        close_source = {
            "SAME_BOOK": "same-book",
            "MANUAL": "manual",
            "LIVE_PROXY": "live proxy",
        }.get(closing_source, "unavailable")
        return (
            '<tr class="history-row">'
            f'<td class="history-operator-cell"><div class="operator-panel history-panel">'
            f'<div class="operator-panel-head"><span class="operator-label">Decision</span>'
            f'<span class="status operator-{operator_state.casefold()}">{escape(operator_state)}</span></div>'
            f"{operator_control}</div></td>"
            f'<td class="history-outcome-cell"><div class="outcome-tile {outcome_tile_class}">'
            f'<div class="outcome-top"><span class="outcome-state">{escape(status)}</span>'
            f'<strong class="outcome-score">{escape(final_score)}</strong></div>'
            f'<div class="outcome-pick"><span>{escape(pick_market)}</span>'
            f'<strong>{escape(pick_selection)}</strong></div>'
            f'<small>{escape(self._dt(pick.get("settled_at")))}</small></div></td>'
            f'<td class="history-fixture"><strong>{escape(fixture)}</strong>'
            f"{self._league_meta(pick)}"
            f"{_production_bucket_links_html(pick.get('matched_bucket_ids'))}</td>"
            f'<td class="num history-odds"><strong>{self._odd(pick.get("pick_odd"))}'
            f" → {self._odd(pick.get('display_closing_odd'))}</strong>"
            f"<small>Pick → Closing · {escape(close_source)}</small>"
            f"<small>Last observed · {escape(self._dt(pick.get('last_observed_at')))}</small></td>"
            f'<td class="num history-probability"><strong>Model {escape(self._pct(pick.get("model_probability")))}</strong>'
            f"<small>Market fair {escape(self._pct(pick.get('devig_probability')))}</small></td>"
            f'<td class="num history-clv {escape(clv_css)}"><strong>{escape(clv)}</strong>'
            f"<small>{escape(clv_verdict)} · {escape(clv_source)}</small></td>"
            f'<td class="num"><strong>{escape(self._money(pick.get("realized_pnl_minor"), currency))}'
            "</strong></td>"
            "</tr>"
        )

    def _render_pick_row(
        self, pick: dict[str, Any], currency: str, *, generated_at: datetime
    ) -> str:
        fixture = f"{pick.get('home_team') or '—'} – {pick.get('away_team') or '—'}"
        status, status_class = self._status(pick)
        quality_live, quality_history, quality_history_title = self._quality_summary(pick)
        quality_label, quality_css, quality_title = quality_live
        history_html = (
            f'<small class="quality-history" title="{escape(quality_history_title)}">'
            f"{escape(' · '.join(quality_history))}</small>"
            if quality_history
            else ""
        )
        quality_html = (
            '<div class="quality-summary">'
            f'<span class="quality-badge {escape(quality_css)}" title="{escape(quality_title)}">'
            f"{escape(quality_label)}</span>"
            f"{history_html}</div>"
        )
        if pick.get("clv_ppm") is not None:
            clv_label = "CLV"
            clv = f"{Decimal(pick['clv_ppm']) / Decimal(10000):+.2f}%"
        elif pick.get("manual_clv_ppm") is not None:
            clv_label = "Manual CLV"
            clv = f"{Decimal(pick['manual_clv_ppm']) / Decimal(10000):+.2f}%"
        elif pick.get("proxy_clv_ppm") is not None:
            clv_label = "Proxy CLV"
            clv = f"{Decimal(pick['proxy_clv_ppm']) / Decimal(10000):+.2f}%"
        else:
            clv_label = "CLV"
            clv = "—"
        provenance = " · ".join(
            filter(
                None,
                [
                    str(pick.get("source_universe") or ""),
                    str(pick.get("source_pick_id") or ""),
                    ", ".join(str(item) for item in (pick.get("matched_bucket_ids") or ())),
                    str(pick.get("model_version_id") or ""),
                    str(pick.get("config_fingerprint") or ""),
                    str(pick.get("prediction_method_version") or ""),
                    str(pick.get("eligibility_policy_version") or ""),
                    str(pick.get("risk_policy_version") or ""),
                    str(pick.get("staking_policy_version") or ""),
                ],
            )
        )
        registered_key = str(pick.get("bookmaker_key") or "").casefold()
        registered_bookmaker = self._bookmaker_badge(registered_key)
        last_source = str(pick.get("last_observed_source") or "UNAVAILABLE").upper()
        closing_source = str(pick.get("display_closing_source") or "UNAVAILABLE").upper()
        last_meta = (
            '<small class="source-label">LIVE PROXY</small>'
            if last_source == "LIVE_PROXY"
            else ""
        )
        closing_meta = {
            "MANUAL": '<small class="source-label manual">MANUAL</small>',
            "LIVE_PROXY": '<small class="source-label">LIVE PROXY</small>',
        }.get(closing_source, "")
        operator_state = str(pick.get("operator_state") or "PENDING")
        action = f"/api/picks/{quote(str(pick.get('pick_id') or ''), safe='')}/operator-state"
        operator_controls = "".join(
            f'<form method="post" action="{action}">'
            f'<input type="hidden" name="request_id" value="dashboard:{uuid4().hex}">'
            f'<button name="state" value="{candidate}" '
            f'class="operator-button {candidate.casefold()}" '
            f"{'disabled' if candidate == operator_state else ''}>{candidate.title()}</button>"
            "</form>"
            for candidate in ("PLAYED", "SKIPPED")
        )
        odds = (
            '<div class="odds-grid">'
            f'<span title="{escape(self._dt(pick.get("first_seen_observed_at")))}">'
            f"<b>First seen</b>{self._odd(pick.get('first_seen_odd'))}</span>"
            f'<span title="{escape(self._dt(pick.get("pick_observed_at")))}">'
            f"<b>Pick</b>{self._odd(pick.get('pick_odd'))}</span>"
            f'<span title="{escape(self._dt(pick.get("last_observed_at")))}">'
            f"<b>Last observed</b>{self._odd(pick.get('last_observed_odd'))}"
            f"{last_meta}"
            f'<small class="quote-age">'
            f"{escape(self._relative_age(pick.get('last_observed_at'), generated_at))}</small>"
            f'<small class="check-age">checked '
            f"{escape(self._relative_age(pick.get('last_checked_at'), generated_at))}</small></span>"
            f'<span title="{escape(self._dt(pick.get("display_closing_observed_at")))}">'
            f"<b>Closing</b>{self._odd(pick.get('display_closing_odd'))}"
            f"{closing_meta}</span>"
            "</div>"
        )
        checkpoint_times = " · ".join(
            [
                f"F {self._checkpoint_time(pick.get('first_seen_observed_at'))}",
                f"P {self._checkpoint_time(pick.get('pick_observed_at'))}",
                f"L {self._checkpoint_time(pick.get('last_observed_at'))}",
                f"X {self._checkpoint_time(pick.get('display_closing_observed_at'))}",
            ]
        )
        return (
            f'<tr data-provenance="{escape(provenance)}">'
            f'<td><code title="{escape(str(pick.get("pick_id") or ""))}">'
            f"{escape(self._short_id(pick.get('pick_id')))}</code></td>"
            f'<td class="operator-cell"><div class="operator-panel">'
            f'<div class="operator-panel-head"><span class="operator-label">Decision</span>'
            f'<span class="status operator-{operator_state.casefold()}">{escape(operator_state)}</span></div>'
            f'<div class="operator-controls">{operator_controls}</div>'
            f'<small class="operator-hint">Confirm whether this pick was actually placed.</small>'
            f'</div></td>'
            f'<td class="fixture"><strong>{escape(fixture)}</strong>'
            f"{self._league_meta(pick, countdown=str(pick.get('dashboard_phase') or 'PREMATCH').upper() == 'PREMATCH')}"
            f'<small class="quality-history">{escape(str(pick.get("source_universe") or "SOURCE"))}</small>'
            f"{_production_bucket_links_html(pick.get('matched_bucket_ids'))}"
            f'<span class="pick-book" title="Source bookmaker">{registered_bookmaker}</span></td>'
            f'<td><span class="market">{escape(str(pick.get("market") or "—"))}</span>'
            f"<strong>{escape(str(pick.get('selection') or '—'))}</strong></td>"
            f'<td>{odds}<small class="timestamps">{escape(checkpoint_times)}</small></td>'
            f'<td class="num"><strong>{self._pct(pick.get("model_probability"))}</strong>'
            f"<small>implied {self._pct(pick.get('implied_probability'))} · "
            f"de-vig {self._pct(pick.get('devig_probability'))}</small></td>"
            f'<td class="num value"><strong>{self._pct(pick.get("edge"))}</strong>'
            f"<small>EV {self._pct(pick.get('expected_value'))}</small></td>"
            f'<td class="num"><strong>{escape(self._money(pick.get("stake_minor"), currency))}'
            f"</strong><small>System P/L {escape(self._money(pick.get('realized_pnl_minor'), currency))}"
            f" · {escape(clv_label)} {escape(clv)}</small></td>"
            f'<td><span class="status {escape(status_class)}">{escape(status)}</span>'
            f"<small>{escape(self._dt(pick.get('settled_at')))}</small></td>"
            f"<td>{quality_html}</td>"
            "</tr>"
        )

    def render_html(self) -> str:
        data = self.snapshot()
        bankroll = data["bankroll"]
        ops = data["operations"]
        currency = bankroll["currency"]
        history_picks = [
            pick for pick in data["picks"] if self._is_history_pick(pick)
        ]
        active_picks = [
            pick for pick in data["picks"] if not self._is_history_pick(pick)
        ]
        active_rows = "".join(
            self._render_pick_row(pick, currency, generated_at=data["generated_at"])
            for pick in active_picks
        )
        if not active_rows:
            active_rows = (
                '<tr><td class="empty" colspan="10"><strong>No active picks.</strong>'
                "<br>Pre-match and live picks will appear here.</td></tr>"
            )
        history_rows = "".join(
            self._render_history_row(pick, currency) for pick in history_picks
        )
        if not history_rows:
            history_rows = (
                '<tr><td class="empty" colspan="7"><strong>No finished picks yet.</strong>'
                "<br>Finished and settled picks will move here automatically.</td></tr>"
            )
        worker_rows = (
            "".join(
                "<tr>"
                f"<td><strong>{escape(item['worker_name'])}</strong></td>"
                f'<td><span class="status {"lost" if item["stale"] else "win"}">'
                f"{'STALE' if item['stale'] else 'CURRENT'}</span></td>"
                f"<td>{escape(self._dt(item['last_success_at']))}</td>"
                f"<td>{item['consecutive_failures']}</td>"
                "</tr>"
                for item in ops["workers"]
            )
            or '<tr><td colspan="4" class="empty">No worker heartbeat records.</td></tr>'
        )
        return self._document(
            active_rows=active_rows,
            history_rows=history_rows,
            history_count=len(history_picks),
            worker_rows=worker_rows,
            bankroll=bankroll,
            counts=data["counts"],
            budget=data["provider_budget"],
            ops=ops,
            generated_at=data["generated_at"],
        )

    def _document(self, **context: Any) -> str:
        bankroll = context["bankroll"]
        counts = context["counts"]
        budget = context["budget"]
        ops = context["ops"]
        currency = bankroll["currency"]
        realized_pnl_minor = bankroll["realized_pnl_minor"]
        pnl_css = (
            "pnl-positive"
            if realized_pnl_minor > 0
            else "pnl-negative"
            if realized_pnl_minor < 0
            else "pnl-zero"
        )
        cards = [
            ("Current bankroll", self._money(bankroll["available_minor"], currency), "primary"),
            ("Initial bankroll", self._money(bankroll["initial_minor"], currency), ""),
            (
                "Risk exposure / cap",
                (
                    f"{self._money(bankroll['risk_exposure_minor'], currency)} / "
                    f"{self._money(bankroll['max_open_exposure_minor'], currency)}"
                ),
                "warn",
            ),
            ("Realized P/L", self._money(realized_pnl_minor, currency), pnl_css),
            ("Total staked", self._money(bankroll["total_staked_minor"], currency), ""),
            ("Settled stakes", self._money(bankroll["settled_stake_minor"], currency), ""),
            ("Gross returns", self._money(bankroll["gross_returns_minor"], currency), ""),
            ("Pending", self._money(bankroll["pending_minor"], currency), "warn"),
        ]
        cards_html = "".join(
            f'<article class="kpi {css}"><span>{escape(label)}</span><strong>{escape(value)}</strong>'
            "</article>"
            for label, value, css in cards
        )
        stale = ", ".join(ops["stale_workers"]) or "None"
        return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>QuantBet · Operations</title>
<style>
:root{{--bg:#07121d;--panel:#0d1a28;--panel2:#13263a;--line:#25445d;--text:#f3f8fb;
--muted:#8fa7b8;--blue:#55b8ff;--cyan:#71cfff;--yellow:#ffd31a;--green:#45d58b;--red:#fb7185;--amber:#ffd05a}}
*{{box-sizing:border-box}}body{{margin:0;background:
radial-gradient(circle at 78% -10%,rgba(53,146,224,.18),transparent 33%),
linear-gradient(180deg,#0b1d2d 0,#07121d 280px,var(--bg) 100%);color:var(--text);font:13px/1.45
Inter,ui-sans-serif,system-ui,-apple-system,sans-serif}}.shell{{max-width:1800px;margin:auto;padding:26px 24px 34px}}
header{{position:relative;display:flex;align-items:end;justify-content:space-between;gap:20px;margin-bottom:20px;padding:4px 0 16px;border-bottom:1px solid #1f3c54}}
header:before{{content:"";position:absolute;left:0;bottom:-1px;width:150px;height:2px;background:linear-gradient(90deg,var(--yellow),var(--blue),transparent)}}
.eyebrow,.section-label{{color:#71cfff;font-size:10px;font-weight:900;letter-spacing:.16em;text-transform:uppercase}}
h1{{font-size:29px;letter-spacing:-.035em;margin:3px 0 2px;font-weight:850}}.subtitle{{color:var(--muted);font-size:12px}}
.live{{display:flex;align-items:center;gap:8px;color:#a9c3d5;font-size:11px;padding:7px 10px;border:1px solid #244a66;background:#0a1a28;border-radius:999px}}.dot{{width:8px;height:8px;border-radius:50%;background:var(--green);box-shadow:0 0 0 3px rgba(69,213,139,.09)}}
.kpis{{display:grid;grid-template-columns:repeat(8,minmax(140px,1fr));gap:9px;margin-bottom:12px}}
.kpi{{background:var(--panel);border:1px solid var(--line);padding:13px 14px;min-height:76px}}
.kpi span{{display:block;color:var(--muted);font-size:11px;margin-bottom:8px}}.kpi strong{{font-size:17px;font-variant-numeric:tabular-nums}}
.kpi.primary{{border-top:2px solid var(--blue)}}.kpi.value strong,.value strong{{color:var(--green)}}.kpi.warn strong{{color:var(--amber)}}
.kpi.pnl-positive strong{{color:var(--green)}}.kpi.pnl-negative strong{{color:var(--red)}}.kpi.pnl-zero strong{{color:var(--muted)}}
.overview{{display:grid;grid-template-columns:2fr 1fr;gap:12px;margin-bottom:12px}}.panel{{background:linear-gradient(180deg,#102238 0,var(--panel) 100%);border:1px solid var(--line);border-radius:12px;overflow:hidden;box-shadow:0 10px 30px rgba(0,0,0,.14)}}
.overview .panel:first-child{{display:flex;flex-direction:column}}
.panel-head{{display:flex;align-items:center;justify-content:space-between;padding:13px 15px;border-bottom:1px solid #264861;background:linear-gradient(90deg,rgba(85,184,255,.08),rgba(255,211,26,.025) 34%,transparent 58%)}}
.panel-head h2:before{{content:"";display:inline-block;width:4px;height:13px;margin-right:8px;border-radius:3px;background:var(--yellow);vertical-align:-2px}}h2{{font-size:14px;margin:0;letter-spacing:-.01em}}
.scoreboard{{display:grid;grid-template-columns:repeat(8,1fr);padding:14px;flex:1;align-items:center}}.score{{padding:0 14px;border-right:1px solid var(--line)}}
.score:last-child{{border:0}}.score span{{display:block;color:var(--muted)}}.score strong{{font-size:22px;font-variant-numeric:tabular-nums}}
.won{{color:var(--green)}}.lost{{color:var(--red)}}.ops{{display:grid;grid-template-columns:1fr 1fr;gap:10px;padding:14px}}
.fact{{background:#102235;padding:10px;border:1px solid #23445e;border-radius:8px}}.fact span{{display:block;color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.06em}}.fact strong{{display:block;margin-top:5px;font-size:12px}}
.table-wrap{{overflow:auto}}table{{border-collapse:separate;border-spacing:0;width:100%;min-width:1680px}}th,td{{padding:11px 12px;border-bottom:1px solid #233033;text-align:left;vertical-align:middle}}
th{{background:#10253a;color:#93adbe;font-size:9px;letter-spacing:.1em;text-transform:uppercase;position:sticky;top:0;z-index:1;border-bottom-color:#2a506d}}
tbody tr{{transition:background .12s ease}}tbody tr:hover{{background:#102941}}td small{{display:block;color:var(--muted);margin-top:4px}}.fixture{{min-width:250px}}.fixture strong{{font-size:14px;letter-spacing:-.01em}}
.league-meta{{display:flex;align-items:center;gap:5px}}.country-flag{{display:inline-flex;font-size:11px;line-height:1;flex:0 0 auto}}.kickoff-countdown{{display:block;color:var(--amber)!important;font-weight:700;margin-top:3px!important}}
.market{{display:block;color:var(--muted);font-size:10px}}.num{{text-align:right;font-variant-numeric:tabular-nums}}
.odds-grid{{display:grid;grid-template-columns:repeat(4,minmax(108px,1fr));gap:7px;font-variant-numeric:tabular-nums;min-width:455px}}
.odds-grid>span{{background:#10253a;padding:9px 8px;text-align:center;min-height:68px;display:flex;flex-direction:column;align-items:center;justify-content:flex-start;border:1px solid #264b66;border-radius:8px}}
.odds-grid>span>b{{display:block;color:#91aabd;font-size:8px;text-transform:uppercase;letter-spacing:.07em;margin-bottom:2px}}
.quote-age{{font-size:7px;line-height:1.1;margin-top:3px;color:#dfff63;font-weight:600}}
.check-age{{font-size:7px!important;line-height:1.1;margin-top:2px!important;color:var(--muted)!important;font-weight:500}}
.pick-book{{display:flex;align-items:center;margin-top:8px;width:max-content}}
.bookmaker-mark{{display:inline-flex;align-items:center;justify-content:center;min-height:24px;border-radius:6px;font-size:10px;font-weight:900;letter-spacing:-.02em;line-height:1;white-space:nowrap;overflow:hidden}}
.brand-bet365{{display:inline-flex;align-items:baseline;gap:1px;background:#087a4b;padding:6px 8px;border-radius:6px}}
.brand-bet365 b{{color:#fff;font-size:11px}}.brand-bet365 strong{{color:#f4ea24;font-size:11px}}
.brand-1xbet{{display:inline-flex;align-items:baseline;gap:1px;background:#fff;padding:6px 8px;border-radius:6px}}
.brand-1xbet b{{color:#1689d4;font-size:11px}}.brand-1xbet strong{{color:#184b91;font-size:11px}}
.brand-superbet{{display:inline-flex;align-items:baseline;gap:1px;background:#e52333;padding:6px 8px;border-radius:6px}}
.brand-superbet b,.brand-superbet strong{{color:#fff;font-size:9px}}
.brand-generic{{display:inline-flex;background:#1b2637;color:var(--text);border:1px solid var(--line);padding:6px 8px;border-radius:6px}}
.sr-only{{position:absolute!important;width:1px;height:1px;padding:0!important;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}}
.status,.quality-badge{{display:inline-block;border:1px solid var(--line);padding:3px 6px;font-size:9px;font-weight:800;letter-spacing:.05em}}
.status.win{{color:var(--green);border-color:#1f6a51}}.status.loss,.status.lost{{color:var(--red);border-color:#6f2c3a}}
.status.void{{color:var(--muted)}}.status.active{{color:#8ab4ff;border-color:#35578c}}
.quality-summary{{display:flex;flex-direction:column;align-items:flex-start;gap:3px;min-width:104px}}
.quality-badge.fresh{{color:var(--green);border-color:#1f6a51}}
.quality-badge.stale{{color:var(--amber);border-color:#6c5425}}
.quality-badge.active{{color:#8ab4ff;border-color:#35578c}}
.quality-badge.unavailable{{color:var(--muted)}}
.quality-history{{margin:0!important;color:var(--muted)!important;font-size:8px!important;line-height:1.3}}
.production-bucket-links{{display:flex;flex-wrap:wrap;gap:4px 7px;margin-top:5px}}
.production-bucket-link{{display:inline-flex;align-items:center;width:max-content;padding:2px 5px;border:1px solid #18d7ff;border-radius:999px;color:#7eeaff!important;background:rgba(24,215,255,.07);font-size:8px;font-weight:850;text-decoration:none;box-shadow:0 0 9px rgba(24,215,255,.10)}}
.production-bucket-link:hover{{color:#e4fbff!important;background:rgba(24,215,255,.16);box-shadow:0 0 12px rgba(24,215,255,.24)}}
.production-bucket-link.unknown{{border-color:#47556a;color:var(--muted)!important;box-shadow:none}}
.source-label{{margin-top:auto!important;padding-top:4px;font-size:7px!important;letter-spacing:.05em;color:#a9c5ff!important}}
.source-label.manual{{color:var(--amber)!important}}
.operator-pending{{color:#b7c2d3;border-color:#47556a;background:#182130}}.operator-played{{color:#9ef2ce;border-color:#2f8c6c;background:#123629}}.operator-skipped{{color:#ffd989;border-color:#8b6a2f;background:#3a2c12}}
.operator-cell{{min-width:176px;width:176px;padding:9px!important}}.operator-panel{{background:linear-gradient(180deg,#161f2d 0%,#111823 100%);border:1px solid #2d3b50;border-radius:10px;padding:10px;box-shadow:0 10px 24px rgba(0,0,0,.18),0 1px 0 rgba(255,255,255,.035) inset}}.operator-panel-head{{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:8px}}.operator-label{{color:#a9b6c8;font-size:9px;font-weight:800;letter-spacing:.11em;text-transform:uppercase}}.operator-hint{{font-size:8px!important;line-height:1.3;margin:8px 1px 0!important;color:#718097!important}}.operator-controls{{display:flex;flex-direction:column;gap:8px}}.operator-controls form{{margin:0;width:100%}}.operator-button{{position:relative;width:100%;border:0;border-radius:7px;padding:10px 12px;cursor:pointer;font:inherit;font-size:10px;font-weight:900;letter-spacing:.055em;transition:transform .12s ease,box-shadow .12s ease,filter .12s ease,background .12s ease;box-shadow:0 4px 10px rgba(0,0,0,.18),0 1px 0 rgba(255,255,255,.10) inset}}.operator-button.played{{background:linear-gradient(180deg,#2f9b73 0%,#247a5c 100%);color:#f5fffb}}.operator-button.skipped{{background:linear-gradient(180deg,#735f36 0%,#5a492a 100%);color:#fff7e6}}.operator-button:hover:not(:disabled){{filter:brightness(1.08);transform:translateY(-1px);box-shadow:0 7px 16px rgba(0,0,0,.24),0 1px 0 rgba(255,255,255,.12) inset}}.operator-button:active:not(:disabled){{transform:translateY(1px);box-shadow:0 2px 6px rgba(0,0,0,.22) inset}}.operator-button:focus-visible{{outline:2px solid #76a9ff;outline-offset:2px}}.operator-button:disabled{{opacity:.42;cursor:default;filter:saturate(.55);box-shadow:none}}
.timestamps{{font-size:9px}}code{{color:#a9c5ff}}.muted{{color:var(--muted)}}
.glossary{{margin-top:12px;padding:15px}}.glossary dl{{display:grid;grid-template-columns:180px 1fr;gap:8px 18px;margin:12px 0 0}}.glossary dt{{font-weight:800}}.glossary dd{{margin:0;color:var(--muted)}}
.empty{{text-align:center!important;color:var(--muted);padding:36px!important}}footer{{display:flex;justify-content:space-between;gap:12px;color:var(--muted);font-size:11px;padding:16px 2px}}
.workers table{{min-width:0}}.workers th,.workers td{{padding:8px 10px}}
.history{{margin-top:12px}}.history table{{min-width:1280px}}.history th,.history td{{padding:11px 14px}}
.history-outcome-cell{{min-width:190px;width:190px;padding:9px!important}}.outcome-tile{{border:1px solid #334157;border-radius:10px;padding:11px 12px;background:linear-gradient(180deg,#17202d 0%,#111822 100%);box-shadow:0 8px 20px rgba(0,0,0,.16),0 1px 0 rgba(255,255,255,.035) inset}}.outcome-tile.win{{border-color:#2f8769;background:linear-gradient(180deg,rgba(31,112,82,.34) 0%,rgba(15,48,37,.72) 100%)}}.outcome-tile.loss{{border-color:#9a4656;background:linear-gradient(180deg,rgba(128,45,62,.34) 0%,rgba(57,22,30,.72) 100%)}}.outcome-tile.void{{border-color:#6f7784}}.outcome-tile.pending{{border-color:#47556a}}.outcome-top{{display:flex;align-items:center;justify-content:space-between;gap:10px}}.outcome-state{{font-size:11px;font-weight:950;letter-spacing:.08em}}.outcome-tile.win .outcome-state,.outcome-tile.win .outcome-score{{color:#83ebbd}}.outcome-tile.loss .outcome-state,.outcome-tile.loss .outcome-score{{color:#ff93a4}}.outcome-tile.void .outcome-state,.outcome-tile.pending .outcome-state{{color:#c0c9d6}}.outcome-score{{font-size:17px;font-weight:900;font-variant-numeric:tabular-nums;letter-spacing:-.02em}}.outcome-pick{{display:flex;align-items:center;justify-content:space-between;gap:8px;border-top:1px solid rgba(255,255,255,.07);margin-top:8px;padding-top:8px}}.outcome-pick span{{color:#8f9db0;font-size:9px;font-weight:800;letter-spacing:.08em}}.outcome-pick strong{{font-size:11px;color:#eef3fb}}.outcome-tile small{{font-size:8px!important;color:#718097!important;margin-top:7px!important}}
.history-operator-cell{{min-width:176px;width:176px;padding:9px!important}}.history-fixture{{min-width:310px}}.history-panel{{padding:9px}}.history-operator-actions{{display:flex;flex-direction:column;gap:8px}}
.history-operator-form{{margin:0;width:100%}}.history-operator-button{{width:100%;border:0;border-radius:7px;padding:10px 12px;cursor:pointer;font:inherit;font-size:10px;font-weight:900;letter-spacing:.055em;transition:transform .12s ease,box-shadow .12s ease,filter .12s ease;box-shadow:0 4px 10px rgba(0,0,0,.18),0 1px 0 rgba(255,255,255,.10) inset}}.history-operator-button.played{{background:linear-gradient(180deg,#2f9b73 0%,#247a5c 100%);color:#f5fffb}}.history-operator-button.skipped{{background:linear-gradient(180deg,#735f36 0%,#5a492a 100%);color:#fff7e6}}.history-operator-button:hover:not(:disabled){{filter:brightness(1.08);transform:translateY(-1px);box-shadow:0 7px 16px rgba(0,0,0,.24)}}.history-operator-button:active:not(:disabled){{transform:translateY(1px)}}.history-operator-button:focus-visible{{outline:2px solid #76a9ff;outline-offset:2px}}.history-operator-button:disabled{{opacity:.42;cursor:default;filter:saturate(.55);box-shadow:none}}
.history-odds{{min-width:210px}}.history-odds strong,.history-probability strong,.history-clv strong{{font-variant-numeric:tabular-nums}}
.history-probability{{min-width:155px}}.history-probability strong{{white-space:nowrap}}
.history-clv.good strong,.history-clv.good small{{color:var(--green)!important}}
.history-clv.bad strong,.history-clv.bad small{{color:var(--red)!important}}
.history-clv.flat strong{{color:var(--muted)}}.history-clv.unavailable strong{{color:var(--muted)}}
.history{{margin-top:12px}}.workers{{border-color:#24455f!important}}.glossary{{margin-top:12px;padding:15px 16px;background:#091724}}.glossary dl{{display:grid;grid-template-columns:170px 1fr;gap:7px 18px;margin:12px 0 0}}.glossary dt{{color:#bfd0dc;font-weight:800}}.glossary dd{{margin:0;color:#829bab}}footer{{border-top:1px solid #1d374b!important;padding-top:13px!important;color:#718b9d!important}}
@media(max-width:1150px){{.kpis{{grid-template-columns:repeat(4,1fr)}}.overview{{grid-template-columns:1fr}}}}
@media(max-width:650px){{.shell{{padding:14px}}header{{align-items:start;flex-direction:column}}.kpis{{grid-template-columns:repeat(2,1fr)}}
.scoreboard{{grid-template-columns:repeat(2,1fr);gap:14px}}.score{{border:0;padding:0}}footer{{flex-direction:column}}
.odds-grid{{grid-template-columns:repeat(4,minmax(100px,1fr));min-width:430px}}.odds-grid>span{{min-height:68px;padding:8px 6px}}.pick-book{{margin-top:7px}}}}
</style></head><body><main class="shell">
<header><div><div class="eyebrow">QuantBet / Production</div><h1>Operations Dashboard</h1>
<div class="subtitle">Read-only view of durable PostgreSQL state</div></div>
<div class="live"><span class="dot"></span>Database Connected · Generated {escape(self._dt(context["generated_at"]))}</div></header>
<section class="kpis">{cards_html}</section>
<section class="overview"><article class="panel"><div class="panel-head"><h2>Pick performance</h2><span class="section-label">All time</span></div>
<div class="scoreboard"><div class="score"><span>System picks</span><strong>{counts["all"]}</strong></div>
<div class="score"><span>Pending</span><strong>{counts.get("pending_operator", 0)}</strong></div><div class="score"><span>Played</span><strong class="won">{counts["played"]}</strong></div><div class="score"><span>Skipped</span><strong>{counts["skipped"]}</strong></div>
<div class="score"><span>Active played</span><strong>{counts["active"]}</strong></div><div class="score"><span>Won</span><strong class="won">{counts["won"]}</strong></div>
<div class="score"><span>Lost</span><strong class="lost">{counts["lost"]}</strong></div><div class="score"><span>Void</span><strong>{counts["void"]}</strong></div></div></article>
<article class="panel"><div class="panel-head"><h2>Operational pulse</h2><span class="section-label">Evidence-backed</span></div><div class="ops">
<div class="fact"><span>Last engine cycle</span><strong>{escape(self._dt(ops["last_engine_refresh"]))}</strong></div>
<div class="fact"><span>Last discovery</span><strong>{escape(self._dt(ops["last_discovery"]))}</strong></div>
<div class="fact"><span>Odds ingestion</span><strong>{escape(self._dt(ops["last_odds_ingestion"]))}</strong></div>
<div class="fact"><span>Provider budget</span><strong>{budget["used"]} / {budget["effective_limit"]} · {budget["remaining"]} left</strong></div>
<div class="fact"><span>Recent item failures</span><strong>{ops["recent_failures"]}</strong></div><div class="fact"><span>Stale workers</span><strong>{escape(stale)}</strong></div>
</div></article></section><section class="panel"><div class="panel-head"><h2>Active picks</h2><span class="section-label">Pre-match & live</span></div>
<div class="table-wrap"><table><thead><tr><th>Pick ID</th><th>Decision</th><th>Fixture</th><th>Market</th><th>Odds lifecycle</th><th class="num">Probability</th>
<th class="num">Edge</th><th class="num">Accounting</th><th>System status</th><th>Quality</th></tr></thead><tbody>{context["active_rows"]}</tbody></table></div></section>
<section class="panel history"><div class="panel-head"><h2>History</h2><span class="section-label">{context["history_count"]} finished</span></div>
<div class="table-wrap"><table><thead><tr><th>Decision</th><th>Outcome</th><th>Fixture</th><th class="num">Odds</th><th class="num">Probability</th><th class="num">CLV</th><th class="num">P/L</th></tr></thead>
<tbody>{context["history_rows"]}</tbody></table></div></section>
<section class="panel workers" style="margin-top:12px"><div class="panel-head"><h2>Worker status</h2><span class="section-label">Durable heartbeat</span></div>
<div class="table-wrap"><table><thead><tr><th>Worker</th><th>Freshness</th><th>Last success</th><th>Consecutive failures</th></tr></thead>
<tbody>{context["worker_rows"]}</tbody></table></div></section>
<section class="panel glossary"><div class="section-label">Plain-language glossary</div><dl>
<dt>First seen</dt><dd>First stored pre-match price for the registered market and bookmaker series.</dd>
<dt>Pick odds</dt><dd>Immutable decimal odds cloned from the source universe when the intake contract matched.</dd>
<dt>Last observed</dt><dd>Newest stored pre-kickoff price. In the final live window this may come from the API-Football live-market proxy and is labeled LIVE PROXY.</dd>
<dt>Closing</dt><dd>True same-book closing when available; otherwise an explicit manual historical override or the live-market proxy, each labeled at the value.</dd>
<dt>Quality</dt><dd>Before kickoff it shows quote freshness. After kickoff it switches to LIVE, FINISHED, CLOSED or SETTLED so stale pre-match quotes do not masquerade as current match state.</dd>
<dt>Proxy CLV</dt><dd>Entry odds compared with a live-market proxy close when no valid same-book close exists.</dd>
<dt>Manual CLV</dt><dd>Entry odds compared with an operator-confirmed manual closing override. It is kept separate from persisted same-book CLV.</dd>
<dt>Implied probability</dt><dd>1 ÷ decimal odds.</dd>
<dt>Edge</dt><dd>Model probability − de-vig bookmaker probability.</dd>
<dt>EV</dt><dd>(model probability × decimal odds) − 1.</dd>
<dt>CLV</dt><dd>Closing-line value compares Pick odds only with the closing price at the same registered bookmaker.</dd>
</dl></section><footer><span>Production funnel · source-cloned picks only</span>
<span>Times: Europe/Belgrade · Refresh page for current durable state</span></footer></main>{COUNTDOWN_SCRIPT}</body></html>"""


class DashboardHTTPService:
    """Small standalone HTTP surface for a Railway dashboard service."""

    def __init__(self, dashboard: DashboardService, *, host: str, port: int) -> None:
        self._dashboard = dashboard
        service = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                path = self.path.split("?", 1)[0]
                if path == "/livez":
                    service._json(self, 200, {"live": True})
                elif path in {"/", "/dashboard"}:
                    if service._authorize(self):
                        try:
                            service._html(self, 200, dashboard.render_html())
                        except (BrokenPipeError, ConnectionResetError):
                            return
                        except Exception as exc:  # noqa: BLE001 - bounded failure response
                            service._json(self, 503, {"error": type(exc).__name__})
                else:
                    service._json(self, 404, {"error": "not_found"})

            def do_POST(self) -> None:
                path = self.path.split("?", 1)[0]
                prefix, suffix = "/api/picks/", "/operator-state"
                if not path.startswith(prefix) or not path.endswith(suffix):
                    service._json(self, 404, {"error": "not_found"})
                    return
                if not service._same_origin(self):
                    service._json(self, 403, {"error": "origin_forbidden"})
                    return
                if not service._authorize(self, allow_public=False):
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if length <= 0 or length > 4096:
                        raise ValueError("invalid body length")
                    values = parse_qs(self.rfile.read(length).decode("utf-8"), strict_parsing=True)
                    pick_id = unquote(path[len(prefix) : -len(suffix)])
                    result = dashboard.set_operator_state(
                        pick_id, values["state"][0], values["request_id"][0]
                    )
                except (KeyError, LookupError, UnicodeDecodeError, ValueError) as exc:
                    service._json(self, 400, {"error": type(exc).__name__})
                    return
                if "application/json" in self.headers.get("Accept", ""):
                    service._json(self, 200, result)
                else:
                    self.send_response(303)
                    self.send_header("Location", "/dashboard")
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()

            def log_message(self, _format: str, *_args: object) -> None:
                return

        self._server = ThreadingHTTPServer((host, port), Handler)
        self._thread = Thread(target=self._server.serve_forever, daemon=True)

    @staticmethod
    def _json(handler: BaseHTTPRequestHandler, status: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(body).encode()
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Content-Length", str(len(encoded)))
        handler.end_headers()
        handler.wfile.write(encoded)

    @staticmethod
    def _html(handler: BaseHTTPRequestHandler, status: int, body: str) -> None:
        encoded = body.encode()
        handler.send_response(status)
        handler.send_header("Content-Type", "text/html; charset=utf-8")
        handler.send_header("Cache-Control", "no-store")
        handler.send_header(
            "Content-Security-Policy",
            f"default-src 'none'; style-src 'unsafe-inline'; script-src {COUNTDOWN_SCRIPT_CSP}",
        )
        handler.send_header("X-Content-Type-Options", "nosniff")
        handler.send_header("X-Frame-Options", "DENY")
        handler.send_header("Content-Length", str(len(encoded)))
        handler.end_headers()
        handler.wfile.write(encoded)

    def _authorize(self, handler: BaseHTTPRequestHandler, *, allow_public: bool = True) -> bool:
        if allow_public and dashboard_is_public():
            return True
        password = os.environ.get("QUANTBET_DASHBOARD_PASSWORD", "")
        username = os.environ.get("QUANTBET_DASHBOARD_USER", "quantbet")
        if not password:
            self._json(handler, 404, {"error": "not_found"})
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
        encoded = b'{"error":"authentication_required"}'
        handler.send_response(401)
        handler.send_header("WWW-Authenticate", 'Basic realm="QuantBet Dashboard"')
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(encoded)))
        handler.end_headers()
        handler.wfile.write(encoded)
        return False

    @staticmethod
    def _same_origin(handler: BaseHTTPRequestHandler) -> bool:
        origin = handler.headers.get("Origin")
        if not origin:
            return True
        parsed = urlsplit(origin)
        return parsed.scheme in {"http", "https"} and parsed.netloc == handler.headers.get("Host")

    def start(self) -> None:
        self._thread.start()

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
