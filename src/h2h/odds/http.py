"""Small, provider-neutral HTTP transport boundary."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class TransportError(RuntimeError):
    """Base error for transport-level failures."""


class TransportTimeoutError(TransportError):
    """Raised when the provider request exceeds its timeout."""


class TransportResponseError(TransportError):
    """Raised when the provider returns an invalid HTTP or JSON response."""


class JsonTransport(Protocol):
    """Protocol consumed by provider adapters."""

    def get_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float = 10.0,
    ) -> Mapping[str, Any]:
        """Fetch and decode one JSON object."""


@dataclass(frozen=True)
class UrllibJsonTransport:
    """stdlib-backed JSON transport with explicit timeout handling."""

    user_agent: str = "quantbet/1.0"

    def get_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float = 10.0,
    ) -> Mapping[str, Any]:
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")

        request_headers = {"User-Agent": self.user_agent, **(headers or {})}
        request = Request(url, headers=request_headers, method="GET")
        try:
            with urlopen(request, timeout=timeout) as response:  # noqa: S310
                raw = response.read()
        except TimeoutError as exc:
            raise TransportTimeoutError(f"request timed out: {url}") from exc
        except HTTPError as exc:
            raise TransportResponseError(
                f"provider returned HTTP {exc.code} for {url}"
            ) from exc
        except URLError as exc:
            raise TransportError(f"transport request failed: {url}") from exc

        try:
            payload = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise TransportResponseError("provider returned invalid JSON") from exc
        if not isinstance(payload, Mapping):
            raise TransportResponseError("provider JSON response must be an object")
        return payload
