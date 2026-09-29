from __future__ import annotations

import h2h.quantlab.collector_entrypoint as entrypoint


def test_collector_entrypoint_enables_collector_only_one_shot(monkeypatch) -> None:
    called: list[bool] = []
    monkeypatch.delenv("QUANTBET_QUANTLAB_COLLECTOR_ONLY", raising=False)
    monkeypatch.delenv("QUANTBET_QUANTLAB_ONE_SHOT", raising=False)
    monkeypatch.setattr(entrypoint, "quantlab_main", lambda: called.append(True))

    entrypoint.main()

    assert called == [True]
    assert entrypoint.os.environ["QUANTBET_QUANTLAB_COLLECTOR_ONLY"] == "true"
    assert entrypoint.os.environ["QUANTBET_QUANTLAB_ONE_SHOT"] == "true"


def test_collector_entrypoint_preserves_explicit_overrides(monkeypatch) -> None:
    called: list[bool] = []
    monkeypatch.setenv("QUANTBET_QUANTLAB_COLLECTOR_ONLY", "false")
    monkeypatch.setenv("QUANTBET_QUANTLAB_ONE_SHOT", "false")
    monkeypatch.setattr(entrypoint, "quantlab_main", lambda: called.append(True))

    entrypoint.main()

    assert called == [True]
    assert entrypoint.os.environ["QUANTBET_QUANTLAB_COLLECTOR_ONLY"] == "false"
    assert entrypoint.os.environ["QUANTBET_QUANTLAB_ONE_SHOT"] == "false"


class _Cursor:
    def __init__(self, acquired: bool = True) -> None:
        self.acquired = acquired
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, query, params):
        self.executed.append((query, params))

    def fetchone(self):
        return (self.acquired,)


class _Connection:
    def __init__(self, acquired: bool = True) -> None:
        self.cursor_instance = _Cursor(acquired)
        self.closed = False

    def cursor(self):
        return self.cursor_instance

    def close(self):
        self.closed = True


def test_collector_entrypoint_skips_when_prior_cycle_owns_lock(monkeypatch) -> None:
    called: list[bool] = []
    monkeypatch.setenv("DATABASE_URL", "postgresql://example.invalid/quantbet")
    monkeypatch.setattr(entrypoint, "_try_collector_lock", lambda: False)
    monkeypatch.setattr(entrypoint, "quantlab_main", lambda: called.append(True))

    entrypoint.main()

    assert called == []


def test_collector_entrypoint_releases_owned_lock(monkeypatch) -> None:
    called: list[bool] = []
    released: list[object] = []
    connection = _Connection()
    monkeypatch.setenv("DATABASE_URL", "postgresql://example.invalid/quantbet")
    monkeypatch.setattr(entrypoint, "_try_collector_lock", lambda: connection)
    monkeypatch.setattr(entrypoint, "_release_collector_lock", released.append)
    monkeypatch.setattr(entrypoint, "quantlab_main", lambda: called.append(True))

    entrypoint.main()

    assert called == [True]
    assert released == [connection]
