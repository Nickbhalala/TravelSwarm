from datetime import date

import pytest

from travelswarm.config import Settings
from travelswarm.db import TripRepository
from travelswarm.messaging import InMemoryBroker
from travelswarm.models import TripRequest


@pytest.fixture
def settings() -> Settings:
    return Settings(database_url="sqlite://", planner="fake", max_attempts=3, _env_file=None)


@pytest.fixture
def repo(tmp_path) -> TripRepository:
    return TripRepository.from_url(f"sqlite:///{tmp_path / 'test.db'}")


@pytest.fixture
def broker() -> InMemoryBroker:
    return InMemoryBroker()


@pytest.fixture
def trip_request() -> TripRequest:
    return TripRequest(
        destination="Lisbon",
        start_date=date(2027, 6, 1),
        days=3,
        travelers=2,
        budget="medium",
        interests=["food", "history", "food"],
    )
