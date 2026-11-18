from __future__ import annotations

from datetime import timedelta
from typing import Protocol

from ..models import Itinerary, TripRequest


class PlannerError(RuntimeError):
    """The planner produced no usable itinerary (bad output, model error, timeout)."""


class Planner(Protocol):
    def plan(self, request: TripRequest) -> Itinerary: ...


def check_itinerary(request: TripRequest, itinerary: Itinerary) -> Itinerary:
    """Reject LLM output that doesn't match what was asked, so it can be retried."""
    if len(itinerary.days) != request.days:
        raise PlannerError(f"expected {request.days} days, got {len(itinerary.days)}")
    for i, day in enumerate(itinerary.days):
        expected = request.start_date + timedelta(days=i)
        if day.date != expected:
            raise PlannerError(f"day {day.day} has date {day.date}, expected {expected}")
    activity_total = sum(a.estimated_cost_usd for d in itinerary.days for a in d.activities)
    if itinerary.estimated_total_cost_usd + 0.01 < activity_total:
        raise PlannerError(
            f"total cost {itinerary.estimated_total_cost_usd} is less than the sum of "
            f"activity costs {activity_total:.2f}"
        )
    return itinerary
