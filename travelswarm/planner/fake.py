from __future__ import annotations

from datetime import timedelta

from ..models import Activity, DayPlan, Itinerary, TripRequest

_COST = {"low": 30.0, "medium": 80.0, "high": 200.0}


class FakePlanner:
    """Deterministic planner for tests and running the stack without cloud credentials."""

    def plan(self, request: TripRequest) -> Itinerary:
        per_activity = _COST[request.budget.value] * request.travelers
        interests = request.interests or ["sightseeing"]
        days = []
        for i in range(request.days):
            focus = interests[i % len(interests)]
            days.append(
                DayPlan(
                    day=i + 1,
                    date=request.start_date + timedelta(days=i),
                    theme=f"{focus.title()} in {request.destination}",
                    activities=[
                        Activity(
                            time="09:00", title=f"Morning {focus}", estimated_cost_usd=per_activity
                        ),
                        Activity(
                            time="13:00", title="Local lunch", estimated_cost_usd=per_activity / 2
                        ),
                        Activity(
                            time="16:00",
                            title=f"Afternoon {focus}",
                            estimated_cost_usd=per_activity,
                        ),
                    ],
                )
            )
        total = sum(a.estimated_cost_usd for d in days for a in d.activities)
        return Itinerary(
            destination=request.destination,
            summary=f"{request.days}-day {request.budget.value}-budget trip to "
            f"{request.destination} (sample plan from FakePlanner).",
            days=days,
            estimated_total_cost_usd=total,
            tips=["This itinerary was generated offline and is for demonstration only."],
        )
