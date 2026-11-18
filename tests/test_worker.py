from travelswarm.models import TripStatus
from travelswarm.planner import FakePlanner, PlannerError
from travelswarm.worker import TripWorker


class FlakyPlanner:
    """Fails the first `failures` calls, then delegates to FakePlanner."""

    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls = 0

    def plan(self, request):
        self.calls += 1
        if self.calls <= self.failures:
            raise PlannerError(f"model timeout #{self.calls}")
        return FakePlanner().plan(request)


def make(repo, broker, settings, planner):
    return TripWorker(repo, planner, broker, settings)


def test_success(repo, broker, settings, trip_request):
    trip = repo.create(trip_request)
    make(repo, broker, settings, FakePlanner()).handle({"trip_id": trip.id, "attempt": 1})
    stored = repo.get(trip.id)
    assert stored.status == TripStatus.DONE
    assert len(stored.itinerary.days) == 3
    assert stored.attempts == 1


def test_duplicate_delivery_is_ignored(repo, broker, settings, trip_request):
    trip = repo.create(trip_request)
    planner = FlakyPlanner(failures=0)
    worker = make(repo, broker, settings, planner)
    worker.handle({"trip_id": trip.id, "attempt": 1})
    worker.handle({"trip_id": trip.id, "attempt": 1})  # redelivered
    assert planner.calls == 1


def test_retries_then_succeeds(repo, broker, settings, trip_request):
    trip = repo.create(trip_request)
    planner = FlakyPlanner(failures=2)
    worker = make(repo, broker, settings, planner)
    worker.handle({"trip_id": trip.id, "attempt": 1})
    assert repo.get(trip.id).status == TripStatus.QUEUED
    assert "model timeout #1" in repo.get(trip.id).error

    broker.drain(settings.trip_queue, worker.handle)
    stored = repo.get(trip.id)
    assert stored.status == TripStatus.DONE
    assert stored.attempts == 3
    assert stored.error is None


def test_dead_letters_after_max_attempts(repo, broker, settings, trip_request):
    trip = repo.create(trip_request)
    worker = make(repo, broker, settings, FlakyPlanner(failures=99))
    worker.handle({"trip_id": trip.id, "attempt": 1})
    broker.drain(settings.trip_queue, worker.handle)

    stored = repo.get(trip.id)
    assert stored.status == TripStatus.FAILED
    assert stored.attempts == 3
    dead = list(broker.queues[settings.dead_letter_queue])
    assert dead == [{"trip_id": trip.id, "attempt": 3, "error": "model timeout #3"}]


def test_invalid_llm_output_is_retried(repo, broker, settings, trip_request):
    class WrongDays:
        def plan(self, request):
            it = FakePlanner().plan(request)
            return it.model_copy(update={"days": it.days[:1]})

    trip = repo.create(trip_request)
    make(repo, broker, settings, WrongDays()).handle({"trip_id": trip.id, "attempt": 1})
    assert "expected 3 days" in repo.get(trip.id).error
    assert broker.queues[settings.trip_queue][0]["attempt"] == 2


def test_unknown_trip_is_dropped(repo, broker, settings):
    make(repo, broker, settings, FakePlanner()).handle({"trip_id": "nope"})
    assert not broker.queues
