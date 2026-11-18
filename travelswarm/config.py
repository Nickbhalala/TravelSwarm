from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./travelswarm.db"
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/%2F"
    trip_queue: str = "trips.plan"
    dead_letter_queue: str = "trips.plan.dead"

    planner: Literal["crewai", "fake"] = "fake"
    google_cloud_project: str | None = None
    google_cloud_location: str = "us-central1"
    gemini_model: str = "gemini-2.5-flash"

    max_attempts: int = 3


@lru_cache
def get_settings() -> Settings:
    return Settings()
