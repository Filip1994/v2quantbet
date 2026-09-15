"""Small, provider-neutral HTTP transport boundary."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from time import time
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class TransportError(RuntimeError):
    """Base error for transport-level failures."""


class TransportTimeoutError(TransportError):
    """Raised when the provider request exceeds its timeout."""


class TransportResponseError(TransportError):
    """Raised when the provider returns an invalid HTTP or JSON response."""


class TransportRateLimitError(TransportResponseError):
    """Raised for HTTP 429, retaining the optional retry delay in seconds."""

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


def _parse_retry_after(value: str | None) -> float | None:
    """Parse Retry-After seconds or an HTTP date into a non-negative delay."""
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        try:
            retry_at = parsedate_to_datetime(value).timestamp()
        except (TypeError, ValueError, OverflowError):
            return None
        return max(0.0, retry_at - time())


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

    def __post_init__(self) -> None:
        if not isinstance(self.user_agent, str) or not self.user_agent.strip():
            raise ValueError("user_agent must be a non-empty string")

    def get_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float = 10.0,
    ) -> Mapping[str, Any]:
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
            raise ValueError("timeout must be a positive number")
        if headers is not None:
            if not isinstance(headers, Mapping):
                raise TypeError("headers must be a mapping")
            if any(
                not isinstance(key, str) or not isinstance(value, str)
                for key, value in headers.items()
            ):
                raise TypeError("header names and values must be strings")

        request_headers = {"User-Agent": self.user_agent, **(headers or {})}
        request = Request(url, headers=request_headers, method="GET")
        try:
            with urlopen(request, timeout=timeout) as response:
                raw = response.read()
        except HTTPError as exc:
            if exc.code == 429:
                retry_after = _parse_retry_after(exc.headers.get("Retry-After"))
                raise TransportRateLimitError(
                    f"provider rate limit reached for {url}",
                    retry_after=retry_after,
                ) from exc
            raise TransportResponseError(
                f"provider returned HTTP {exc.code} for {url}"
            ) from exc
        except (TimeoutError, OSError) as exc:
            if isinstance(exc, TimeoutError):
                raise TransportTimeoutError(f"request timed out: {url}") from exc
            raise TransportError(f"transport request failed: {url}") from exc
        except URLError as exc:
            raise TransportError(f"transport request failed: {url}") from exc

        try:
            payload = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise TransportResponseError("provider returned invalid JSON") from exc
        if not isinstance(payload, Mapping):
            raise TransportResponseError("provider JSON response must be an object")
        return payload
