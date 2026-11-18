"""Planning worker: consumes trip requests, runs the planner, stores the result."""

from __future__ import annotations

import logging
import time

from .config import Settings, get_settings
from .db import TripRepository
from .messaging import Broker, Message
from .planner import Planner, PlannerError, build_planner, check_itinerary

log = logging.getLogger("travelswarm.worker")


class TripWorker:
    def __init__(
        self, repo: TripRepository, planner: Planner, broker: Broker, settings: Settings
    ) -> None:
        self.repo = repo
        self.planner = planner
        self.broker = broker
        self.settings = settings

    def handle(self, message: Message) -> None:
        trip_id = str(message.get("trip_id", ""))
        attempt = int(message.get("attempt", 1))
        trip = self.repo.get(trip_id)
        if trip is None:
            log.warning("dropping message for unknown trip %s", trip_id)
            return
        if not self.repo.claim(trip_id, attempt):
            log.info("trip %s is %s; skipping duplicate delivery", trip_id, trip.status)
            return

        started = time.perf_counter()
        try:
            itinerary = check_itinerary(trip.request, self.planner.plan(trip.request))
        except (PlannerError, ValueError) as e:
            self._retry_or_fail(trip_id, attempt, str(e))
            return

        self.repo.complete(trip_id, itinerary)
        log.info(
            "trip %s planned in %.1fs (attempt %d)", trip_id, time.perf_counter() - started, attempt
        )

    def _retry_or_fail(self, trip_id: str, attempt: int, error: str) -> None:
        if attempt < self.settings.max_attempts:
            log.warning("trip %s attempt %d failed: %s; retrying", trip_id, attempt, error)
            self.repo.requeue(trip_id, error)
            self.broker.publish(
                self.settings.trip_queue, {"trip_id": trip_id, "attempt": attempt + 1}
            )
        else:
            log.error("trip %s failed after %d attempts: %s", trip_id, attempt, error)
            self.repo.fail(trip_id, error)
            self.broker.publish(
                self.settings.dead_letter_queue,
                {"trip_id": trip_id, "attempt": attempt, "error": error},
            )


def main() -> None:
    from .messaging import RabbitMQBroker

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()
    repo = TripRepository.from_url(settings.database_url)
    broker = RabbitMQBroker(
        settings.rabbitmq_url, [settings.trip_queue, settings.dead_letter_queue]
    )
    worker = TripWorker(repo, build_planner(settings), broker, settings)
    broker.consume(settings.trip_queue, worker.handle)


if __name__ == "__main__":
    main()
