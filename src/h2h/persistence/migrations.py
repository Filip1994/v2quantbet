"""Small, provider-neutral migration runner for SQL files."""

from collections.abc import Iterable
from pathlib import Path
from typing import Any


_MIGRATION_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""


def apply_migrations(connection: Any, migration_dir: str | Path) -> tuple[str, ...]:
    """Apply pending ``*.sql`` files in lexical order.

    The supplied connection must support context-manager transactions and a
    DB-API cursor. Each migration is recorded only after its SQL succeeds.
    """
    directory = Path(migration_dir)
    migrations = tuple(sorted(directory.glob("*.sql")))
    applied: list[str] = []

    with connection, connection.cursor() as cursor:
        cursor.execute(_MIGRATION_TABLE_SQL)
        cursor.execute("SELECT version FROM schema_migrations")
        completed = {row[0] for row in cursor.fetchall()}

        for migration in migrations:
            version = migration.name
            if version in completed:
                continue
            sql = migration.read_text(encoding="utf-8")
            cursor.execute(sql)
            cursor.execute(
                "INSERT INTO schema_migrations (version) VALUES (%s)",
                (version,),
            )
            applied.append(version)

    return tuple(applied)
