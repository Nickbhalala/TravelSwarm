"""CrewAI wiring tests. No model is called: kickoff is replaced with a stub."""

from types import SimpleNamespace

import pytest

pytest.importorskip("crewai")

from travelswarm.planner import FakePlanner, PlannerError  # noqa: E402
from travelswarm.planner.crew import CrewAIPlanner  # noqa: E402


@pytest.fixture
def planner():
    return CrewAIPlanner(model="gemini-2.5-flash", project="test-project", location="us-central1")


def test_requires_project():
    with pytest.raises(PlannerError, match="GOOGLE_CLOUD_PROJECT"):
        CrewAIPlanner(model="gemini-2.5-flash", project=None, location="us-central1")


def test_crew_shape(planner, trip_request):
    crew = planner.build_crew(trip_request)
    assert [a.role for a in crew.agents] == [
        "Destination researcher",
        "Itinerary scheduler",
        "Budget and feasibility reviewer",
    ]
    final = crew.tasks[-1]
    assert final.output_pydantic.__name__ == "Itinerary"
    assert "exactly 3 days" in crew.tasks[1].description
    assert "Lisbon" in crew.tasks[0].description


def test_plan_returns_pydantic_output(planner, trip_request, monkeypatch):
    expected = FakePlanner().plan(trip_request)
    stub = SimpleNamespace(kickoff=lambda: SimpleNamespace(pydantic=expected))
    monkeypatch.setattr(planner, "build_crew", lambda req: stub)
    assert planner.plan(trip_request) == expected


def test_plan_wraps_failures(planner, trip_request, monkeypatch):
    def boom():
        raise RuntimeError("429 quota exceeded")

    monkeypatch.setattr(planner, "build_crew", lambda req: SimpleNamespace(kickoff=boom))
    with pytest.raises(PlannerError, match="429 quota exceeded"):
        planner.plan(trip_request)

    monkeypatch.setattr(
        planner,
        "build_crew",
        lambda req: SimpleNamespace(kickoff=lambda: SimpleNamespace(pydantic=None)),
    )
    with pytest.raises(PlannerError, match="did not return"):
        planner.plan(trip_request)
