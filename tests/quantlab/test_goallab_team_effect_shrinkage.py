import inspect

import numpy as np

from h2h.quantlab.goal_lab import model


def test_dc_plus_team_effects_require_minimum_training_appearances() -> None:
    home_ids = np.asarray([1, 1, 1, 1, 1, 2, 3, 4, 5], dtype=np.int64)
    away_ids = np.asarray([2, 3, 4, 5, 6, 1, 1, 1, 1], dtype=np.int64)

    eligible = model._eligible_team_values(home_ids, away_ids)

    assert 1 in eligible
    assert 2 not in eligible
    assert 6 not in eligible


def test_dc_plus_prediction_uses_neutral_effect_for_sparse_team() -> None:
    source = inspect.getsource(model.GoalStructuralModelService.estimate)

    assert 'attacks.get(str(home_id), 0.0)' in source
    assert 'defenses.get(str(away_id), 0.0)' in source
    assert '"home_team_effect_available"' in source
    assert '"rare_team_effect_strategy"' in source
