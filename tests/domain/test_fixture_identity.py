import pytest

from h2h.domain.fixture_identity import (
    ProviderFixtureReference,
    ResolvedFixtureIdentity,
    api_football_fixture_identity,
    api_football_provider_fixture_id,
)


def test_api_football_fixture_identity_has_separate_canonical_and_provider_ids() -> None:
    identity = api_football_fixture_identity(123)

    assert identity.fixture_id == "api-football:123"
    assert identity.provider_reference == ProviderFixtureReference(
        provider="api-football",
        provider_fixture_id="123",
    )
    assert api_football_provider_fixture_id(identity) == 123


def test_provider_namespaces_do_not_collide() -> None:
    api_football = ProviderFixtureReference("api-football", "123")
    another_provider = ProviderFixtureReference("another-provider", "123")

    assert api_football != another_provider
    assert len({api_football, another_provider}) == 2


def test_resolved_identity_rejects_mismatched_canonical_id() -> None:
    with pytest.raises(ValueError, match="does not match"):
        ResolvedFixtureIdentity(
            fixture_id="123",
            provider_reference=ProviderFixtureReference("api-football", "123"),
        )


@pytest.mark.parametrize("provider_fixture_id", [0, -1, True, 1.0, "1"])
def test_api_football_fixture_identity_requires_positive_integer(
    provider_fixture_id: object,
) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        api_football_fixture_identity(provider_fixture_id)  # type: ignore[arg-type]
