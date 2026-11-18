# TravelSwarm

A multi-agent travel itinerary planner built as two services around a message queue.
The **gateway** accepts a trip request and returns immediately; **workers** pick it up
from RabbitMQ, run a CrewAI crew of three agents on Google Gemini (Vertex AI), check
the result, and store it in PostgreSQL. Clients poll for the finished itinerary.

## Why a queue?

An LLM crew takes tens of seconds and sometimes fails (rate limits, malformed output).
Doing that inside an HTTP request ties up the API and loses work on failure. With a
queue:

- The API answers in milliseconds with `202 Accepted` and a `Location` to poll.
- Workers scale independently (`docker compose up --scale worker=4`).
- Messages are acked only after the result is saved, so a crashed worker's job is
  redelivered. An atomic database "claim" makes redelivery safe: one trip is never
  planned twice in parallel.
- Failures are retried with the attempt number carried in the message; after
  `MAX_ATTEMPTS` the trip is marked failed and sent to a dead-letter queue.
- LLM output is validated (exact day count, consecutive dates, totals at least the sum
  of activity costs) and a bad plan counts as a failed attempt.

## Architecture

```mermaid
flowchart LR
    C[Client] -- "POST /trips" --> G[Gateway<br/>FastAPI]
    G -- "insert (queued)" --> DB[(PostgreSQL)]
    G -- "publish trip_id" --> Q[[RabbitMQ<br/>trips.plan]]
    Q --> W1[Worker]
    Q --> W2[Worker]
    subgraph Crew[CrewAI crew on Gemini / Vertex AI]
      R[Researcher] --> S[Scheduler] --> V[Reviewer]
    end
    W1 --> Crew
    W1 -- "claim / save itinerary" --> DB
    W1 -- "retry" --> Q
    W1 -- "give up" --> DLQ[[trips.plan.dead]]
    C -- "GET /trips/{id}" --> G
```

The three agents run sequentially: the **researcher** lists candidate places and
food for the travelers' interests and budget, the **scheduler** groups them into timed
days by area, and the **reviewer** fixes budget, pacing and date problems and returns
the final itinerary as a typed Pydantic model.

## Tech stack

Python 3.11-3.13, FastAPI, CrewAI, Google Gemini on Vertex AI, RabbitMQ (pika),
PostgreSQL, SQLAlchemy 2, Pydantic 2, Docker Compose, pytest, Ruff, GitHub Actions.

## Run it locally

### With Docker Compose

```bash
cp .env.example .env
docker compose up --build
```

`.env.example` uses `PLANNER=fake`, a deterministic planner that needs no cloud account,
so the whole pipeline runs offline. Then:

```bash
curl -i -X POST localhost:8000/trips -H 'Content-Type: application/json' -d '{
  "destination": "Lisbon", "start_date": "2027-06-01", "days": 3,
  "travelers": 2, "budget": "medium", "interests": ["food", "history"]}'
curl localhost:8000/trips/<id>       # status: queued -> planning -> done
```

API docs: http://localhost:8000/docs. RabbitMQ UI: http://localhost:15672 (guest/guest).

### Using Gemini (Vertex AI)

1. Enable the Vertex AI API in a Google Cloud project and run
   `gcloud auth application-default login`.
2. In `.env`: `PLANNER=crewai`, `GOOGLE_CLOUD_PROJECT=<your project>`.
3. Uncomment the credentials volume on the `worker` service in `docker-compose.yml`, then
   `INSTALL_CREW=true docker compose up --build`.

Calls to Vertex AI are billed to your project.

### Without Docker

Needs PostgreSQL and RabbitMQ running locally.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,crew]"
export DATABASE_URL=postgresql+psycopg://travelswarm:travelswarm@localhost:5432/travelswarm
uvicorn travelswarm.gateway:app --port 8000      # terminal 1
travelswarm-worker                               # terminal 2 (and 3, 4...)
```

### Tests

```bash
pytest                      # unit tests: SQLite + in-memory broker, no network
pytest -m integration       # real PostgreSQL + RabbitMQ (DATABASE_URL, RABBITMQ_URL)
```

The CrewAI tests check how the crew is wired and how results and errors are handled;
they replace `kickoff()` with a stub, so they don't call Gemini.

## Configuration

See [.env.example](.env.example).

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | SQLite file | SQLAlchemy URL; PostgreSQL in Compose |
| `RABBITMQ_URL` | `amqp://guest:guest@localhost:5672/%2F` | Broker |
| `PLANNER` | `fake` | `crewai` for real planning |
| `GOOGLE_CLOUD_PROJECT` / `GOOGLE_CLOUD_LOCATION` | none / `us-central1` | Vertex AI project |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Model used by all three agents |
| `MAX_ATTEMPTS` | `3` | Attempts before a trip is dead-lettered |

## Project structure

```text
travelswarm/
  gateway.py          FastAPI service: create / get / list trips
  worker.py           queue consumer: claim, plan, validate, retry or dead-letter
  messaging.py        RabbitMQ broker (durable, persistent, manual ack) + in-memory broker
  db.py               SQLAlchemy model and repository with atomic claim
  models.py           request, itinerary and status schemas
  planner/
    crew.py           CrewAI researcher / scheduler / reviewer on Gemini
    fake.py           deterministic planner
    base.py           planner protocol and itinerary checks
tests/                unit, gateway, worker, CrewAI wiring, integration
```

## What I'd improve next

- Alembic migrations instead of `create_all`.
- Exponential backoff between retries (a delayed-message exchange) rather than
  immediate requeue.
- Server-sent events or webhooks instead of polling.
- Tools for the researcher agent (maps / opening hours APIs) so the plan is grounded in
  live data, plus an evaluation set to compare prompts and models.
- OpenTelemetry tracing across gateway -> queue -> worker -> LLM.

## About this project

Built by Nikhil Bhalala with AI assistance (Claude by Anthropic) for code generation and
review.

## License

[MIT](LICENSE)
