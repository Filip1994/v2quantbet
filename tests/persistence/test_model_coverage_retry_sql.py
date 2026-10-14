from __future__ import annotations

from datetime import UTC, datetime

from h2h.domain.model_coverage import ProductionTrainingPolicy
from h2h.domain.model_lifecycle import DixonColesModelScope
from h2h.persistence.postgres_model_coverage import PostgreSQLModelCoverageRepository
from h2h.quant.dixon_coles import DixonColesFitError


class Cursor:
    def __init__(self):
        self.commands = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, query, params=()):
        assert query.count("%s") == len(params)
        self.commands.append((query, params))

    def fetchall(self):
        return []


class Connection:
    def __init__(self):
        self.cursors = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def cursor(self):
        cursor = Cursor()
        self.cursors.append(cursor)
        return cursor


def test_refresh_keeps_failed_retrain_backoff_and_resets_on_policy_change():
    connection = Connection()
    repository = PostgreSQLModelCoverageRepository(connect=lambda: connection)
    policy = ProductionTrainingPolicy()
    repository.refresh_inventory(policy,
                                 now=datetime(2026, 10, 14, tzinfo=UTC))
    queries = [query for cursor in connection.cursors for query, _ in cursor.commands]
    assert "c.status NOT IN ('TRAINING_FAILED', 'INSUFFICIENT_DATA', 'TRAINING_PENDING')" in queries[2]
    assert "policy_fingerprint <> %s AND policy_fingerprint <> %s" in queries[3]
    assert "failure_streak = CASE WHEN" in queries[3]
    params = connection.cursors[0].commands[3][1]
    assert params[0] == policy.fingerprint
    assert params[1] == policy.previous_trainer_policy_fingerprint
    assert params[0] != params[1]


def test_failure_update_is_scope_local_and_retains_active_pointer():
    connection = Connection()
    repository = PostgreSQLModelCoverageRepository(connect=lambda: connection)
    error = DixonColesFitError("ABNORMAL")
    error.dataset_sha256 = "a" * 64
    scope = DixonColesModelScope("api-football", "api-football", 510, 2026)
    repository.mark_failed(scope, error, duration_seconds=1.0,
                           now=datetime(2026, 10, 14, tzinfo=UTC))
    query, params = connection.cursors[0].commands[0]
    assert "active_model_version_id = COALESCE(%s, active_model_version_id)" in query
    assert "failure_streak + 1" in query
    assert params[-4:] == ("api-football", "api-football", 510, 2026)


def test_unchanged_dataset_check_does_not_increment_fit_failure_streak():
    connection = Connection()
    repository = PostgreSQLModelCoverageRepository(connect=lambda: connection)
    error = DixonColesFitError("unchanged dataset")
    error.dataset_sha256 = "a" * 64
    scope = DixonColesModelScope("api-football", "api-football", 510, 2026)
    repository.mark_failed(scope, error, duration_seconds=0.1,
                           now=datetime(2026, 10, 14, tzinfo=UTC),
                           count_fit_failure=False)
    _, params = connection.cursors[0].commands[0]
    assert all(params[index] is None for index in (12, 13, 15, 16, 17))
