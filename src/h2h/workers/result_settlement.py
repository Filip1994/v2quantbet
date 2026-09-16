"""Restart-safe Task #12 result and settlement worker."""

from dataclasses import dataclass

from h2h.use_cases.result_settlement import ReconcileFixtureResults, ResultCycle


@dataclass(frozen=True, slots=True)
class ResultSettlementWorker:
    reconcile: ReconcileFixtureResults

    def run_once(self) -> ResultCycle:
        return self.reconcile.execute()
