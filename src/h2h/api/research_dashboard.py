"""Read-only dashboard for bankroll-free exposure research signals."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
from html import escape
from typing import Any

from h2h.domain.settlement import realized_clv_ppm


class ResearchDashboardService:
    def __init__(self, database_url: str | None = None, *, fixed_stake_minor: int = 30_000) -> None:
        self._database_url = database_url or os.environ.get("DATABASE_URL")
        if not self._database_url:
            raise ValueError("DATABASE_URL is required")
        if isinstance(fixed_stake_minor, bool) or fixed_stake_minor <= 0:
            raise ValueError("fixed_stake_minor must be positive")
        self._fixed_stake_minor = int(fixed_stake_minor)

    def connect(self) -> Any:
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("PostgreSQL support requires psycopg[binary]") from exc
        return psycopg.connect(self._database_url)

    def snapshot(self) -> dict[str, Any]:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                WITH latest_fixture AS (
                    SELECT DISTINCT ON (fo.fixture_id)
                        fo.fixture_id, fo.home_team, fo.away_team, fo.competition_name,
                        fo.country, fo.kickoff_at, fo.provider_status
                    FROM fixture_observations fo
                    ORDER BY fo.fixture_id, fo.observed_at DESC, fo.fixture_observation_id DESC
                ), result_context AS (
                    SELECT
                        state.fixture_id,
                        state.phase AS result_phase,
                        state.candidate_confirmation_count,
                        result.result_classification,
                        result.provider_status AS result_provider_status,
                        result.regulation_home_goals,
                        result.regulation_away_goals,
                        result.first_acquired_at
                    FROM fixture_result_acquisition_states state
                    LEFT JOIN fixture_result_observations result
                        ON result.result_observation_id = COALESCE(
                            state.candidate_observation_id,
                            state.current_observation_id
                        )
                )
                SELECT
                    signal.signal_id,
                    signal.detected_at,
                    signal.fixture_id,
                    fixture.provider_fixture_id,
                    fixture.league_id,
                    fixture.season,
                    latest.home_team,
                    latest.away_team,
                    latest.competition_name,
                    latest.country,
                    latest.kickoff_at,
                    latest.provider_status,
                    evaluation.market,
                    evaluation.selected_selection,
                    evaluation.bookmaker_key,
                    evaluation.selected_odd,
                    evaluation.companion_odd,
                    evaluation.model_probability,
                    evaluation.selected_devig_probability,
                    evaluation.edge,
                    evaluation.expected_value,
                    evaluation.quote_observed_at,
                    evaluation.source,
                    evaluation.model_version_id,
                    monitoring.state AS monitoring_state,
                    monitoring.updated_at AS monitoring_updated_at,
                    closing.outcome AS closing_outcome,
                    close_quote.odd AS closing_odd,
                    close_quote.observed_at AS closing_observed_at,
                    latest_quote.odd AS latest_same_book_odd,
                    latest_quote.observed_at AS latest_same_book_observed_at,
                    result_context.result_phase,
                    result_context.candidate_confirmation_count,
                    result_context.result_classification,
                    result_context.result_provider_status,
                    result_context.regulation_home_goals,
                    result_context.regulation_away_goals,
                    result_context.first_acquired_at
                FROM research_signals signal
                JOIN value_evaluations evaluation
                    ON evaluation.evaluation_id = signal.evaluation_id
                JOIN fixtures fixture ON fixture.fixture_id = signal.fixture_id
                JOIN latest_fixture latest ON latest.fixture_id = signal.fixture_id
                LEFT JOIN research_signal_monitoring_states monitoring
                    ON monitoring.signal_id = signal.signal_id
                LEFT JOIN research_signal_closing_finalizations closing
                    ON closing.signal_id = signal.signal_id
                LEFT JOIN quote_snapshots close_quote
                    ON close_quote.snapshot_id = closing.closing_snapshot_id
                LEFT JOIN LATERAL (
                    SELECT q.odd, q.observed_at
                    FROM quote_snapshots q
                    WHERE q.series_id = evaluation.selected_series_id
                      AND q.source = evaluation.source
                      AND q.observed_at < latest.kickoff_at
                      AND q.captured_at < latest.kickoff_at
                    ORDER BY q.observed_at DESC, q.captured_at DESC, q.snapshot_id DESC
                    LIMIT 1
                ) latest_quote ON TRUE
                LEFT JOIN result_context
                    ON result_context.fixture_id = signal.fixture_id
                ORDER BY signal.detected_at DESC, signal.signal_id DESC
                """
            )
            columns = [item.name for item in cursor.description]
            rows = [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
        for row in rows:
            row["counterfactual_outcome"] = self._outcome(row)
            row["counterfactual_pnl_minor"] = self._pnl(row)
            row["clv_ppm"] = self._clv(row)
        return {"generated_at": datetime.now(UTC), "signals": rows}

    @staticmethod
    def _outcome(row: dict[str, Any]) -> str | None:
        classification = str(row.get("result_classification") or "")
        if classification == "NON_PLAYED_VOIDABLE":
            return "VOID"
        if classification != "PLAYED_SETTLEABLE":
            return None
        home = row.get("regulation_home_goals")
        away = row.get("regulation_away_goals")
        if home is None or away is None:
            return None
        home, away = int(home), int(away)
        market = str(row["market"])
        selection = str(row["selected_selection"])
        if market == "OU_25":
            won = home + away > 2 if selection == "OVER" else home + away <= 2
        elif market == "BTTS":
            yes = home > 0 and away > 0
            won = yes if selection == "YES" else not yes
        else:
            return None
        return "WIN" if won else "LOSS"

    def _pnl(self, row: dict[str, Any]) -> int | None:
        outcome = row["counterfactual_outcome"]
        if outcome is None:
            return None
        if outcome == "VOID":
            return 0
        if outcome == "LOSS":
            return -self._fixed_stake_minor
        profit = (
            Decimal(self._fixed_stake_minor)
            * (Decimal(str(row["selected_odd"])) - Decimal("1"))
        ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        return int(profit)

    @staticmethod
    def _clv(row: dict[str, Any]) -> int | None:
        closing = row.get("closing_odd")
        if closing is None:
            return None
        return realized_clv_ppm(
            Decimal(str(row["selected_odd"])),
            Decimal(str(closing)),
        )

    @staticmethod
    def _pct(value: object) -> str:
        return "—" if value is None else f"{float(value) * 100:.2f}%"

    @staticmethod
    def _odd(value: object) -> str:
        return "—" if value is None else f"{float(value):.2f}"

    @staticmethod
    def _dt(value: object) -> str:
        if not isinstance(value, datetime):
            return "—"
        return value.astimezone(UTC).strftime("%d %b %Y · %H:%M UTC")

    @staticmethod
    def _money(value: object) -> str:
        if value is None:
            return "—"
        return f"{int(value) / 100:,.2f} RSD"

    @staticmethod
    def _clv_label(value: object) -> str:
        if value is None:
            return "—"
        return f"{int(value) / 10000:+.2f}%"

    def render_html(self) -> str:
        data = self.snapshot()
        signals = data["signals"]
        closed = sum(row.get("closing_outcome") is not None for row in signals)
        resolved = sum(row.get("counterfactual_outcome") is not None for row in signals)
        positive_clv = sum(
            row.get("clv_ppm") is not None and int(row["clv_ppm"]) > 0 for row in signals
        )
        extreme = sum(float(row["expected_value"]) >= 0.30 for row in signals)
        rows = "".join(self._row(row) for row in signals)
        if not rows:
            rows = '<tr><td colspan="13" class="empty">No exposure-blocked research signals yet.</td></tr>'
        return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>QuantBet · Research</title>
<style>
:root{{--bg:#090c12;--panel:#111722;--line:#253044;--text:#e7edf7;--muted:#8592a6;--green:#36d399;--red:#fb7185;--amber:#f5b942;--blue:#4e8cff}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:13px/1.45 Inter,system-ui,sans-serif}}
.shell{{max-width:1900px;margin:auto;padding:24px}}h1{{margin:3px 0;font-size:27px}}.eyebrow{{color:var(--blue);font-size:11px;font-weight:800;letter-spacing:.13em;text-transform:uppercase}}
.sub{{color:var(--muted);max-width:920px}}.cards{{display:grid;grid-template-columns:repeat(5,1fr);gap:9px;margin:20px 0 12px}}
.card{{background:var(--panel);border:1px solid var(--line);padding:13px}}.card span{{display:block;color:var(--muted);font-size:11px}}.card strong{{font-size:20px}}
.panel{{background:var(--panel);border:1px solid var(--line)}}.wrap{{overflow:auto}}table{{border-collapse:collapse;width:100%;min-width:1750px}}
th,td{{padding:10px 11px;border-bottom:1px solid var(--line);text-align:left;vertical-align:middle}}th{{color:var(--muted);font-size:10px;text-transform:uppercase;position:sticky;top:0;background:#161e2b}}
.num{{text-align:right;font-variant-numeric:tabular-nums}}small{{display:block;color:var(--muted)}}code{{color:#a9c5ff}}.good{{color:var(--green)}}.bad{{color:var(--red)}}.warn{{color:var(--amber)}}.empty{{text-align:center;padding:40px}}
.status{{font-size:9px;font-weight:800;border:1px solid var(--line);padding:3px 6px}}footer{{color:var(--muted);padding:14px 2px}}
@media(max-width:900px){{.cards{{grid-template-columns:repeat(2,1fr)}}.shell{{padding:12px}}}}
</style></head><body><main class="shell">
<div class="eyebrow">QuantBet / Shadow Research</div><h1>Exposure-blocked signals</h1>
<div class="sub">Counterfactual tracking only. These signals reserve no bankroll and do not alter production betting decisions. Same-book quote monitoring and authoritative fixture results are tracked for later calibration, EV, CLV and bucket analysis.</div>
<section class="cards">
<article class="card"><span>Signals</span><strong>{len(signals)}</strong></article>
<article class="card"><span>Odds closed</span><strong>{closed}</strong></article>
<article class="card"><span>Results available</span><strong>{resolved}</strong></article>
<article class="card"><span>Positive same-book CLV</span><strong>{positive_clv}</strong></article>
<article class="card"><span>EV ≥ 30%</span><strong>{extreme}</strong></article>
</section>
<section class="panel"><div class="wrap"><table><thead><tr>
<th>Match</th><th>Signal</th><th>Book</th><th class="num">Entry</th><th class="num">Model p</th>
<th class="num">Market fair</th><th class="num">Edge</th><th class="num">EV</th>
<th class="num">Latest same-book</th><th class="num">Close</th><th class="num">CLV</th>
<th>Result</th><th class="num">Flat 300 P/L</th>
</tr></thead><tbody>{rows}</tbody></table></div></section>
<footer>Generated {escape(self._dt(data["generated_at"]))} · research-only · no bankroll reservation</footer>
</main></body></html>"""

    def _row(self, row: dict[str, Any]) -> str:
        fixture = f"{row.get('home_team') or '—'} – {row.get('away_team') or '—'}"
        outcome = row.get("counterfactual_outcome")
        outcome_css = "good" if outcome == "WIN" else "bad" if outcome == "LOSS" else ""
        clv = row.get("clv_ppm")
        clv_css = "good" if clv is not None and int(clv) > 0 else "bad" if clv is not None and int(clv) < 0 else ""
        ev_css = "warn" if float(row["expected_value"]) >= 0.30 else ""
        return (
            "<tr>"
            f"<td><strong>{escape(fixture)}</strong>"
            f"<small>{escape(str(row.get('competition_name') or '—'))} · {escape(self._dt(row.get('kickoff_at')))}</small>"
            f"<small>fixture {escape(str(row.get('provider_fixture_id') or '—'))} · league {escape(str(row.get('league_id') or '—'))}</small></td>"
            f"<td><strong>{escape(str(row['market']))} {escape(str(row['selected_selection']))}</strong>"
            f"<small>blocked {escape(self._dt(row.get('detected_at')))}</small></td>"
            f"<td>{escape(str(row.get('bookmaker_key') or '—'))}</td>"
            f"<td class='num'>{self._odd(row.get('selected_odd'))}</td>"
            f"<td class='num'><strong>{self._pct(row.get('model_probability'))}</strong></td>"
            f"<td class='num'>{self._pct(row.get('selected_devig_probability'))}</td>"
            f"<td class='num'>{self._pct(row.get('edge'))}</td>"
            f"<td class='num {ev_css}'><strong>{self._pct(row.get('expected_value'))}</strong></td>"
            f"<td class='num'>{self._odd(row.get('latest_same_book_odd'))}<small>{escape(self._dt(row.get('latest_same_book_observed_at')))}</small></td>"
            f"<td class='num'>{self._odd(row.get('closing_odd'))}<small>{escape(str(row.get('closing_outcome') or 'PENDING'))}</small></td>"
            f"<td class='num {clv_css}'><strong>{self._clv_label(clv)}</strong></td>"
            f"<td class='{outcome_css}'><strong>{escape(str(outcome or 'PENDING'))}</strong>"
            f"<small>{escape(str(row.get('result_provider_status') or row.get('result_phase') or '—'))}</small></td>"
            f"<td class='num {outcome_css}'><strong>{escape(self._money(row.get('counterfactual_pnl_minor')))}</strong></td>"
            "</tr>"
        )
