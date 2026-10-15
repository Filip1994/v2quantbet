from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from h2h.quant.dixon_coles import DixonColesFitError, DixonColesModel


FIXTURE = Path(__file__).parents[1] / "fixtures" / "dc_510_2026_sanitized.json"


def training_records():
    payload = json.loads(FIXTURE.read_text())
    records = [SimpleNamespace(**{**row, "date": datetime.fromisoformat(row["date"])})
               for row in payload["records"]]
    return records, datetime.fromisoformat(payload["reference_time"])


def test_sanitized_510_2026_converges_with_valid_corrections() -> None:
    records, reference = training_records()
    assert len(records) == 99
    model = DixonColesModel.fit(records, team_id_namespace="api-football",
                                reference_time=reference, xi=0.0018, ridge=0.01,
                                min_matches=80)
    assert model.fitted_matches == 99
    assert np.isfinite(model.objective)
    assert abs(model.rho) <= 0.1
    assert model.optimizer_fallback is None
    for home in model.team_ids:
        for away in model.team_ids:
            if home != away:
                matrix = model.score_matrix(home, away)
                assert np.isfinite(matrix).all()


def test_insufficient_sample_is_rejected() -> None:
    records, reference = training_records()
    with pytest.raises(DixonColesFitError, match="Premalo"):
        DixonColesModel.fit(records[:79], team_id_namespace="api-football",
                            reference_time=reference, xi=0.0018, min_matches=80)


def test_malformed_score_is_rejected_before_optimization() -> None:
    records, reference = training_records()
    records[0].home_goals = -1
    with pytest.raises(DixonColesFitError, match="invalid team or score"):
        DixonColesModel.fit(records, team_id_namespace="api-football",
                            reference_time=reference, xi=0.0018, min_matches=80)


def test_optimizer_failure_cannot_return_a_model(monkeypatch) -> None:
    records, reference = training_records()
    def failed_minimize(*_args, **_kwargs):
        return SimpleNamespace(success=False, status=2, message="ABNORMAL", nit=8,
                               fun=275.8, jac=np.ones(37))
    monkeypatch.setattr("h2h.quant.dixon_coles.minimize", failed_minimize)
    with pytest.raises(DixonColesFitError, match="ABNORMAL") as caught:
        DixonColesModel.fit(records, team_id_namespace="api-football",
                            reference_time=reference, xi=0.0018, min_matches=80)
    assert caught.value.optimizer_status == 2
    assert caught.value.optimizer_iterations == 8
