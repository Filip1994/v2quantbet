"""Retry policy for transient JSON transport failures."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from time import sleep
from typing import Any

from .http import (
    JsonTransport,
    TransportError,
    TransportResponseError,
    TransportTimeoutError,
)


@dataclass(frozen=True)
class RetryingJsonTransport:
    """Retry timeout and generic transport failures with bounded attempts."""

    transport: JsonTransport
    max_attempts: int = 3
    backoff_seconds: float = 0.0
    sleeper: Callable[[float], None] = sleep

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least one")
        if self.backoff_seconds < 0:
            raise ValueError("backoff_seconds must not be negative")

    def get_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float = 10.0,
    ) -> Mapping[str, Any]:
        last_error: TransportError | None = None
        for attempt in range(self.max_attempts):
            try:
                return self.transport.get_json(
                    url,
                    headers=headers,
                    timeout=timeout,
                )
            except TransportResponseError:
                raise
            except (TransportTimeoutError, TransportError) as exc:
                last_error = exc
                if attempt + 1 < self.max_attempts:
                    self.sleeper(self.backoff_seconds * (2**attempt))
        assert last_error is not None
        raise last_error
