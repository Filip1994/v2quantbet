from h2h.persistence.postgres_research_signals import PostgreSQLResearchSignalRepository

rows = PostgreSQLResearchSignalRepository().list_all_signals()
for row in rows:
    if str(row["provider_fixture_id"]) == "1636701":
        print(
            "VERIFY "
            f"fixture={row['provider_fixture_id']} "
            f"pick_id={row['production_pick_id']} "
            f"teams={row['home_team']}-{row['away_team']} "
            f"disposition={row['disposition']} "
            f"production_manual_void={row['production_manual_void']} "
            f"result_status={row['result_provider_status']} "
            f"result_classification={row['result_classification']}"
        )
