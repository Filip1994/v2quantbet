import json
import logging

from h2h.logging_config import JsonFormatter


def test_json_formatter_exposes_opportunity_diagnostics() -> None:
    record = logging.LogRecord(
        "quantbet.opportunity",
        logging.INFO,
        __file__,
        1,
        "opportunity cycle outcomes",
        (),
        None,
    )
    record.item_retry_deferred = 7
    record.fresh_market_count = 3
    record.stale_market_count = 5
    record.hard_stale_market_count = 2
    record.live_corroborations = 1
    record.live_proxy_rejections = 1
    record.no_valid_quote_count = 4

    payload = json.loads(JsonFormatter().format(record))

    assert payload["item_retry_deferred"] == 7
    assert payload["fresh_market_count"] == 3
    assert payload["stale_market_count"] == 5
    assert payload["hard_stale_market_count"] == 2
    assert payload["live_corroborations"] == 1
    assert payload["live_proxy_rejections"] == 1
    assert payload["no_valid_quote_count"] == 4
