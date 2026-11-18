import pytest
from fastapi.testclient import TestClient

from travelswarm.gateway import create_app
from travelswarm.planner import FakePlanner
from travelswarm.worker import TripWorker

PAYLOAD = {
    "destination": "Kyoto",
    "start_date": "2027-04-01",
    "days": 2,
    "travelers": 2,
    "budget": "high",
    "interests": ["temples", "food"],
}


@pytest.fixture
def client(repo, broker, settings):
    with TestClient(create_app(repo, broker, settings)) as c:
        yield c


def test_create_queues_trip(client, broker, settings):
    r = client.post("/trips", json=PAYLOAD)
    assert r.status_code == 202
    trip = r.json()
    assert trip["status"] == "queued"
    assert r.headers["Location"] == f"/trips/{trip['id']}"
    assert list(broker.queues[settings.trip_queue]) == [{"trip_id": trip["id"], "attempt": 1}]


def test_validation_errors(client):
    assert client.post("/trips", json={**PAYLOAD, "days": 0}).status_code == 422
    assert client.post("/trips", json={**PAYLOAD, "budget": "luxury"}).status_code == 422


def test_get_and_404(client):
    trip_id = client.post("/trips", json=PAYLOAD).json()["id"]
    assert client.get(f"/trips/{trip_id}").json()["request"]["destination"] == "Kyoto"
    assert client.get("/trips/does-not-exist").status_code == 404
    assert len(client.get("/trips").json()) == 1


def test_end_to_end_with_worker(client, repo, broker, settings):
    trip_id = client.post("/trips", json=PAYLOAD).json()["id"]
    worker = TripWorker(repo, FakePlanner(), broker, settings)
    assert broker.drain(settings.trip_queue, worker.handle) == 1

    body = client.get(f"/trips/{trip_id}").json()
    assert body["status"] == "done"
    assert [d["date"] for d in body["itinerary"]["days"]] == ["2027-04-01", "2027-04-02"]


def test_broker_down_returns_503(repo, settings):
    class DownBroker:
        def publish(self, queue, message):
            raise ConnectionError("connection refused")

    with TestClient(create_app(repo, DownBroker(), settings)) as c:
        r = c.post("/trips", json=PAYLOAD)
    assert r.status_code == 503
    [trip] = repo.list_recent()
    assert trip.status == "failed"
