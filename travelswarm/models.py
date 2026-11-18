"""API and domain schemas shared by the gateway and the worker."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator


class Budget(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TripRequest(BaseModel):
    destination: str = Field(min_length=2, max_length=100)
    start_date: date
    days: int = Field(ge=1, le=14)
    travelers: int = Field(default=1, ge=1, le=12)
    budget: Budget = Budget.MEDIUM
    interests: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("interests")
    @classmethod
    def _clean_interests(cls, v: list[str]) -> list[str]:
        cleaned = [i.strip()[:40] for i in v if i.strip()]
        return list(dict.fromkeys(cleaned))  # dedupe, keep order

    @property
    def end_date(self) -> date:
        return self.start_date + timedelta(days=self.days - 1)


class Activity(BaseModel):
    time: str = Field(description="Local time, e.g. 09:00")
    title: str
    description: str = ""
    estimated_cost_usd: float = Field(default=0, ge=0)


class DayPlan(BaseModel):
    day: int = Field(ge=1)
    date: date
    theme: str
    activities: list[Activity] = Field(min_length=1)


class Itinerary(BaseModel):
    destination: str
    summary: str
    days: list[DayPlan]
    estimated_total_cost_usd: float = Field(ge=0)
    tips: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _days_are_sequential(self) -> Itinerary:
        if [d.day for d in self.days] != list(range(1, len(self.days) + 1)):
            raise ValueError("days must be numbered 1..N in order")
        return self


class TripStatus(StrEnum):
    QUEUED = "queued"
    PLANNING = "planning"
    DONE = "done"
    FAILED = "failed"


class TripView(BaseModel):
    id: str
    status: TripStatus
    request: TripRequest
    itinerary: Itinerary | None = None
    attempts: int = 0
    error: str | None = None
    created_at: datetime
    updated_at: datetime
