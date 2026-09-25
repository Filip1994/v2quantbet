import pytest

from h2h.persistence.postgres_research_signals import research_signal_id


def test_research_signal_id_is_deterministic_from_evaluation_id() -> None:
    suffix = "a" * 64
    assert research_signal_id("value-evaluation-v1:" + suffix) == "research-signal-v1:" + suffix


@pytest.mark.parametrize("value", ["", "value-evaluation-v1:nope", "pick-v1:" + "a" * 64])
def test_research_signal_id_rejects_non_evaluation_identifiers(value: str) -> None:
    with pytest.raises(ValueError):
        research_signal_id(value)
