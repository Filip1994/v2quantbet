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
from threading import Thread
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlsplit

from h2h.domain.operator_pick_state import OperatorPickState


WORKER_FRESHNESS_SECONDS = 120


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


class DashboardService:
    """Project durable PostgreSQL facts without mutating or recomputing them."""

    def __init__(self, application: Any) -> None:
        self._application = application

    def snapshot(self) -> dict[str, Any]:
        generated_at = datetime.now(UTC)
        policy = _policy(self._application)
        system_performance = self._application.results.performance.summary(
            policy.bankroll_account_id
        )
        performance = self._application.results.performance.operator_summary(
            policy.bankroll_account_id
        )
        picks = self._picks()
        operations = self._operations(generated_at)
        usage = self._application.budget.usage_by_category()
        used = sum(usage.values())
        played = sum(pick.get("operator_state") == "PLAYED" for pick in picks)
        skipped = len(picks) - played
        return {
            "generated_at": generated_at,
            "bankroll": {
                "initial_minor": performance.initial_bankroll_minor,
                "available_minor": performance.available_bankroll_minor,
                "open_exposure_minor": performance.open_exposure_minor,
                "total_staked_minor": performance.total_staked_minor,
                "settled_stake_minor": performance.resolved_stake_minor,
                "gross_returns_minor": performance.gross_returns_minor,
                "realized_pnl_minor": performance.realized_pnl_minor,
                "pending_minor": performance.pending_stake_minor,
                "currency": performance.currency,
            },
            "counts": {
                "all": len(picks),
                "played": played,
                "skipped": skipped,
                "active": performance.pending_count,
                "won": performance.win_count,
                "lost": performance.loss_count,
                "void": performance.void_count,
            },
            "system_performance": {
                "registered_picks": len(picks),
                "pending": system_performance.pending_count,
                "won": system_performance.win_count,
                "lost": system_performance.loss_count,
                "void": system_performance.void_count,
                "realized_pnl_minor": system_performance.realized_pnl_minor,
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
            WITH latest_fixture AS (
                SELECT DISTINCT ON (fo.fixture_id)
                    fo.fixture_id, fo.home_team, fo.away_team, fo.competition_name,
                    fo.kickoff_at, fo.provider_status
                FROM fixture_observations fo
                ORDER BY fo.fixture_id, fo.observed_at DESC, fo.fixture_observation_id DESC
            ), effective_settlement AS (
                SELECT event.* FROM pick_settlement_events event
                WHERE NOT EXISTS (
                    SELECT 1 FROM pick_settlement_events successor
                    WHERE successor.prior_event_id = event.settlement_event_id
                )
            )
            SELECT
                r.pick_id, r.registered_at, r.fixture_id,
                latest.home_team, latest.away_team, latest.competition_name,
                latest.kickoff_at, latest.provider_status,
                r.market, r.selection, r.stake_minor, r.currency,
                entry.odd AS pick_odd, entry.observed_at AS pick_observed_at,
                entry.captured_at AS pick_captured_at,
                opening.odd AS first_seen_odd,
                opening.observed_at AS first_seen_observed_at,
                opening.captured_at AS first_seen_captured_at,
                current_quote.odd AS current_odd,
                current_quote.observed_at AS current_observed_at,
                current_quote.captured_at AS current_captured_at,
                CASE
                    WHEN current_quote.observed_at IS NULL THEN 'UNAVAILABLE'
                    WHEN current_quote.observed_at >=
                        LEAST(CURRENT_TIMESTAMP, latest.kickoff_at)
                        - make_interval(secs => COALESCE(
                            monitoring.current_max_age_seconds,
                            (config.configuration->>'maximum_quote_age_seconds')::integer
                        ))
                    THEN 'FRESH'
                    ELSE 'STALE'
                END AS current_freshness,
                CASE
                    WHEN current_quote.observed_at IS NULL THEN NULL
                    ELSE GREATEST(
                        0,
                        FLOOR(EXTRACT(EPOCH FROM (
                            LEAST(CURRENT_TIMESTAMP, latest.kickoff_at)
                            - current_quote.observed_at
                        )))
                    )::bigint
                END AS current_quote_age_seconds,
                COALESCE(
                    monitoring.current_max_age_seconds,
                    (config.configuration->>'maximum_quote_age_seconds')::integer
                ) AS current_max_age_seconds,
                best_current.odd AS best_current_odd,
                best_current.observed_at AS best_current_observed_at,
                best_current.captured_at AS best_current_captured_at,
                best_current.bookmaker_key AS best_current_bookmaker_key,
                closing.outcome AS closing_status,
                closing.finalized_at AS closing_finalized_at,
                closing_quote.odd AS closing_odd,
                closing_quote.observed_at AS closing_observed_at,
                closing_quote.captured_at AS closing_captured_at,
                proxy_close.outcome AS proxy_closing_status,
                proxy_close.proxy_closing_odd_decimal AS proxy_closing_odd,
                proxy_close.proxy_clv_ppm,
                proxy_observation.provider_observed_at AS proxy_closing_observed_at,
                e.bookmaker_key, e.source, e.model_probability,
                e.selected_raw_implied_probability AS implied_probability,
                e.selected_devig_probability AS devig_probability,
                e.edge, e.expected_value,
                prediction.model_version_id, prediction.prediction_method_version,
                r.config_fingerprint,
                config.eligibility_policy_version, config.risk_policy_version,
                config.staking_policy_version,
                fq.stale_quote, fq.quote_age_seconds, fq.warning_codes,
                monitoring.state AS monitoring_state,
                settlement.outcome AS settlement_outcome,
                settlement.gross_return_minor, settlement.realized_pnl_minor,
                settlement.occurred_at AS settled_at,
                clv.clv_ppm, clv.method_version AS clv_method_version
                , COALESCE(operator_state.state, 'PLAYED') AS operator_state
            FROM registered_picks r
            JOIN pick_decisions decision ON decision.decision_id = r.decision_id
            JOIN value_evaluations e ON e.evaluation_id = r.evaluation_id
            JOIN fixture_predictions prediction ON prediction.prediction_id = e.prediction_id
            JOIN pick_policy_configurations config
                ON config.config_fingerprint = r.config_fingerprint
            LEFT JOIN pick_monitoring_states monitoring ON monitoring.pick_id = r.pick_id
            JOIN quote_snapshots entry ON entry.snapshot_id = r.entry_snapshot_id
            LEFT JOIN final_quote_verifications fq
                ON fq.verification_id = decision.final_quote_verification_id
            LEFT JOIN latest_fixture latest ON latest.fixture_id = r.fixture_id
            LEFT JOIN LATERAL (
                SELECT q.odd, q.observed_at, q.captured_at
                FROM quote_snapshots q
                WHERE q.series_id = e.selected_series_id AND q.source = e.source
                  AND q.observed_at < latest.kickoff_at
                  AND q.captured_at < latest.kickoff_at
                ORDER BY q.captured_at, q.observed_at, q.snapshot_id
                LIMIT 1
            ) opening ON TRUE
            LEFT JOIN LATERAL (
                SELECT q.odd, q.observed_at, q.captured_at
                FROM quote_snapshots q
                WHERE q.series_id = e.selected_series_id AND q.source = e.source
                  AND q.observed_at < latest.kickoff_at
                  AND q.captured_at < latest.kickoff_at
                ORDER BY q.observed_at DESC, q.captured_at DESC, q.snapshot_id DESC
                LIMIT 1
            ) current_quote ON TRUE
            LEFT JOIN LATERAL (
                SELECT latest_price.odd, latest_price.observed_at,
                    latest_price.captured_at,
                    CASE series.bookmaker_id
                        WHEN 8 THEN 'bet365'
                        WHEN 11 THEN '1xbet'
                        WHEN 34 THEN 'superbet'
                    END AS bookmaker_key
                FROM quote_series series
                JOIN LATERAL (
                    SELECT q.odd, q.observed_at, q.captured_at
                    FROM quote_snapshots q
                    WHERE q.series_id = series.series_id AND q.source = e.source
                      AND q.observed_at < latest.kickoff_at
                      AND q.captured_at < latest.kickoff_at
                    ORDER BY q.observed_at DESC, q.captured_at DESC, q.snapshot_id DESC
                    LIMIT 1
                ) latest_price ON TRUE
                WHERE series.fixture_id = r.fixture_id
                  AND series.market = r.market AND series.selection = r.selection
                  AND series.bookmaker_id = ANY(ARRAY[8, 11, 34]::bigint[])
                  AND latest_price.observed_at >=
                      LEAST(CURRENT_TIMESTAMP, latest.kickoff_at)
                      - make_interval(secs => COALESCE(
                          monitoring.current_max_age_seconds,
                          (config.configuration->>'maximum_quote_age_seconds')::integer
                      ))
                ORDER BY latest_price.odd DESC, series.bookmaker_id
                LIMIT 1
            ) best_current ON TRUE
            LEFT JOIN pick_closing_finalizations closing ON closing.pick_id = r.pick_id
            LEFT JOIN quote_snapshots closing_quote
                ON closing_quote.snapshot_id = closing.closing_snapshot_id
            LEFT JOIN pick_live_close_finalizations proxy_close
                ON proxy_close.pick_id = r.pick_id
            LEFT JOIN pick_live_close_observations proxy_observation
                ON proxy_observation.observation_id = proxy_close.observation_id
            LEFT JOIN effective_settlement settlement ON settlement.pick_id = r.pick_id
            LEFT JOIN pick_realized_clv clv ON clv.pick_id = r.pick_id
            LEFT JOIN LATERAL (
                SELECT state FROM pick_operator_state_events operator_event
                WHERE operator_event.pick_id = r.pick_id
                ORDER BY occurred_at DESC, persisted_at DESC, event_id DESC LIMIT 1
            ) operator_state ON TRUE
            ORDER BY r.registered_at DESC, r.pick_id DESC
        """
        with self._application.runtime.connect() as connection, connection.cursor() as cursor:
            cursor.execute(sql)
            columns = [item.name for item in cursor.description]
            rows = cursor.fetchall()
        return [dict(zip(columns, row, strict=True)) for row in rows]

    def set_operator_state(self, pick_id: str, state: str, request_id: str) -> dict[str, Any]:
        event = self._application.operator_picks.set_state(
            pick_id,
            OperatorPickState(state),
            request_id,
            occurred_at=datetime.now(UTC),
        )
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
        if value is None:
            return "—"
        return value.astimezone(UTC).strftime("%d %b %Y · %H:%M UTC")

    @staticmethod
    def _checkpoint_time(value: datetime | None) -> str:
        if value is None:
            return "—"
        return value.astimezone(UTC).strftime("%d %b %H:%M")

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
        """Return one live freshness badge plus compact historical context."""
        freshness = str(pick.get("current_freshness") or "UNAVAILABLE").upper()
        if freshness == "FRESH":
            live = (
                "FRESH",
                "fresh",
                "Latest registered-book quote is within its freshness limit",
            )
        elif freshness == "STALE":
            live = (
                "STALE NOW",
                "stale",
                "Latest registered-book provider observation is too old",
            )
        else:
            live = (
                "UNAVAILABLE",
                "unavailable",
                "No current registered-book quote is available",
            )

        warning_codes = [str(value) for value in (pick.get("warning_codes") or ())]
        history: list[str] = []
        history_titles: list[str] = []
        if pick.get("stale_quote") or "STALE_QUOTE_WARNING" in warning_codes:
            history.append("Entry stale")
            history_titles.append(
                "Final quote verification was stale when this pick was registered"
            )

        other_entry_warnings = [
            warning for warning in warning_codes if warning != "STALE_QUOTE_WARNING"
        ]
        if other_entry_warnings:
            history.append("Entry warning")
            history_titles.append("Registration warnings: " + ", ".join(other_entry_warnings))

        closing_status = str(pick.get("closing_status") or "")
        if closing_status == "STALE_QUOTE":
            history.append("Same-book close stale")
            history_titles.append("No fresh quote was available at the closing cutoff")
        elif closing_status == "NO_VALID_QUOTE":
            history.append("Same-book close unavailable")
            history_titles.append("No valid quote was available at the closing cutoff")

        return live, tuple(dict.fromkeys(history)), " · ".join(history_titles)

    @staticmethod
    def _quote_age(value: Any) -> str:
        if value is None:
            return ""
        seconds = max(0, int(value))
        if seconds < 60:
            return f"{seconds}s old"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes}m old"
        hours, remainder = divmod(minutes, 60)
        return f"{hours}h {remainder:02d}m old" if remainder else f"{hours}h old"

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
    def _movement(pick: dict[str, Any]) -> str:
        if str(pick.get("current_freshness") or "").upper() != "FRESH":
            return ""
        entry = pick.get("pick_odd")
        current = pick.get("current_odd")
        if entry is None or current is None or Decimal(str(current)) == Decimal(str(entry)):
            css, symbol, label = "neutral", "→", "Same-bookmaker price unchanged"
        elif Decimal(str(current)) > Decimal(str(entry)):
            css, symbol, label = "up", "↑", "Same-bookmaker price moved up"
        else:
            css, symbol, label = "down", "↓", "Same-bookmaker price moved down"
        return (
            f'<span class="movement {css}" role="img" aria-label="{label}" title="{label}">'
            f'{symbol}<span class="sr-only">{label}</span></span>'
        )

    def _render_pick_row(self, pick: dict[str, Any], currency: str) -> str:
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
        best_key = str(pick.get("best_current_bookmaker_key") or "").casefold()
        registered_bookmaker = self._bookmaker_badge(registered_key)
        best_bookmaker_footer = (
            f'<small class="best-book-switch"><span>best at</span>'
            f'{self._bookmaker_badge(best_key)}</small>'
            if best_key and best_key != registered_key and pick.get("best_current_odd") is not None
            else ""
        )
        current_freshness = str(pick.get("current_freshness") or "UNAVAILABLE").upper()
        current_label = "Last observed" if current_freshness == "STALE" else "Same-book current"
        if current_freshness == "STALE":
            age = self._quote_age(pick.get("current_quote_age_seconds"))
            current_meta = (
                f'<small class="quote-age stale">STALE'
                f"{' · ' + escape(age) if age else ''}</small>"
            )
        elif current_freshness == "UNAVAILABLE":
            current_meta = '<small class="quote-age unavailable">UNAVAILABLE</small>'
        else:
            current_meta = ""
        movement = self._movement(pick)
        operator_state = str(pick.get("operator_state") or "PLAYED")
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
            f"<b>First</b>{self._odd(pick.get('first_seen_odd'))}</span>"
            f'<span title="{escape(self._dt(pick.get("pick_observed_at")))}">'
            f"<b>Pick</b>{self._odd(pick.get('pick_odd'))}</span>"
            f'<span title="{escape(self._dt(pick.get("current_observed_at")))}">'
            f"<b>{escape(current_label)}</b>{self._odd(pick.get('current_odd'))}{movement}"
            f"{current_meta}</span>"
            f'<span title="{escape(self._dt(pick.get("best_current_observed_at")))}">'
            f"<b>Best current</b>{self._odd(pick.get('best_current_odd'))}"
            f"{best_bookmaker_footer}</span>"
            f'<span title="{escape(self._dt(pick.get("closing_observed_at")))}">'
            f"<b>Same-book close</b>{self._odd(pick.get('closing_odd'))}</span>"
            f'<span title="{escape(self._dt(pick.get("proxy_closing_observed_at")))}">'
            f"<b>Market close</b>{self._odd(pick.get('proxy_closing_odd'))}"
            f'<small class="proxy-label">LIVE PROXY</small></span>'
            "</div>"
        )
        checkpoint_times = " · ".join(
            [
                f"F {self._checkpoint_time(pick.get('first_seen_observed_at'))}",
                f"P {self._checkpoint_time(pick.get('pick_observed_at'))}",
                f"C {self._checkpoint_time(pick.get('current_observed_at'))}",
                f"X {self._checkpoint_time(pick.get('closing_observed_at'))}",
                f"M {self._checkpoint_time(pick.get('proxy_closing_observed_at'))}",
            ]
        )
        return (
            f'<tr data-provenance="{escape(provenance)}">'
            f'<td><code title="{escape(str(pick.get("pick_id") or ""))}">'
            f"{escape(self._short_id(pick.get('pick_id')))}</code></td>"
            f'<td class="fixture"><strong>{escape(fixture)}</strong><small>'
            f"{escape(str(pick.get('competition_name') or '—'))} · "
            f"{escape(self._dt(pick.get('kickoff_at')))}</small>"
            f'<span class="pick-book" title="Registered bookmaker">{registered_bookmaker}</span></td>'
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
            f'<td><span class="status operator-{operator_state.casefold()}">'
            f'{escape(operator_state)}</span><div class="operator-controls">'
            f"{operator_controls}</div></td>"
            f"<td>{quality_html}</td>"
            "</tr>"
        )

    def render_html(self) -> str:
        data = self.snapshot()
        bankroll = data["bankroll"]
        ops = data["operations"]
        currency = bankroll["currency"]
        rows = "".join(self._render_pick_row(pick, currency) for pick in data["picks"])
        if not rows:
            rows = (
                '<tr><td class="empty" colspan="10"><strong>No registered picks yet.</strong>'
                "<br>Durable pick history will appear here after registration.</td></tr>"
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
            rows=rows,
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
        cards = [
            ("Current bankroll", self._money(bankroll["available_minor"], currency), "primary"),
            ("Initial bankroll", self._money(bankroll["initial_minor"], currency), ""),
            ("Open exposure", self._money(bankroll["open_exposure_minor"], currency), "warn"),
            ("Realized P/L", self._money(bankroll["realized_pnl_minor"], currency), "value"),
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
:root{{--bg:#090c12;--panel:#111722;--panel2:#161e2b;--line:#253044;--text:#e7edf7;
--muted:#8592a6;--blue:#4e8cff;--green:#36d399;--red:#fb7185;--amber:#f5b942}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:13px/1.45
Inter,ui-sans-serif,system-ui,-apple-system,sans-serif}}.shell{{max-width:1800px;margin:auto;padding:24px}}
header{{display:flex;align-items:end;justify-content:space-between;gap:20px;margin-bottom:20px}}
.eyebrow,.section-label{{color:var(--blue);font-size:11px;font-weight:800;letter-spacing:.13em;text-transform:uppercase}}
h1{{font-size:27px;letter-spacing:-.03em;margin:3px 0}}.subtitle{{color:var(--muted)}}
.live{{display:flex;align-items:center;gap:8px;color:var(--muted)}}.dot{{width:8px;height:8px;border-radius:50%;background:var(--green)}}
.kpis{{display:grid;grid-template-columns:repeat(8,minmax(140px,1fr));gap:9px;margin-bottom:12px}}
.kpi{{background:var(--panel);border:1px solid var(--line);padding:13px 14px;min-height:76px}}
.kpi span{{display:block;color:var(--muted);font-size:11px;margin-bottom:8px}}.kpi strong{{font-size:17px;font-variant-numeric:tabular-nums}}
.kpi.primary{{border-top:2px solid var(--blue)}}.kpi.value strong,.value strong{{color:var(--green)}}.kpi.warn strong{{color:var(--amber)}}
.overview{{display:grid;grid-template-columns:2fr 1fr;gap:12px;margin-bottom:12px}}.panel{{background:var(--panel);border:1px solid var(--line)}}
.overview .panel:first-child{{display:flex;flex-direction:column}}
.panel-head{{display:flex;align-items:center;justify-content:space-between;padding:13px 15px;border-bottom:1px solid var(--line)}}h2{{font-size:14px;margin:0}}
.scoreboard{{display:grid;grid-template-columns:repeat(7,1fr);padding:14px;flex:1;align-items:center}}.score{{padding:0 14px;border-right:1px solid var(--line)}}
.score:last-child{{border:0}}.score span{{display:block;color:var(--muted)}}.score strong{{font-size:22px;font-variant-numeric:tabular-nums}}
.won{{color:var(--green)}}.lost{{color:var(--red)}}.ops{{display:grid;grid-template-columns:1fr 1fr;gap:10px;padding:14px}}
.fact{{background:var(--panel2);padding:10px}}.fact span{{display:block;color:var(--muted);font-size:11px}}.fact strong{{display:block;margin-top:4px}}
.table-wrap{{overflow:auto}}table{{border-collapse:collapse;width:100%;min-width:1450px}}th,td{{padding:11px 12px;border-bottom:1px solid var(--line);text-align:left;vertical-align:middle}}
th{{background:var(--panel2);color:var(--muted);font-size:10px;letter-spacing:.08em;text-transform:uppercase;position:sticky;top:0;z-index:1}}
tbody tr:hover{{background:#141c29}}td small{{display:block;color:var(--muted);margin-top:4px}}.fixture{{min-width:250px}}.fixture strong{{font-size:14px}}
.market{{display:block;color:var(--muted);font-size:10px}}.num{{text-align:right;font-variant-numeric:tabular-nums}}
.odds-grid{{display:grid;grid-template-columns:repeat(6,minmax(72px,1fr));gap:5px;font-variant-numeric:tabular-nums}}
.odds-grid>span{{background:var(--panel2);padding:7px 6px;text-align:center;min-height:62px;display:flex;flex-direction:column;align-items:center;justify-content:flex-start}}
.odds-grid>span>b{{display:block;color:var(--muted);font-size:8px;text-transform:uppercase;margin-bottom:2px}}
.movement{{display:inline!important;background:transparent!important;padding:0 0 0 4px!important;font-weight:900}}.movement.up{{color:var(--green)}}.movement.down{{color:var(--red)}}.movement.neutral{{color:var(--muted)}}
.pick-book{{display:flex;align-items:center;margin-top:8px;width:max-content}}
.bookmaker-mark{{display:inline-flex;align-items:center;justify-content:center;min-height:24px;border-radius:6px;font-size:10px;font-weight:900;letter-spacing:-.02em;line-height:1;white-space:nowrap;overflow:hidden}}
.brand-bet365{{display:inline-flex;align-items:baseline;gap:1px;background:#087a4b;padding:6px 8px;border-radius:6px}}
.brand-bet365 b{{color:#fff;font-size:11px}}.brand-bet365 strong{{color:#f4ea24;font-size:11px}}
.brand-1xbet{{display:inline-flex;align-items:baseline;gap:1px;background:#fff;padding:6px 8px;border-radius:6px}}
.brand-1xbet b{{color:#1689d4;font-size:11px}}.brand-1xbet strong{{color:#184b91;font-size:11px}}
.brand-superbet{{display:inline-flex;align-items:baseline;gap:1px;background:#e52333;padding:6px 8px;border-radius:6px}}
.brand-superbet b,.brand-superbet strong{{color:#fff;font-size:9px}}
.brand-generic{{display:inline-flex;background:#1b2637;color:var(--text);border:1px solid var(--line);padding:6px 8px;border-radius:6px}}
.best-book-switch{{display:flex!important;align-items:center;justify-content:center;gap:5px;width:100%;margin-top:auto!important;padding-top:5px;border-top:1px solid var(--line);font-size:8px!important;color:var(--muted)}}
.best-book-switch .bookmaker-mark{{transform:scale(.82);transform-origin:center;min-height:20px}}
.sr-only{{position:absolute!important;width:1px;height:1px;padding:0!important;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}}
.status,.quality-badge{{display:inline-block;border:1px solid var(--line);padding:3px 6px;font-size:9px;font-weight:800;letter-spacing:.05em}}
.status.win{{color:var(--green);border-color:#1f6a51}}.status.loss,.status.lost{{color:var(--red);border-color:#6f2c3a}}
.status.void{{color:var(--muted)}}.status.active{{color:#8ab4ff;border-color:#35578c}}
.quality-summary{{display:flex;flex-direction:column;align-items:flex-start;gap:3px;min-width:104px}}
.quality-badge.fresh{{color:var(--green);border-color:#1f6a51}}
.quality-badge.stale{{color:var(--amber);border-color:#6c5425}}
.quality-badge.unavailable{{color:var(--muted)}}
.quality-history{{margin:0!important;color:var(--muted)!important;font-size:8px!important;line-height:1.3}}
.quote-age{{margin-top:auto!important;padding-top:4px;font-size:8px!important;letter-spacing:.04em}}
.quote-age.stale{{color:var(--amber)}}.quote-age.unavailable{{color:var(--muted)}}.proxy-label{{color:#a9c5ff!important;font-size:7px!important;letter-spacing:.05em}}
.operator-played{{color:var(--green);border-color:#1f6a51}}.operator-skipped{{color:var(--amber);border-color:#6c5425}}
.operator-controls{{display:flex;gap:4px;margin-top:6px}}.operator-controls form{{margin:0}}.operator-button{{background:var(--panel2);color:var(--text);border:1px solid var(--line);padding:4px 7px;cursor:pointer;font:inherit;font-size:9px}}.operator-button:disabled{{opacity:.45;cursor:default}}.operator-button.played:not(:disabled){{border-color:#1f6a51}}.operator-button.skipped:not(:disabled){{border-color:#6c5425}}
.timestamps{{font-size:9px}}code{{color:#a9c5ff}}.muted{{color:var(--muted)}}
.glossary{{margin-top:12px;padding:15px}}.glossary dl{{display:grid;grid-template-columns:180px 1fr;gap:8px 18px;margin:12px 0 0}}.glossary dt{{font-weight:800}}.glossary dd{{margin:0;color:var(--muted)}}
.empty{{text-align:center!important;color:var(--muted);padding:36px!important}}footer{{display:flex;justify-content:space-between;gap:12px;color:var(--muted);font-size:11px;padding:16px 2px}}
.workers table{{min-width:0}}.workers th,.workers td{{padding:8px 10px}}
@media(max-width:1150px){{.kpis{{grid-template-columns:repeat(4,1fr)}}.overview{{grid-template-columns:1fr}}}}
@media(max-width:650px){{.shell{{padding:14px}}header{{align-items:start;flex-direction:column}}.kpis{{grid-template-columns:repeat(2,1fr)}}
.scoreboard{{grid-template-columns:repeat(2,1fr);gap:14px}}.score{{border:0;padding:0}}footer{{flex-direction:column}}
.odds-grid{{grid-template-columns:repeat(6,minmax(82px,1fr))}}.odds-grid>span{{min-height:68px;padding:7px 5px}}.pick-book{{margin-top:7px}}}}
</style></head><body><main class="shell">
<header><div><div class="eyebrow">QuantBet / Production</div><h1>Operations Dashboard</h1>
<div class="subtitle">Read-only view of durable PostgreSQL state</div></div>
<div class="live"><span class="dot"></span>Database Connected · Generated {escape(self._dt(context["generated_at"]))}</div></header>
<section class="kpis">{cards_html}</section>
<section class="overview"><article class="panel"><div class="panel-head"><h2>Pick performance</h2><span class="section-label">All time</span></div>
<div class="scoreboard"><div class="score"><span>System picks</span><strong>{counts["all"]}</strong></div>
<div class="score"><span>Played</span><strong class="won">{counts["played"]}</strong></div><div class="score"><span>Skipped</span><strong>{counts["skipped"]}</strong></div>
<div class="score"><span>Active played</span><strong>{counts["active"]}</strong></div><div class="score"><span>Won</span><strong class="won">{counts["won"]}</strong></div>
<div class="score"><span>Lost</span><strong class="lost">{counts["lost"]}</strong></div><div class="score"><span>Void</span><strong>{counts["void"]}</strong></div></div></article>
<article class="panel"><div class="panel-head"><h2>Operational pulse</h2><span class="section-label">Evidence-backed</span></div><div class="ops">
<div class="fact"><span>Last engine cycle</span><strong>{escape(self._dt(ops["last_engine_refresh"]))}</strong></div>
<div class="fact"><span>Last discovery</span><strong>{escape(self._dt(ops["last_discovery"]))}</strong></div>
<div class="fact"><span>Odds ingestion</span><strong>{escape(self._dt(ops["last_odds_ingestion"]))}</strong></div>
<div class="fact"><span>Provider budget</span><strong>{budget["used"]} / {budget["effective_limit"]} · {budget["remaining"]} left</strong></div>
<div class="fact"><span>Recent item failures</span><strong>{ops["recent_failures"]}</strong></div><div class="fact"><span>Stale workers</span><strong>{escape(stale)}</strong></div>
</div></article></section><section class="panel"><div class="panel-head"><h2>Complete pick history</h2><span class="section-label">Newest first</span></div>
<div class="table-wrap"><table><thead><tr><th>Pick ID</th><th>Fixture</th><th>Market</th><th>Odds lifecycle</th><th class="num">Probability</th>
<th class="num">Edge</th><th class="num">Accounting</th><th>System status</th><th>Operator</th><th>Quality</th></tr></thead><tbody>{context["rows"]}</tbody></table></div></section>
<section class="panel workers" style="margin-top:12px"><div class="panel-head"><h2>Worker status</h2><span class="section-label">Durable heartbeat</span></div>
<div class="table-wrap"><table><thead><tr><th>Worker</th><th>Freshness</th><th>Last success</th><th>Consecutive failures</th></tr></thead>
<tbody>{context["worker_rows"]}</tbody></table></div></section>
<section class="panel glossary"><div class="section-label">Plain-language glossary</div><dl>
<dt>Pick odds</dt><dd>Immutable decimal odds registered with the pick.</dd>
<dt>Same-book current</dt><dd>Latest provider observation at the registered bookmaker. If it exceeds the pinned freshness limit, the tile becomes Last observed and the movement arrow is suppressed.</dd>
<dt>Best current</dt><dd>Highest fresh price for the same fixture, market and selection across Bet365, 1xBet and Superbet. Stale prices are excluded.</dd>
<dt>Quality</dt><dd>One live status: FRESH, STALE NOW or UNAVAILABLE. Historical context such as Entry stale or Closing stale is shown as secondary text underneath.</dd>
<dt>Current freshness</dt><dd>Live freshness is calculated from the provider observed-at timestamp, not merely from whether the monitoring worker ran successfully.</dd>
<dt>Closing same-book</dt><dd>Last valid pre-kickoff price at the registered bookmaker.</dd>
<dt>Market close</dt><dd>API-Football live-market proxy captured in the final 15 minutes before kickoff. It is not bookmaker-specific and never replaces the same-book closing fact.</dd>
<dt>Proxy CLV</dt><dd>Entry odds compared with Market close when a valid same-book close is unavailable. It is labeled separately from true same-book CLV.</dd>
<dt>Implied probability</dt><dd>1 ÷ decimal odds.</dd>
<dt>Edge</dt><dd>Model probability − de-vig bookmaker probability.</dd>
<dt>EV</dt><dd>(model probability × decimal odds) − 1.</dd>
<dt>CLV</dt><dd>Closing-line value compares Pick odds only with the closing price at the same registered bookmaker.</dd>
</dl></section><footer><span>Read-only · no betting, settlement or worker controls</span>
<span>Refresh page for current durable state</span></footer></main></body></html>"""


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
            "Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'"
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
