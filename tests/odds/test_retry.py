from unittest.mock import Mock

import pytest

from h2h.odds.http import TransportError, TransportRateLimitError, TransportResponseError
from h2h.odds.retry import RetryingJsonTransport


def test_retries_transient_errors_with_exponential_backoff() -> None:
    transport = Mock()
    transport.get_json.side_effect = [TransportError("temporary"), {"response": []}]
    sleeper = Mock()

    result = RetryingJsonTransport(transport, max_attempts=3, backoff_seconds=0.5, sleeper=sleeper).get_json("url")

    assert result == {"response": []}
    assert transport.get_json.call_count == 2
    sleeper.assert_called_once_with(0.5)


def test_retries_rate_limit_using_retry_after_delay() -> None:
    transport = Mock()
    transport.get_json.side_effect = [
        TransportRateLimitError("limited", retry_after=4.0),
        {"response": []},
    ]
    sleeper = Mock()

    result = RetryingJsonTransport(
        transport,
        max_attempts=3,
        backoff_seconds=0.5,
        sleeper=sleeper,
    ).get_json("url")

    assert result == {"response": []}
    assert transport.get_json.call_count == 2
    sleeper.assert_called_once_with(4.0)


def test_does_not_retry_invalid_provider_response() -> None:
    transport = Mock()
    error = TransportResponseError("bad response")
    transport.get_json.side_effect = error

    with pytest.raises(TransportResponseError):
        RetryingJsonTransport(transport).get_json("url")

    assert transport.get_json.call_count == 1


def test_shutdown_after_backoff_starts_no_new_provider_request() -> None:
    transport = Mock()
    transport.get_json.side_effect = TransportError("temporary")
    stopping = False

    def sleeper(_seconds: float) -> None:
        nonlocal stopping
        stopping = True

    with pytest.raises(TransportError, match="temporary"):
        RetryingJsonTransport(
            transport,
            max_attempts=3,
            backoff_seconds=0.5,
            sleeper=sleeper,
            should_stop=lambda: stopping,
        ).get_json("url")

    assert transport.get_json.call_count == 1


def test_rejects_invalid_policy() -> None:
    with pytest.raises(ValueError):
        RetryingJsonTransport(Mock(), max_attempts=0)
    with pytest.raises(ValueError):
        RetryingJsonTransport(Mock(), backoff_seconds=-1)
