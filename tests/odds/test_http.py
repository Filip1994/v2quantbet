import json
from io import BytesIO
from unittest.mock import patch

import pytest

from h2h.odds.http import (
    TransportResponseError,
    TransportTimeoutError,
    UrllibJsonTransport,
)


def test_get_json_decodes_object_and_merges_headers() -> None:
    response = BytesIO(json.dumps({"response": []}).encode())
    response.__enter__ = lambda: response
    response.__exit__ = lambda *args: None

    with patch("h2h.odds.http.urlopen", return_value=response) as opener:
        payload = UrllibJsonTransport().get_json(
            "https://example.test/odds", headers={"x-apisports-key": "secret"}
        )

    assert payload == {"response": []}
    request = opener.call_args.args[0]
    assert request.get_header("X-apisports-key") == "secret"
    opener.assert_called_once()


def test_invalid_json_raises_response_error() -> None:
    response = BytesIO(b"not-json")
    response.__enter__ = lambda: response
    response.__exit__ = lambda *args: None

    with patch("h2h.odds.http.urlopen", return_value=response):
        with pytest.raises(TransportResponseError, match="invalid JSON"):
            UrllibJsonTransport().get_json("https://example.test/odds")


def test_non_object_json_raises_response_error() -> None:
    response = BytesIO(b"[]")
    response.__enter__ = lambda: response
    response.__exit__ = lambda *args: None

    with patch("h2h.odds.http.urlopen", return_value=response):
        with pytest.raises(TransportResponseError, match="must be an object"):
            UrllibJsonTransport().get_json("https://example.test/odds")


def test_timeout_is_mapped() -> None:
    with patch("h2h.odds.http.urlopen", side_effect=TimeoutError):
        with pytest.raises(TransportTimeoutError):
            UrllibJsonTransport().get_json("https://example.test/odds")


def test_timeout_must_be_positive() -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        UrllibJsonTransport().get_json("https://example.test/odds", timeout=0)
