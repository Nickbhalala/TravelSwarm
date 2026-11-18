"""Runs against real PostgreSQL and RabbitMQ: pytest -m integration

Requires DATABASE_URL (postgresql+psycopg://...) and RABBITMQ_URL.
"""

import json
import os
import threading
import time
import uuid

import pytest

from travelswarm.config import Settings
from travelswarm.db import TripRepository
from travelswarm.messaging import RabbitMQBroker
from travelswarm.models import TripStatus
from travelswarm.planner import FakePlanner
from travelswarm.worker import TripWorker

pytestmark = pytest.mark.integration


@pytest.fixture
def real_settings():
    if "postgresql" not in os.environ.get("DATABASE_URL", ""):
        pytest.skip("DATABASE_URL must point at PostgreSQL")
    suffix = uuid.uuid4().hex[:8]
    return Settings(trip_queue=f"test.plan.{suffix}", dead_letter_queue=f"test.dead.{suffix}")


def test_queue_to_worker_to_postgres(real_settings, trip_request):
    s = real_settings
    repo = TripRepository.from_url(s.database_url)
    publisher = RabbitMQBroker(s.rabbitmq_url, [s.trip_queue, s.dead_letter_queue])
    consumer = RabbitMQBroker(s.rabbitmq_url, [s.trip_queue, s.dead_letter_queue])
    worker = TripWorker(repo, FakePlanner(), publisher, s)

    trip = repo.create(trip_request)
    publisher.publish(s.trip_queue, {"trip_id": trip.id, "attempt": 1})

    t = threading.Thread(target=consumer.consume, args=(s.trip_queue, worker.handle), daemon=True)
    t.start()
    deadline = time.time() + 15
    while time.time() < deadline and repo.get(trip.id).status != TripStatus.DONE:
        time.sleep(0.2)

    stored = repo.get(trip.id)
    assert stored.status == TripStatus.DONE
    assert len(stored.itinerary.days) == trip_request.days

    # Message was acked: nothing left on the queue.
    import pika

    conn = pika.BlockingConnection(pika.URLParameters(s.rabbitmq_url))
    ch = conn.channel()
    method, _, body = ch.basic_get(s.trip_queue)
    assert method is None, json.loads(body) if body else None
    ch.queue_delete(s.trip_queue)
    ch.queue_delete(s.dead_letter_queue)
    conn.close()
    publisher.close()
