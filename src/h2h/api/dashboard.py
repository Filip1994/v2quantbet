"""Read-only server-rendered QuantBet dashboard."""

from __future__ import annotations

from datetime import UTC, datetime
from html import escape
from typing import Any

from h2h.production import ProductionApplication


class DashboardService:
    """Project durable production state into a compact read-only dashboard."""

    def __init__(self, application: ProductionApplication) -> None:
        self._application = application

    def snapshot(self) -> dict[str, Any]:
        app = self._application
        policy = app.settings.application.registration_policy
        assert policy is not None
        performance = app.results.performance.summary(policy.bankroll_account_id)
        picks = self._picks()
        usage = app.budget.usage_by_category()
        used = sum(usage.values())
        return {
            "generated_at": datetime.now(UTC),
            "bankroll": {
                "available_minor": performance.available_bankroll_minor,
                "open_exposure_minor": performance.open_exposure_minor,
                "currency": performance.currency,
            },
            "provider_budget": {
                "used": used,
                "remaining": max(0, app.budget.effective_limit - used),
                "effective_limit": app.budget.effective_limit,
                "by_category": usage,
            },
            "pick_count": len(picks),
            "picks": picks,
        }

    def _picks(self) -> list[dict[str, Any]]:
        sql = """
            WITH latest_fixture AS (
                SELECT DISTINCT ON (fo.fixture_id)
                    fo.fixture_id,
                    fo.home_team,
                    fo.away_team,
                    fo.competition_name,
                    fo.kickoff_at,
                    fo.provider_status
                FROM fixture_observations fo
                ORDER BY fo.fixture_id, fo.observed_at DESC, fo.fixture_observation_id DESC
            )
            SELECT
                r.pick_id,
                r.registered_at,
                r.fixture_id,
                latest.home_team,
                latest.away_team,
                latest.competition_name,
                latest.kickoff_at,
                latest.provider_status,
                r.market,
                r.selection,
                r.stake_minor,
                r.currency,
                fq.final_odd,
                fq.minimum_playable_odds,
                fq.final_model_probability,
                fq.final_devig_probability,
                fq.final_edge,
                fq.final_expected_value,
                fq.stale_quote,
                fq.quote_age_seconds,
                fq.warning_codes,
                fq.returned_bookmaker_key,
                fq.returned_observed_at,
                opening.odd AS opening_odd,
                current_quote.odd AS current_odd,
                current_quote.observed_at AS current_observed_at,
                current_quote.captured_at AS current_captured_at,
                monitoring.state AS monitoring_state,
                monitoring.next_refresh_at,
                closing.outcome AS closing_outcome,
                closing_quote.odd AS closing_odd
            FROM registered_picks r
            JOIN pick_decisions d ON d.decision_id = r.decision_id
            JOIN value_evaluations e ON e.evaluation_id = r.evaluation_id
            LEFT JOIN final_quote_verifications fq
                ON fq.verification_id = d.final_quote_verification_id
            LEFT JOIN latest_fixture latest ON latest.fixture_id = r.fixture_id
            LEFT JOIN LATERAL (
                SELECT q.odd
                FROM quote_snapshots q
                WHERE q.series_id = e.selected_series_id
                  AND q.source = e.source
                  AND q.observed_at < latest.kickoff_at
                  AND q.captured_at < latest.kickoff_at
                ORDER BY q.captured_at ASC, q.observed_at ASC, q.snapshot_id ASC
                LIMIT 1
            ) opening ON TRUE
            LEFT JOIN LATERAL (
                SELECT q.odd, q.observed_at, q.captured_at
                FROM quote_snapshots q
                WHERE q.series_id = e.selected_series_id
                  AND q.source = e.source
                  AND q.observed_at < latest.kickoff_at
                  AND q.captured_at < latest.kickoff_at
                ORDER BY q.observed_at DESC, q.captured_at DESC, q.snapshot_id DESC
                LIMIT 1
            ) current_quote ON TRUE
            LEFT JOIN pick_monitoring_states monitoring
                ON monitoring.pick_id = r.pick_id
            LEFT JOIN pick_closing_finalizations closing
                ON closing.pick_id = r.pick_id
            LEFT JOIN quote_snapshots closing_quote
                ON closing_quote.snapshot_id = closing.closing_snapshot_id
            ORDER BY r.registered_at DESC, r.pick_id DESC
        """
        with self._application.monitoring.repository.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql)
                columns = [item.name for item in cursor.description]
                rows = cursor.fetchall()
        return [dict(zip(columns, row, strict=True)) for row in rows]

    @staticmethod
    def _money(minor: int | None, currency: str | None) -> str:
        if minor is None:
            return "—"
        return f"{minor / 100:,.2f} {currency or ''}".replace(",", " ")

    @staticmethod
    def _pct(value: float | None) -> str:
        return "—" if value is None else f"{value * 100:.2f}%"

    @staticmethod
    def _odd(value: float | None) -> str:
        return "—" if value is None else f"{value:.2f}"

    @staticmethod
    def _dt(value: datetime | None) -> str:
        if value is None:
            return "—"
        return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")

    def render_html(self) -> str:
        data = self.snapshot()
        bankroll = data["bankroll"]
        budget = data["provider_budget"]
        rows: list[str] = []
        for pick in data["picks"]:
            fixture = f"{pick.get('home_team') or '?'} – {pick.get('away_team') or '?'}"
            warning = "STALE" if pick.get("stale_quote") else ""
            rows.append(
                "<tr>"
                f"<td>{escape(self._dt(pick.get('registered_at')))}</td>"
                f"<td><strong>{escape(fixture)}</strong><br><small>{escape(str(pick.get('competition_name') or ''))}</small></td>"
                f"<td>{escape(self._dt(pick.get('kickoff_at')))}</td>"
                f"<td>{escape(str(pick.get('market') or ''))} / <strong>{escape(str(pick.get('selection') or ''))}</strong></td>"
                f"<td>{self._odd(pick.get('final_odd'))}</td>"
                f"<td>{self._odd(pick.get('minimum_playable_odds'))}</td>"
                f"<td>{self._odd(pick.get('current_odd'))}</td>"
                f"<td>{self._pct(pick.get('final_model_probability'))}</td>"
                f"<td>{self._pct(pick.get('final_edge'))}</td>"
                f"<td>{self._pct(pick.get('final_expected_value'))}</td>"
                f"<td>{escape(self._money(pick.get('stake_minor'), pick.get('currency')))}</td>"
                f"<td>{escape(str(pick.get('monitoring_state') or 'REGISTERED'))}</td>"
                f"<td>{escape(warning)}</td>"
                f"<td><code>{escape(str(pick.get('fixture_id') or ''))}</code></td>"
                "</tr>"
            )
        table_rows = "".join(rows) or '<tr><td colspan="14">No registered picks.</td></tr>'
        generated = self._dt(data["generated_at"])
        return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>QuantBet Dashboard</title>
<style>
:root {{ color-scheme: dark; }}
body {{ font-family: ui-sans-serif,system-ui,-apple-system,sans-serif; margin: 0; background:#0f1117; color:#e7e9ee; }}
main {{ max-width: 1500px; margin: 0 auto; padding: 24px; }}
h1 {{ margin: 0 0 18px; }}
.cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; margin-bottom:20px; }}
.card {{ background:#171a22; border:1px solid #2b303b; border-radius:10px; padding:14px; }}
.card small {{ color:#9da5b4; display:block; margin-bottom:5px; }}
.card strong {{ font-size:1.25rem; }}
.wrap {{ overflow-x:auto; border:1px solid #2b303b; border-radius:10px; }}
table {{ border-collapse:collapse; width:100%; min-width:1400px; background:#171a22; }}
th,td {{ padding:10px 12px; border-bottom:1px solid #2b303b; text-align:left; white-space:nowrap; }}
th {{ position:sticky; top:0; background:#20242e; }}
small {{ color:#9da5b4; }}
code {{ font-size:.85em; }}
footer {{ margin-top:14px; color:#9da5b4; font-size:.85rem; }}
</style>
</head>
<body>
<main>
<h1>QuantBet Production Dashboard</h1>
<section class="cards">
<div class="card"><small>Available bankroll</small><strong>{escape(self._money(bankroll["available_minor"], bankroll["currency"]))}</strong></div>
<div class="card"><small>Open exposure</small><strong>{escape(self._money(bankroll["open_exposure_minor"], bankroll["currency"]))}</strong></div>
<div class="card"><small>Registered picks</small><strong>{data["pick_count"]}</strong></div>
<div class="card"><small>API calls used</small><strong>{budget["used"]} / {budget["effective_limit"]}</strong></div>
<div class="card"><small>API calls remaining</small><strong>{budget["remaining"]}</strong></div>
</section>
<div class="wrap">
<table>
<thead><tr>
<th>Registered</th><th>Fixture</th><th>Kickoff</th><th>Pick</th>
<th>Entry odds</th><th>Min playable</th><th>Current odds</th>
<th>Model p</th><th>Edge</th><th>EV</th><th>Stake</th>
<th>Monitoring</th><th>Warning</th><th>Fixture ID</th>
</tr></thead>
<tbody>{table_rows}</tbody>
</table>
</div>
<footer>Generated {escape(generated)}. Read-only. No bets are placed from this page.</footer>
</main>
</body>
</html>"""
