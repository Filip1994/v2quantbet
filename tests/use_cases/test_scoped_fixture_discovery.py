from datetime import UTC, datetime, timedelta

from h2h.domain.fixture import Fixture
from h2h.use_cases.scoped_fixture_discovery import ScopedFixtureDiscovery


class StubDiscovery:
    def __init__(self, fixtures: tuple[Fixture, ...]) -> None:
        self.fixtures = fixtures

    def discover(self, start_at: datetime, end_at: datetime) -> tuple[Fixture, ...]:
        return self.fixtures


def make_fixture(country: str, name: str, competition_type: str = "league") -> Fixture:
    return Fixture(
        fixture_id=f"{country}-{name}",
        home_team="Home",
        away_team="Away",
        competition_id=1,
        competition_name=name,
        country=country,
        kickoff_at=datetime(2026, 1, 1, tzinfo=UTC),
        competition_type=competition_type,
    )


def test_scoped_discovery_keeps_eligible_and_rejects_out_of_scope() -> None:
    fixtures = (
        make_fixture("England", "Premier League"),
        make_fixture("England", "League Two"),
        make_fixture("Spain", "Copa del Rey", "cup"),
    )
    result = ScopedFixtureDiscovery(StubDiscovery(fixtures)).discover(
        datetime(2026, 1, 1, tzinfo=UTC),
        datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert result == (fixtures[0],)


def test_scoped_discovery_rejects_invalid_window() -> None:
    discovery = ScopedFixtureDiscovery(StubDiscovery(()))
    start = datetime(2026, 1, 2, tzinfo=UTC)
    with __import__("pytest").raises(ValueError):
        discovery.discover(start, start - timedelta(minutes=1))
