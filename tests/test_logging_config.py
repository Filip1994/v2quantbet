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
    record.market = "BTTS"
    record.selection = "YES"
    record.preliminary_odds = 2.05
    record.preliminary_edge = 0.041
    record.preliminary_ev = 0.028
    record.rejection_reasons = ("EDGE_BELOW_MINIMUM",)
    record.open_exposure_minor = 300000
    record.fixed_stake_minor = 30000
    record.max_open_exposure_minor = 300000
    record.available_bankroll_minor = 2700000
    record.risk_reserved_pick_count = 10
    record.risk_reserved_played_count = 8
    record.risk_reserved_skipped_count = 2
    record.risk_reserved_played_minor = 240000
    record.risk_reserved_skipped_minor = 60000
    record.risk_reserved_monitoring_count = 6
    record.risk_reserved_closed_for_odds_count = 3
    record.risk_reserved_without_monitoring_count = 1
    record.selection_seconds = 0.12
    record.model_gate_seconds = 0.34
    record.preliminary_fetch_seconds = 4.56
    record.quote_processing_seconds = 1.23
    record.prediction_seconds = 2.34
    record.evaluation_seconds = 3.45
    record.registration_seconds = 4.56
    record.final_fetch_seconds = 5.67
    record.failure_flush_seconds = 0.11

    payload = json.loads(JsonFormatter().format(record))

    assert payload["item_retry_deferred"] == 7
    assert payload["fresh_market_count"] == 3
    assert payload["stale_market_count"] == 5
    assert payload["hard_stale_market_count"] == 2
    assert payload["live_corroborations"] == 1
    assert payload["live_proxy_rejections"] == 1
    assert payload["no_valid_quote_count"] == 4
    assert payload["market"] == "BTTS"
    assert payload["selection"] == "YES"
    assert payload["preliminary_odds"] == 2.05
    assert payload["preliminary_edge"] == 0.041
    assert payload["preliminary_ev"] == 0.028
    assert payload["rejection_reasons"] == ["EDGE_BELOW_MINIMUM"]
    assert payload["open_exposure_minor"] == 300000
    assert payload["fixed_stake_minor"] == 30000
    assert payload["max_open_exposure_minor"] == 300000
    assert payload["available_bankroll_minor"] == 2700000
    assert payload["risk_reserved_pick_count"] == 10
    assert payload["risk_reserved_played_count"] == 8
    assert payload["risk_reserved_skipped_count"] == 2
    assert payload["risk_reserved_played_minor"] == 240000
    assert payload["risk_reserved_skipped_minor"] == 60000
    assert payload["risk_reserved_monitoring_count"] == 6
    assert payload["risk_reserved_closed_for_odds_count"] == 3
    assert payload["risk_reserved_without_monitoring_count"] == 1
    assert payload["selection_seconds"] == 0.12
    assert payload["model_gate_seconds"] == 0.34
    assert payload["preliminary_fetch_seconds"] == 4.56
    assert payload["quote_processing_seconds"] == 1.23
    assert payload["prediction_seconds"] == 2.34
    assert payload["evaluation_seconds"] == 3.45
    assert payload["registration_seconds"] == 4.56
    assert payload["final_fetch_seconds"] == 5.67
    assert payload["failure_flush_seconds"] == 0.11
