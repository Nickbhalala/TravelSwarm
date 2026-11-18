"""CrewAI planner: three agents in sequence, running on Gemini via Vertex AI.

researcher  -> destination notes tailored to the travelers' interests and budget
scheduler   -> day-by-day plan with times and cost estimates
reviewer    -> checks pacing, geography and budget, returns the final Itinerary JSON
"""

from __future__ import annotations

from ..models import Itinerary, TripRequest
from .base import PlannerError


def _describe(req: TripRequest) -> str:
    interests = ", ".join(req.interests) or "general sightseeing"
    return (
        f"Destination: {req.destination}\n"
        f"Dates: {req.start_date} to {req.end_date} ({req.days} days)\n"
        f"Travelers: {req.travelers}\n"
        f"Budget level: {req.budget.value}\n"
        f"Interests: {interests}"
    )


class CrewAIPlanner:
    def __init__(
        self, model: str, project: str | None, location: str, temperature: float = 0.4
    ) -> None:
        from crewai import LLM

        if not project:
            raise PlannerError("GOOGLE_CLOUD_PROJECT must be set to use the CrewAI planner")
        self.llm = LLM(
            model=f"gemini/{model}",
            project=project,
            location=location,
            use_vertexai=True,
            temperature=temperature,
        )

    def build_crew(self, req: TripRequest):
        from crewai import Agent, Crew, Process, Task

        researcher = Agent(
            role="Destination researcher",
            goal="Find the experiences in the destination that best fit the travelers",
            backstory="A travel writer who knows neighborhoods, seasons and local customs.",
            llm=self.llm,
            allow_delegation=False,
        )
        scheduler = Agent(
            role="Itinerary scheduler",
            goal="Turn research into a realistic day-by-day schedule",
            backstory="A tour operator who groups activities by area to minimize travel time.",
            llm=self.llm,
            allow_delegation=False,
        )
        reviewer = Agent(
            role="Budget and feasibility reviewer",
            goal="Make sure the plan fits the budget, pacing and dates exactly",
            backstory="A meticulous planner who checks every cost and opening time.",
            llm=self.llm,
            allow_delegation=False,
        )

        trip = _describe(req)
        research = Task(
            description=f"{trip}\n\nList 10-15 specific places, activities and food "
            "experiences that match the interests and budget, with the area of "
            "the city each is in and a rough per-person cost in USD.",
            expected_output="A bullet list of candidates with area and cost.",
            agent=researcher,
        )
        schedule = Task(
            description=f"{trip}\n\nUsing the research, build a plan with exactly "
            f"{req.days} days starting {req.start_date}. Give each day a theme "
            "and 3-5 timed activities near each other. Costs are for the whole "
            "group.",
            expected_output="A day-by-day schedule with times and group cost estimates.",
            agent=scheduler,
            context=[research],
        )
        review = Task(
            description=f"{trip}\n\nReview the schedule. Fix anything that overruns the "
            "budget, packs too much into a day, or has wrong dates. Days must be "
            f"numbered 1..{req.days} with consecutive dates from {req.start_date}. "
            "estimated_total_cost_usd must be at least the sum of activity costs.",
            expected_output="The final itinerary.",
            agent=reviewer,
            context=[research, schedule],
            output_pydantic=Itinerary,
        )
        return Crew(
            agents=[researcher, scheduler, reviewer],
            tasks=[research, schedule, review],
            process=Process.sequential,
        )

    def plan(self, request: TripRequest) -> Itinerary:
        try:
            result = self.build_crew(request).kickoff()
        except Exception as e:  # model/network errors are retryable
            raise PlannerError(f"crew run failed: {e}") from e
        itinerary = getattr(result, "pydantic", None)
        if not isinstance(itinerary, Itinerary):
            raise PlannerError("crew did not return a valid itinerary")
        return itinerary
