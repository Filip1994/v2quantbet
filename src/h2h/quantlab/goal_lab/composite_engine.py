"""Run GoalLab control and DC+ structural evaluation side by side."""

from __future__ import annotations

from typing import Any

from h2h.quantlab.goal_lab.shadow_engine import GoalEngineResult


class GoalLabCompositeEngine:
    """Preserve plain DC control audit while running structural DC+ independently."""

    def __init__(self, control_engine: Any, structural_engine: Any) -> None:
        self._control = control_engine
        self._structural = structural_engine

    def run_fixture(self, fixture: dict[str, Any], *, decision_at) -> GoalEngineResult:
        control = self._control.run_fixture(fixture, decision_at=decision_at)
        structural = self._structural.run_fixture(fixture, decision_at=decision_at)
        return GoalEngineResult(
            decisions_inserted=(
                int(control.decisions_inserted) + int(structural.decisions_inserted)
            ),
            picks_inserted=(
                int(control.picks_inserted) + int(structural.picks_inserted)
            ),
        )
