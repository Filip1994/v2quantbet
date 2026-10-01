from __future__ import annotations
import json
from h2h.persistence.postgres_research_signals import PostgreSQLResearchSignalRepository

rows = PostgreSQLResearchSignalRepository().list_all_signals()
target = [
    {
        "provider_fixture_id": row["provider_fixture_id"],
        "fixture_id": row["fixture_id"],
        "production_pick_id": row["production_pick_id"],
        "home_team": row["home_team"],
        "away_team": row["away_team"],
        "competition_name": row["competition_name"],
        "kickoff_at": str(row["kickoff_at"]),
        "disposition": row["disposition"],
        "result_provider_status": row["result_provider_status"],
        "result_classification": row["result_classification"],
        "production_manual_void": row["production_manual_void"],
    }
    for row in rows
    if str(row["provider_fixture_id"]) == "1636701"
    or (
        "cumbay" in row["home_team"].lower()
        and "santo domingo" in row["away_team"].lower()
    )
]
print("TARGET_JSON=" + json.dumps(target, ensure_ascii=False))

# trigger Railway branch deployment
