from types import SimpleNamespace

from h2h.workers.registered_pick_monitoring import RegisteredPickMonitoringWorker


class Operation:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def execute(self):
        self.calls += 1
        return self.result


def test_worker_reconciles_before_refreshing() -> None:
    order = []

    class Reconcile:
        def execute(self):
            order.append("reconcile")
            return SimpleNamespace(started_pick_ids=(), finalized_pick_ids=())

    class Refresh:
        def execute(self):
            order.append("refresh")
            return SimpleNamespace(persisted_snapshot_count=0)

    result = RegisteredPickMonitoringWorker(Reconcile(), Refresh()).run_once()
    assert order == ["reconcile", "refresh"]
    assert result.refresh.persisted_snapshot_count == 0
