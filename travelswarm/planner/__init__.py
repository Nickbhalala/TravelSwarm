from .base import Planner, PlannerError, check_itinerary
from .fake import FakePlanner

__all__ = ["Planner", "PlannerError", "FakePlanner", "check_itinerary", "build_planner"]


def build_planner(settings) -> Planner:
    if settings.planner == "crewai":
        from .crew import CrewAIPlanner  # heavy import; only when configured

        return CrewAIPlanner(
            model=settings.gemini_model,
            project=settings.google_cloud_project,
            location=settings.google_cloud_location,
        )
    return FakePlanner()
