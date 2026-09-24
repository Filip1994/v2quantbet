import json
import logging

from h2h.logging_config import JsonFormatter


def test_json_formatter_exposes_opportunity_and_model_diagnostics() -> None:
    record = logging.LogRecord(
        "quantbet.opportunity",
        logging.INFO,
        __file__,
        1,
        "cycle",
        (),
        None,
    )
    record.model_training_deferred = 7
    record.hard_stale_market_count = 3
    record.live_corroborations = 2
    record.item_retry_deferred = 4
    record.activated_model_scopes = 1
    record.model_scope = "api-football:api-football:140:2026"

    payload = json.loads(JsonFormatter().format(record))

    assert payload["model_training_deferred"] == 7
    assert payload["hard_stale_market_count"] == 3
    assert payload["live_corroborations"] == 2
    assert payload["item_retry_deferred"] == 4
    assert payload["activated_model_scopes"] == 1
    assert payload["model_scope"] == "api-football:api-football:140:2026"
