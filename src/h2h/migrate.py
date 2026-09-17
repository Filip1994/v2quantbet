"""Explicit Railway pre-deploy migration command."""

from pathlib import Path
import os

from h2h.persistence.migrations import apply_migrations
from h2h.persistence.postgres_runtime import PostgreSQLRuntimeRepository


def main() -> None:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")
    repository = PostgreSQLRuntimeRepository(database_url)
    migration_dir = Path(__file__).resolve().parents[2] / "migrations"
    with repository.connect() as connection:
        applied = apply_migrations(connection, migration_dir)
    print(f"applied {len(applied)} migration(s)")


if __name__ == "__main__":
    main()
