from datetime import date

import pytest
from pydantic import ValidationError

from travelswarm.models import Itinerary, TripRequest
from travelswarm.planner import FakePlanner, PlannerError, check_itinerary


def test_request_validation_and_cleanup(trip_request):
    assert trip_request.interests == ["food", "history"]
    assert trip_request.end_date == date(2027, 6, 3)
    with pytest.raises(ValidationError):
        TripRequest(destination="X", start_date=date(2027, 1, 1), days=3)  # too short
    with pytest.raises(ValidationError):
        TripRequest(destination="Rome", start_date=date(2027, 1, 1), days=15)


def test_fake_plan_passes_checks(trip_request):
    it = check_itinerary(trip_request, FakePlanner().plan(trip_request))
    assert [d.date for d in it.days] == [date(2027, 6, d) for d in (1, 2, 3)]
    assert it.days[0].theme == "Food in Lisbon"


def _mutate(it: Itinerary, **changes) -> Itinerary:
    data = it.model_dump()
    data.update(changes)
    return Itinerary.model_validate(data)


def test_check_rejects_wrong_day_count(trip_request):
    it = FakePlanner().plan(trip_request)
    with pytest.raises(PlannerError, match="expected 3 days, got 2"):
        check_itinerary(trip_request, _mutate(it, days=it.model_dump()["days"][:2]))


def test_check_rejects_wrong_dates(trip_request):
    it = FakePlanner().plan(trip_request)
    days = it.model_dump()["days"]
    days[1]["date"] = date(2027, 6, 5)
    with pytest.raises(PlannerError, match="day 2 has date 2027-06-05"):
        check_itinerary(trip_request, _mutate(it, days=days))


def test_check_rejects_undercounted_total(trip_request):
    it = FakePlanner().plan(trip_request)
    with pytest.raises(PlannerError, match="less than the sum"):
        check_itinerary(trip_request, _mutate(it, estimated_total_cost_usd=1.0))


def test_itinerary_days_must_be_sequential(trip_request):
    data = FakePlanner().plan(trip_request).model_dump()
    data["days"][0]["day"] = 2
    with pytest.raises(ValidationError, match="numbered 1..N"):
        Itinerary.model_validate(data)
