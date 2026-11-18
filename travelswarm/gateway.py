"""API gateway: accepts trip requests, queues them, and serves status/results.

Run with: uvicorn travelswarm.gateway:app
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Response, status

from .config import Settings, get_settings
from .db import TripRepository
from .messaging import Broker
from .models import TripRequest, TripView


def create_app(
    repo: TripRepository | None = None,
    broker: Broker | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    state: dict = {"repo": repo, "broker": broker}

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if state["repo"] is None:
            state["repo"] = TripRepository.from_url(settings.database_url)
        if state["broker"] is None:
            from .messaging import RabbitMQBroker

            state["broker"] = RabbitMQBroker(
                settings.rabbitmq_url, [settings.trip_queue, settings.dead_letter_queue]
            )
        yield

    app = FastAPI(title="TravelSwarm", version="0.1.0", lifespan=lifespan)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/trips", status_code=status.HTTP_202_ACCEPTED, response_model=TripView)
    def create_trip(req: TripRequest, response: Response) -> TripView:
        trip = state["repo"].create(req)
        try:
            state["broker"].publish(settings.trip_queue, {"trip_id": trip.id, "attempt": 1})
        except Exception as e:
            state["repo"].fail(trip.id, f"could not queue request: {e}")
            raise HTTPException(503, "planning queue unavailable, try again later") from e
        response.headers["Location"] = f"/trips/{trip.id}"
        return trip

    @app.get("/trips/{trip_id}", response_model=TripView)
    def get_trip(trip_id: str) -> TripView:
        trip = state["repo"].get(trip_id)
        if trip is None:
            raise HTTPException(404, "trip not found")
        return trip

    @app.get("/trips", response_model=list[TripView])
    def recent_trips(limit: int = 20) -> list[TripView]:
        return state["repo"].list_recent(min(max(limit, 1), 100))

    return app


app = create_app()
