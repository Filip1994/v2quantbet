from __future__ import annotations

import gzip
import hashlib
import json
from datetime import UTC, datetime

import pytest

from h2h.archive.object_store import S3ObjectStoreConfig
from h2h.archive.repository import ColdArchiveReader
from h2h.archive.service import ColdArchiveWriter


class FakeStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_bytes(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
        content_encoding: str | None = None,
    ) -> str:
        del content_type, content_encoding
        self.objects[key] = data
        return hashlib.sha256(data).hexdigest()

    def get_bytes(self, key: str) -> bytes:
        return self.objects[key]

    def get_jsonl_gzip(self, key: str):
        raw = gzip.decompress(self.objects[key])
        return tuple(json.loads(line) for line in raw.splitlines() if line)


class FakeCatalog:
    def __init__(self) -> None:
        self.registered: list[dict] = []

    def register_verified_batch(self, **kwargs):
        self.registered.append(kwargs)
        return "cold-archive-v1:test"

    def list_batches(self, dataset: str, *, start=None, end=None):
        del start, end
        return tuple(
            {
                "dataset": dataset,
                "object_key": row["object_key"],
                "row_count": row["row_count"],
            }
            for row in self.registered
            if row["dataset"] == dataset
        )


def test_bucket_config_supports_railway_variables(monkeypatch):
    monkeypatch.setenv("BUCKET", "durable-barrel-test")
    monkeypatch.setenv("ACCESS_KEY_ID", "access")
    monkeypatch.setenv("SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("REGION", "auto")
    monkeypatch.setenv("ENDPOINT", "https://example.storageapi.dev")

    config = S3ObjectStoreConfig.from_environment()

    assert config.bucket == "durable-barrel-test"
    assert config.endpoint == "https://example.storageapi.dev"


def test_bucket_config_rejects_missing_credentials(monkeypatch):
    for name in (
        "BUCKET",
        "ACCESS_KEY_ID",
        "SECRET_ACCESS_KEY",
        "ENDPOINT",
        "AWS_S3_BUCKET",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_ENDPOINT_URL",
    ):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ValueError, match="Missing object-store configuration"):
        S3ObjectStoreConfig.from_environment()


def test_verified_writer_and_research_reader_round_trip():
    store = FakeStore()
    catalog = FakeCatalog()
    writer = ColdArchiveWriter(catalog, store)
    recorded_at = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    rows = (
        {"id": "one", "recorded_at": recorded_at, "raw_payload": {"a": 1}},
        {"id": "two", "recorded_at": recorded_at, "raw_payload": {"b": 2}},
    )

    result = writer.archive_rows(
        "quantlab/raw",
        rows,
        recorded_at_field="recorded_at",
        metadata={"source": "test"},
    )

    assert result["row_count"] == 2
    assert result["object_key"].startswith("quantbet-cold/quantlab/raw/")
    assert catalog.registered[0]["content_sha256"] == result["content_sha256"]

    reader = ColdArchiveReader(catalog, store)
    restored = reader.rows("quantlab/raw")

    assert [row["id"] for row in restored] == ["one", "two"]
    assert restored[0]["raw_payload"] == {"a": 1}


def test_writer_uses_content_addressed_object_key_for_retries():
    store = FakeStore()
    catalog = FakeCatalog()
    writer = ColdArchiveWriter(catalog, store)
    recorded_at = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    rows = ({"id": "one", "recorded_at": recorded_at, "raw_payload": {"a": 1}},)

    first = writer.archive_rows("quantlab/raw", rows, recorded_at_field="recorded_at")
    second = writer.archive_rows("quantlab/raw", rows, recorded_at_field="recorded_at")

    assert first["object_key"] == second["object_key"]
    assert first["content_sha256"] == second["content_sha256"]
    assert first["object_key"].startswith("quantbet-cold/quantlab/raw/2026/09/01/")
