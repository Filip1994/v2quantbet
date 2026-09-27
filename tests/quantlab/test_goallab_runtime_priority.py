import inspect

from h2h.quantlab.runtime import QuantLabRuntime


def test_goallab_evaluation_precedes_corner_history_bootstrap() -> None:
    source = inspect.getsource(QuantLabRuntime.run_once)

    goal_eval = source.index("self._evaluate_goal_picks(now)")
    corner_bootstrap = source.index("self._bootstrap_corner_team_history(now)")
    corner_eval = source.index('self._corner_engine, "CORNER", now')

    assert goal_eval < corner_bootstrap < corner_eval
