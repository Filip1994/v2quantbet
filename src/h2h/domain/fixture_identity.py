"""Canonical fixture identity bound to an explicit provider reference."""

from dataclasses import dataclass


API_FOOTBALL_PROVIDER = "api-football"


@dataclass(frozen=True, slots=True)
class ProviderFixtureReference:
    """One fixture identifier inside a named provider namespace."""

    provider: str
    provider_fixture_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.provider, str) or not isinstance(
            self.provider_fixture_id, str
        ):
            raise TypeError("provider and provider_fixture_id must be strings")
        if not self.provider.strip() or not self.provider_fixture_id.strip():
            raise ValueError("provider and provider_fixture_id must not be empty")


@dataclass(frozen=True, slots=True)
class ResolvedFixtureIdentity:
    """Canonical fixture ID paired with the provider reference that resolved it."""

    fixture_id: str
    provider_reference: ProviderFixtureReference

    def __post_init__(self) -> None:
        if not isinstance(self.fixture_id, str):
            raise TypeError("fixture_id must be a string")
        if not isinstance(self.provider_reference, ProviderFixtureReference):
            raise TypeError("provider_reference must be a ProviderFixtureReference")
        expected = _canonical_api_football_fixture_id(self.provider_reference)
        if self.fixture_id != expected:
            raise ValueError("fixture_id does not match its provider fixture reference")


def _api_football_id_from_text(value: str) -> int:
    if not value.isascii() or not value.isdecimal():
        raise ValueError("API-Football provider_fixture_id must be a positive integer")
    provider_fixture_id = int(value)
    if provider_fixture_id <= 0 or str(provider_fixture_id) != value:
        raise ValueError("API-Football provider_fixture_id must be a positive integer")
    return provider_fixture_id


def _canonical_api_football_fixture_id(reference: ProviderFixtureReference) -> str:
    if reference.provider != API_FOOTBALL_PROVIDER:
        raise ValueError("unsupported provider fixture namespace")
    provider_fixture_id = _api_football_id_from_text(reference.provider_fixture_id)
    return f"{API_FOOTBALL_PROVIDER}:{provider_fixture_id}"


def api_football_fixture_identity(provider_fixture_id: int) -> ResolvedFixtureIdentity:
    """Allocate the canonical identity for one positive API-Football fixture ID."""
    if (
        isinstance(provider_fixture_id, bool)
        or not isinstance(provider_fixture_id, int)
        or provider_fixture_id <= 0
    ):
        raise ValueError("API-Football fixture ID must be a positive integer")
    reference = ProviderFixtureReference(
        provider=API_FOOTBALL_PROVIDER,
        provider_fixture_id=str(provider_fixture_id),
    )
    return ResolvedFixtureIdentity(
        fixture_id=_canonical_api_football_fixture_id(reference),
        provider_reference=reference,
    )


def api_football_provider_fixture_id(identity: ResolvedFixtureIdentity) -> int:
    """Return the positive numeric transport ID from a resolved API-Football identity."""
    if not isinstance(identity, ResolvedFixtureIdentity):
        raise TypeError("identity must be a ResolvedFixtureIdentity")
    return _api_football_id_from_text(identity.provider_reference.provider_fixture_id)
