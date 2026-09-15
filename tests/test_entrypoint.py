import pytest

from h2h.domain.fixture_identity import api_football_fixture_identity
from h2h.entrypoint import _fixture_identities_from_environment


def test_manual_fixture_allowlist_resolves_api_football_canonical_identities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QUANTBET_FIXTURE_IDS", "123, 456")

    assert _fixture_identities_from_environment() == (
        api_football_fixture_identity(123),
        api_football_fixture_identity(456),
    )


@pytest.mark.parametrize("value", ["0", "-1", "raw-id"])
def test_manual_fixture_allowlist_rejects_invalid_provider_ids(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    monkeypatch.setenv("QUANTBET_FIXTURE_IDS", value)

    with pytest.raises(ValueError, match="positive integers|contain integers"):
        _fixture_identities_from_environment()
