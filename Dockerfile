FROM python:3.12-slim

# Set INSTALL_CREW=true to include CrewAI + Gemini (needed for PLANNER=crewai).
ARG INSTALL_CREW=false

WORKDIR /app
RUN useradd --system --uid 1001 app
COPY pyproject.toml README.md ./
COPY travelswarm ./travelswarm
RUN if [ "$INSTALL_CREW" = "true" ]; then pip install --no-cache-dir ".[crew]"; \
    else pip install --no-cache-dir .; fi
USER app

# Default command runs the gateway; the worker service overrides it.
EXPOSE 8000
CMD ["uvicorn", "travelswarm.gateway:app", "--host", "0.0.0.0", "--port", "8000"]
