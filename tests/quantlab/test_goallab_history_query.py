import inspect

from h2h.quantlab.repository import PostgreSQLQuantLabRepository


def test_goal_model_history_limits_fixtures_before_statistics_lookup() -> None:
    source = inspect.getsource(PostgreSQLQuantLabRepository.goal_model_history)

    assert "fixture_candidates AS" in source
    assert "fixture_rows AS" in source
    assert "ORDER BY kickoff_at DESC, fixture_id DESC LIMIT %s" in source
    assert "LEFT JOIN LATERAL (" in source
    assert "quantlab_match_statistics_observations" in source
    assert "stats AS (" not in source
    assert "(before, before, limit, before, before)" in source
