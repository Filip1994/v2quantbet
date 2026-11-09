"""One-shot deployment probe for diagnosing Production CornerLab provider calls.

Read-only to pick state. Consumes at most one manual provider request.
Remove from Railway pre-deploy commands after diagnosis.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

from h2h.quantlab.budget import QuantLabRequestBudget
from h2h.quantlab.fixture_discovery import parse_fixture_discovery_response
from h2h.quantlab.provider import QuantLabApiFootballClient


def main() -> None:
    api_key = os.environ["API_FOOTBALL_KEY"]
    database_url = os.environ["DATABASE_URL"]
    budget = QuantLabRequestBudget(
        shared_daily_limit=int(os.getenv("QUANTBET_API_DAILY_LIMIT", "7500")),
        production_reserve=int(os.getenv("QUANTBET_API_RESERVE", "0")),
        database_url=database_url,
        request_category="manual_corner_settlement",
        category_daily_limit=30,
    )
    client = QuantLabApiFootballClient(api_key=api_key, budget=budget, timeout=6.0)
    try:
        payload = client.fetch_fixture(1575541)
        print(
            "CORNER_PROBE_FETCH_OK",
            "response_count", len(payload.get("response") or []),
            "provider_errors", bool(payload.get("errors")),
            flush=True,
        )
        try:
            observations = parse_fixture_discovery_response(
                payload, captured_at=datetime.now(UTC)
            )
            print("CORNER_PROBE_PARSE_OK", len(observations), flush=True)
        except Exception as exc:  # noqa: BLE001 - boundary diagnostics
            print(
                "CORNER_PROBE_PARSE_ERROR", type(exc).__name__,
                str(exc).replace(api_key, "[key]").replace(database_url, "[database]")[:220],
                flush=True,
            )
    except Exception as exc:  # noqa: BLE001 - boundary diagnostics
        print(
            "CORNER_PROBE_FETCH_ERROR", type(exc).__name__,
            str(exc).replace(api_key, "[key]").replace(database_url, "[database]")[:220],
            flush=True,
        )


if __name__ == "__main__":
    main()
