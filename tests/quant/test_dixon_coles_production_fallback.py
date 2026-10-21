from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from h2h.quant.dixon_coles import DixonColesModel


FIXTURES = Path(__file__).parents[1] / "fixtures"


@pytest.mark.parametrize("league", [205, 388, 731])
def test_reported_scopes_converge_to_valid_zero_rho_fallback(league: int) -> None:
    payload = json.loads((FIXTURES / f"dc_{league}_2026_sanitized.json").read_text())
    records = [
        SimpleNamespace(**{**row, "date": datetime.fromisoformat(row["date"])})
        for row in payload["records"]
    ]
    model = DixonColesModel.fit(
        records,
        team_id_namespace="api-football",
        reference_time=datetime.fromisoformat(payload["reference_time"]),
        xi=0.0018,
        ridge=0.01,
        min_matches=80,
    )

    assert model.optimizer_fallback == "rho_zero"
    assert model.rho == 0.0
    assert np.isfinite(model.objective)
    assert model.optimizer_gradient_norm is not None
    assert np.isfinite(model.optimizer_gradient_norm)
    for home in model.team_ids:
        for away in model.team_ids:
            if home != away:
                matrix = model.score_matrix(home, away)
                assert np.isfinite(matrix).all()
                assert np.isclose(matrix.sum(), 1.0)
