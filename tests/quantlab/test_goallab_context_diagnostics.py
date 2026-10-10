from __future__ import annotations

import logging
from datetime import UTC, datetime

import pytest

from h2h.quantlab.goal_lab import model


def test_scoring_context_progress_does_not_change_results_or_log_row_payload(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_marker = "raw-provider-payload-must-not-be-logged"
    rows = tuple({"fixture_id": secret_marker, "raw_payload": secret_marker} for _ in range(2_000))
    monkeypatch.setattr(model, "_peak_rss_bytes", lambda: 123_456)

    expected = model._build_scoring_context(rows)
    with caplog.at_level(logging.INFO, logger=model.LOGGER.name):
        actual = model._build_scoring_context(rows, diagnostics=True)

    assert actual == expected
    assert "stage=scoring_context_progress processed=2000 total=2000" in caplog.text
    assert "peak_rss_bytes=123456" in caplog.text
    assert secret_marker not in caplog.text


def test_scoring_context_failure_reports_class_without_payload(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_marker = "raw-provider-payload-must-not-be-logged"

    class Repository:
        def goal_scoring_history(self, *, before: datetime, limit: int):
            assert before == datetime(2026, 10, 10, 16, tzinfo=UTC)
            assert limit == model.HISTORY_LIMIT
            return ({"raw_payload": secret_marker},)

        def goal_model_contract(self, model_version: str):
            assert model_version == "approved-model"
            return {"model_version": model_version}

    def failed_context(*_args, **_kwargs):
        raise MemoryError(secret_marker)

    monkeypatch.setattr(model, "_build_scoring_context", failed_context)
    monkeypatch.setattr(model, "_peak_rss_bytes", lambda: 654_321)

    service = model.GoalStructuralModelService(
        Repository(), artifact_model_version="approved-model"
    )
    with caplog.at_level(logging.INFO, logger=model.LOGGER.name), pytest.raises(MemoryError):
        service.readiness(decision_at=datetime(2026, 10, 10, 16, tzinfo=UTC))

    assert "stage=scoring_context_started rows=1 peak_rss_bytes=654321" in caplog.text
    assert "stage=scoring_context_failed error_class=MemoryError" in caplog.text
    assert secret_marker not in caplog.text
