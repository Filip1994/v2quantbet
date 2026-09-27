from datetime import UTC, datetime

from h2h.quantlab.card_lab.context import parse_fixture_contexts_from_fixture_response


NOW = datetime(2026, 9, 27, 21, 0, tzinfo=UTC)


def test_team_history_fixture_payload_yields_referee_context_without_extra_call() -> None:
    payload = {
        "errors": [],
        "response": [
            {
                "fixture": {
                    "id": 1001,
                    "date": "2026-09-20T18:00:00+00:00",
                    "referee": "Ref A",
                    "status": {"short": "FT"},
                },
                "league": {
                    "id": 39,
                    "name": "Premier League",
                    "country": "England",
                    "type": "League",
                    "season": 2026,
                },
                "teams": {
                    "home": {"id": 10, "name": "Home"},
                    "away": {"id": 11, "name": "Away"},
                },
            },
            {
                "fixture": {
                    "id": 1002,
                    "date": "2026-09-21T18:00:00+00:00",
                    "referee": "Ref B",
                    "status": {"short": "FT"},
                },
                "league": {
                    "id": 39,
                    "name": "Premier League",
                    "country": "England",
                    "type": "League",
                    "season": 2026,
                },
                "teams": {
                    "home": {"id": 12, "name": "Home 2"},
                    "away": {"id": 13, "name": "Away 2"},
                },
            },
        ],
    }

    rows = parse_fixture_contexts_from_fixture_response(payload, captured_at=NOW)

    assert len(rows) == 2
    assert [row.fixture_id for row in rows] == [
        "api-football:1001",
        "api-football:1002",
    ]
    assert [row.referee for row in rows] == ["Ref A", "Ref B"]
    assert all(row.available_at == NOW for row in rows)
    assert all(row.provider_status == "FT" for row in rows)
