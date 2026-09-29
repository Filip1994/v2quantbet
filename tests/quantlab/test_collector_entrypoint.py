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
