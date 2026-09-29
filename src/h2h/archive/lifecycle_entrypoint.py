"""One-shot Durable Barrel lifecycle entrypoint."""

from __future__ import annotations

import json

from h2h.archive.lifecycle import ArchiveLifecycleService
from h2h.archive.object_store import S3ObjectStore
from h2h.archive.repository import ColdArchiveCatalog


def main() -> None:
    result = ArchiveLifecycleService(
        ColdArchiveCatalog(),
        S3ObjectStore.from_environment(),
    ).run()
    print("ARCHIVE_LIFECYCLE " + json.dumps(result, default=str, separators=(",", ":")))


if __name__ == "__main__":
    main()
