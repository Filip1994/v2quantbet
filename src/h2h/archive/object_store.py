"""Small dependency-free S3 client for Railway Buckets.

Railway Buckets are S3-compatible. Keeping this client stdlib-only avoids changing the
locked Python dependency graph just to archive immutable JSON payloads.
"""

from __future__ import annotations

import gzip
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Iterable
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class S3ObjectStoreConfig:
    bucket: str
    access_key_id: str
    secret_access_key: str
    region: str
    endpoint: str

    @classmethod
    def from_environment(cls) -> "S3ObjectStoreConfig":
        def first(*names: str) -> str:
            for name in names:
                value = os.getenv(name, "").strip()
                if value:
                    return value
            return ""

        config = cls(
            bucket=first("BUCKET", "AWS_S3_BUCKET"),
            access_key_id=first("ACCESS_KEY_ID", "AWS_ACCESS_KEY_ID"),
            secret_access_key=first("SECRET_ACCESS_KEY", "AWS_SECRET_ACCESS_KEY"),
            region=first("REGION", "AWS_REGION", "AWS_DEFAULT_REGION") or "auto",
            endpoint=first("ENDPOINT", "AWS_ENDPOINT_URL", "AWS_S3_ENDPOINT"),
        )
        missing = [
            name
            for name, value in (
                ("BUCKET", config.bucket),
                ("ACCESS_KEY_ID", config.access_key_id),
                ("SECRET_ACCESS_KEY", config.secret_access_key),
                ("ENDPOINT", config.endpoint),
            )
            if not value
        ]
        if missing:
            raise ValueError("Missing object-store configuration: " + ", ".join(missing))
        return config


class S3ObjectStore:
    """Put/get immutable objects using AWS Signature V4."""

    def __init__(self, config: S3ObjectStoreConfig) -> None:
        self.config = config
        parsed = urlsplit(config.endpoint.rstrip("/"))
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("ENDPOINT must be an absolute http(s) URL")
        self._scheme = parsed.scheme
        self._endpoint_host = parsed.netloc
        self._endpoint_path = parsed.path.rstrip("/")

    @classmethod
    def from_environment(cls) -> "S3ObjectStore":
        return cls(S3ObjectStoreConfig.from_environment())

    def _host(self) -> str:
        # Railway's current buckets use virtual-hosted style.
        if self._endpoint_host.startswith(self.config.bucket + "."):
            return self._endpoint_host
        return f"{self.config.bucket}.{self._endpoint_host}"

    def _canonical_uri(self, key: str) -> str:
        if not key or key.startswith("/"):
            raise ValueError("object key must be non-empty and relative")
        prefix = self._endpoint_path
        return (prefix + "/" if prefix else "/") + quote(key, safe="/-_.~")

    @staticmethod
    def _sign(key: bytes, value: str) -> bytes:
        return hmac.new(key, value.encode(), hashlib.sha256).digest()

    def _authorization(
        self,
        *,
        method: str,
        canonical_uri: str,
        payload_hash: str,
        now: datetime,
        extra_headers: dict[str, str] | None = None,
    ) -> tuple[str, dict[str, str]]:
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")
        headers = {
            "host": self._host(),
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amz_date,
        }
        if extra_headers:
            for key, value in extra_headers.items():
                headers[key.lower().strip()] = " ".join(value.strip().split())

        ordered = sorted(headers.items())
        canonical_headers = "".join(f"{key}:{value}\n" for key, value in ordered)
        signed_headers = ";".join(key for key, _ in ordered)
        canonical_request = "\n".join(
            [
                method,
                canonical_uri,
                "",
                canonical_headers,
                signed_headers,
                payload_hash,
            ]
        )
        scope = f"{date_stamp}/{self.config.region}/s3/aws4_request"
        string_to_sign = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                amz_date,
                scope,
                hashlib.sha256(canonical_request.encode()).hexdigest(),
            ]
        )
        date_key = self._sign(("AWS4" + self.config.secret_access_key).encode(), date_stamp)
        region_key = self._sign(date_key, self.config.region)
        service_key = self._sign(region_key, "s3")
        signing_key = self._sign(service_key, "aws4_request")
        signature = hmac.new(
            signing_key, string_to_sign.encode(), hashlib.sha256
        ).hexdigest()
        authorization = (
            "AWS4-HMAC-SHA256 "
            f"Credential={self.config.access_key_id}/{scope},"
            f"SignedHeaders={signed_headers},Signature={signature}"
        )
        request_headers = {
            "Host": headers["host"],
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amz_date,
            "Authorization": authorization,
        }
        if extra_headers:
            request_headers.update(extra_headers)
        return authorization, request_headers

    def _request(
        self,
        method: str,
        key: str,
        *,
        body: bytes = b"",
        extra_headers: dict[str, str] | None = None,
    ) -> bytes:
        uri = self._canonical_uri(key)
        payload_hash = hashlib.sha256(body).hexdigest()
        _, headers = self._authorization(
            method=method,
            canonical_uri=uri,
            payload_hash=payload_hash,
            now=datetime.now(UTC),
            extra_headers=extra_headers,
        )
        url = f"{self._scheme}://{self._host()}{uri}"
        request = Request(url, data=body if method in {"PUT", "POST"} else None, method=method)
        for name, value in headers.items():
            request.add_header(name, value)
        try:
            with urlopen(request, timeout=60) as response:
                return response.read()
        except HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:500]
            raise RuntimeError(f"S3 {method} failed status={exc.code}: {detail}") from exc

    def put_bytes(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
        content_encoding: str | None = None,
    ) -> str:
        digest = hashlib.sha256(data).hexdigest()
        headers = {
            "Content-Type": content_type,
            "x-amz-meta-sha256": digest,
        }
        if content_encoding:
            headers["Content-Encoding"] = content_encoding
        self._request("PUT", key, body=data, extra_headers=headers)
        return digest

    def get_bytes(self, key: str) -> bytes:
        return self._request("GET", key)

    def put_jsonl_gzip(self, key: str, rows: Iterable[dict[str, Any]]) -> tuple[str, int, int]:
        raw_lines = [
            json.dumps(row, sort_keys=True, separators=(",", ":"), default=str).encode() + b"\n"
            for row in rows
        ]
        raw = b"".join(raw_lines)
        compressed = gzip.compress(raw, compresslevel=6, mtime=0)
        digest = self.put_bytes(
            key,
            compressed,
            content_type="application/x-ndjson",
            content_encoding="gzip",
        )
        return digest, len(raw_lines), len(compressed)

    def get_jsonl_gzip(self, key: str) -> tuple[dict[str, Any], ...]:
        raw = gzip.decompress(self.get_bytes(key))
        return tuple(
            json.loads(line)
            for line in raw.splitlines()
            if line.strip()
        )
